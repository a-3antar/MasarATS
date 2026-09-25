"""خدمة الهيكل التنظيمي: أقسام، مسميات وظيفية، ومنع الحلقات الدائرية في التبعية."""

from sqlalchemy.orm import Session

from core.exceptions import ValidationError
from models.department import Department
from models.position import Position
from repositories.organization_repository import DepartmentRepository, PositionRepository

_DEPT_EDITABLE = {"name", "parent_department_id"}
_POS_EDITABLE = {"title", "department_id", "reports_to_position_id", "required_headcount", "current_headcount"}


class OrganizationService:
    def __init__(self, session: Session) -> None:
        self._departments = DepartmentRepository(session)
        self._positions = PositionRepository(session)

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
        return department

    def delete_department(self, department_id: int) -> None:
        self._get_department_or_raise(department_id)
        if self._positions.list_for_department(department_id):
            raise ValidationError("لا يمكن حذف قسم يحتوي على مسميات وظيفية. انقلها أو احذفها أولاً.")
        if any(d.parent_department_id == department_id for d in self._departments.list_all()):
            raise ValidationError("لا يمكن حذف قسم له أقسام فرعية. انقلها أو احذفها أولاً.")
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