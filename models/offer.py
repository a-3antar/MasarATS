"""نموذج العرض الوظيفي (جدول offers). عرض واحد نشط كحد أقصى لكل تقديم."""

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.constants import OFFER_STATUSES
from database.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(20), default=OFFER_STATUSES[0], nullable=False, index=True)
    salary: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(150), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<Offer id={self.id} application_id={self.application_id} status={self.status}>"
