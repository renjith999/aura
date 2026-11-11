from app.schemas.memory_enrichment import MemoryEnrichmentV1

enrichment = MemoryEnrichmentV1(
    summary="User is building Aura using Python and FastAPI.",
    category="project",
    memory_type="goal",
    tags=["Aura", "Python", "aura"],
    entities=[
        {"name": "Aura", "entity_type": "project"} if False else
        {"name": "Aura", "entity_type": "other"},
        {"name": "FastAPI", "entity_type": "technology"},
    ],
    importance=5,
)

print(enrichment.model_dump(mode="json"))