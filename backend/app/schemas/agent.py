from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AgentBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    system_prompt: str = "You are a helpful assistant."
    model: str = "gpt-4o"
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(4096, ge=1, le=200000)
    knowledge_base_ids: List[str] = []
    mcp_server_ids: List[str] = []
    avatar_color: str = "#6366f1"


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=200000)
    knowledge_base_ids: Optional[List[str]] = None
    mcp_server_ids: Optional[List[str]] = None
    avatar_color: Optional[str] = None
    is_active: Optional[bool] = None


class AgentResponse(AgentBase):
    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
