
from sentence_transformers import SentenceTransformer
from sentence_transformers.util import cos_sim

from memory_store import load_memories


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

model = None

_cached_memories = None
_cached_embeddings = None


def _get_memory_embeddings(memories):
    global _cached_memories, _cached_embeddings, model

    # Reuse cached embeddings if the stored memories haven't changed.
    if memories == _cached_memories and _cached_embeddings is not None:
        return _cached_embeddings

    contents = [memory["content"] for memory in memories]

    if not contents:
        return None

    if model is None:
        model = SentenceTransformer(MODEL_NAME)

    _cached_embeddings = model.encode(
        contents,
        normalize_embeddings=True,
        convert_to_tensor=True,
    )
    _cached_memories = [memory.copy() for memory in memories]

    return _cached_embeddings


def semantic_search(query: str, top_k: int = 5) -> list[dict]:
    """Retrieve memories by semantic similarity."""
    if not query or not query.strip() or top_k <= 0:
        return []

    memories = load_memories()

    if not memories:
        return []

    memory_embeddings = _get_memory_embeddings(memories)

    query_embedding = model.encode(
        query,
        normalize_embeddings=True,
        convert_to_tensor=True,
    )

    scores = cos_sim(query_embedding, memory_embeddings)[0]

    results = []

    for memory, score in zip(memories, scores.tolist()):
        results.append({
            **memory,
            "similarity": round(score, 4),
        })

    results.sort(
        key=lambda item: item["similarity"],
        reverse=True,
    )

    return results[:top_k]


if __name__ == "__main__":
    question = input("Ask Aura: ")

    for result in semantic_search(question):
        print(
            f'{result["similarity"]:.4f} | '
            f'{result["content"]}'
        )
