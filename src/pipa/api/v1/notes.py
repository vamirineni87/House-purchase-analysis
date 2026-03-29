"""Property notes endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipa.core.dependencies import get_db
from pipa.models.document import PropertyNote

router = APIRouter(tags=["notes"])


class NoteCreate(BaseModel):
    content: str
    note_type: str = "general"


class NoteResponse(BaseModel):
    id: str
    property_id: str
    content: str
    note_type: str
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/properties/{property_id}/notes", response_model=list[NoteResponse])
async def list_notes(property_id: str, db: AsyncSession = Depends(get_db)):
    """List notes for a property, newest first."""
    result = await db.execute(
        select(PropertyNote)
        .where(PropertyNote.property_id == property_id)
        .order_by(PropertyNote.created_at.desc())
    )
    return result.scalars().all()


@router.post("/properties/{property_id}/notes", response_model=NoteResponse, status_code=201)
async def create_note(property_id: str, body: NoteCreate, db: AsyncSession = Depends(get_db)):
    """Add a note to a property."""
    note = PropertyNote(
        property_id=property_id,
        content=body.content,
        note_type=body.note_type,
        created_at=datetime.now(timezone.utc),
    )
    db.add(note)
    await db.flush()
    return note


@router.delete("/properties/{property_id}/notes/{note_id}", status_code=204)
async def delete_note(property_id: str, note_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a property note."""
    result = await db.execute(
        select(PropertyNote).where(
            PropertyNote.id == note_id,
            PropertyNote.property_id == property_id,
        )
    )
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    await db.delete(note)
