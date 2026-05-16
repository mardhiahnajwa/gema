"""
settings_service.py

Reads and writes app settings (API keys, etc.) stored in the `app_settings`
PostgreSQL table. On write the value is also applied to os.environ so litellm
and other libraries pick it up immediately without a restart.
"""

import os
from typing import Dict

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.setting import AppSetting

# Map of setting key → environment variable name
_KEY_TO_ENV: Dict[str, str] = {
    "OPENAI_API_KEY": "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY": "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY": "GEMINI_API_KEY",
    "MISTRAL_API_KEY": "MISTRAL_API_KEY",
    "COHERE_API_KEY": "COHERE_API_KEY",
    "GROQ_API_KEY": "GROQ_API_KEY",
    "TOGETHER_API_KEY": "TOGETHERAI_API_KEY",
    "HUGGINGFACE_API_KEY": "HUGGINGFACE_API_KEY",
    "AZURE_OPENAI_API_KEY": "AZURE_API_KEY",
    "AZURE_OPENAI_ENDPOINT": "AZURE_API_BASE",
    "AZURE_OPENAI_DEPLOYMENT": "AZURE_OPENAI_DEPLOYMENT",
}

# All keys exposed in the UI (ordered for display)
ALL_KEYS = list(_KEY_TO_ENV.keys())


def _apply_to_env(key: str, value: str | None) -> None:
    """Push a setting value into the process environment so litellm picks it up."""
    env_var = _KEY_TO_ENV.get(key)
    if not env_var:
        return
    if value:
        os.environ[env_var] = value
    else:
        os.environ.pop(env_var, None)


def mask_value(value: str | None) -> str:
    """Return a masked version: first 4 + *** + last 4 chars."""
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]


# ── Async (FastAPI routes) ────────────────────────────────────────────────────

async def load_settings_from_db(db: AsyncSession) -> Dict[str, str | None]:
    """Return all settings as {key: value} dict (raw values, not masked)."""
    result = await db.execute(select(AppSetting))
    rows = result.scalars().all()
    return {r.key: r.value for r in rows}


async def apply_all_settings_to_env(db: AsyncSession) -> None:
    """Called at startup — push all DB settings into os.environ."""
    settings = await load_settings_from_db(db)
    for key, value in settings.items():
        _apply_to_env(key, value)


async def upsert_settings(db: AsyncSession, updates: Dict[str, str | None]) -> None:
    """Save a dict of {key: value} to the DB and apply to env."""
    for key, value in updates.items():
        if key not in ALL_KEYS:
            continue
        existing = await db.get(AppSetting, key)
        if existing is None:
            db.add(AppSetting(key=key, value=value or None))
        else:
            existing.value = value or None
        _apply_to_env(key, value)
    await db.commit()


# ── Sync (Celery tasks) ────────────────────────────────────────────────────────

def load_settings_sync(db: Session) -> Dict[str, str | None]:
    rows = db.query(AppSetting).all()
    return {r.key: r.value for r in rows}


def apply_all_settings_to_env_sync(db: Session) -> None:
    settings = load_settings_sync(db)
    for key, value in settings.items():
        _apply_to_env(key, value)
