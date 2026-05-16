from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    agent_id: Optional[UUID] = None
    prompt_template: str = Field(..., min_length=1)
    input_data: Dict[str, Any] = {}
    schedule_cron: Optional[str] = None


class TaskUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    agent_id: Optional[UUID] = None
    prompt_template: Optional[str] = None
    input_data: Optional[Dict[str, Any]] = None
    schedule_cron: Optional[str] = None


class TaskRunRequest(BaseModel):
    input_data: Dict[str, Any] = {}


class TaskResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    agent_id: Optional[UUID]
    prompt_template: str
    input_data: Dict[str, Any]
    output: Optional[str]
    status: str
    error_message: Optional[str]
    celery_task_id: Optional[str]
    schedule_cron: Optional[str]
    is_scheduled: bool
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}
