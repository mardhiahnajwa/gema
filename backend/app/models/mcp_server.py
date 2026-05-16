import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class MCPServer(Base):
    __tablename__ = "mcp_servers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    # "stdio" spawns a subprocess; "sse" connects to an HTTP/SSE endpoint
    transport = Column(String(10), nullable=False, default="sse")
    # stdio fields
    command = Column(String(512), nullable=True)
    args = Column(JSON, default=list)
    env = Column(JSON, default=dict)
    # sse / http fields
    url = Column(String(1024), nullable=True)
    headers = Column(JSON, default=dict)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
