import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.mcp_server import MCPServer
from app.schemas.mcp_server import (
    MCPServerCreate,
    MCPServerResponse,
    MCPServerUpdate,
)
from app.services import mcp_service

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[MCPServerResponse])
async def list_mcp_servers(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(MCPServer).order_by(MCPServer.created_at.desc()))
    return res.scalars().all()


@router.post("/", response_model=MCPServerResponse, status_code=201)
async def create_mcp_server(body: MCPServerCreate, db: AsyncSession = Depends(get_db)):
    _validate_transport_fields(body)
    server = MCPServer(id=uuid.uuid4(), **body.model_dump())
    db.add(server)
    await db.flush()
    await db.refresh(server)
    return server


@router.get("/{server_id}", response_model=MCPServerResponse)
async def get_mcp_server(server_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    server = await _get_or_404(db, server_id)
    return server


@router.patch("/{server_id}", response_model=MCPServerResponse)
async def update_mcp_server(
    server_id: uuid.UUID, body: MCPServerUpdate, db: AsyncSession = Depends(get_db)
):
    server = await _get_or_404(db, server_id)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(server, field, value)
    server.updated_at = datetime.utcnow()
    await db.flush()
    await db.refresh(server)
    return server


@router.delete("/{server_id}")
async def delete_mcp_server(server_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    server = await _get_or_404(db, server_id)
    await db.delete(server)
    return {"message": "MCP server deleted"}


# ── Test connection ───────────────────────────────────────────────────────────

@router.post("/{server_id}/test")
async def test_mcp_server(server_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Connect to the MCP server, list its tools, and return a summary."""
    server = await _get_or_404(db, server_id)
    try:
        summary = await mcp_service.test_server(server)
        return summary
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"MCP connection failed: {exc}")


# ── List tools (live) ─────────────────────────────────────────────────────────

@router.get("/{server_id}/tools")
async def list_mcp_tools(server_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Return the live list of tools exposed by this MCP server."""
    server = await _get_or_404(db, server_id)
    try:
        tools, _ = await mcp_service.get_tools_for_servers([server])
        return {"tools": [t["function"] for t in tools]}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"MCP connection failed: {exc}")


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_or_404(db: AsyncSession, server_id: uuid.UUID) -> MCPServer:
    res = await db.execute(select(MCPServer).where(MCPServer.id == server_id))
    server = res.scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    return server


def _validate_transport_fields(body: MCPServerCreate) -> None:
    if body.transport == "stdio" and not body.command:
        raise HTTPException(
            status_code=422,
            detail="'command' is required for stdio transport",
        )
    if body.transport == "sse" and not body.url:
        raise HTTPException(
            status_code=422,
            detail="'url' is required for sse transport",
        )
