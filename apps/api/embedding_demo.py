
from sentence_transformers import SentenceTransformer
from sentence_transformers.util import cos_sim

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

memories = [
    "The Aura backend uses Python and FastAPI.",
    "My favorite food is biryani.",
    "Aura stores personal memories for later retrieval.",
]

question = "Which technologies power my personal assistant?"

texts = [question, *memories]
embeddings = model.encode(texts, normalize_embeddings=True)

scores = cos_sim(embeddings[0], embeddings[1:])[0]

ranked = sorted(
    zip(memories, scores.tolist()),
    key=lambda item: item[1],
    reverse=True,
)

print(f"Question: {question}\n")
print("Ranked memories:")

for content, score in ranked:
    print(f"{score:.3f} | {content}")
