import uuid as _uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ArtifactCreate(BaseModel):
    title: Optional[str] = "Untitled Artifact"
    html_content: str
    agent_id: Optional[_uuid.UUID] = None
    conversation_id: Optional[_uuid.UUID] = None
    source: Optional[str] = "chat"


class ArtifactResponse(BaseModel):
    id: _uuid.UUID
    title: str
    html_content: str
    agent_id: Optional[_uuid.UUID]
    conversation_id: Optional[_uuid.UUID]
    source: str
    created_at: datetime

    model_config = {"from_attributes": True}
