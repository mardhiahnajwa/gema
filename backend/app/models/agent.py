import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Agent(Base):
    __tablename__ = "agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    system_prompt = Column(Text, nullable=False, default="You are a helpful assistant.")
    model = Column(String(255), nullable=False, default="gpt-4o")
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=4096)
    knowledge_base_ids = Column(JSON, default=list)   # list of KB UUID strings
    mcp_server_ids = Column(JSON, default=list)        # list of MCPServer UUID strings
    avatar_color = Column(String(20), default="#6366f1")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    conversations = relationship(
        "Conversation", back_populates="agent", cascade="all, delete-orphan"
    )
    tasks = relationship(
        "Task", back_populates="agent", cascade="all, delete-orphan"
    )
