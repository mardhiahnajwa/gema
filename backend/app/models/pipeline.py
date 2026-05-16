import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String, Text, JSON
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class Pipeline(Base):
    """
    A Pipeline is an ordered sequence of Steps.
    Each Step calls an AI model/agent and can reference outputs from previous steps.

    Step schema (stored in JSON array):
    {
        "id":            "step-1",          # unique within pipeline
        "name":          "Planner",
        "agent_id":      "uuid or null",    # if set, overrides model/system_prompt/temp
        "model":         "gpt-4o",
        "system_prompt": "You are...",
        "temperature":   0.7,
        "max_tokens":    2048,
        "input_template": "{{user_input}}\n\n{{previous_output}}"
        # Template variables available:
        #   {{user_input}}        — the original user input to the pipeline run
        #   {{previous_output}}   — the output of the immediately preceding step
        #   {{step_<id>_output}}  — output of any specific step by its id
    }
    """
    __tablename__ = "pipelines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    steps = Column(JSON, default=list)       # ordered list of step dicts
    # Memory settings
    memory_enabled = Column(Boolean, default=True)
    # 'pipeline' = memories scoped to this pipeline; 'global' = shared across all pipelines
    memory_scope = Column(String(50), default="pipeline")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PipelineRun(Base):
    """Tracks a single execution of a Pipeline."""
    __tablename__ = "pipeline_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_id = Column(UUID(as_uuid=True), nullable=False)
    pipeline_name = Column(String(255), nullable=True)   # snapshot at run time
    user_input = Column(Text, nullable=True)
    user_id = Column(String(255), nullable=True)  # for memory scoping
    status = Column(String(50), default="pending")       # pending|running|completed|failed
    step_outputs = Column(JSON, default=dict)            # {step_id: output_text}
    final_output = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    celery_task_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
