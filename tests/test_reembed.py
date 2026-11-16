from types import SimpleNamespace

from app.reembed import _update_batch
from app.db import PaperChunk


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
