import asyncio
from pathlib import Path
from typing import Any, Dict, List

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings

# Collection name inside the "gema" database
_COLLECTION = "chunks"


def _get_collection():
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB]
    return db[_COLLECTION]


def _embed(texts: List[str]) -> List[List[float]]:
    """Generate embeddings using sentence-transformers (CPU-friendly)."""
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(settings.EMBEDDING_MODEL)
    return model.encode(texts, normalize_embeddings=True).tolist()


# ── Text extraction ────────────────────────────────────────────────────────────

async def extract_text(file_path: str, file_type: str) -> str:
    """Extract plain text from various file types."""
    path = Path(file_path)

    if file_type in {"txt", "md", "csv", "json", "yaml", "yml", "rst"}:
        return path.read_text(encoding="utf-8", errors="ignore")

    if file_type == "pdf":
        import PyPDF2

        def _read_pdf() -> str:
            text = ""
            with open(path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
            return text

        return await asyncio.to_thread(_read_pdf)

    if file_type in {"docx", "doc"}:
        from docx import Document

        def _read_docx() -> str:
            doc = Document(path)
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

        return await asyncio.to_thread(_read_docx)

    # Fallback — attempt to read as UTF-8 text
    return path.read_text(encoding="utf-8", errors="ignore")


# ── Chunking ───────────────────────────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """Split text into overlapping chunks."""
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return [c for c in chunks if c.strip()]


# ── Ensure vector search index exists ─────────────────────────────────────────

async def ensure_vector_index() -> None:
    """Create the Atlas vector search index if it doesn't exist yet."""
    col = _get_collection()
    existing = [idx async for idx in col.list_search_indexes()]
    names = {idx.get("name") for idx in existing}
    if "vector_index" not in names:
        index_def = {
            "name": "vector_index",
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


# ── Document processing ───────────────────────────────────────────────────────

async def process_document(
    kb_id: str,
    doc_id: str,
    file_path: str,
    file_type: str,
) -> int:
    """Extract, chunk, embed and index a document. Returns the number of chunks created."""
    text = await extract_text(file_path, file_type)
    chunks = chunk_text(text)
    if not chunks:
        return 0

    embeddings = await asyncio.to_thread(_embed, chunks)

    col = _get_collection()
    docs = [
        {
            "_id": f"{doc_id}_{i}",
            "kb_id": kb_id,
            "doc_id": doc_id,
            "chunk_index": i,
            "text": chunk,
            "embedding": emb,
        }
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]

    # Upsert in batches of 100
    batch = 100
    for i in range(0, len(docs), batch):
        ops = [
            {
                "replaceOne": {
                    "filter": {"_id": d["_id"]},
                    "replacement": d,
                    "upsert": True,
                }
            }
            for d in docs[i : i + batch]
        ]
        await col.bulk_write(ops)

    return len(chunks)


# ── Query ─────────────────────────────────────────────────────────────────────

async def query_knowledge_bases(
    knowledge_base_ids: List[str],
    query: str,
    n_results: int = 5,
) -> List[Dict[str, Any]]:
    """Query knowledge bases using MongoDB $vectorSearch and return ranked results."""
    query_embedding = await asyncio.to_thread(_embed, [query])
    q_vec = query_embedding[0]

    col = _get_collection()
    all_results: List[Dict[str, Any]] = []

    for kb_id in knowledge_base_ids:
        try:
            pipeline = [
                {
                    "$vectorSearch": {
                        "index": "vector_index",
                        "path": "embedding",
                        "queryVector": q_vec,
                        "numCandidates": n_results * 10,
                        "limit": n_results,
                        "filter": {"kb_id": kb_id},
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "text": 1,
                        "doc_id": 1,
                        "score": {"$meta": "vectorSearchScore"},
                    }
                },
            ]
            async for doc in col.aggregate(pipeline):
                all_results.append(
                    {
                        "content": doc["text"],
                        "score": float(doc.get("score", 0)),
                        "kb_id": kb_id,
                        "doc_id": doc.get("doc_id", ""),
                    }
                )
        except Exception:
            continue

    all_results.sort(key=lambda x: x["score"], reverse=True)
    return all_results[:n_results]


# ── Deletion ──────────────────────────────────────────────────────────────────

async def delete_knowledge_base_collection(kb_id: str) -> None:
    try:
        col = _get_collection()
        await col.delete_many({"kb_id": kb_id})
    except Exception:
        pass


async def delete_document_chunks(kb_id: str, doc_id: str) -> None:
    try:
        col = _get_collection()
        await col.delete_many({"kb_id": kb_id, "doc_id": doc_id})
    except Exception:
        pass
