from enum import Enum
import re
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MemoryCategory(str, Enum):
    PERSONAL = "personal"
    WORK = "work"
    LEARNING = "learning"
    PROJECT = "project"
    FINANCE = "finance"
    HEALTH = "health"
    OTHER = "other"


class MemoryType(str, Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    GOAL = "goal"
    ACHIEVEMENT = "achievement"
    EVENT = "event"
    DECISION = "decision"
    INSTRUCTION = "instruction"
    OTHER = "other"


class EntityType(str, Enum):
    PERSON = "person"
    ORGANIZATION = "organization"
    TECHNOLOGY = "technology"
    PRODUCT = "product"
    LOCATION = "location"
    CERTIFICATION = "certification"
    ROLE = "role"
    OTHER = "other"


class MemoryEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    entity_type: EntityType

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Entity name must not be blank")

        return value


class MemoryEnrichmentV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str | None
    category: MemoryCategory | None
    memory_type: MemoryType | None
    tags: list[str] = Field(max_length=10)
    entities: list[MemoryEntity] = Field(max_length=20)
    importance: int | None = Field(ge=1, le=5)

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()

            if not value:
                raise ValueError("Summary must not be blank")

            if len(value) > 500:
                raise ValueError("Summary must be at most 500 characters")

        return value

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        normalized = []
        seen = set()

        for value in values:
            tag = unicodedata.normalize("NFKC", value).strip().casefold()

            # Preserve Unicode letters, numbers, and combining marks.
            # Convert all other characters into separators.
            characters = []

            for char in tag:
                category = unicodedata.category(char)

                if category[0] in {"L", "N", "M"}:
                    characters.append(char)
                else:
                    characters.append("-")

            tag = "".join(characters)

            # Collapse repeated separators and remove edge hyphens.
            tag = re.sub(r"-+", "-", tag).strip("-")

            if not tag:
                continue

            if tag not in seen:
                seen.add(tag)
                normalized.append(tag)

        return normalized

    @field_validator("entities")
    @classmethod
    def remove_duplicate_entities(
        cls,
        values: list[MemoryEntity],
    ) -> list[MemoryEntity]:
        normalized = []
        seen = set()

        for entity in values:
            key = (entity.name.casefold(), entity.entity_type)

            if key not in seen:
                seen.add(key)
                normalized.append(entity)

        return normalized