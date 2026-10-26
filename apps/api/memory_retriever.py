
from memory_store import load_memories, search_memories
from semantic_search import semantic_search


def retrieve_memories(
    query: str,
    top_k: int = 5,
    keyword_weight: float = 0.4,
    semantic_weight: float = 0.6,
    min_score: float = 0.25,
) -> list[dict]:
    """Retrieve and rank memories using keyword and semantic relevance."""
    if not query or not query.strip() or top_k <= 0:
        return []

    if keyword_weight < 0 or semantic_weight < 0:
        raise ValueError("Weights cannot be negative.")

    total_weight = keyword_weight + semantic_weight

    if total_weight == 0:
        raise ValueError("At least one weight must be greater than zero.")

    memories = load_memories()

    if not memories:
        return []

    keyword_results = (
        search_memories(query) if keyword_weight > 0 else []
    )
    semantic_results = (
        semantic_search(query, top_k=len(memories))
        if semantic_weight > 0
        else []
    )

    keyword_max = max(
        (item["match_count"] for item in keyword_results),
        default=0,
    )

    combined = {}

    for item in keyword_results:
        memory_id = item["id"]
        combined[memory_id] = {
            **item,
            "keyword_score": (
                item["match_count"] / keyword_max if keyword_max else 0
            ),
            "semantic_score": 0,
        }

    for item in semantic_results:
        memory_id = item["id"]
        semantic_score = max(0.0, min(1.0, item["similarity"]))

        if memory_id in combined:
            combined[memory_id].update(item)
            combined[memory_id]["semantic_score"] = semantic_score
        else:
            combined[memory_id] = {
                **item,
                "keyword_score": 0,
                "semantic_score": semantic_score,
            }

    for item in combined.values():
        item["score"] = (
            keyword_weight * item["keyword_score"]
            + semantic_weight * item["semantic_score"]
        ) / total_weight

    ranked_results = sorted(
        combined.values(),
        key=lambda item: item["score"],
        reverse=True,
    )

    filtered_results = [
        item for item in ranked_results
        if item["score"] >= min_score
    ]

    return filtered_results[:top_k]
