import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskResponse, TaskRunRequest, TaskUpdate

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/", response_model=List[TaskResponse])
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    q = select(Task).order_by(Task.created_at.desc()).limit(limit).offset(offset)
    if status:
        q = q.where(Task.status == status)
    res = await db.execute(q)
    return res.scalars().all()


@router.post("/", response_model=TaskResponse, status_code=201)
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_db)):
    task = Task(id=uuid.uuid4(), **body.model_dump())
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Task).where(Task.id == task_id))
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: uuid.UUID, body: TaskUpdate, db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(Task).where(Task.id == task_id))
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(task, field, value)
    task.updated_at = datetime.utcnow()
    await db.flush()
    await db.refresh(task)
    return task


@router.post("/{task_id}/run", response_model=TaskResponse)
async def run_task(
    task_id: uuid.UUID,
    body: TaskRunRequest,
    db: AsyncSession = Depends(get_db),
):
    """Dispatch task to Celery worker."""
    res = await db.execute(select(Task).where(Task.id == task_id))
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status == "running":
        raise HTTPException(status_code=409, detail="Task is already running")

    # Merge request input_data over stored defaults
    merged_input = {**(task.input_data or {}), **body.input_data}
    task.input_data = merged_input
    task.status = "pending"
    task.error_message = None
    task.output = None
    await db.flush()

    # Dispatch to Celery
    from app.worker import execute_task  # noqa: avoid circular at module level

    result = execute_task.delay(str(task_id))
    task.celery_task_id = result.id
    task.status = "running"
    await db.flush()
    await db.refresh(task)
    return task


@router.delete("/{task_id}")
async def delete_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Task).where(Task.id == task_id))
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await db.delete(task)
    return {"message": "Task deleted"}
