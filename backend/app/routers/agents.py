import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent import Agent
from app.schemas.agent import AgentCreate, AgentResponse, AgentUpdate

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("/", response_model=List[AgentResponse])
async def list_agents(db: AsyncSession = Depends(get_db), active_only: bool = False):
    q = select(Agent).order_by(Agent.created_at.desc())
    if active_only:
        q = q.where(Agent.is_active == True)
    res = await db.execute(q)
    return res.scalars().all()


@router.post("/", response_model=AgentResponse, status_code=201)
async def create_agent(body: AgentCreate, db: AsyncSession = Depends(get_db)):
    agent = Agent(id=uuid.uuid4(), **body.model_dump())
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    return agent


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = res.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: uuid.UUID, body: AgentUpdate, db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = res.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(agent, field, value)
    agent.updated_at = datetime.utcnow()
    await db.flush()
    await db.refresh(agent)
    return agent


@router.delete("/{agent_id}")
async def delete_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = res.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await db.delete(agent)
    return {"message": "Agent deleted"}
