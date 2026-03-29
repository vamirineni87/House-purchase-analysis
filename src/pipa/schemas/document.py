"""Pydantic v2 schemas for document and note endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DocumentUpload(BaseModel):
    """Schema for uploading a document (metadata only; file content via multipart)."""

    filename: str
    document_type: str = "other"
    mime_type: Optional[str] = None


class DocumentResponse(BaseModel):
    """Document returned by the API."""

    id: str
    property_id: str
    filename: str
    storage_path: str
    mime_type: Optional[str] = None
    document_type: str
    uploaded_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class NoteCreate(BaseModel):
    """Create a property note."""

    content: str
    note_type: str = "general"


class NoteResponse(BaseModel):
    """Property note returned by the API."""

    id: str
    property_id: str
    content: str
    note_type: str
    created_at: datetime

    model_config = {"from_attributes": True}
