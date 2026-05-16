"""
Dynamic model catalog for Gema.

For each configured provider, this module calls the provider's live /models
API endpoint to get the current model list. Results are cached in Redis (TTL
1 hour) so we don't hammer the APIs on every request.

The only "hardcoded" part is KNOWN_META — a lookup table for context-window
sizes, vision support, and category. Providers don't expose these fields in
their model-list APIs, so we enrich from the table and fall back to
heuristics for unknown/new models.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional

import httpx
import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

CACHE_KEY = "gema:model_catalog:v1"
CACHE_TTL = 3600  # seconds (1 hour)

# ── Metadata enrichment ────────────────────────────────────────────────────────
# ctx   = context window in tokens
# vision = accepts image input
# category = text | code | reasoning
KNOWN_META: Dict[str, Dict[str, Any]] = {
    # ── OpenAI ────────────────────────────────────────────────────────────
    "gpt-4o":                         {"ctx": 128_000,  "vision": True,  "category": "text"},
    "gpt-4o-mini":                    {"ctx": 128_000,  "vision": True,  "category": "text"},
    "gpt-4-turbo":                    {"ctx": 128_000,  "vision": True,  "category": "text"},
    "gpt-4-turbo-preview":            {"ctx": 128_000,  "vision": False, "category": "text"},
    "gpt-4":                          {"ctx": 8_192,    "vision": False, "category": "text"},
    "gpt-3.5-turbo":                  {"ctx": 16_385,   "vision": False, "category": "text"},
    "gpt-3.5-turbo-16k":              {"ctx": 16_385,   "vision": False, "category": "text"},
    "o1":                             {"ctx": 200_000,  "vision": True,  "category": "reasoning"},
    "o1-mini":                        {"ctx": 128_000,  "vision": False, "category": "reasoning"},
    "o1-preview":                     {"ctx": 128_000,  "vision": False, "category": "reasoning"},
    "o3":                             {"ctx": 200_000,  "vision": True,  "category": "reasoning"},
    "o3-mini":                        {"ctx": 200_000,  "vision": False, "category": "reasoning"},
    "o4-mini":                        {"ctx": 200_000,  "vision": True,  "category": "reasoning"},
    # ── Anthropic ─────────────────────────────────────────────────────────
    "claude-opus-4-5":                {"ctx": 200_000,  "vision": True,  "category": "text"},
    "claude-sonnet-4-5":              {"ctx": 200_000,  "vision": True,  "category": "text"},
    "claude-3-5-sonnet-20241022":     {"ctx": 200_000,  "vision": True,  "category": "text"},
    "claude-3-5-haiku-20241022":      {"ctx": 200_000,  "vision": True,  "category": "text"},
    "claude-3-opus-20240229":         {"ctx": 200_000,  "vision": True,  "category": "text"},
    "claude-3-sonnet-20240229":       {"ctx": 200_000,  "vision": True,  "category": "text"},
    "claude-3-haiku-20240307":        {"ctx": 200_000,  "vision": True,  "category": "text"},
    # ── Google ────────────────────────────────────────────────────────────
    "gemini-2.5-pro":                 {"ctx": 1_048_576,"vision": True,  "category": "reasoning"},
    "gemini-2.5-flash":               {"ctx": 1_048_576,"vision": True,  "category": "reasoning"},
    "gemini-2.0-flash":               {"ctx": 1_048_576,"vision": True,  "category": "text"},
    "gemini-2.0-flash-exp":           {"ctx": 1_048_576,"vision": True,  "category": "text"},
    "gemini-1.5-pro":                 {"ctx": 2_097_152,"vision": True,  "category": "text"},
    "gemini-1.5-flash":               {"ctx": 1_048_576,"vision": True,  "category": "text"},
    "gemini-1.5-flash-8b":            {"ctx": 1_048_576,"vision": True,  "category": "text"},
    # ── Mistral ───────────────────────────────────────────────────────────
    "mistral-large-latest":           {"ctx": 131_072,  "vision": False, "category": "text"},
    "mistral-medium-latest":          {"ctx": 131_072,  "vision": False, "category": "text"},
    "mistral-small-latest":           {"ctx": 131_072,  "vision": False, "category": "text"},
    "mistral-tiny-latest":            {"ctx": 32_768,   "vision": False, "category": "text"},
    "codestral-latest":               {"ctx": 32_768,   "vision": False, "category": "code"},
    "pixtral-large-latest":           {"ctx": 131_072,  "vision": True,  "category": "text"},
    "pixtral-12b-2409":               {"ctx": 131_072,  "vision": True,  "category": "text"},
    # ── Groq ──────────────────────────────────────────────────────────────
    "llama-3.3-70b-versatile":        {"ctx": 128_000,  "vision": False, "category": "text"},
    "llama-3.1-8b-instant":           {"ctx": 131_072,  "vision": False, "category": "text"},
    "llama-3.2-90b-vision-preview":   {"ctx": 8_192,    "vision": True,  "category": "text"},
    "llama-3.2-11b-vision-preview":   {"ctx": 8_192,    "vision": True,  "category": "text"},
    "mixtral-8x7b-32768":             {"ctx": 32_768,   "vision": False, "category": "text"},
    "gemma2-9b-it":                   {"ctx": 8_192,    "vision": False, "category": "text"},
    "deepseek-r1-distill-llama-70b":  {"ctx": 128_000,  "vision": False, "category": "reasoning"},
    # ── Cohere ────────────────────────────────────────────────────────────
    "command-r-plus":                 {"ctx": 128_000,  "vision": False, "category": "text"},
    "command-r":                      {"ctx": 128_000,  "vision": False, "category": "text"},
    "command-a-03-2025":              {"ctx": 256_000,  "vision": False, "category": "text"},
    "command":                        {"ctx": 4_096,    "vision": False, "category": "text"},
}

# ── Inference helpers ──────────────────────────────────────────────────────────

def _enrich(model_id: str, bare_id: str, provided_ctx: Optional[int] = None) -> Dict[str, Any]:
    """
    Return ctx / vision / category for a model.
    Priority: KNOWN_META exact → KNOWN_META bare_id → heuristics.
    """
    meta = KNOWN_META.get(model_id) or KNOWN_META.get(bare_id) or {}
    lower = (model_id + bare_id).lower()

    category = meta.get("category") or (
        "reasoning" if any(k in lower for k in ("o1", "o3", "o4", "r1", "reason", "think")) else
        "code"      if any(k in lower for k in ("code", "coder", "codestral"))              else
        "text"
    )
    vision = meta.get("vision", any(
        k in lower for k in ("vision", "pixtral", "llava", "4o", "claude-3", "gemini", "llava")
    ))
    ctx = provided_ctx or meta.get("ctx", 8_192)
    return {"ctx": ctx, "vision": vision, "category": category}


# ── Static provider: Anthropic (no public models endpoint) ────────────────────
# Anthropic releases very few models; this short list is the only static part.
ANTHROPIC_MODELS = [
    ("claude-opus-4-5",          "Claude Opus 4.5"),
    ("claude-sonnet-4-5",        "Claude Sonnet 4.5"),
    ("claude-3-5-sonnet-20241022","Claude 3.5 Sonnet"),
    ("claude-3-5-haiku-20241022", "Claude 3.5 Haiku"),
    ("claude-3-opus-20240229",    "Claude 3 Opus"),
    ("claude-3-haiku-20240307",   "Claude 3 Haiku"),
]

# ── HuggingFace static fallback ───────────────────────────────────────────────
# HF has tens of thousands of models — listing all is impractical.
# We expose a small curated set; users can override via the model ID field.
HUGGINGFACE_MODELS = [
    ("huggingface/meta-llama/Llama-3.1-70B-Instruct", "Llama 3.1 70B (HF)"),
    ("huggingface/mistralai/Mistral-7B-Instruct-v0.3",  "Mistral 7B v0.3 (HF)"),
    ("huggingface/google/gemma-2-27b-it",               "Gemma 2 27B (HF)"),
]


# ── Redis helper ──────────────────────────────────────────────────────────────

async def _get_redis() -> Optional[aioredis.Redis]:
    try:
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await r.ping()
        return r
    except Exception as exc:
        logger.warning("Redis unavailable for model catalog cache: %s", exc)
        return None


# ── Individual provider fetchers ───────────────────────────────────────────────

async def _fetch_openai(key: str) -> List[Dict]:
    SKIP = ("tts", "whisper", "dall-e", "text-embedding", "babbage",
            "davinci", "ada", "curie", "embedding", "moderation")
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        r.raise_for_status()
    out = []
    for m in r.json().get("data", []):
        mid = m.get("id", "")
        if m.get("object") != "model" or any(mid.startswith(p) or p in mid for p in SKIP):
            continue
        out.append({"id": mid, "name": mid, "provider": "openai",
                    **_enrich(mid, mid)})
    return out


async def _fetch_anthropic(key: str) -> List[Dict]:
    # No public endpoint — return curated static list (key is validated implicitly on first chat call)
    return [
        {"id": mid, "name": name, "provider": "anthropic", **_enrich(mid, mid)}
        for mid, name in ANTHROPIC_MODELS
    ]


async def _fetch_google(key: str) -> List[Dict]:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": key},
        )
        r.raise_for_status()
    out = []
    for m in r.json().get("models", []):
        if "generateContent" not in m.get("supportedGenerationMethods", []):
            continue
        bare = m["name"].replace("models/", "")     # e.g. gemini-1.5-pro
        litellm_id = f"gemini/{bare}"
        display = m.get("displayName") or bare
        ctx = m.get("inputTokenLimit") or None
        out.append({"id": litellm_id, "name": display, "provider": "google",
                    **_enrich(litellm_id, bare, provided_ctx=ctx)})
    return out


async def _fetch_mistral(key: str) -> List[Dict]:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            "https://api.mistral.ai/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        r.raise_for_status()
    out = []
    for m in r.json().get("data", []):
        mid = m.get("id", "")
        if "embed" in mid:
            continue
        litellm_id = f"mistral/{mid}"
        out.append({"id": litellm_id, "name": m.get("name") or mid,
                    "provider": "mistral", **_enrich(litellm_id, mid)})
    return out


async def _fetch_groq(key: str) -> List[Dict]:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        r.raise_for_status()
    out = []
    for m in r.json().get("data", []):
        mid = m.get("id", "")
        if m.get("object") != "model":
            continue
        ctx = m.get("context_window") or None
        litellm_id = f"groq/{mid}"
        out.append({"id": litellm_id, "name": mid, "provider": "groq",
                    **_enrich(litellm_id, mid, provided_ctx=ctx)})
    return out


async def _fetch_cohere(key: str) -> List[Dict]:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            "https://api.cohere.ai/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        r.raise_for_status()
    out = []
    for m in r.json().get("models", []):
        mid = m.get("name", "")
        if "chat" not in m.get("endpoints", []):
            continue
        ctx = m.get("context_length") or None
        out.append({"id": mid, "name": mid, "provider": "cohere",
                    **_enrich(mid, mid, provided_ctx=ctx)})
    return out


async def _fetch_together(key: str) -> List[Dict]:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            "https://api.together.xyz/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        return []
    out = []
    for m in data:
        if m.get("type") not in ("chat", "language"):
            continue
        base_id = m.get("id", "")
        ctx = m.get("context_length") or None
        display = m.get("display_name") or base_id.split("/")[-1]
        litellm_id = f"together_ai/{base_id}"
        out.append({"id": litellm_id, "name": display, "provider": "together",
                    **_enrich(litellm_id, base_id, provided_ctx=ctx)})
    return out


async def _fetch_huggingface(key: str) -> List[Dict]:
    return [
        {"id": mid, "name": name, "provider": "huggingface", **_enrich(mid, mid)}
        for mid, name in HUGGINGFACE_MODELS
    ]


# ── Provider registry ─────────────────────────────────────────────────────────
# Maps provider_id → (settings_key_attr, fetcher_coroutine)
PROVIDERS: Dict[str, tuple] = {
    "openai":      ("OPENAI_API_KEY",      _fetch_openai),
    "anthropic":   ("ANTHROPIC_API_KEY",   _fetch_anthropic),
    "google":      ("GOOGLE_API_KEY",      _fetch_google),
    "mistral":     ("MISTRAL_API_KEY",     _fetch_mistral),
    "groq":        ("GROQ_API_KEY",        _fetch_groq),
    "cohere":      ("COHERE_API_KEY",      _fetch_cohere),
    "together":    ("TOGETHER_API_KEY",    _fetch_together),
    "huggingface": ("HUGGINGFACE_API_KEY", _fetch_huggingface),
}

# Human-friendly display names for each provider
PROVIDER_NAMES: Dict[str, str] = {
    "openai":      "OpenAI",
    "anthropic":   "Anthropic",
    "google":      "Google AI",
    "mistral":     "Mistral",
    "groq":        "Groq",
    "cohere":      "Cohere",
    "together":    "Together AI",
    "huggingface": "HuggingFace",
}


# ── Core public API ───────────────────────────────────────────────────────────

async def _fetch_one(provider_id: str, key_attr: str, fetcher) -> List[Dict]:
    """Fetch models for a single provider; returns [] on error."""
    key = getattr(settings, key_attr, None)
    if not key:
        return []
    try:
        models = await fetcher(key)
        for m in models:
            m["available"] = True
        logger.info("[catalog] %s → %d models", provider_id, len(models))
        return models
    except Exception as exc:
        logger.warning("[catalog] %s fetch failed: %s", provider_id, exc)
        return []


async def fetch_all_models() -> List[Dict]:
    """Fetch live model lists from all configured providers in parallel."""
    results = await asyncio.gather(*[
        _fetch_one(pid, key_attr, fetcher)
        for pid, (key_attr, fetcher) in PROVIDERS.items()
    ])
    return [m for batch in results for m in batch]


async def get_models(force_refresh: bool = False) -> List[Dict]:
    """
    Return the live model catalog.
    - Cache hit  → return Redis-cached list (TTL 1 h).
    - Cache miss → fetch from all providers, cache result, return.
    - If Redis is down → fetch fresh every time (graceful degradation).
    """
    redis = await _get_redis()
    if redis and not force_refresh:
        try:
            cached = await redis.get(CACHE_KEY)
            if cached:
                await redis.aclose()
                return json.loads(cached)
        except Exception:
            pass

    models = await fetch_all_models()

    if redis:
        try:
            await redis.setex(CACHE_KEY, CACHE_TTL, json.dumps(models))
        except Exception as exc:
            logger.warning("[catalog] cache write failed: %s", exc)
        await redis.aclose()

    return models


def get_providers_status() -> List[Dict]:
    """Return all providers with their configured/available status."""
    return [
        {
            "id": pid,
            "name": PROVIDER_NAMES.get(pid, pid.title()),
            "configured": bool(getattr(settings, key_attr, None)),
            "key_env_var": key_attr,
        }
        for pid, (key_attr, _) in PROVIDERS.items()
    ]
