"""Document and note management service."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipa.models.document import Document, PropertyNote


# Default document storage directory (relative to project root)
_STORAGE_DIR = "uploads"


class DocumentService:
    """Manages document uploads and property notes."""

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    @staticmethod
    async def upload(
        db: AsyncSession,
        property_id: str,
        filename: str,
        content: bytes,
        document_type: str = "other",
        mime_type: Optional[str] = None,
    ) -> Document:
        """Store a document and create the database record.

        In production this would write to object storage (S3 / local fs).
        For now it writes to a local uploads directory.
        """
        # Ensure storage directory exists
        prop_dir = os.path.join(_STORAGE_DIR, property_id)
        os.makedirs(prop_dir, exist_ok=True)

        # Write file
        storage_path = os.path.join(prop_dir, filename)
        with open(storage_path, "wb") as f:
            f.write(content)

        doc = Document(
            property_id=property_id,
            filename=filename,
            storage_path=storage_path,
            mime_type=mime_type,
            document_type=document_type,
            uploaded_at=datetime.now(timezone.utc),
        )
        db.add(doc)
        await db.flush()
        return doc

    @staticmethod
    async def list_documents(
        db: AsyncSession,
        property_id: str,
    ) -> list[Document]:
        """List all documents for a property."""
        result = await db.execute(
            select(Document)
            .where(Document.property_id == property_id)
            .order_by(Document.uploaded_at.desc())
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Notes
    # ------------------------------------------------------------------

    @staticmethod
    async def add_note(
        db: AsyncSession,
        property_id: str,
        content: str,
        note_type: str = "general",
    ) -> PropertyNote:
        """Create a property note."""
        note = PropertyNote(
            property_id=property_id,
            content=content,
            note_type=note_type,
            created_at=datetime.now(timezone.utc),
        )
        db.add(note)
        await db.flush()
        return note

    @staticmethod
    async def get_notes(
        db: AsyncSession,
        property_id: str,
    ) -> list[PropertyNote]:
        """Get all notes for a property, newest first."""
        result = await db.execute(
            select(PropertyNote)
            .where(PropertyNote.property_id == property_id)
            .order_by(PropertyNote.created_at.desc())
        )
        return list(result.scalars().all())
