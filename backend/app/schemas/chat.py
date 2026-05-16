from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str


class ChatRequest(BaseModel):
    model: str = "gpt-4o"
    messages: List[ChatMessage]
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(4096, ge=1, le=200000)
    stream: bool = False
    conversation_id: Optional[UUID] = None
    agent_id: Optional[UUID] = None
    user_id: Optional[str] = None          # stable identifier for long-term memory
    knowledge_base_ids: Optional[List[str]] = None
    mcp_server_ids: Optional[List[str]] = None


class ChatResponse(BaseModel):
    id: str
    model: str
    content: str
    role: str = "assistant"
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    conversation_id: Optional[UUID] = None


class ConversationCreate(BaseModel):
    title: str = "New Conversation"
    agent_id: Optional[UUID] = None
    model: Optional[str] = None


class ConversationResponse(BaseModel):
    id: UUID
    title: str
    agent_id: Optional[UUID]
    model: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    model: Optional[str]
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}
