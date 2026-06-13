# -*- coding: utf-8 -*-
"""Build 2: WhatsApp contribution intake. Students photograph past papers; the bot validates each
image (Flash), collects multi-page sessions, confirms filing off the masthead, soft-dedups against
the live corpus, rate-caps the public, and writes to an `awaiting_review` queue. NOTHING becomes
student-visible here — the Build-3 web app approves/denies. Retrieval-only firewall holds (this is
intake, not tutoring). Gated by serve_contributions_enabled.

State lives in serve_session (kind="contribution"): {"kind","cid","state"} where state is
collecting | confirm | filing | fix_course | fix_year | fix_session. The contributions row holds the
data + lifecycle status (collecting -> awaiting_review | denied). Idle sessions are swept
opportunistically (per the Phase-5 precedent) — check-in then finalize.
"""
import io
import json
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.config import settings
from app.schemas import WAMessage, Reply, TextReply
from app import whatsapp, llm

log = logging.getLogger(__name__)

_DONE = {"done", "finished", "complete", "completed", "that's all", "thats all", "finish"}
_YES = {"yes", "y", "yeah", "yep", "correct", "right", "ok", "okay", "yes please", "yh"}
_MORE = {"send more", "more", "no", "not yet", "add more", "wait"}
_FIX = {"fix", "no", "wrong", "edit", "change"}
_CANCEL = {"cancel", "stop", "quit"}

_SESSIONS = ("CA1", "CA2", "exam")


# ---------------------------------------------------------------- serve_session state (peek, not pop)
def _get_state(session: Session, phone: str) -> dict | None:
    row = session.execute(text(
        "SELECT candidates FROM serve_session WHERE phone_number = :p"
    ), {"p": phone}).mappings().first()
    if not row:
        return None
    pl = row["candidates"] if isinstance(row["candidates"], (dict, list)) else json.loads(row["candidates"])
    return pl if isinstance(pl, dict) and pl.get("kind") == "contribution" else None


def _set_state(session: Session, phone: str, cid: int, state: str) -> None:
    session.execute(text(
        "INSERT INTO serve_session (phone_number, candidates, created_at) VALUES (:p, :c, now()) "
        "ON CONFLICT (phone_number) DO UPDATE SET candidates = EXCLUDED.candidates, created_at = now()"
    ), {"p": phone, "c": json.dumps({"kind": "contribution", "cid": cid, "state": state})})


def _clear_state(session: Session, phone: str) -> None:
    session.execute(text("DELETE FROM serve_session WHERE phone_number = :p"), {"p": phone})


# ---------------------------------------------------------------- contribution rows
def _school_of(session: Session, phone: str) -> str | None:
    r = session.execute(text("SELECT school FROM student_profile WHERE phone_number = :p"),
                        {"p": phone}).mappings().first()
    return r["school"] if r else None


def _open_contribution(session: Session, phone: str) -> int:
    cid = session.execute(text(
        "INSERT INTO contributions (contributor_phone, contributor_school, status) "
        "VALUES (:p, :s, 'collecting') RETURNING id"
    ), {"p": phone, "s": _school_of(session, phone)}).scalar()
    return cid


def _add_page(session: Session, cid: int, gcs_object: str, validation: dict) -> int:
    order = (session.execute(text(
        "SELECT COALESCE(max(page_order), 0) + 1 FROM contribution_pages WHERE contribution_id = :c"
    ), {"c": cid}).scalar())
    session.execute(text(
        "INSERT INTO contribution_pages (contribution_id, gcs_object, page_order, page_validation) "
        "VALUES (:c, :g, :o, :v)"
    ), {"c": cid, "g": gcs_object, "o": order, "v": json.dumps(validation)})
    session.execute(text("UPDATE contributions SET updated_at = now() WHERE id = :c"), {"c": cid})
    return order


def _page_count(session: Session, cid: int) -> int:
    return session.execute(text("SELECT count(*) FROM contribution_pages WHERE contribution_id = :c"),
                          {"c": cid}).scalar() or 0


def _first_page_object(session: Session, cid: int) -> str | None:
    return session.execute(text(
        "SELECT gcs_object FROM contribution_pages WHERE contribution_id = :c ORDER BY page_order LIMIT 1"
    ), {"c": cid}).scalar()


# ---------------------------------------------------------------- trusted registry + rate cap
def _is_trusted(session: Session, phone: str) -> bool:
    return session.execute(text(
        "SELECT 1 FROM trusted_uploaders WHERE phone = :p AND uncapped LIMIT 1"
    ), {"p": phone}).scalar() is not None


def _over_cap(session: Session, phone: str) -> bool:
    if _is_trusted(session, phone):
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    n = session.execute(text(
        "SELECT count(*) FROM contributions WHERE contributor_phone = :p "
        "AND status IN ('awaiting_review', 'approved') AND created_at >= :cut"
    ), {"p": phone, "cut": cutoff}).scalar() or 0
    return n >= settings.contribution_weekly_cap


# ---------------------------------------------------------------- media fetch + validate + store
def _download(http, msg: WAMessage):
    url, mime, size = whatsapp.get_media_metadata(http, msg.image.id)
    if size and size > settings.contribution_max_image_bytes:
        return None, mime, "too_large"
    return whatsapp.download_media(http, url), mime, None


def _store_image(gcs, cid: int, msg: WAMessage, raw: bytes, mime: str) -> str:
    ext = "jpg" if mime in ("image/jpeg", "image/jpg") else ("png" if mime == "image/png"
          else ("heic" if "heic" in (mime or "") else "bin"))
    key = f"{settings.contribution_gcs_prefix}{cid}/{msg.id}.{ext}"
    gcs.bucket(settings.gcs_bucket).blob(key).upload_from_string(raw, content_type=mime or "image/jpeg")
    return key


# ---------------------------------------------------------------- dedup
def _find_dup(session: Session, school: str | None, course: str | None, year: str | None) -> int | None:
    if not course:
        return None
    sql = ("SELECT id FROM pending_papers WHERE student_visible AND source = 'corpus_full' "
           "AND upper(course_code) = upper(:c)")
    params = {"c": course}
    if school:
        sql += " AND split_part(school, ' ', 1) = :s"; params["s"] = school
    if year:
        sql += " AND (year ILIKE '%' || :y || '%')"; params["y"] = str(year)
    sql += " LIMIT 1"
    return session.execute(text(sql), params).scalar()


# ---------------------------------------------------------------- main entry
def handle(session: Session, msg: WAMessage, http_client, gcs_client) -> Reply | None:
    """Returns a Reply if this message belongs to the contribution path, else None (-> retrieval)."""
    phone = msg.from_
    state = _get_state(session, phone)
    if msg.type == "image":
        return _on_image(session, msg, http_client, gcs_client, state)
    if state:
        return _on_text(session, msg, state, http_client, gcs_client)
    return None


def _on_image(session, msg, http, gcs, state) -> Reply:
    phone = msg.from_
    if msg.image is None:
        return TextReply(body="That image didn't come through — please resend the photo.")
    # download + validate BEFORE storing (rejects are never stored, never counted)
    try:
        raw, mime, err = _download(http, msg)
    except Exception as e:
        log.error("contrib_download_failed", extra={"err": str(e)})
        return TextReply(body="I couldn't fetch that image — please resend it.")
    if err == "too_large":
        return TextReply(body="That image is a bit large — send a slightly smaller photo, please.")
    try:
        v = llm.validate_contribution_image(raw, mime or "image/jpeg")
    except Exception as e:
        log.error("contrib_validate_failed", extra={"err": str(e)})
        return TextReply(body="I had trouble reading that one — please resend it.")
    if not v.is_paper_like:
        return TextReply(body="This doesn't look like a past paper — send a clear photo of the question paper.")
    if not v.clarity_ok:
        return TextReply(body="Could you resend in better lighting? That photo's hard to read.")

    # accepted -> open or append
    cid = state["cid"] if state else _open_contribution(session, phone)
    key = _store_image(gcs, cid, msg, raw, mime)
    n = _add_page(session, cid, key, v.model_dump())
    reopened = bool(state and state.get("state") not in ("collecting", None))
    _set_state(session, phone, cid, "collecting")
    session.commit()
    if not state:
        return TextReply(body="Got page 1 ✅ Thank you so much! Send all the pages of this paper — I'll wait. "
                              "Tap 'done' when you've sent them all (or I'll check in shortly).")
    if reopened:
        return TextReply(body=f"Added page {n}. Send more, or 'done' when finished.")
    return TextReply(body=f"Got page {n} ✅ — keep them coming, or 'done' when finished.")


def _on_text(session, msg, state, http, gcs) -> Reply:
    phone = msg.from_
    cid = state["cid"]
    st = state.get("state", "collecting")
    body = (msg.text.body if msg.text else "").strip()
    low = body.lower()

    if low in _CANCEL:
        session.execute(text("UPDATE contributions SET status='denied', review_comment='cancelled by contributor', updated_at=now() WHERE id=:c"), {"c": cid})
        _clear_state(session, phone); session.commit()
        return TextReply(body="No problem — cancelled. Send a photo anytime to contribute, or a course code to find a paper.")

    if st == "collecting":
        if low in _DONE:
            n = _page_count(session, cid)
            _set_state(session, phone, cid, "confirm"); session.commit()
            return TextReply(body=f"Got {n} page(s) — is that the whole paper? (yes / send more)")
        return TextReply(body="Send the pages of the paper, then tap 'done'. (Or 'cancel' to stop.)")

    if st == "confirm":
        if low in _YES or low in _DONE:
            return _to_filing(session, phone, cid, http, gcs)
        if low in _MORE:
            _set_state(session, phone, cid, "collecting"); session.commit()
            return TextReply(body="Sure — send the rest, then 'done'.")
        return TextReply(body="Is that the whole paper? Reply 'yes', or 'send more' to add pages.")

    if st == "filing":
        if low in _YES:
            return _commit(session, phone, cid)
        if low in _FIX:
            _set_state(session, phone, cid, "fix_course"); session.commit()
            return TextReply(body="No problem. What's the course code or title?")
        return TextReply(body="Is the filing right? Reply 'yes' to submit, or 'fix' to correct it.")

    if st == "fix_course":
        session.execute(text("UPDATE contributions SET course_code=:v, course_title=:v2, updated_at=now() WHERE id=:c"),
                        {"v": body.upper().replace(" ", "")[:32] or None, "v2": body[:200], "c": cid})
        _set_state(session, phone, cid, "fix_year"); session.commit()
        return TextReply(body="Got it. Which year? (e.g. 2024)")

    if st == "fix_year":
        yr = "".join(ch for ch in body if ch.isdigit())[:4] or None
        session.execute(text("UPDATE contributions SET year=:y, updated_at=now() WHERE id=:c"), {"y": yr, "c": cid})
        _set_state(session, phone, cid, "fix_session"); session.commit()
        return TextReply(body="And which one — Exam, CA1, or CA2?")

    if st == "fix_session":
        sess = next((s for s in _SESSIONS if s.lower() in low), "exam")
        session.execute(text("UPDATE contributions SET exam_session=:s, doc_type=:d, updated_at=now() WHERE id=:c"),
                        {"s": sess, "d": ("CA" if sess.startswith("CA") else "exam"), "c": cid})
        _set_state(session, phone, cid, "filing"); session.commit()
        return _filing_confirm_text(session, cid)

    return None


def _filing_confirm_text(session, cid) -> Reply:
    r = session.execute(text("SELECT course_code, course_title, year, exam_session FROM contributions WHERE id=:c"),
                        {"c": cid}).mappings().first()
    code = r["course_code"] or r["course_title"] or "this course"
    bits = [code]
    if r["year"]: bits.append(str(r["year"]))
    if r["exam_session"]: bits.append(r["exam_session"])
    return TextReply(body=f"This looks like: {', '.join(bits)}. Is that right? (yes / fix)")


def _to_filing(session, phone, cid, http, gcs) -> Reply:
    # rate cap at finalize (counts attempts, not files) — before the masthead Vertex cost
    if _over_cap(session, phone):
        session.execute(text("UPDATE contributions SET status='denied', review_comment='auto: weekly cap', updated_at=now() WHERE id=:c"), {"c": cid})
        _clear_state(session, phone); session.commit()
        return TextReply(body="You've hit this week's upload limit (20). Thanks so much for contributing! It resets in a few days.")
    # masthead read off page 1 (best-effort) — ALWAYS confirmed next
    guess = None
    try:
        obj = _first_page_object(session, cid)
        raw = gcs.bucket(settings.gcs_bucket).blob(obj).download_as_bytes()
        guess = llm.read_masthead(raw, school_hint=_school_of(session, phone))
    except Exception as e:
        log.warning("masthead_read_failed", extra={"cid": cid, "err": str(e)})
    if guess:
        session.execute(text(
            "UPDATE contributions SET course_code=:c, course_title=:t, year=:y, exam_session=:s, "
            "doc_type=:d, updated_at=now() WHERE id=:id"
        ), {"c": guess.course_code, "t": guess.course_title, "y": (str(guess.year) if guess.year else None),
            "s": guess.exam_session, "d": guess.doc_type, "id": cid})
    if guess and (guess.course_code or guess.course_title):
        _set_state(session, phone, cid, "filing"); session.commit()
        return _filing_confirm_text(session, cid)
    # masthead unreadable -> ask the contributor to file it
    _set_state(session, phone, cid, "fix_course"); session.commit()
    return TextReply(body="I couldn't read the course off the page. What's the course code or title?")


def _aggregate_validation(session, cid) -> str:
    rows = session.execute(text(
        "SELECT page_order, page_validation FROM contribution_pages WHERE contribution_id=:c ORDER BY page_order"
    ), {"c": cid}).mappings().all()
    def pv(x):
        v = x["page_validation"]
        return v if isinstance(v, dict) else (json.loads(v) if v else {})
    return json.dumps({"pages": [{"page": x["page_order"], **pv(x)} for x in rows]})


def _commit(session, phone, cid) -> Reply:
    r = session.execute(text("SELECT contributor_school, course_code, year FROM contributions WHERE id=:c"),
                        {"c": cid}).mappings().first()
    dup = _find_dup(session, r["contributor_school"], r["course_code"], r["year"])
    session.execute(text(
        "UPDATE contributions SET status='awaiting_review', bot_validation=CAST(:bv AS jsonb), "
        "likely_dup_of=:d, updated_at=now() WHERE id=:c"
    ), {"bv": _aggregate_validation(session, cid), "d": dup, "c": cid})
    _clear_state(session, phone); session.commit()
    if dup:
        return TextReply(body="We already have a copy of this one — but no worries, yours will still go to review "
                              "(a clearer scan always helps). Thank you so much! It's pending review.")
    return TextReply(body="Thank you so much! Your contribution's been received and is pending review. "
                          "You'll hear back once it's checked.")


# ---------------------------------------------------------------- opportunistic idle sweep
def sweep(session: Session, http_client, gcs_client) -> int:
    """Find idle 'collecting' contributions: nudge once (check-in), then finalize on continued silence.
    Runs opportunistically on each webhook; sends directly via http (contributor's 24h window is open)."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.contribution_idle_seconds)
    rows = session.execute(text(
        "SELECT id, contributor_phone FROM contributions WHERE status='collecting' AND updated_at < :cut "
        "ORDER BY id LIMIT 10"
    ), {"cut": cutoff}).mappings().all()
    acted = 0
    for r in rows:
        cid, phone = r["id"], r["contributor_phone"]
        st = _get_state(session, phone)
        sub = st.get("state") if st else None
        try:
            if _page_count(session, cid) == 0:
                session.execute(text("UPDATE contributions SET status='denied', review_comment='auto: empty/idle', updated_at=now() WHERE id=:c"), {"c": cid})
                if st and st.get("cid") == cid:
                    _clear_state(session, phone)
                session.commit()
                continue
            if sub == "collecting":
                # first idle -> check in once, advance to confirm, reset the clock
                n = _page_count(session, cid)
                _set_state(session, phone, cid, "confirm")
                session.execute(text("UPDATE contributions SET updated_at=now() WHERE id=:c"), {"c": cid})
                session.commit()
                whatsapp.send_text(http_client, phone, f"Got {n} page(s) so far — is that the whole paper? (yes / send more)")
            else:
                # continued silence (confirm/filing/fix) -> finalize for the reviewer with whatever we have
                session.execute(text(
                    "UPDATE contributions SET status='awaiting_review', bot_validation=CAST(:bv AS jsonb), "
                    "review_comment=COALESCE(review_comment,'auto: finalized on idle; filing unconfirmed'), "
                    "updated_at=now() WHERE id=:c"
                ), {"bv": _aggregate_validation(session, cid), "c": cid})
                if st and st.get("cid") == cid:
                    _clear_state(session, phone)
                session.commit()
                whatsapp.send_text(http_client, phone, "Thanks — I've received your pages and they're pending review.")
            acted += 1
        except Exception:
            log.exception("contrib_sweep_item_failed", extra={"cid": cid})
            session.rollback()
    return acted
