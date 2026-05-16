import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class Artifact(Base):
    __tablename__ = "artifacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False, default="Untitled Artifact")
    html_content = Column(Text, nullable=False)
    # optional linking context
    agent_id = Column(UUID(as_uuid=True), nullable=True)
    conversation_id = Column(UUID(as_uuid=True), nullable=True)
    source = Column(String(50), default="chat")  # 'chat' | 'pipeline'
    created_at = Column(DateTime, default=datetime.utcnow)
