"""Phase 2 Part A tests: channel-neutral core (`app.inbound`) + WhatsApp adapter round-trip,
plus the mechanical AC-4 scan asserting the core imports no WhatsApp types."""
import ast
import pytest
from unittest.mock import patch

from sqlalchemy import select

from app.inbound import InboundMessage, handle_inbound, OutboundReply
from app.channels import whatsapp as whatsapp_channel
from app.schemas import WAMessage, WAText, WAImage, TextReply, DocumentReply, Reply, RouterOutput
from app.db import RequestLog, Paper, Course


# ----------------------------------------------------------------- adapter: to_inbound
def test_to_inbound_text():
    wa = WAMessage(id="m1", from_="2348000000000", timestamp="123", type="text", text=WAText(body="MTH102"))
    inbound = whatsapp_channel.to_inbound(wa)
    assert isinstance(inbound, InboundMessage)
    assert inbound.channel == "whatsapp"
    assert inbound.kind == "text"
    assert inbound.sender == "2348000000000"
    assert inbound.message_id == "m1"
    assert inbound.text == "MTH102"
    assert inbound.media_id is None


def test_to_inbound_image():
    wa = WAMessage(id="m2", from_="2348000000001", timestamp="123", type="image",
                   image=WAImage(id="media99", mime_type="image/jpeg"))
    inbound = whatsapp_channel.to_inbound(wa)
    assert inbound.kind == "image"
    assert inbound.sender == "2348000000001"
    assert inbound.media_id == "media99"
    assert inbound.text is None


def test_to_inbound_unsupported_type_is_other():
    wa = WAMessage(id="m3", from_="2348000000002", timestamp="123", type="audio")
    inbound = whatsapp_channel.to_inbound(wa)
    assert inbound.kind == "other"


def test_from_reply_is_identity():
    r = TextReply(body="hi")
    assert whatsapp_channel.from_reply(r) is r


# ----------------------------------------------------------------- AC-4 static scan
def _imported_module_names(path: str) -> set[str]:
    with open(path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
    return names


def test_inbound_core_imports_no_whatsapp():
    import app.inbound as inbound_mod
    names = _imported_module_names(inbound_mod.__file__)
    assert not any("whatsapp" in n for n in names), names
    with open(inbound_mod.__file__, "r", encoding="utf-8") as fh:
        src = fh.read()
    assert "WAMessage" not in src
    assert "WAImage" not in src


def test_answer_query_module_imports_no_whatsapp():
    import app.retrieval as retrieval_mod
    assert hasattr(retrieval_mod, "answer_query")
    names = _imported_module_names(retrieval_mod.__file__)
    assert not any("whatsapp" in n for n in names), names
    with open(retrieval_mod.__file__, "r", encoding="utf-8") as fh:
        src = fh.read()
    assert "WAMessage" not in src
    assert "WAImage" not in src


# ----------------------------------------------------------------- handle_inbound parity
def _text_inbound(message_id: str, body: str) -> InboundMessage:
    return InboundMessage(channel="whatsapp", sender="2348000000000",
                          message_id=message_id, kind="text", text=body)


@patch("app.inbound.llm.route")
def test_handle_inbound_greeting(mock_route, db_session):
    mock_route.return_value = (RouterOutput(intent="greeting", confidence=0.9), 10, 10)
    reply = handle_inbound(db_session, _text_inbound("ib_greet", "Hello"), None, None)
    assert isinstance(reply, TextReply)
    assert "Wa alaykum salaam" in reply.body


@patch("app.inbound.llm.route")
def test_handle_inbound_unknown_course(mock_route, db_session):
    db_session.add_all([
        Course(code="MTH102", title="A", level=100, department="D"),
        Course(code="MTH101", title="A", level=100, department="D"),
    ])
    db_session.commit()
    mock_route.return_value = (RouterOutput(intent="paper_request", course_code="MTH999", year=2020, confidence=0.9), 10, 10)
    reply = handle_inbound(db_session, _text_inbound("ib_unknown", "MTH999 2020"), None, None)
    assert isinstance(reply, TextReply)
    assert "Did you mean:" in reply.body
    assert "MTH102" in reply.body


@patch("app.inbound.llm.route")
def test_handle_inbound_found_paper(mock_route, db_session):
    db_session.add(Course(code="MTH102", title="A", level=100, department="D"))
    p = Paper(course_code="MTH102", semester="harmattan", year=2020, gcs_object="obj1", sha256="h1", uploaded_by="t")
    db_session.add(p)
    db_session.commit()
    mock_route.return_value = (RouterOutput(intent="paper_request", course_code="MTH102", year=2020, semester="harmattan", confidence=0.9), 10, 10)
    reply = handle_inbound(db_session, _text_inbound("ib_found", "MTH102 harmattan 2020"), None, None)
    assert isinstance(reply, DocumentReply)
    assert reply.paper_id == p.id


@patch("app.inbound.llm.route")
def test_handle_inbound_returns_reply_and_logs(mock_route, db_session):
    mock_route.return_value = (RouterOutput(intent="greeting", confidence=0.9), 10, 10)
    reply = handle_inbound(db_session, _text_inbound("ib_reply", "Hi"), None, None)
    # Reply is the Annotated union; its members are what isinstance can check.
    assert isinstance(reply, (TextReply, DocumentReply))
    log_row = db_session.execute(
        select(RequestLog).where(RequestLog.wa_message_id == "ib_reply")
    ).scalar_one()
    assert log_row.wa_from == "2348000000000"


def test_outbound_reply_alias_is_reply():
    assert OutboundReply is Reply
