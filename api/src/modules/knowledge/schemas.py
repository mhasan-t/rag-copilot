import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from src.core.validation import ServiceName

type DocType = Literal["runbook", "postmortem", "wiki"]


class DocumentIngest(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=255)]
    source_uri: Annotated[
        str, Field(min_length=1, max_length=1024, description="Stable identity; re-ingesting it replaces the document")
    ]
    doc_type: DocType
    service_tags: Annotated[
        list[ServiceName], Field(max_length=20, description="Services this applies to; empty means all services")
    ] = []
    content: Annotated[str, Field(min_length=1, max_length=500_000, description="Markdown")]


class IngestResult(BaseModel):
    document_id: uuid.UUID
    source_uri: str
    result: Literal["created", "updated", "unchanged"]
    chunk_count: int


class SearchHit(BaseModel):
    document_id: uuid.UUID
    title: str
    source_uri: str
    doc_type: DocType
    chunk_index: int
    content: str
    score: float = Field(description="Cosine similarity; higher is more relevant")
