
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Candidate(Base):

    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    candidate_code: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)

    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    location: Mapped[str | None] = mapped_column(String(150), nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    birth_date: Mapped[str | None] = mapped_column(String(50), nullable=True)
    photo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    marital_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    military_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    languages: Mapped[list] = mapped_column(JSON, default=list, nullable=True)

    current_position: Mapped[str | None] = mapped_column(String(150), nullable=True)
    total_experience_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous_positions: Mapped[list] = mapped_column(JSON, default=list, nullable=True)

    skills: Mapped[list] = mapped_column(JSON, default=list)
    education: Mapped[list] = mapped_column(JSON, default=list)
    experience: Mapped[list] = mapped_column(JSON, default=list)

    technical_skills: Mapped[list] = mapped_column(JSON, default=list, nullable=True)
    computer_skills: Mapped[list] = mapped_column(JSON, default=list, nullable=True)
    managerial_skills: Mapped[list] = mapped_column(JSON, default=list, nullable=True)
    soft_skills: Mapped[list] = mapped_column(JSON, default=list, nullable=True)
    industries: Mapped[list] = mapped_column(JSON, default=list, nullable=True)
    previous_companies: Mapped[list] = mapped_column(JSON, default=list, nullable=True)

    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    applied_job: Mapped[str | None] = mapped_column(String(150), nullable=True)
    status: Mapped[str | None] = mapped_column(String(20), default="New", nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_salary: Mapped[float | None] = mapped_column(Float, nullable=True)
    notice_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recruiter_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    translations: Mapped[dict] = mapped_column(JSON, default=dict, nullable=True)
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_analyzed: Mapped[bool] = mapped_column(default=False)
    ai_analysis: Mapped[dict] = mapped_column(JSON, default=dict, nullable=True)
    analysis_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    analysis_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    embedding_meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    @property
    def all_skills(self) -> list[str]:
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
