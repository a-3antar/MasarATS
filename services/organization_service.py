"""خدمة الهيكل التنظيمي: أقسام، مسميات وظيفية، منع الحلقات الدائرية، وربط الهيكل بالوظائف."""

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.constants import JOB_STATUSES
from core.exceptions import ValidationError
from models.department import Department
from models.job import Job
from models.position import Position
from repositories.organization_repository import DepartmentRepository, PositionRepository

_DEPT_EDITABLE = {"name", "parent_department_id"}
_POS_EDITABLE = {"title", "department_id", "reports_to_position_id", "required_headcount", "current_headcount"}
_CLOSED = JOB_STATUSES[3]


class OrganizationService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._departments = DepartmentRepository(session)
        self._positions = PositionRepository(session)

    # ------------------------------------------------------------ نظرة شاملة للواجهة

    def overview(self) -> dict:
        """
        كل بيانات صفحة الهيكل كقواميس بسيطة قابلة للتخزين في كاش Streamlit:
        الأقسام والمسميات (مع الوظائف المرتبطة بكل مسمى) والمؤشرات.
        """
        departments = self._departments.list_all()
        positions = self._positions.list_all()
        dept_names = {d.id: d.name for d in departments}
        titles = {p.id: p.title for p in positions}

        jobs_by_position: dict[int, list[dict]] = {}
        jobs_by_department: Counter[int] = Counter()
        for job in self._session.scalars(select(Job)):
            if job.department_id is not None:
                jobs_by_department[job.department_id] += 1
            if job.position_id is not None:
                jobs_by_position.setdefault(job.position_id, []).append({
                    "id": job.id,
                    "title": job.title,
                    "status": job.status,
                    "has_requirements": bool(job.all_required_skills or job.required_experience_years),
                })
        positions_per_department = Counter(p.department_id for p in positions if p.department_id is not None)

        position_rows = []
        for p in positions:
            linked = jobs_by_position.get(p.id, [])
            position_rows.append({
                "id": p.id,
                "title": p.title,
                "department_id": p.department_id,
                "department": dept_names.get(p.department_id),
                "reports_to_id": p.reports_to_position_id,
                "reports_to": titles.get(p.reports_to_position_id),
                "required": p.required_headcount,
                "current": p.current_headcount,
                "gap": p.gap,
                "jobs": linked,
                "active_jobs": sum(1 for j in linked if j["status"] != _CLOSED),
            })

        return {
            "departments": [
                {
                    "id": d.id,
                    "name": d.name,
                    "parent_id": d.parent_department_id,
                    "positions": positions_per_department.get(d.id, 0),
                    "jobs": jobs_by_department.get(d.id, 0),
                }
                for d in departments
            ],
            "positions": position_rows,
            "kpis": {
                "departments": len(departments),
                "positions": len(positions),
                "total_gap": sum(max(p.gap, 0) for p in positions),
                "linked_jobs": sum(r["active_jobs"] for r in position_rows),
            },
        }

    # ------------------------------------------------------------ مزامنة الوظائف

    def _sync_job_departments(self, where_clause, department: Department | None) -> None:
        """يحدّث قسم (id + النص) الوظائف المطابقة للشرط ليبقى متسقاً مع الهيكل."""
        for job in self._session.scalars(select(Job).where(where_clause)):
            job.department_id = department.id if department else None
            job.department = department.name if department else None

    def _count_jobs(self, where_clause) -> int:
        return self._session.scalar(select(func.count()).select_from(Job).where(where_clause)) or 0

    # ------------------------------------------------------------ الأقسام

    def create_department(self, name: str, parent_department_id: int | None = None) -> Department:
        if not (name or "").strip():
            raise ValidationError("اسم القسم مطلوب.")
        if parent_department_id is not None and self._departments.get_by_id(parent_department_id) is None:
            raise ValidationError("القسم الأب غير موجود.")
        department = Department(name=name.strip(), parent_department_id=parent_department_id)
        self._departments.add(department)
        return department

    def update_department(self, department_id: int, **fields) -> Department:
        department = self._get_department_or_raise(department_id)
        unknown = set(fields) - _DEPT_EDITABLE
        if unknown:
            raise ValidationError(f"حقول غير قابلة للتعديل: {', '.join(sorted(unknown))}")
        if "name" in fields and not (fields["name"] or "").strip():
            raise ValidationError("اسم القسم مطلوب.")

        new_parent = fields.get("parent_department_id", department.parent_department_id)
        if new_parent == department_id:
            raise ValidationError("لا يمكن أن يكون القسم أباً لنفسه.")
        if new_parent is not None and self._would_cycle(department_id, new_parent):
            raise ValidationError("هذا التغيير يُنشئ حلقة دائرية في الهيكل التنظيمي.")

        for name, value in fields.items():
            setattr(department, name, value.strip() if name == "name" else value)
        if "name" in fields:  # الوظائف المرتبطة تحمل نسخة نصية من اسم القسم
            self._sync_job_departments(Job.department_id == department_id, department)
        return department

    def delete_department(self, department_id: int) -> None:
        self._get_department_or_raise(department_id)
        if self._positions.list_for_department(department_id):
            raise ValidationError("لا يمكن حذف قسم يحتوي على مسميات وظيفية. انقلها أو احذفها أولاً.")
        if any(d.parent_department_id == department_id for d in self._departments.list_all()):
            raise ValidationError("لا يمكن حذف قسم له أقسام فرعية. انقلها أو احذفها أولاً.")
        if self._count_jobs(Job.department_id == department_id):
            raise ValidationError("لا يمكن حذف قسم مرتبط بوظائف. غيّر قسم هذه الوظائف أولاً.")
        self._departments.delete(self._departments.get_by_id(department_id))

    def _would_cycle(self, department_id: int, new_parent_id: int) -> bool:
        """يمنع جعل القسم أباً لأحد أجداده (حلقة دائرية في الشجرة)."""
        by_id = {d.id: d for d in self._departments.list_all()}
        current = by_id.get(new_parent_id)
        visited: set[int] = set()
        while current is not None:
            if current.id == department_id:
                return True
            if current.id in visited:
                break
            visited.add(current.id)
            current = by_id.get(current.parent_department_id)
        return False

    def _get_department_or_raise(self, department_id: int) -> Department:
        department = self._departments.get_by_id(department_id)
        if department is None:
            raise ValidationError("القسم غير موجود.")
        return department

    def list_departments(self) -> list[Department]:
        return self._departments.list_all()

    # -------------------------------------------------------- المسميات الوظيفية

    def create_position(self, title: str, **fields) -> Position:
        if not (title or "").strip():
            raise ValidationError("المسمى الوظيفي مطلوب.")
        self._validate_position_fields(fields)
        position = Position(title=title.strip(), **fields)
        self._positions.add(position)
        return position

    def update_position(self, position_id: int, **fields) -> Position:
        position = self._get_position_or_raise(position_id)
        unknown = set(fields) - _POS_EDITABLE
        if unknown:
            raise ValidationError(f"حقول غير قابلة للتعديل: {', '.join(sorted(unknown))}")
        if "title" in fields and not (fields["title"] or "").strip():
            raise ValidationError("المسمى الوظيفي مطلوب.")

        reports_to = fields.get("reports_to_position_id", position.reports_to_position_id)
        if reports_to == position_id:
            raise ValidationError("لا يمكن أن يتبع المسمى نفسه.")

        self._validate_position_fields(fields)
        for name, value in fields.items():
            setattr(position, name, value.strip() if name == "title" else value)
        if "department_id" in fields:  # الوظائف المرتبطة بالمسمى تنتقل مع قسمه
            department_id = fields["department_id"]
            department = self._departments.get_by_id(department_id) if department_id is not None else None
            self._sync_job_departments(Job.position_id == position_id, department)
        return position

    def _validate_position_fields(self, fields: dict) -> None:
        department_id = fields.get("department_id")
        if department_id is not None and self._departments.get_by_id(department_id) is None:
            raise ValidationError("القسم المحدد غير موجود.")
        reports_to = fields.get("reports_to_position_id")
        if reports_to is not None and self._positions.get_by_id(reports_to) is None:
            raise ValidationError("المسمى الأعلى (Reports To) غير موجود.")
        for key in ("required_headcount", "current_headcount"):
            if key in fields and fields[key] is not None and fields[key] < 0:
                raise ValidationError("العدد لا يمكن أن يكون سالباً.")

    def delete_position(self, position_id: int) -> None:
        self._get_position_or_raise(position_id)
        if any(p.reports_to_position_id == position_id for p in self._positions.list_all()):
            raise ValidationError("لا يمكن حذف مسمى يتبعه مسميات أخرى. عدّل تبعيتها أولاً.")
        if self._count_jobs(Job.position_id == position_id):
            raise ValidationError("لا يمكن حذف مسمى مرتبط بوظائف. فُكّ ارتباط هذه الوظائف به أولاً.")
        self._positions.delete(self._positions.get_by_id(position_id))

    def _get_position_or_raise(self, position_id: int) -> Position:
        position = self._positions.get_by_id(position_id)
        if position is None:
            raise ValidationError("المسمى الوظيفي غير موجود.")
        return position

    def list_positions(self) -> list[Position]:
        return self._positions.list_all()

    def get_position(self, position_id: int) -> Position | None:
        return self._positions.get_by_id(position_id)

    def workforce_gaps(self) -> list[Position]:
        """المسميات التي بها نقص فعلي (required > current)، الأكبر فجوة أولاً."""
        return sorted((p for p in self._positions.list_all() if p.gap > 0), key=lambda p: p.gap, reverse=True)