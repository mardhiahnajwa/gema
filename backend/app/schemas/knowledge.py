from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class KnowledgeBaseUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None


class KnowledgeBaseResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    embedding_model: str
    created_at: datetime
    updated_at: datetime
    document_count: int = 0

    model_config = {"from_attributes": True}


class DocumentResponse(BaseModel):
    id: UUID
    knowledge_base_id: UUID
    filename: str
    file_type: str
    file_size: Optional[int]
    chunks_count: int
    status: str
    error_message: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    knowledge_base_ids: List[str]
    n_results: int = Field(5, ge=1, le=20)


class QueryResult(BaseModel):
    content: str
    score: float
    kb_id: str
    doc_id: str
