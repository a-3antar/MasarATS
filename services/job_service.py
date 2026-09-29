"""خدمة الوظائف: إنشاء وتعديل وحذف ونسخ وإدراج الوظائف الشاغرة."""

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from core.constants import CAREER_LEVELS, EMPLOYMENT_TYPES, JOB_STATUSES
from core.exceptions import ValidationError
from models.interview_answer import InterviewAnswer
from models.job import Job
from models.job_question import JobQuestion
from repositories.application_repository import ApplicationRepository
from repositories.job_repository import JobRepository

# الحقول المسموح تعديلها من الواجهة (قائمة بيضاء)
_EDITABLE_FIELDS = {
    "title", "department", "location", "required_experience_years", "status", "description",
    "required_skills", "required_technical_skills", "required_computer_skills",
    "required_managerial_skills", "required_soft_skills", "preferred_industries",
    "employment_type", "career_level", "reports_to", "education",
    "salary_min", "salary_max", "vacancies",
}

# الحقول التي تُنسخ عند "نسخ الوظيفة" (بدون embedding لأنه يُعاد حسابه)
_DUPLICATED_FIELDS = _EDITABLE_FIELDS - {"title", "status"} | {
    "preferred_skills", "match_weights", "competency_weights",
}
_COPY_SUFFIX = " (نسخة)"
_DRAFT = JOB_STATUSES[0]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobService:
    def __init__(self, session: Session) -> None:
        self._jobs = JobRepository(session)
        self._applications = ApplicationRepository(session)
        self._session = session

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
        employment = fields.get("employment_type")
        if employment is not None and employment not in EMPLOYMENT_TYPES:
            raise ValidationError(f"نوع التوظيف غير صالح: {employment}")
        level = fields.get("career_level")
        if level is not None and level not in CAREER_LEVELS:
            raise ValidationError(f"المستوى الوظيفي غير صالح: {level}")
        low, high = fields.get("salary_min"), fields.get("salary_max")
        if low is not None and high is not None and high < low:
            raise ValidationError("الحد الأعلى للراتب أقل من الحد الأدنى.")
        vacancies = fields.get("vacancies")
        if vacancies is not None and vacancies < 1:
            raise ValidationError("عدد الشواغر يجب ألا يقل عن 1.")

    def _get_or_raise(self, job_id: int) -> Job:
        job = self._jobs.get_by_id(job_id)
        if job is None:
            raise ValidationError("الوظيفة غير موجودة.")
        return job

    def create_job(self, title: str, **fields) -> Job:
        self._validate_fields({"title": title, **fields})
        job = Job(title=title.strip(), updated_at=_utcnow(), **fields)
        self._jobs.add(job)
        return job

    def update_job(self, job_id: int, **fields) -> Job:
        job = self._get_or_raise(job_id)
        self._validate_fields(fields)
        for name, value in fields.items():
            setattr(job, name, value.strip() if name == "title" else value)
        job.updated_at = _utcnow()
        return job

    def duplicate_job(self, job_id: int) -> Job:
        """ينسخ الوظيفة (وبنك أسئلتها) كمسودة جديدة. لا تُنسخ التقديمات ولا الـ embedding."""
        from services.question_bank_service import QuestionBankService

        source = self._get_or_raise(job_id)
        values = {}
        for name in _DUPLICATED_FIELDS:
            value = getattr(source, name)
            values[name] = list(value) if isinstance(value, list) else dict(value) if isinstance(value, dict) else value
        copy = Job(title=f"{source.title}{_COPY_SUFFIX}", status=_DRAFT, updated_at=_utcnow(), **values)
        self._jobs.add(copy)
        QuestionBankService(self._session).copy_from_job(copy.id, source.id)
        return copy

    def close_job(self, job_id: int) -> Job:
        return self.update_job(job_id, status="Closed")

    def list_all(self) -> list[Job]:
        return self._jobs.list_all(limit=200)

    def search(self, query: str) -> list[Job]:
        query = (query or "").strip()
        return self._jobs.search(query) if query else self.list_all()

    def list_open(self) -> list[Job]:
        return self._jobs.list_open()

    def get_by_id(self, job_id: int) -> Job | None:
        return self._jobs.get_by_id(job_id)

    def delete_job(self, job_id: int) -> None:
        """يحذف الوظيفة وكل التقديمات وأسئلة بنك الوظيفة وإجاباتها المرتبطة بها."""
        job = self._get_or_raise(job_id)
        self._applications.delete_for_job(job_id)

        question_ids = self._session.scalars(
            select(JobQuestion.id).where(JobQuestion.job_id == job_id)
        ).all()
        if question_ids:
            self._session.execute(delete(InterviewAnswer).where(InterviewAnswer.question_id.in_(question_ids)))
        self._session.execute(delete(JobQuestion).where(JobQuestion.job_id == job_id))

        self._jobs.delete(job)