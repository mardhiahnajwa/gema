from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import create_tables
from app.routers import agents, chat, knowledge, models, tasks
from app.routers import mcp as mcp_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await create_tables()
    # Bootstrap MongoDB vector search indexes (best-effort)
    from app.services.knowledge_service import ensure_vector_index
    from app.services.memory_service import ensure_memory_index
    import asyncio
    asyncio.create_task(ensure_vector_index())
    asyncio.create_task(ensure_memory_index())
    yield
    # Shutdown (nothing needed)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Gema — AI automation platform. "
        "Connect to 30+ AI models, build agents, manage knowledge bases, and automate tasks."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(models.router)
app.include_router(chat.router)
app.include_router(agents.router)
app.include_router(knowledge.router)
app.include_router(tasks.router)
app.include_router(mcp_router.router)


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


@app.get("/api/stats", tags=["system"])
async def stats():
    """Quick summary counts for the dashboard."""
    from sqlalchemy import func, select
    from app.database import AsyncSessionLocal
    from app.models.agent import Agent
    from app.models.conversation import Conversation, Message
    from app.models.knowledge_base import Document, KnowledgeBase
    from app.models.task import Task
    from app.services.model_catalog import get_models

    async with AsyncSessionLocal() as db:
        agents_count = (await db.execute(select(func.count()).select_from(Agent))).scalar()
        convs_count = (await db.execute(select(func.count()).select_from(Conversation))).scalar()
        msgs_count = (await db.execute(select(func.count()).select_from(Message))).scalar()
        kbs_count = (await db.execute(select(func.count()).select_from(KnowledgeBase))).scalar()
        docs_count = (await db.execute(select(func.count()).select_from(Document))).scalar()
        tasks_count = (await db.execute(select(func.count()).select_from(Task))).scalar()
        tasks_done = (
            await db.execute(select(func.count()).select_from(Task).where(Task.status == "completed"))
        ).scalar()

    available_models = sum(1 for m in await get_models() if m.get("available"))

    return {
        "agents": agents_count,
        "conversations": convs_count,
        "messages": msgs_count,
        "knowledge_bases": kbs_count,
        "documents": docs_count,
        "tasks": tasks_count,
        "tasks_completed": tasks_done,
        "available_models": available_models,
    }
