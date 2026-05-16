from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class MCPServerBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    transport: str = Field(..., pattern="^(stdio|sse)$")
    # stdio
    command: Optional[str] = Field(None, max_length=512)
    args: List[str] = []
    env: Dict[str, str] = {}
    # sse / http
    url: Optional[str] = Field(None, max_length=1024)
    headers: Dict[str, str] = {}


class MCPServerCreate(MCPServerBase):
    pass


class MCPServerUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    transport: Optional[str] = Field(None, pattern="^(stdio|sse)$")
    command: Optional[str] = Field(None, max_length=512)
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    url: Optional[str] = Field(None, max_length=1024)
    headers: Optional[Dict[str, str]] = None
    is_active: Optional[bool] = None


class MCPServerResponse(MCPServerBase):
    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MCPToolInfo(BaseModel):
    name: str
    description: Optional[str] = None
    input_schema: Optional[dict] = None
