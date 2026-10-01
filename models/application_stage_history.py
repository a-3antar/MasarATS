"""سجل تغيير مراحل التقديم (جدول application_stage_history). كل انتقال بين مرحلتين = صف واحد لا يُعدَّل."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ApplicationStageHistory(Base):
    """انتقال تقديم من مرحلة إلى أخرى، مع من نفّذه ومتى. أساس تقرير وقت التعيين وخط الزمن."""

    __tablename__ = "application_stage_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), nullable=False, index=True)

    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False, index=True)
    changed_by: Mapped[str | None] = mapped_column(String(150), nullable=True)  # اسم المستخدم البشري
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<StageHistory app={self.application_id} {self.from_status}->{self.to_status}>"
