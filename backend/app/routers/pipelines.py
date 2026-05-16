import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.pipeline import Pipeline, PipelineRun
from app.schemas.pipeline import (
    PipelineCreate,
    PipelineResponse,
    PipelineRunRequest,
    PipelineRunResponse,
    PipelineUpdate,
)

router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])


# ── Pipeline CRUD ─────────────────────────────────────────────────────────────

@router.get("/", response_model=List[PipelineResponse])
async def list_pipelines(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Pipeline).order_by(Pipeline.created_at.desc()))
    return res.scalars().all()


@router.post("/", response_model=PipelineResponse, status_code=201)
async def create_pipeline(body: PipelineCreate, db: AsyncSession = Depends(get_db)):
    pipeline = Pipeline(
        id=uuid.uuid4(),
        name=body.name,
        description=body.description,
        steps=[s.model_dump() for s in body.steps],
        memory_enabled=body.memory_enabled,
        memory_scope=body.memory_scope,
    )
    db.add(pipeline)
    await db.flush()
    await db.refresh(pipeline)
    return pipeline


@router.get("/{pipeline_id}", response_model=PipelineResponse)
async def get_pipeline(pipeline_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))
    p = res.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return p


@router.patch("/{pipeline_id}", response_model=PipelineResponse)
async def update_pipeline(
    pipeline_id: uuid.UUID, body: PipelineUpdate, db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))
    p = res.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    if body.name is not None:
        p.name = body.name
    if body.description is not None:
        p.description = body.description
    if body.steps is not None:
        p.steps = [s.model_dump() for s in body.steps]
    if body.memory_enabled is not None:
        p.memory_enabled = body.memory_enabled
    if body.memory_scope is not None:
        p.memory_scope = body.memory_scope
    p.updated_at = datetime.utcnow()
    await db.flush()
    await db.refresh(p)
    return p


@router.delete("/{pipeline_id}", status_code=204)
async def delete_pipeline(pipeline_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))
    p = res.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    await db.delete(p)


# ── Run ───────────────────────────────────────────────────────────────────────

@router.post("/{pipeline_id}/run", response_model=PipelineRunResponse, status_code=202)
async def run_pipeline(
    pipeline_id: uuid.UUID,
    body: PipelineRunRequest,
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))
    p = res.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    run = PipelineRun(
        id=uuid.uuid4(),
        pipeline_id=pipeline_id,
        pipeline_name=p.name,
        user_input=body.user_input,
        user_id=body.user_id or "",
        status="pending",
        step_outputs={},
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)

    # Dispatch to Celery
    from app.worker import execute_pipeline
    task = execute_pipeline.delay(str(run.id))
    run.celery_task_id = task.id
    await db.flush()
    await db.refresh(run)
    return run


@router.get("/{pipeline_id}/runs", response_model=List[PipelineRunResponse])
async def list_runs(
    pipeline_id: uuid.UUID,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(PipelineRun)
        .where(PipelineRun.pipeline_id == pipeline_id)
        .order_by(PipelineRun.created_at.desc())
        .limit(limit)
    )
    return res.scalars().all()


@router.get("/runs/{run_id}", response_model=PipelineRunResponse)
async def get_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(PipelineRun).where(PipelineRun.id == run_id))
    run = res.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
