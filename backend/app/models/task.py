import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Task(Base):
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    agent_id = Column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    # Template supports {{variable}} substitution
    prompt_template = Column(Text, nullable=False)
    input_data = Column(JSON, default=dict)
    output = Column(Text, nullable=True)
    status = Column(String(50), default="pending")  # pending|running|completed|failed
    error_message = Column(Text, nullable=True)
    celery_task_id = Column(String(255), nullable=True)
    schedule_cron = Column(String(100), nullable=True)
    is_scheduled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    agent = relationship("Agent", back_populates="tasks")
