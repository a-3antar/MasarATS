"""نموذج المرشح (جدول candidates). يُبقي المرحلة الحالية مبسّطة: حقول أساسية + JSON للتفاصيل المرنة."""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Candidate(Base):
    """مرشح تم استخلاص بياناته من سيرة ذاتية (أو إدخاله يدوياً)."""

    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    candidate_code: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)  # CAND-2026-001

    # معلومات شخصية
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    location: Mapped[str | None] = mapped_column(String(150), nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    photo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)  # مسار نسبي لجذر المشروع

    # الحالة الشخصية
    marital_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    military_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    languages: Mapped[list] = mapped_column(JSON, default=list, nullable=True)

    # معلومات مهنية
    current_position: Mapped[str | None] = mapped_column(String(150), nullable=True)
    total_experience_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous_positions: Mapped[list] = mapped_column(JSON, default=list, nullable=True)

    # قوائم مرنة نخزّنها JSON في هذه المرحلة لتفادي جداول فرعية معقدة قبل استقرار المتطلبات.
    # skills = "مهارات أخرى" لا تنتمي لأي فئة من الفئات المفصّلة أدناه.
    skills: Mapped[list] = mapped_column(JSON, default=list)
    education: Mapped[list] = mapped_column(JSON, default=list)
    experience: Mapped[list] = mapped_column(JSON, default=list)

    # فئات المهارات - nullable=True لأنها أُضيفت لاحقاً (السجلات القديمة ستحمل NULL)
    technical_skills: Mapped[list] = mapped_column(JSON, default=list, nullable=True)
    computer_skills: Mapped[list] = mapped_column(JSON, default=list, nullable=True)
    managerial_skills: Mapped[list] = mapped_column(JSON, default=list, nullable=True)
    soft_skills: Mapped[list] = mapped_column(JSON, default=list, nullable=True)
    industries: Mapped[list] = mapped_column(JSON, default=list, nullable=True)
    previous_companies: Mapped[list] = mapped_column(JSON, default=list, nullable=True)

    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # بيانات إدارة التوظيف (يدخلها مسؤول التوظيف)
    applied_job: Mapped[str | None] = mapped_column(String(150), nullable=True)
    status: Mapped[str | None] = mapped_column(String(20), default="New", nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1 إلى 5
    expected_salary: Mapped[float | None] = mapped_column(Float, nullable=True)
    notice_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recruiter_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ترجمات البيانات: {"ar": {"summary": "...", "soft_skills": [...], ...}} - الأصل يبقى بالإنجليزية
    translations: Mapped[dict] = mapped_column(JSON, default=dict, nullable=True)
    # بيانات المستند الأصلي
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # تتبع تحليل الذكاء الاصطناعي
    ai_analyzed: Mapped[bool] = mapped_column(default=False)
        # نتيجة تحليل الذكاء الاصطناعي مخزّنة (كاش) لتفادي إعادة الاستدعاء - القسم 28 (AI Cost Optimization)
    ai_analysis: Mapped[dict] = mapped_column(JSON, default=dict, nullable=True)
    analysis_status: Mapped[str | None] = mapped_column(String(20), nullable=True)  # pending / done / failed
    analysis_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    @property
    def all_skills(self) -> list[str]:
        """كل المهارات من كل الفئات في قائمة واحدة بدون تكرار (تستخدمها المطابقة)."""
        groups = (
            self.technical_skills, self.computer_skills, self.managerial_skills,
            self.soft_skills, self.skills,
        )
        merged: list[str] = []
        seen: set[str] = set()
        for group in groups:
            for skill in group or []:
                key = skill.strip().lower()
                if key and key not in seen:
                    seen.add(key)
                    merged.append(skill)
        return merged

    def __repr__(self) -> str:
        return f"<Candidate id={self.id} name={self.full_name!r}>"