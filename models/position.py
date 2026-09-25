"""نموذج المسمى الوظيفي (جدول positions) - يُستخدم لبناء الشجرة التنظيمية وتحليل فجوة القوى العاملة."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Position(Base):
    """مسمى وظيفي ضمن قسم، يتبع مسمى أعلى (reports_to)، بقوى عاملة مطلوبة وحالية."""

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True, index=True)
    reports_to_position_id: Mapped[int | None] = mapped_column(
        ForeignKey("positions.id"), nullable=True, index=True
    )

    required_headcount: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    current_headcount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    @property
    def gap(self) -> int:
        """الفجوة = المطلوب - الحالي. موجبة يعني نقص في التوظيف."""
        return self.required_headcount - self.current_headcount

    def __repr__(self) -> str:
        return f"<Position id={self.id} title={self.title!r} dept={self.department_id}>"