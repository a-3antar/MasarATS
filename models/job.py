"""نموذج الوظيفة الشاغرة (جدول jobs). فئات المهارات هنا تطابق فئات المرشح تماماً."""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.constants import DEFAULT_MATCH_WEIGHTS, JOB_STATUSES
from database.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Job(Base):
    """وظيفة شاغرة يمكن مطابقة المرشحين معها."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    title: Mapped[str] = mapped_column(String(150), nullable=False)
    # نص القسم يبقى للتوافق (تقارير/تصدير) ويُزامَن من JobService مع اسم القسم المرتبط
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(String(150), nullable=True)

    # ربط الوظيفة بالهيكل التنظيمي (المرحلة 4)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True, index=True)
    position_id: Mapped[int | None] = mapped_column(ForeignKey("positions.id"), nullable=True, index=True)

    # بيانات وصفية للوظيفة - كلها nullable لأنها أُضيفت لاحقاً (الوظائف القديمة تحمل NULL)
    employment_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    career_level: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reports_to: Mapped[str | None] = mapped_column(String(150), nullable=True)
    education: Mapped[str | None] = mapped_column(String(200), nullable=True)
    salary_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    vacancies: Mapped[int | None] = mapped_column(Integer, nullable=True)

    required_experience_years: Mapped[float | None] = mapped_column(Float, nullable=True)

    # required_skills = "مهارات أخرى" لا تنتمي لفئة محددة (نفس منطق Candidate.skills)
    required_skills: Mapped[list] = mapped_column(JSON, default=list)
    preferred_skills: Mapped[list] = mapped_column(JSON, default=list)

    # فئات المهارات المطلوبة - nullable لأنها أُضيفت لاحقاً (الوظائف القديمة ستحمل NULL)
    required_technical_skills: Mapped[list] = mapped_column(JSON, default=list, nullable=True)
    required_computer_skills: Mapped[list] = mapped_column(JSON, default=list, nullable=True)
    required_managerial_skills: Mapped[list] = mapped_column(JSON, default=list, nullable=True)
    required_soft_skills: Mapped[list] = mapped_column(JSON, default=list, nullable=True)
    preferred_industries: Mapped[list] = mapped_column(JSON, default=list, nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=JOB_STATUSES[1])  # "Open" افتراضياً

    match_weights: Mapped[dict] = mapped_column(JSON, default=lambda: dict(DEFAULT_MATCH_WEIGHTS))
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    embedding_meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=True)
    # أوزان الكفاءات لتقييم المقابلات: {"Leadership": 20, "Planning": 10}
    competency_weights: Mapped[dict] = mapped_column(JSON, default=dict, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    # يُحدَّث صراحةً من JobService عند تعديل المستخدم (وليس onupdate) حتى لا يتغيّر عند حفظ الـ embedding
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def all_required_skills(self) -> list[str]:
        """كل المهارات المطلوبة من كل الفئات بدون تكرار (تستخدمها المطابقة)."""
        groups = (
            self.required_technical_skills, self.required_computer_skills,
            self.required_managerial_skills, self.required_soft_skills, self.required_skills,
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
        return f"<Job id={self.id} title={self.title!r} status={self.status}>"