"""نموذج المرشح (جدول candidates). يُبقي المرحلة الحالية مبسّطة: حقول أساسية + JSON للتفاصيل المرنة."""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Candidate(Base):
    """مرشح تم استخلاص بياناته من سيرة ذاتية (أو إدخاله يدوياً)."""

    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # معلومات شخصية
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    location: Mapped[str | None] = mapped_column(String(150), nullable=True)

    # معلومات مهنية
    current_position: Mapped[str | None] = mapped_column(String(150), nullable=True)
    total_experience_years: Mapped[float | None] = mapped_column(Float, nullable=True)

    # قوائم مرنة (skills, education, experience...) نخزّنها JSON في هذه المرحلة
    # لتفادي جداول فرعية معقدة قبل استقرار المتطلبات. يمكن تطبيعها (normalize)
    # إلى جداول منفصلة لاحقاً دون كسر بقية الطبقات (الـ repository يعزل هذا التفصيل).
    skills: Mapped[list] = mapped_column(JSON, default=list)
    education: Mapped[list] = mapped_column(JSON, default=list)
    experience: Mapped[list] = mapped_column(JSON, default=list)

    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # بيانات المستند الأصلي
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # تتبع تحليل الذكاء الاصطناعي
    ai_analyzed: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<Candidate id={self.id} name={self.full_name!r}>"
