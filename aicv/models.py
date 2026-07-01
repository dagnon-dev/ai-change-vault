from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_serializer, field_validator


class BackupResult(BaseModel):
    turn_number: int
    backup_id: str
    message: str
    path: Path
    timestamp: datetime
    files_copied: int

    @field_serializer("path")
    def serialize_path(self, value: Path) -> str:
        return value.as_posix()

    @field_serializer("timestamp")
    def serialize_timestamp(self, value: datetime) -> str:
        return value.isoformat()


class TurnDocument(BaseModel):
    turn_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    request: str
    description: str | None = None
    files_changed: list[str] = Field(default_factory=list)
    backup_before: str | None = None
    backup_after: str | None = None
    validation: str | None = None
    status: str = "indexed"

    @field_validator("turn_id", mode="before")
    @classmethod
    def normalize_turn(cls, value: object) -> str:
        from .utils import normalize_turn_id

        return normalize_turn_id(str(value))

    @field_serializer("timestamp")
    def serialize_timestamp(self, value: datetime) -> str:
        return value.isoformat()


class SearchResult(BaseModel):
    turn: TurnDocument
    score: int
    matched_terms: list[str] = Field(default_factory=list)


class EmbeddingRecord(BaseModel):
    turn_id: str
    kind: Literal["turn", "diff", "snippet"] = "turn"
    chunk_id: str | None = None
    provider: str
    model: str
    source_path: str | None = None
    title: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    text: str
    vector: list[float] = Field(default_factory=list)
    text_hash: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_serializer("updated_at")
    def serialize_updated_at(self, value: datetime) -> str:
        return value.isoformat()


class EmbeddingStore(BaseModel):
    schema_version: int = 1
    records: list[EmbeddingRecord] = Field(default_factory=list)


class RevertResult(BaseModel):
    turn_id: str
    state: str
    backup_path: Path
    restored_files: list[str]
    removed_paths: list[str] = Field(default_factory=list)

    @field_serializer("backup_path")
    def serialize_backup_path(self, value: Path) -> str:
        return value.as_posix()
