from typing import Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.settings_service import (
    ALL_KEYS,
    load_settings_from_db,
    mask_value,
    upsert_settings,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingEntry(BaseModel):
    key: str
    masked_value: str  # shown to frontend — never the raw key
    is_set: bool


class SettingsResponse(BaseModel):
    settings: List[SettingEntry]


class SettingsUpdate(BaseModel):
    # Map of key → plain-text value (empty string = clear the key)
    updates: Dict[str, Optional[str]]


@router.get("/", response_model=SettingsResponse)
async def get_settings(db: AsyncSession = Depends(get_db)):
    stored = await load_settings_from_db(db)
    entries = []
    for key in ALL_KEYS:
        val = stored.get(key)
        entries.append(SettingEntry(key=key, masked_value=mask_value(val), is_set=bool(val)))
    return SettingsResponse(settings=entries)


@router.put("/")
async def update_settings(body: SettingsUpdate, db: AsyncSession = Depends(get_db)):
    await upsert_settings(db, body.updates)
    return {"status": "ok", "updated": list(body.updates.keys())}
