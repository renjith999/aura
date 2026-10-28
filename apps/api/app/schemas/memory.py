from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MemoryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    category: str = Field(default="uncategorized", min_length=1, max_length=100)
    is_favorite: bool = False

    @field_validator("title", "content", "category")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value must not be blank.")
        return value


class MemoryUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    is_favorite: bool | None = None

    @field_validator("title", "content", "category")
    @classmethod
    def validate_non_blank(cls, value: str | None) -> str:
        if value is None or not value.strip():
            raise ValueError("Value must not be blank.")
        return value

    @model_validator(mode="after")
    def require_update_field(self) -> "MemoryUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided.")
        return self


class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    content: str
    category: str
    is_favorite: bool
    user_id: str
    created_at: datetime
    updated_at: datetime
