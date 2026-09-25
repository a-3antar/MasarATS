"""مستودعا الأقسام والمسميات الوظيفية."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.department import Department
from models.position import Position
from repositories.base import BaseRepository


class DepartmentRepository(BaseRepository[Department]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Department)

    def list_all(self, limit: int = 500, offset: int = 0) -> list[Department]:
        stmt = select(Department).order_by(Department.name)
        return list(self._session.scalars(stmt).all())


class PositionRepository(BaseRepository[Position]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Position)

    def list_all(self, limit: int = 1000, offset: int = 0) -> list[Position]:
        stmt = select(Position).order_by(Position.title)
        return list(self._session.scalars(stmt).all())

    def list_for_department(self, department_id: int) -> list[Position]:
        stmt = select(Position).where(Position.department_id == department_id)
        return list(self._session.scalars(stmt).all())