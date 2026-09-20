"""خدمة الوظائف: إنشاء وتعديل وحذف وإدراج الوظائف الشاغرة."""

from sqlalchemy.orm import Session

from core.constants import JOB_STATUSES
from core.exceptions import ValidationError
from models.job import Job
from repositories.application_repository import ApplicationRepository
from repositories.job_repository import JobRepository

# الحقول المسموح تعديلها من الواجهة (قائمة بيضاء)
_EDITABLE_FIELDS = {
    "title", "department", "location", "required_experience_years", "status", "description",
    "required_skills", "required_technical_skills", "required_computer_skills",
    "required_managerial_skills", "required_soft_skills", "preferred_industries",
}


class JobService:
    def __init__(self, session: Session) -> None:
        self._jobs = JobRepository(session)
        self._applications = ApplicationRepository(session)

    @staticmethod
    def _validate_fields(fields: dict) -> None:
        unknown = set(fields) - _EDITABLE_FIELDS
        if unknown:
            raise ValidationError(f"حقول غير قابلة للتعديل: {', '.join(sorted(unknown))}")
        if "title" in fields and not (fields["title"] or "").strip():
            raise ValidationError("مسمى الوظيفة مطلوب.")
        status = fields.get("status")
        if status is not None and status not in JOB_STATUSES:
            raise ValidationError(f"حالة الوظيفة غير صالحة: {status}")

    def _get_or_raise(self, job_id: int) -> Job:
        job = self._jobs.get_by_id(job_id)
        if job is None:
            raise ValidationError("الوظيفة غير موجودة.")
        return job

    def create_job(self, title: str, **fields) -> Job:
        self._validate_fields({"title": title, **fields})
        job = Job(title=title.strip(), **fields)
        self._jobs.add(job)
        return job

    def update_job(self, job_id: int, **fields) -> Job:
        job = self._get_or_raise(job_id)
        self._validate_fields(fields)
        for name, value in fields.items():
            setattr(job, name, value.strip() if name == "title" else value)
        return job

    def delete_job(self, job_id: int) -> None:
        """يحذف الوظيفة وكل التقديمات المرتبطة بها."""
        job = self._get_or_raise(job_id)
        self._applications.delete_for_job(job_id)
        self._jobs.delete(job)

    def list_all(self) -> list[Job]:
        return self._jobs.list_all(limit=200)

    def list_open(self) -> list[Job]:
        return self._jobs.list_open()

    def get_by_id(self, job_id: int) -> Job | None:
        return self._jobs.get_by_id(job_id)