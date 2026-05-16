from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text

from app.database import Base


class AppSetting(Base):
    """Key-value store for runtime configuration (API keys, etc.)."""

    __tablename__ = "app_settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
