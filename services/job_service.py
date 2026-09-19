"""خدمة الوظائف: إنشاء وإدراج الوظائف الشاغرة."""

from sqlalchemy.orm import Session

from core.exceptions import ValidationError
from models.job import Job
from repositories.job_repository import JobRepository


class JobService:
    def __init__(self, session: Session) -> None:
        self._jobs = JobRepository(session)

    def create_job(
        self,
        title: str,
        department: str | None = None,
        location: str | None = None,
        required_experience_years: float | None = None,
        required_skills: list[str] | None = None,
        description: str | None = None,
    ) -> Job:
        if not title or not title.strip():
            raise ValidationError("مسمى الوظيفة مطلوب.")

        job = Job(
            title=title.strip(),
            department=department,
            location=location,
            required_experience_years=required_experience_years,
            required_skills=required_skills or [],
            description=description,
            status="Open",
        )
        self._jobs.add(job)
        return job

    def list_all(self) -> list[Job]:
        return self._jobs.list_all(limit=200)

    def list_open(self) -> list[Job]:
        return self._jobs.list_open()

    def get_by_id(self, job_id: int) -> Job | None:
        return self._jobs.get_by_id(job_id)
