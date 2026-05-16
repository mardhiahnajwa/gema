import json
import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.agent import Agent
from app.models.conversation import Conversation, Message
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationCreate,
    ConversationResponse,
    MessageResponse,
)
from app.models.mcp_server import MCPServer
from app.services.ai_service import (
    chat_completion,
    run_tool_loop,
    stream_chat_completion,
)
from app.services.knowledge_service import query_knowledge_bases
from app.services.memory_service import build_memory_context, store_long_term_memory
from app.services.mcp_service import get_tools_for_servers

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _build_messages(
    messages: list,
    system_prompt: str,
    kb_ids: List[str],
    short_term_history: list = None,
    long_term_block: str = "",
) -> list:
    """Prepend system prompt (with memory + RAG context) and inject short-term history."""
    final: list = []

    if kb_ids:
        user_text = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        if user_text:
            results = await query_knowledge_bases(kb_ids, user_text, n_results=5)
            if results:
                context = "\n\n".join(
                    f"[Source {i+1}]: {r['content']}" for i, r in enumerate(results)
                )
                system_prompt = (
                    f"{system_prompt}\n\n"
                    f"## Relevant Knowledge Base Context\n{context}\n\n"
                    "Use the context above when answering the user's question."
                )

    # Append long-term memory block to system prompt
    if long_term_block:
        system_prompt = system_prompt + long_term_block

    if system_prompt:
        final.append({"role": "system", "content": system_prompt})

    # Inject short-term history (DB messages) before the current request messages,
    # deduplicating against messages the frontend already sent.
    if short_term_history:
        # Avoid duplicating messages the caller already included
        existing_set = {(m["role"], m["content"]) for m in messages}
        for m in short_term_history:
            if (m["role"], m["content"]) not in existing_set:
                final.append(m)

    final.extend(messages)
    return final


async def _save_pair(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    user_content: str,
    assistant_content: str,
    model: str,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> None:
    """Persist a user+assistant message pair and bump conversation updated_at."""
    db.add(
        Message(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            role="user",
            content=user_content,
            model=model,
            prompt_tokens=prompt_tokens,
        )
    )
    db.add(
        Message(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            role="assistant",
            content=assistant_content,
            model=model,
            completion_tokens=completion_tokens,
        )
    )
    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(updated_at=datetime.utcnow())
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/completions")
async def chat_completions(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """Send a chat completion request. Supports streaming via SSE."""
    system_prompt = ""
    kb_ids = request.knowledge_base_ids or []
    model = request.model
    temperature = request.temperature
    max_tokens = request.max_tokens or 4096

    # Load agent overrides
    agent = None
    if request.agent_id:
        res = await db.execute(select(Agent).where(Agent.id == request.agent_id))
        agent = res.scalar_one_or_none()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        system_prompt = agent.system_prompt
        model = agent.model
        temperature = agent.temperature
        max_tokens = agent.max_tokens
        kb_ids = agent.knowledge_base_ids or kb_ids

    # Collect MCP server IDs from agent + request (union, deduplicated)
    mcp_ids_raw: List[str] = list(
        dict.fromkeys(
            (agent.mcp_server_ids if agent else []) +
            (request.mcp_server_ids or [])
        )
    )

    # Load active MCP servers for tool calling
    mcp_servers = []
    if mcp_ids_raw:
        import uuid as _uuid
        id_list = [_uuid.UUID(i) for i in mcp_ids_raw]
        srv_res = await db.execute(
            select(MCPServer).where(
                MCPServer.id.in_(id_list), MCPServer.is_active == True  # noqa: E712
            )
        )
        mcp_servers = srv_res.scalars().all()

    raw_messages = [m.model_dump() for m in request.messages]

    # ── Memory context ────────────────────────────────────────────────
    agent_id_str = str(request.agent_id) if request.agent_id else (str(agent.id) if agent else None)
    user_id_str = request.user_id or (str(request.conversation_id) if request.conversation_id else None)
    conv_id_str = str(request.conversation_id) if request.conversation_id else None
    user_query = next((m["content"] for m in reversed(raw_messages) if m["role"] == "user"), "")

    short_term_history, long_term_block = await build_memory_context(
        agent_id=agent_id_str,
        user_id=user_id_str,
        conversation_id=conv_id_str,
        query=user_query,
        db=db,
    )

    final_messages = await _build_messages(
        raw_messages, system_prompt, kb_ids,
        short_term_history=short_term_history,
        long_term_block=long_term_block,
    )
    user_content = user_query  # already computed above

    # Resolve MCP tools (empty list = no tool calling)
    mcp_tools, tool_registry = [], {}
    if mcp_servers:
        mcp_tools, tool_registry = await get_tools_for_servers(mcp_servers)

    # ── Streaming ─────────────────────────────────────────────────────
    if request.stream:
        async def _generate():
            full = ""

            if mcp_tools:
                # Run the tool loop (non-streaming), then emit the final answer
                final_resp = await run_tool_loop(
                    model, final_messages, temperature, max_tokens,
                    mcp_tools, tool_registry,
                )
                final_content = final_resp.choices[0].message.content or ""
                full = final_content
                yield f"data: {json.dumps({'content': final_content})}\n\n"
            else:
                async for chunk in stream_chat_completion(model, final_messages, temperature, max_tokens):
                    full += chunk
                    yield f"data: {json.dumps({'content': chunk})}\n\n"

            if request.conversation_id:
                async with db.begin_nested():
                    await _save_pair(db, request.conversation_id, user_content, full, model)

            # Fire-and-forget long-term memory extraction
            if agent_id_str and user_query and full:
                import asyncio as _asyncio
                _asyncio.create_task(store_long_term_memory(
                    agent_id=agent_id_str,
                    user_id=user_id_str or "",
                    conversation_id=conv_id_str or "",
                    user_message=user_query,
                    assistant_message=full,
                ))

            yield "data: [DONE]\n\n"

        return StreamingResponse(_generate(), media_type="text/event-stream")

    # ── Non-streaming ─────────────────────────────────────────────────
    if mcp_tools:
        resp = await run_tool_loop(
            model, final_messages, temperature, max_tokens,
            mcp_tools, tool_registry,
        )
    else:
        resp = await chat_completion(model, final_messages, temperature, max_tokens)

    content = resp.choices[0].message.content
    usage = resp.usage

    if request.conversation_id:
        await _save_pair(
            db,
            request.conversation_id,
            user_content,
            content,
            model,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
        )

    # Fire-and-forget long-term memory extraction
    if agent_id_str and user_query and content:
        import asyncio as _asyncio
        _asyncio.create_task(store_long_term_memory(
            agent_id=agent_id_str,
            user_id=user_id_str or "",
            conversation_id=conv_id_str or "",
            user_message=user_query,
            assistant_message=content,
        ))

    return ChatResponse(
        id=resp.id,
        model=resp.model,
        content=content,
        prompt_tokens=usage.prompt_tokens if usage else None,
        completion_tokens=usage.completion_tokens if usage else None,
        conversation_id=request.conversation_id,
    )


# ── Conversations ─────────────────────────────────────────────────────────────

@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    request: ConversationCreate,
    db: AsyncSession = Depends(get_db),
):
    conv = Conversation(
        id=uuid.uuid4(),
        title=request.title,
        agent_id=request.agent_id,
        model=request.model,
    )
    db.add(conv)
    await db.flush()
    await db.refresh(conv)
    return conv


@router.get("/conversations", response_model=List[ConversationResponse])
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    res = await db.execute(
        select(Conversation)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return res.scalars().all()


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(conversation_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conv = res.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.get("/conversations/{conversation_id}/messages", response_model=List[MessageResponse])
async def get_messages(conversation_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return res.scalars().all()


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conv = res.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await db.delete(conv)
    return {"message": "Conversation deleted"}
