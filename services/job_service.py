"""خدمة الوظائف: إنشاء وتعديل وحذف ونسخ وإدراج الوظائف الشاغرة، وربطها بالهيكل التنظيمي."""

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from core.constants import CAREER_LEVELS, DEFAULT_VACANCIES, EMPLOYMENT_TYPES, JOB_STATUSES
from core.exceptions import ValidationError
from models.interview_answer import InterviewAnswer
from models.job import Job
from models.job_question import JobQuestion
from repositories.application_repository import ApplicationRepository
from repositories.job_repository import JobRepository
from repositories.organization_repository import DepartmentRepository, PositionRepository

# الحقول المسموح تعديلها من الواجهة (قائمة بيضاء)
_EDITABLE_FIELDS = {
    "title", "department", "location", "required_experience_years", "status", "description",
    "required_skills", "required_technical_skills", "required_computer_skills",
    "required_managerial_skills", "required_soft_skills", "preferred_industries",
    "employment_type", "career_level", "reports_to", "education",
    "salary_min", "salary_max", "vacancies", "department_id", "position_id",
}

# الحقول التي تُنسخ عند "نسخ الوظيفة" (بدون embedding لأنه يُعاد حسابه)
_DUPLICATED_FIELDS = _EDITABLE_FIELDS - {"title", "status"} | {
    "preferred_skills", "match_weights", "competency_weights",
}
_COPY_SUFFIX = " (نسخة)"
_DRAFT = JOB_STATUSES[0]
_CLOSED = JOB_STATUSES[3]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobService:
    def __init__(self, session: Session) -> None:
        self._jobs = JobRepository(session)
        self._applications = ApplicationRepository(session)
        self._departments = DepartmentRepository(session)
        self._positions = PositionRepository(session)
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

    def _resolve_org_links(self, fields: dict) -> dict:
        """
        يتحقق من القسم والمسمى الوظيفي ويزامن نص القسم (department) مع اسم القسم المرتبط.
        إن اختير مسمى بدون قسم يرث قسمه، وإن تعارضا يُرفض الحفظ.
        """
        if "department_id" not in fields and "position_id" not in fields:
            return fields

        resolved = dict(fields)
        department_id = resolved.get("department_id")
        position_id = resolved.get("position_id")

        if position_id is not None:
            position = self._positions.get_by_id(position_id)
            if position is None:
                raise ValidationError("المسمى الوظيفي المحدد غير موجود في الهيكل التنظيمي.")
            if department_id is None:
                department_id = position.department_id
            elif position.department_id not in (None, department_id):
                raise ValidationError("المسمى الوظيفي المختار لا يتبع القسم المحدد.")
            resolved["department_id"] = department_id
            if not (resolved.get("reports_to") or "").strip():
                boss = (
                    self._positions.get_by_id(position.reports_to_position_id)
                    if position.reports_to_position_id else None
                )
                if boss is not None:
                    resolved["reports_to"] = boss.title  # تبعية آلية من الهيكل

        if department_id is not None:
            department = self._departments.get_by_id(department_id)
            if department is None:
                raise ValidationError("القسم المحدد غير موجود في الهيكل التنظيمي.")
            resolved["department"] = department.name
        elif "department" not in resolved:
            resolved["department"] = None
        return resolved

    def _get_or_raise(self, job_id: int) -> Job:
        job = self._jobs.get_by_id(job_id)
        if job is None:
            raise ValidationError("الوظيفة غير موجودة.")
        return job

    def create_job(self, title: str, **fields) -> Job:
        self._validate_fields({"title": title, **fields})
        fields = self._resolve_org_links(fields)
        job = Job(title=title.strip(), updated_at=_utcnow(), **fields)
        self._jobs.add(job)
        return job

    def create_from_position(self, position_id: int) -> Job:
        """
        ينشئ وظيفة مسودة من مسمى في الهيكل التنظيمي (طلب توظيف لسد الفجوة):
        القسم والمسمى من الهيكل، وعدد الشواغر = الفجوة (وبحد أدنى شاغر واحد).
        """

        position = self._positions.get_by_id(position_id)
        if position is None:
            raise ValidationError("المسمى الوظيفي غير موجود.")
        if position.gap <= 0:
            raise ValidationError(
                f"لا توجد فجوة لهذا المسمى (المطلوب {position.required_headcount} والحالي {position.current_headcount})."
            )
        if any(job.status != _CLOSED for job in self._jobs.list_for_position(position_id)):
            raise ValidationError("توجد وظيفة نشطة مرتبطة بهذا المسمى بالفعل. عدّلها بدل إنشاء وظيفة جديدة.")
        return self.create_job(
            title=position.title,
            department_id=position.department_id,
            position_id=position.id,
            vacancies=max(position.gap, DEFAULT_VACANCIES),
            status=_DRAFT,
        )

    def jobs_for_position(self, position_id: int) -> list[Job]:
        return self._jobs.list_for_position(position_id)

    def update_job(self, job_id: int, **fields) -> Job:
        job = self._get_or_raise(job_id)
        self._validate_fields(fields)
        fields = self._resolve_org_links(fields)
        for name, value in fields.items():
            setattr(job, name, value.strip() if name == "title" else value)
        job.updated_at = _utcnow()
        return job

    def duplicate_job(self, job_id: int) -> Job:
        """ينسخ الوظيفة كمسودة جديدة. لا تُنسخ التقديمات ولا المقابلات ولا الأسئلة ولا الـ embedding."""
        source = self._get_or_raise(job_id)
        values = {}
        for name in _DUPLICATED_FIELDS:
            value = getattr(source, name)
            values[name] = list(value) if isinstance(value, list) else dict(value) if isinstance(value, dict) else value
        copy = Job(title=f"{source.title}{_COPY_SUFFIX}", status=_DRAFT, updated_at=_utcnow(), **values)
        self._jobs.add(copy)
        return copy

    def close_job(self, job_id: int) -> Job:
        return self.update_job(job_id, status=_CLOSED)

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