"""نموذج التقديم (جدول applications). يربط مرشحاً بوظيفة، ويخزن نتيجة المطابقة."""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from core.constants import APPLICATION_STATUSES
from database.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Application(Base):
    """تقديم مرشح على وظيفة محددة، مع درجة المطابقة وتفاصيلها."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False, index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(20), default=APPLICATION_STATUSES[0])  # "New"

    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # تفصيل الدرجة لكل معيار + نقاط القوة والفجوات - لتفادي "درجة غامضة" (شرط الشفافية في المواصفات)
    match_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<Application candidate_id={self.candidate_id} job_id={self.job_id} score={self.match_score}>"
