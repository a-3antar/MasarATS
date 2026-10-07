"""خدمة الهيكل التنظيمي: أقسام، مسميات، مديرو الأقسام، تبعية آلية، فجوات وتحذيرات ودراسة احتياج."""

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.constants import DEFAULT_VACANCIES, JOB_STATUSES
from core.exceptions import ValidationError
from models.department import Department
from models.job import Job
from models.position import Position
from repositories.organization_repository import DepartmentRepository, PositionRepository

_DEPT_EDITABLE = {"name", "parent_department_id"}
_POS_EDITABLE = {
    "title", "department_id", "reports_to_position_id", "required_headcount", "current_headcount", "sort_order",
}
_CLOSED = JOB_STATUSES[3]
_MAX_DEPTH = 50  # حماية من الحلقات عند حساب العمق


class OrganizationService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._departments = DepartmentRepository(session)
        self._positions = PositionRepository(session)

    # ------------------------------------------------------------ نظرة شاملة للواجهة

    def overview(self) -> dict:
        """كل بيانات صفحة الهيكل (قواميس بسيطة قابلة للكاش) مع الترتيب والتحذيرات."""
        departments = self._departments.list_all()
        positions = self._positions.list_all()
        dept_names = {d.id: d.name for d in departments}
        by_id = {p.id: p for p in positions}
        titles = {p.id: p.title for p in positions}
        manager_ids = {d.manager_position_id for d in departments if d.manager_position_id}

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
                    "vacancies": job.vacancies or DEFAULT_VACANCIES,
                    "has_requirements": bool(job.all_required_skills or job.required_experience_years),
                })
        positions_per_department = Counter(p.department_id for p in positions if p.department_id is not None)

        position_rows = []
        for p in positions:
            linked = jobs_by_position.get(p.id, [])
            active = [j for j in linked if j["status"] != _CLOSED]
            open_vacancies = sum(j["vacancies"] for j in active)
            gap = p.gap
            row = {
                "id": p.id,
                "title": p.title,
                "department_id": p.department_id,
                "department": dept_names.get(p.department_id),
                "reports_to_id": p.reports_to_position_id,
                "reports_to": titles.get(p.reports_to_position_id),
                "required": p.required_headcount,
                "current": p.current_headcount,
                "gap": gap,
                "sort_order": p.sort_order or 0,
                "depth": self._depth(p.id, by_id),
                "is_manager": p.id in manager_ids,
                "jobs": linked,
                "active_jobs": len(active),
                "open_vacancies": open_vacancies,
                "uncovered": max(gap - open_vacancies, 0),  # فجوة لم تُغطَّ بعد بشواغر
            }
            row["warnings"] = self._position_warnings(row)
            position_rows.append(row)

        position_rows.sort(key=lambda r: (r["department"] or "~", r["depth"], r["sort_order"], r["title"]))

        department_rows = [
            {
                "id": d.id,
                "name": d.name,
                "parent_id": d.parent_department_id,
                "manager_position_id": d.manager_position_id,
                "manager": titles.get(d.manager_position_id),
                "positions": positions_per_department.get(d.id, 0),
                "jobs": jobs_by_department.get(d.id, 0),
            }
            for d in departments
        ]

        warnings = [
            {"level": "error" if "تجاوز" in w else "warning", "text": f"{r['title']}: {w}"}
            for r in position_rows for w in r["warnings"]
        ]
        warnings += [
            {"level": "warning", "text": f"القسم «{d['name']}» بدون مدير محدد."}
            for d in department_rows if d["positions"] and not d["manager_position_id"]
        ]

        return {
            "departments": department_rows,
            "positions": position_rows,
            "warnings": warnings,
            "kpis": {
                "departments": len(departments),
                "positions": len(positions),
                "total_gap": sum(max(p.gap, 0) for p in positions),
                "linked_jobs": sum(r["active_jobs"] for r in position_rows),
                "warnings": len(warnings),
            },
        }

    @staticmethod
    def _depth(position_id: int, by_id: dict[int, Position]) -> int:
        """عدد الرؤساء فوق المسمى (0 = قمة الهرم)."""
        depth, current, seen = 0, by_id.get(position_id), set()
        while current is not None and current.reports_to_position_id and current.id not in seen and depth < _MAX_DEPTH:
            seen.add(current.id)
            current = by_id.get(current.reports_to_position_id)
            depth += 1
        return depth

    @staticmethod
    def _position_warnings(row: dict) -> list[str]:
        warnings = []
        if row["current"] > row["required"]:
            warnings.append(f"تجاوز الحد: الحالي {row['current']} أكبر من المطلوب {row['required']}")
        if row["open_vacancies"] > max(row["gap"], 0):
            warnings.append(f"الشواغر المفتوحة ({row['open_vacancies']}) تتجاوز الفجوة ({max(row['gap'], 0)})")
        if row["gap"] > 0 and not row["active_jobs"]:
            warnings.append(f"فجوة {row['gap']} بدون وظيفة منشورة")
        return warnings

    @staticmethod
    def staffing_study(positions: list[dict]) -> list[dict]:
        """دراسة الاحتياج: المسميات ذات الفجوة مرتبة بالأولوية (المدراء ثم الأعلى في الهرم ثم الأكبر فجوة)."""
        rows = []
        for p in positions:
            if p["gap"] <= 0:
                continue
            if not p["active_jobs"]:
                action = "إنشاء وظيفة من الفجوة"
            elif p["uncovered"] > 0:
                action = f"زيادة الشواغر بمقدار {p['uncovered']}"
            else:
                action = "متابعة المطابقة والمقابلات"
            rows.append({**p, "action": action})
        rows.sort(key=lambda r: (not r["is_manager"], r["depth"], -r["gap"], r["title"]))
        return rows

    # ------------------------------------------------------------ مزامنة الوظائف

    def _sync_job_departments(self, where_clause, department: Department | None) -> None:
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
        if "name" in fields:
            self._sync_job_departments(Job.department_id == department_id, department)
        if "parent_department_id" in fields:
            self._session.flush()
            self._apply_reporting(department)  # القسم انتقل: أعد ربط مديره بمدير القسم الأب الجديد
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

    # ------------------------------------------------------------ المديرون والتبعية الآلية

    def set_department_manager(self, department_id: int, position_id: int | None) -> Department:
        """يحدد مسمى مدير القسم (أو None لإلغائه) ثم يربط التبعيات الفارغة آلياً."""
        department = self._get_department_or_raise(department_id)
        if position_id is None:
            department.manager_position_id = None
            return department
        position = self._get_position_or_raise(position_id)
        if position.department_id != department_id:
            raise ValidationError("مدير القسم يجب أن يكون مسمى تابعاً للقسم نفسه.")
        department.manager_position_id = position_id
        self._session.flush()
        self._apply_reporting(department)
        return department

    def _set_boss_if_empty(self, position: Position | None, boss_id: int | None) -> None:
        """يضبط الرئيس فقط إن كان فارغاً ولا يُنشئ حلقة. لا يستبدل تبعية حددها المستخدم."""
        if position is None or boss_id is None or position.id == boss_id:
            return
        if position.reports_to_position_id is None and not self._position_would_cycle(position.id, boss_id):
            position.reports_to_position_id = boss_id

    def _apply_reporting(self, department: Department) -> None:
        """يربط: أعضاء القسم ← مديره، مدير القسم ← مدير القسم الأب، مديرو الأقسام الفرعية ← مدير هذا القسم."""
        manager_id = department.manager_position_id
        if manager_id is not None:
            for position in self._positions.list_for_department(department.id):
                self._set_boss_if_empty(position, manager_id)
            for child in self._departments.list_all():
                if child.parent_department_id == department.id and child.manager_position_id:
                    self._set_boss_if_empty(self._positions.get_by_id(child.manager_position_id), manager_id)

        parent = (
            self._departments.get_by_id(department.parent_department_id)
            if department.parent_department_id else None
        )
        if manager_id is not None and parent is not None:
            self._set_boss_if_empty(self._positions.get_by_id(manager_id), parent.manager_position_id)

    def _auto_assign_boss(self, position: Position) -> None:
        """تبعية آلية لمسمى بلا رئيس: مدير قسمه، أو مدير القسم الأب إن كان هو مدير قسمه."""
        if position.reports_to_position_id is not None or position.department_id is None:
            return
        department = self._departments.get_by_id(position.department_id)
        if department is None:
            return
        if department.manager_position_id and department.manager_position_id != position.id:
            self._set_boss_if_empty(position, department.manager_position_id)
        elif department.manager_position_id == position.id and department.parent_department_id:
            parent = self._departments.get_by_id(department.parent_department_id)
            self._set_boss_if_empty(position, parent.manager_position_id if parent else None)

    def _position_would_cycle(self, position_id: int, new_boss_id: int) -> bool:
        by_id = {p.id: p for p in self._positions.list_all()}
        current, seen = by_id.get(new_boss_id), set()
        while current is not None and current.id not in seen:
            if current.id == position_id:
                return True
            seen.add(current.id)
            current = by_id.get(current.reports_to_position_id)
        return False

    def boss_title(self, position_id: int | None) -> str | None:
        """اسم رئيس المسمى (يُستخدم لملء «يتبع لـ» في الوظيفة آلياً)."""
        position = self._positions.get_by_id(position_id) if position_id else None
        boss = self._positions.get_by_id(position.reports_to_position_id) if position and position.reports_to_position_id else None
        return boss.title if boss else None

    # -------------------------------------------------------- المسميات الوظيفية

    def create_position(self, title: str, **fields) -> Position:
        if not (title or "").strip():
            raise ValidationError("المسمى الوظيفي مطلوب.")
        self._validate_position_fields(fields)
        position = Position(title=title.strip(), **fields)
        self._positions.add(position)
        self._auto_assign_boss(position)
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
        if reports_to is not None and self._position_would_cycle(position_id, reports_to):
            raise ValidationError("هذه التبعية تُنشئ حلقة دائرية في الهيكل.")

        self._validate_position_fields(fields)
        old_department = position.department_id
        for name, value in fields.items():
            setattr(position, name, value.strip() if name == "title" else value)

        if "department_id" in fields:
            department_id = fields["department_id"]
            department = self._departments.get_by_id(department_id) if department_id is not None else None
            self._sync_job_departments(Job.position_id == position_id, department)
            if old_department != department_id:  # انتقل من قسم: لم يعد مديراً له
                for old in self._departments.list_all():
                    if old.manager_position_id == position_id and old.id != department_id:
                        old.manager_position_id = None
        self._session.flush()
        self._auto_assign_boss(position)
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
        for department in self._departments.list_all():
            if department.manager_position_id == position_id:
                department.manager_position_id = None
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
        return sorted((p for p in self._positions.list_all() if p.gap > 0), key=lambda p: p.gap, reverse=True)