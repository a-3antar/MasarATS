
from typing import Generic, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):

    def __init__(self, session: Session, model: Type[ModelType]) -> None:
        self._session = session
        self._model = model

    def get_by_id(self, record_id: int) -> ModelType | None:
        return self._session.get(self._model, record_id)

    def list_all(self, limit: int = 100, offset: int = 0) -> list[ModelType]:
        stmt = select(self._model).limit(limit).offset(offset)
        return list(self._session.scalars(stmt).all())

    def add(self, instance: ModelType) -> ModelType:
        self._session.add(instance)
        self._session.flush()
        return instance

    def delete(self, instance: ModelType) -> None:
        self._session.delete(instance)
