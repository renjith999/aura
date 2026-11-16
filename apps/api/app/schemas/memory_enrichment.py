import re
import unicodedata
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_validator,
    model_validator,
)


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

    name: StrictStr = Field(max_length=100)
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


class MemoryEnrichmentStatusResponse(BaseModel):
    memory_id: str
    status: Literal["pending", "processing", "completed", "failed"]
    attempt_count: int
    last_error: str | None
    next_retry_at: datetime | None
    completed_at: datetime | None
    summary: StrictStr | None = None
    category: MemoryCategory | None = None
    memory_type: MemoryType | None = None
    tags: list[str] = Field(default_factory=list)
    entities: list[MemoryEntity] = Field(default_factory=list)
    importance: int | None = None
    manual_fields: list[str] = Field(default_factory=list)


class MemoryEnrichmentCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: StrictStr | None = None
    category: MemoryCategory | None = None
    memory_type: MemoryType | None = None
    tags: list[StrictStr] | None = Field(default=None, max_length=10)
    entities: list[MemoryEntity] | None = Field(default=None, max_length=20)
    importance: int | None = Field(default=None, ge=1, le=5, strict=True)
    clear_overrides: list[
        Literal[
            "summary",
            "category",
            "memory_type",
            "tags",
            "entities",
            "importance",
        ]
    ] = Field(default_factory=list, max_length=6)

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
    def normalize_manual_tags(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        if any(not value.strip() or len(value.strip()) > 64 for value in values):
            raise ValueError("Tags must be nonblank and at most 64 characters")
        for value in values:
            normalized = MemoryEnrichmentV1(
                summary=None,
                category=None,
                memory_type=None,
                tags=[value],
                entities=[],
                importance=None,
            ).tags
            if not normalized:
                raise ValueError("Tags must contain at least one letter or number")
        return MemoryEnrichmentV1(
            summary=None,
            category=None,
            memory_type=None,
            tags=values,
            entities=[],
            importance=None,
        ).tags

    @field_validator("entities")
    @classmethod
    def deduplicate_manual_entities(
        cls,
        values: list[MemoryEntity] | None,
    ) -> list[MemoryEntity] | None:
        if values is None:
            return None
        normalized = []
        seen = set()
        for entity in values:
            key = (entity.name.casefold(), entity.entity_type)
            if key not in seen:
                seen.add(key)
                normalized.append(entity)
        return normalized

    @model_validator(mode="after")
    def validate_patch(self) -> "MemoryEnrichmentCorrection":
        metadata_fields = {
            "summary",
            "category",
            "memory_type",
            "tags",
            "entities",
            "importance",
        }
        provided_fields = self.model_fields_set & metadata_fields
        if not provided_fields and not self.clear_overrides:
            raise ValueError("At least one metadata field must be provided")
        if provided_fields.intersection(self.clear_overrides):
            raise ValueError("A field cannot be set and cleared in the same request")
        if any(
            field in self.model_fields_set and getattr(self, field) is None
            for field in ("tags", "entities")
        ):
            raise ValueError("Tags and entities must be arrays; use [] to clear them")
        if len(set(self.clear_overrides)) != len(self.clear_overrides):
            raise ValueError("clear_overrides cannot contain duplicates")
        return self
