import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.database import get_db
from app.models.artifact import Artifact
from app.schemas.artifact import ArtifactCreate, ArtifactResponse

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


@router.get("/", response_model=List[ArtifactResponse])
async def list_artifacts(limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Artifact).order_by(Artifact.created_at.desc()).limit(limit)
    )
    return result.scalars().all()


@router.post("/", response_model=ArtifactResponse, status_code=201)
async def save_artifact(body: ArtifactCreate, db: AsyncSession = Depends(get_db)):
    artifact = Artifact(
        id=uuid.uuid4(),
        title=body.title or "Untitled Artifact",
        html_content=body.html_content,
        agent_id=body.agent_id,
        conversation_id=body.conversation_id,
        source=body.source or "chat",
    )
    db.add(artifact)
    await db.commit()
    await db.refresh(artifact)
    return artifact


@router.get("/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(artifact_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Artifact).where(Artifact.id == artifact_id))
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return artifact


@router.delete("/{artifact_id}", status_code=204)
async def delete_artifact(artifact_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Artifact).where(Artifact.id == artifact_id))
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    await db.execute(delete(Artifact).where(Artifact.id == artifact_id))
    await db.commit()
