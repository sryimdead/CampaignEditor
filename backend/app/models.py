from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CampaignChange(Base):
    """Локальный журнал изменений кампаний, которые сделал редактор.

    Keitaro хранит только текущее состояние, поэтому историю ведём здесь.
    """

    __tablename__ = "campaign_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    action: Mapped[str] = mapped_column(String(16))  # create | update
    keitaro_campaign_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class OfferPin(Base):
    """Закреплённый вес оффера в кампании. Нет строки - вес считается автоматически."""

    __tablename__ = "offer_pins"
    __table_args__ = (UniqueConstraint("keitaro_campaign_id", "offer_id", name="uq_offer_pin"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keitaro_campaign_id: Mapped[int] = mapped_column(Integer, index=True)
    offer_id: Mapped[int] = mapped_column(Integer)
    share: Mapped[int] = mapped_column(Integer)
