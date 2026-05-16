import asyncio
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.knowledge_base import Document, KnowledgeBase
from app.schemas.knowledge import (
    DocumentResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
    QueryRequest,
    QueryResult,
)
from app.services.knowledge_service import (
    delete_document_chunks,
    delete_knowledge_base_collection,
    process_document,
    query_knowledge_bases,
)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

ALLOWED_EXTENSIONS = {"pdf", "txt", "md", "docx", "doc", "csv", "json", "yaml", "rst"}


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"


# ── Knowledge Bases ───────────────────────────────────────────────────────────

@router.get("/", response_model=List[KnowledgeBaseResponse])
async def list_knowledge_bases(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(KnowledgeBase).order_by(KnowledgeBase.created_at.desc()))
    kbs = res.scalars().all()
    enriched = []
    for kb in kbs:
        cnt_res = await db.execute(
            select(func.count()).where(Document.knowledge_base_id == kb.id)
        )
        doc_count = cnt_res.scalar() or 0
        kb_dict = KnowledgeBaseResponse.model_validate(kb).model_dump()
        kb_dict["document_count"] = doc_count
        enriched.append(kb_dict)
    return enriched


@router.post("/", response_model=KnowledgeBaseResponse, status_code=201)
async def create_knowledge_base(body: KnowledgeBaseCreate, db: AsyncSession = Depends(get_db)):
    kb = KnowledgeBase(id=uuid.uuid4(), **body.model_dump())
    db.add(kb)
    await db.flush()
    await db.refresh(kb)
    return kb


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base(kb_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = res.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    cnt_res = await db.execute(
        select(func.count()).where(Document.knowledge_base_id == kb_id)
    )
    doc_count = cnt_res.scalar() or 0
    result = KnowledgeBaseResponse.model_validate(kb).model_dump()
    result["document_count"] = doc_count
    return result


@router.patch("/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    kb_id: uuid.UUID, body: KnowledgeBaseUpdate, db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = res.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(kb, field, value)
    kb.updated_at = datetime.utcnow()
    await db.flush()
    await db.refresh(kb)
    return kb


@router.delete("/{kb_id}")
async def delete_knowledge_base(kb_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = res.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    await delete_knowledge_base_collection(str(kb_id))
    await db.delete(kb)
    return {"message": "Knowledge base deleted"}


# ── Documents ─────────────────────────────────────────────────────────────────

@router.get("/{kb_id}/documents", response_model=List[DocumentResponse])
async def list_documents(kb_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(Document)
        .where(Document.knowledge_base_id == kb_id)
        .order_by(Document.created_at.desc())
    )
    return res.scalars().all()


@router.post("/{kb_id}/documents", response_model=DocumentResponse, status_code=201)
async def upload_document(
    kb_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    # Validate KB exists
    res = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = res.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    file_type = _ext(file.filename or "file.txt")
    if file_type not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{file_type}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Size check
    content = await file.read()
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {settings.MAX_UPLOAD_SIZE_MB} MB limit",
        )

    # Save to disk
    doc_id = uuid.uuid4()
    upload_dir = Path(settings.UPLOAD_DIR) / str(kb_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"{doc_id}.{file_type}"
    file_path.write_bytes(content)

    # Create DB record
    doc = Document(
        id=doc_id,
        knowledge_base_id=kb_id,
        filename=file.filename or f"{doc_id}.{file_type}",
        file_type=file_type,
        file_size=len(content),
        status="processing",
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)

    # Process in background
    async def _process():
        async with db.begin_nested():
            try:
                n_chunks = await process_document(str(kb_id), str(doc_id), str(file_path), file_type)
                doc.chunks_count = n_chunks
                doc.status = "ready"
            except Exception as exc:
                doc.status = "failed"
                doc.error_message = str(exc)

    asyncio.create_task(_process())
    return doc


@router.delete("/{kb_id}/documents/{doc_id}")
async def delete_document(
    kb_id: uuid.UUID, doc_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    res = await db.execute(
        select(Document).where(
            Document.id == doc_id, Document.knowledge_base_id == kb_id
        )
    )
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await delete_document_chunks(str(kb_id), str(doc_id))

    # Remove file from disk
    file_path = Path(settings.UPLOAD_DIR) / str(kb_id) / f"{doc_id}.{doc.file_type}"
    if file_path.exists():
        file_path.unlink()

    await db.delete(doc)
    return {"message": "Document deleted"}


# ── Query ─────────────────────────────────────────────────────────────────────

@router.post("/query", response_model=List[QueryResult])
async def query_knowledge(body: QueryRequest):
    results = await query_knowledge_bases(
        body.knowledge_base_ids, body.query, body.n_results
    )
    return results
