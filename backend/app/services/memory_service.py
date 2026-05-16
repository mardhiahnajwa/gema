"""
Agent memory service — short-term and long-term memory.

Short-term  : the recent N messages of the current conversation (already in
              the messages table; we pull the last SHORT_TERM_TURNS turns and
              inject them so the LLM always has fresh context even if the
              frontend doesn't send the full history).

Long-term   : key facts/summaries extracted from past conversations and stored
              as vector-embedded documents in MongoDB.  On every new message the
              top-K most relevant long-term memories are injected into the
              system prompt so the agent "remembers" across sessions.
"""

import asyncio
import re
from datetime import datetime
from typing import List, Optional

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings

# MongoDB collection for memory documents
_MEMORY_COLLECTION = "agent_memories"

# How many recent turns to surface as short-term context
SHORT_TERM_TURNS = 6  # last N user+assistant pairs = 2N messages

# How many long-term memories to inject per request
LONG_TERM_TOP_K = 4


# ── MongoDB helpers ────────────────────────────────────────────────────────────

def _get_memory_col():
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB]
    return db[_MEMORY_COLLECTION]


def _embed(texts: List[str]) -> List[List[float]]:
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(settings.EMBEDDING_MODEL)
    return model.encode(texts, normalize_embeddings=True).tolist()


# ── Index bootstrap ────────────────────────────────────────────────────────────

async def ensure_memory_index() -> None:
    """Create the vector search index for memories if it doesn't exist."""
    col = _get_memory_col()
    try:
        existing = [idx async for idx in col.list_search_indexes()]
        names = {idx.get("name") for idx in existing}
        if "memory_vector_index" not in names:
            index_def = {
                "name": "memory_vector_index",
                "type": "vectorSearch",
                "definition": {
                    "fields": [
                        {
                            "type": "vector",
                            "path": "embedding",
                            "numDimensions": settings.EMBEDDING_DIMENSIONS,
                            "similarity": "cosine",
                        }
                    ]
                },
            }
            await col.create_search_index(index_def)
    except Exception:
        pass  # index creation is best-effort; atlas local may need a moment


# ── Short-term memory ─────────────────────────────────────────────────────────

async def get_short_term_context(
    conversation_id: str,
    db,  # AsyncSession — imported lazily to avoid circular imports
) -> List[dict]:
    """
    Return the last SHORT_TERM_TURNS * 2 messages from the conversation as a
    list of {"role": ..., "content": ...} dicts, oldest-first.
    Returns an empty list if conversation_id is None or no messages exist.
    """
    if not conversation_id:
        return []
    try:
        import uuid as _uuid
        from sqlalchemy import select
        from app.models.conversation import Message

        conv_uuid = _uuid.UUID(str(conversation_id))
        res = await db.execute(
            select(Message)
            .where(Message.conversation_id == conv_uuid)
            .order_by(Message.created_at.desc())
            .limit(SHORT_TERM_TURNS * 2)
        )
        msgs = res.scalars().all()
        # Reverse so they're chronological (oldest first)
        return [
            {"role": m.role, "content": m.content}
            for m in reversed(msgs)
        ]
    except Exception:
        return []


# ── Long-term memory ──────────────────────────────────────────────────────────

async def retrieve_long_term_memories(
    agent_id: str,
    user_id: str,
    query: str,
) -> List[str]:
    """
    Vector-search the memory store for facts relevant to `query`.
    Returns a list of plain-text memory strings.
    """
    if not agent_id or not query:
        return []
    try:
        q_vec = await asyncio.to_thread(_embed, [query])
        q_vec = q_vec[0]

        col = _get_memory_col()
        # Filter by agent_id; also filter by user_id when provided
        filter_doc: dict = {"agent_id": agent_id}
        if user_id:
            filter_doc["user_id"] = user_id

        pipeline = [
            {
                "$vectorSearch": {
                    "index": "memory_vector_index",
                    "path": "embedding",
                    "queryVector": q_vec,
                    "numCandidates": LONG_TERM_TOP_K * 10,
                    "limit": LONG_TERM_TOP_K,
                    "filter": filter_doc,
                }
            },
            {"$project": {"_id": 0, "fact": 1, "score": {"$meta": "vectorSearchScore"}}},
        ]
        memories = []
        async for doc in col.aggregate(pipeline):
            if doc.get("score", 0) > 0.4:  # relevance threshold
                memories.append(doc["fact"])
        return memories
    except Exception:
        return []


async def store_long_term_memory(
    agent_id: str,
    user_id: str,
    conversation_id: str,
    user_message: str,
    assistant_message: str,
) -> None:
    """
    Extract and store memorable facts from a user↔assistant exchange.
    Uses simple heuristics; can be upgraded to an LLM-based extractor.
    """
    if not agent_id:
        return
    try:
        facts = _extract_facts(user_message, assistant_message)
        if not facts:
            return

        embeddings = await asyncio.to_thread(_embed, facts)
        col = _get_memory_col()
        docs = []
        for fact, emb in zip(facts, embeddings):
            docs.append(
                {
                    "agent_id": agent_id,
                    "user_id": user_id or "",
                    "conversation_id": conversation_id or "",
                    "fact": fact,
                    "embedding": emb,
                    "created_at": datetime.utcnow().isoformat(),
                }
            )
        if docs:
            await col.insert_many(docs)
    except Exception:
        pass  # memory storage is best-effort; never fail a chat


def _extract_facts(user_msg: str, assistant_msg: str) -> List[str]:
    """
    Lightweight rule-based extractor.  Pulls sentences from the assistant reply
    that contain concrete, memorable information (names, dates, preferences,
    decisions, numbers).  Returns at most 3 facts per turn.
    """
    sentences = re.split(r"(?<=[.!?])\s+", assistant_msg.strip())
    # Keep sentences that look factual (contain nouns / digits / proper nouns)
    fact_patterns = [
        r"\b(is|are|was|were|will be|prefers?|likes?|wants?|needs?|uses?|decided|agreed)\b",
        r"\b\d+\b",                          # any number
        r"[A-Z][a-z]+ [A-Z][a-z]+",          # Proper Name
        r"\b(always|never|usually|often)\b",
    ]
    combined = "|".join(fact_patterns)
    facts = [s.strip() for s in sentences if re.search(combined, s) and len(s) > 20][:3]

    # Also store the user's explicit statements about themselves
    user_sentences = re.split(r"(?<=[.!?])\s+", user_msg.strip())
    first_person = [
        s.strip()
        for s in user_sentences
        if re.search(r"\b(I am|I'm|my name|I prefer|I like|I want|I need|I use|I decided)\b", s, re.I)
        and len(s) > 10
    ][:2]

    return facts + first_person


# ── Build memory context string ────────────────────────────────────────────────

async def build_memory_context(
    agent_id: Optional[str],
    user_id: Optional[str],
    conversation_id: Optional[str],
    query: str,
    db,
) -> tuple[List[dict], str]:
    """
    Returns (short_term_messages, long_term_system_block).

    short_term_messages : list of message dicts to prepend after the system prompt
    long_term_system_block : extra text to append to the system prompt
    """
    short_term = await get_short_term_context(conversation_id, db)

    long_term_block = ""
    if agent_id:
        memories = await retrieve_long_term_memories(
            agent_id=agent_id,
            user_id=user_id or conversation_id or "",
            query=query,
        )
        if memories:
            formatted = "\n".join(f"- {m}" for m in memories)
            long_term_block = (
                f"\n\n## Long-Term Memory (what you know about this user/context)\n"
                f"{formatted}\n"
                "Draw on this when relevant, but don't repeat it verbatim."
            )

    return short_term, long_term_block
