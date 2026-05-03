import pytest
from unittest.mock import patch
from app.embeddings import embed_one, embed_many
from app.errors import EmbeddingError

class MockEmbedResponse:
    def __init__(self, vals):
        class Emb:
            def __init__(self, v):
                self.values = v
        self.embeddings = [Emb(vals)]

@patch("app.embeddings.client.models.embed_content")
def test_embed_one_success(mock_embed):
    mock_embed.return_value = MockEmbedResponse([0.1] * 768)
    vec = embed_one("test")
    assert len(vec) == 768
    assert isinstance(vec[0], float)

@patch("app.embeddings.client.models.embed_content")
def test_embed_one_wrong_dim(mock_embed):
    mock_embed.return_value = MockEmbedResponse([0.1] * 512)
    with pytest.raises(EmbeddingError):
        embed_one("test")

@patch("app.embeddings.client.models.embed_content")
def test_embed_many_success(mock_embed):
    mock_embed.return_value = MockEmbedResponse([0.1] * 768)
    res = embed_many(["a", "b", "c"])
    assert len(res) == 3
    assert len(res[0]) == 768
    assert len(res[1]) == 768

@patch("app.embeddings.client.models.embed_content")
def test_embed_many_partial_failure(mock_embed):
    call_count = 0
    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("API error")
        return MockEmbedResponse([0.1] * 768)
    
    mock_embed.side_effect = side_effect
    with pytest.raises(EmbeddingError) as exc:
        embed_many(["a", "b", "c"], concurrency=1)
    
    assert "batch failed" in str(exc.value)