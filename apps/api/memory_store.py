
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

MEMORY_FILE = Path(__file__).parent / "memories.json"


def load_memories() -> list[dict]:
    if not MEMORY_FILE.exists():
        return []

    with MEMORY_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)



import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

MEMORY_FILE = Path(__file__).parent / "memories.json"


def load_memories() -> list[dict]:
    if not MEMORY_FILE.exists():
        return []

    with MEMORY_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)



def update_memory(
    memory_id: str,
    new_content: str,
    new_category: str | None = None,
) -> dict:
    """Update an existing memory while preserving its ID."""
    new_content = new_content.strip()

    if not new_content:
        raise ValueError("Memory content cannot be empty")

    if new_category is not None:
        new_category = new_category.strip().lower()
        if not new_category:
            raise ValueError("Memory category cannot be empty")

    memories = load_memories()

    for memory in memories:
        
        if memory["id"] == memory_id:
            normalized_content = " ".join(new_content.lower().split())

            for other_memory in memories:
                if other_memory["id"] == memory_id:
                    continue

                existing_content = " ".join(
                    other_memory["content"].lower().split()
                )

                if (
                    existing_content == normalized_content
                    and other_memory["category"] == (
                        new_category
                        if new_category is not None
                        else memory["category"]
                    )
                ):
                        raise ValueError(
                            f"Memory content already exists: {other_memory['id']}"
                        )

            memory["content"] = new_content
            memory["updated_at"] = datetime.now(timezone.utc).isoformat()

            if new_category is not None:
                memory["category"] = new_category

            with MEMORY_FILE.open("w", encoding="utf-8") as file:
                json.dump(
                    memories,
                    file,
                    indent=2,
                    ensure_ascii=False,
                )

            return memory

    raise ValueError(f"Memory not found: {memory_id}")


def save_memory(content: str, category: str) -> dict:
    """Save a memory unless the same content already exists."""
    content = content.strip()
    category = category.strip().lower()

    if not content:
        raise ValueError("Memory content cannot be empty")
    if not category:
        raise ValueError("Memory category cannot be empty")

    memories = load_memories()

    # Prevent duplicate content, ignoring case and extra whitespace.
    normalized_content = " ".join(content.lower().split())

    for memory in memories:
        existing_content = " ".join(
            memory["content"].lower().split()
        )

        if (
            existing_content == normalized_content
            and memory["category"] == category
        ):
            print("Memory already exists; skipping duplicate.")
            return memory

    memory = {
        "id": f"mem-{uuid.uuid4().hex}",
        "content": content,
        "category": category,
        "source": "user",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    memories.append(memory)

    with MEMORY_FILE.open("w", encoding="utf-8") as file:
        json.dump(memories, file, indent=2, ensure_ascii=False)

    return memory


import re

STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were",
    "what", "which", "who", "does", "do", "did",
    "how", "when", "where", "why", "and", "or",
    "to", "of", "in", "on", "for", "my", "i", "use",
}


def normalize_words(text: str) -> set[str]:
    words = set(re.findall(r"\b[a-z0-9]+\b", text.lower()))
    return words - STOP_WORDS



def search_memories(query: str) -> list[dict]:
    """Find memories using normalized keyword overlap."""
    query_words = normalize_words(query)

    if not query_words:
        return []

    scored_memories = []

    for memory in load_memories():
        content_words = normalize_words(memory["content"])
        matches = query_words & content_words

        if matches:
            scored_memories.append({
                **memory,
                "match_count": len(matches),
                "matched_words": sorted(matches),
            })

    return sorted(
        scored_memories,
        key=lambda memory: memory["match_count"],
        reverse=True,
    )
def find_similar_memories(content, threshold=2):
    new_words = normalize_words(content)
    memories = load_memories()
    results = []

    for memory in memories:
        existing_words = normalize_words(memory["content"])
        matched_words = new_words & existing_words

        if len(matched_words) >= threshold:
            results.append({
                "memory": memory,
                "matched_words": sorted(matched_words),
                "match_count": len(matched_words),
            })

    return sorted(
        results,
        key=lambda item: item["match_count"],
        reverse=True,
    )

def review_new_memory(content):
    similar = find_similar_memories(content)

    if not similar:
        return {
            "action": "save",
            "message": "No similar memories found.",
            "matches": [],
        }

    return {
        "action": "review",
        "message": "Possible related memories found. Review before saving.",
        "matches": similar,
    }
def resolve_memory(content, decision, memory_id=None, category="general"):
    if decision == "save":
        return save_memory(content, category)

    if decision == "update":
        if not memory_id:
            raise ValueError("memory_id is required to update a memory")

        return update_memory(
            memory_id,
            content,
            new_category=category,
        )

    if decision == "keep_both":
        return save_memory(content, category)

    raise ValueError(
        "decision must be 'save', 'update', or 'keep_both'"
    )
# if __name__ == "__main__":
#     memory = save_memory(
#         content="The Aura backend uses Python and FastAPI.",
#         category="technology",
#     )

#     print("Saved memory:")
#     print(json.dumps(memory, indent=2))

#     print("\nAll saved memories:")
#     print(json.dumps(load_memories(), indent=2))


# if __name__ == "__main__":
#     results = search_memories("What technology does Aura use?")

#     print("Matching memories:")
#     for memory in results:
#         print(f"- {memory['content']} (matches: {memory['match_count']})")


# if __name__ == "__main__":
#     memory = save_memory(
#         "The Aura backend uses Python.",
#         "technology",
#     )

#     print("Before update:", memory)

#     updated = update_memory(
#         memory_id=memory["id"],
#         new_content="The Aura backend uses Python and FastAPI.",
#     )

#     print("\nAfter update:", updated)


# first = save_memory(
#     "The Aura backend uses Python and FastAPI.",
#     "technology",
# )

# second = save_memory(
#     "  THE Aura backend uses Python and FastAPI.  ",
#     "technology",
# )

# print("First ID:", first["id"])
# print("Second ID:", second["id"])
# print("Same memory:", first["id"] == second["id"])

# if __name__ == "__main__":
#     results = find_similar_memories(
#         "I am learning Python for my Aura project"
#     )

#     for result in results:
#         print(result)

# if __name__ == "__main__":
#     result = review_new_memory(
#         "I am learning Python for my Aura project"
#     )

#     print(result["message"])

#     for item in result["matches"]:
#         print(
#             f'{item["memory"]["id"]}: '
#             f'{item["memory"]["content"]}'
#         )

if __name__ == "__main__":
    result = resolve_memory(
        content="The Aura backend uses Python and FastAPI with improved memory retrieval.",
        decision="update",
        memory_id="mem-002",
        category="technology",
    )

    print(result)
