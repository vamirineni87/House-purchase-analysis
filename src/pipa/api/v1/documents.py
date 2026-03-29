"""Document and note endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipa.core.dependencies import get_db
from pipa.models.property import Property
from pipa.schemas.document import DocumentResponse, DocumentUpload
from pipa.services.document_service import DocumentService

router = APIRouter(tags=["documents"])


async def _verify_property(db: AsyncSession, property_id: str) -> None:
    """Raise 404 if property does not exist."""
    result = await db.execute(
        select(Property).where(Property.id == property_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Property not found")


# ------------------------------------------------------------------
# Documents
# ------------------------------------------------------------------


@router.get(
    "/properties/{property_id}/documents",
    response_model=list[DocumentResponse],
)
async def list_documents(
    property_id: str,
    db: AsyncSession = Depends(get_db),
):
    """List all documents for a property."""
    await _verify_property(db, property_id)
    return await DocumentService.list_documents(db, property_id)


@router.post(
    "/properties/{property_id}/documents",
    response_model=DocumentResponse,
    status_code=201,
)
async def upload_document(
    property_id: str,
    body: DocumentUpload,
    db: AsyncSession = Depends(get_db),
):
    """Upload a document (metadata + placeholder content).

    In a full implementation this would accept multipart/form-data.
    For now, it creates the record with placeholder content.
    """
    await _verify_property(db, property_id)
    doc = await DocumentService.upload(
        db,
        property_id=property_id,
        filename=body.filename,
        content=b"",  # Placeholder — real impl uses UploadFile
        document_type=body.document_type,
        mime_type=body.mime_type,
    )
    return doc
