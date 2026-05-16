from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid as _uuid

from pydantic import BaseModel, Field


# ── Step ──────────────────────────────────────────────────────────────────────

class PipelineStep(BaseModel):
    id: str = Field(default_factory=lambda: f"step-{_uuid.uuid4().hex[:6]}")
    name: str
    agent_id: Optional[str] = None      # if set, inherits model/prompt from that agent
    model: str = "gpt-4o"
    system_prompt: str = ""
    temperature: float = 0.7
    max_tokens: int = 2048
    # Template may use: {{user_input}}, {{previous_output}}, {{step_<id>_output}}
    input_template: str = "{{user_input}}"


# ── Pipeline CRUD ─────────────────────────────────────────────────────────────

class PipelineCreate(BaseModel):
    name: str
    description: Optional[str] = None
    steps: List[PipelineStep] = []
    memory_enabled: bool = True
    memory_scope: str = "pipeline"  # 'pipeline' | 'global'


class PipelineUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    steps: Optional[List[PipelineStep]] = None
    memory_enabled: Optional[bool] = None
    memory_scope: Optional[str] = None


class PipelineResponse(BaseModel):
    id: _uuid.UUID
    name: str
    description: Optional[str]
    steps: List[Dict[str, Any]]
    memory_enabled: bool
    memory_scope: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Pipeline Run ──────────────────────────────────────────────────────────────

class PipelineRunRequest(BaseModel):
    user_input: str = ""
    user_id: Optional[str] = None  # stable id for long-term memory scoping


class PipelineRunResponse(BaseModel):
    id: _uuid.UUID
    pipeline_id: _uuid.UUID
    pipeline_name: Optional[str]
    user_input: Optional[str]
    user_id: Optional[str]
    status: str
    step_outputs: Dict[str, Any]
    final_output: Optional[str]
    error_message: Optional[str]
    celery_task_id: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}
