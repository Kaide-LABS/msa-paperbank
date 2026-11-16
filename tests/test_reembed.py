from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as SASession

from app.reembed import _update_batch, reembed_all
from app.db import (
    Base,
    Course,
    Paper,
    PaperChunk,
    PendingPaper,
    PendingPaperChunk,
)


@pytest.fixture
def pg_session():
    """Isolated in-memory sqlite with only the embedding tables.

    The shared conftest `session` fixture creates the full schema, which includes
    JSONB columns sqlite cannot compile; this fixture creates just the tables the
    re-embed job touches so the end-to-end path runs network-free on any host.
    """
    engine = create_engine("sqlite://")
    tables = [m.__table__ for m in (Course, Paper, PaperChunk, PendingPaper, PendingPaperChunk)]
    Base.metadata.create_all(engine, tables=tables)
    s = SASession(engine)
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


class FakeSession:
    def __init__(self):
        self.calls = []

    def execute(self, statement):
        self.calls.append(statement)


class FakeEmbedder:
    def embed_documents(self, texts):
        return [[float(len(text)), 0.0] for text in texts]


def test_update_batch_only_emits_embedding_updates_and_preserves_rows():
    rows = [SimpleNamespace(id=2, text="abc"), SimpleNamespace(id=4, text="x")]
    session = FakeSession()
    assert _update_batch(session, PaperChunk, rows, FakeEmbedder()) == 2
    assert len(session.calls) == 2
    assert [row.text for row in rows] == ["abc", "x"]
    assert all("embedding" in str(call) for call in session.calls)


class SeededEmbedder:
    """Deterministic 768-dim fake: the first component encodes the text length,
    the rest are zeros, so re-encoding the same text always yields the same vector."""

    def embed_documents(self, texts):
        return [[float(len(t))] + [0.0] * 767 for t in texts]


def _seed_corpus(session):
    session.add(Paper(
        id=901, course_code="MTH102", semester="harmattan", year=2019,
        object_key="k/901.pdf", sha256="sha-901", uploaded_by="op",
    ))
    session.add_all([
        PaperChunk(id=9011, paper_id=901, chunk_no=0, text="limits and continuity",
                   embedding=[0.0] * 768),
        PaperChunk(id=9012, paper_id=901, chunk_no=1, text="derivative rules",
                   embedding=[0.0] * 768),
    ])
    session.add(PendingPaper(
        id=902, course_code="MTH102", semester="rain", year=2020,
        object_key="k/902.pdf", sha256="sha-902", uploaded_by="op",
    ))
    session.add(PendingPaperChunk(id=9021, pending_paper_id=902, chunk_no=0,
                                  text="integration by parts", embedding=[0.0] * 768))
    session.commit()


def test_reembed_all_updates_every_row_is_idempotent_and_issues_no_ddl(pg_session, monkeypatch):
    import app.reembed as reembed

    session = pg_session
    _seed_corpus(session)

    # Guard: the default (non-fast) path must issue NO DDL. DDL only flows through
    # reembed.text(...); make any such call fail the test.
    def _no_ddl(*args, **kwargs):
        raise AssertionError("default re-embed path must not issue DDL")
    monkeypatch.setattr(reembed, "text", _no_ddl)

    embedder = SeededEmbedder()
    total = reembed.reembed_all(session, embedder, batch_size=1)
    assert total == 3  # two paper_chunks + one pending_paper_chunk

    def _vec(model, row_id, length):
        row = session.get(model, row_id)
        return [float(x) for x in row.embedding]

    # Every row's embedding became the fake's vector (first component = text length).
    assert _vec(PaperChunk, 9011, 0)[0] == float(len("limits and continuity"))
    assert _vec(PaperChunk, 9012, 0)[0] == float(len("derivative rules"))
    assert _vec(PendingPaperChunk, 9021, 0)[0] == float(len("integration by parts"))

    # text / id columns untouched.
    assert session.get(PaperChunk, 9011).text == "limits and continuity"
    assert session.get(PendingPaperChunk, 9021).text == "integration by parts"

    # Idempotent: a second run over identical input yields identical vectors.
    before = [session.get(PaperChunk, 9011).embedding,
              session.get(PaperChunk, 9012).embedding,
              session.get(PendingPaperChunk, 9021).embedding]
    assert reembed.reembed_all(session, embedder, batch_size=32) == 3
    after = [session.get(PaperChunk, 9011).embedding,
             session.get(PaperChunk, 9012).embedding,
             session.get(PendingPaperChunk, 9021).embedding]
    assert [list(map(float, v)) for v in before] == [list(map(float, v)) for v in after]


def test_reembed_all_rejects_unknown_table_and_bad_batch(pg_session):
    with pytest.raises(ValueError):
        reembed_all(pg_session, SeededEmbedder(), tables=("nope",))
    with pytest.raises(ValueError):
        reembed_all(pg_session, SeededEmbedder(), batch_size=0)
