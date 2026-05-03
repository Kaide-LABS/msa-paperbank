import concurrent.futures
from google.genai import types
from app.llm import client
from app.config import settings
from app.errors import EmbeddingError

def embed_one(text: str) -> list[float]:
    try:
        resp = client.models.embed_content(
            model=settings.model_embedding,
            contents=text,
            config=types.EmbedContentConfig(
                output_dimensionality=settings.embedding_dim,
                task_type="RETRIEVAL_DOCUMENT"
            )
        )
        vec = list(resp.embeddings[0].values)
        if len(vec) != settings.embedding_dim:
            raise EmbeddingError(f"Expected dim {settings.embedding_dim}, got {len(vec)}")
        return vec
    except Exception as e:
        raise EmbeddingError("Embedding failed") from e

def embed_query(text: str) -> list[float]:
    try:
        resp = client.models.embed_content(
            model=settings.model_embedding,
            contents=text,
            config=types.EmbedContentConfig(
                output_dimensionality=settings.embedding_dim,
                task_type="RETRIEVAL_QUERY"
            )
        )
        vec = list(resp.embeddings[0].values)
        if len(vec) != settings.embedding_dim:
            raise EmbeddingError(f"Expected dim {settings.embedding_dim}, got {len(vec)}")
        return vec
    except Exception as e:
        raise EmbeddingError("Embedding failed") from e

def embed_many(texts: list[str], concurrency: int | None = None) -> list[list[float]]:
    conc = concurrency or settings.embedding_concurrency
    if conc > 16:
        conc = 16
        
    results = [None] * len(texts)
    exceptions = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=conc) as executor:
        future_to_idx = {executor.submit(embed_one, text): i for i, text in enumerate(texts)}
        for future in concurrent.futures.as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                exceptions.append(e)
                
    if exceptions:
        ok_count = len([r for r in results if r is not None])
        fail_count = len(texts) - ok_count
        raise EmbeddingError(f"batch failed: {ok_count} ok, {fail_count} failed") from exceptions[0]
        
    return results