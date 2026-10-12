
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, defer

from models.candidate import Candidate
from repositories.base import BaseRepository


class CandidateRepository(BaseRepository[Candidate]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Candidate)

    def get_by_file_hash(self, file_hash: str) -> Candidate | None:
        stmt = select(Candidate).where(Candidate.file_hash == file_hash)
        return self._session.scalars(stmt).first()

    def list_all(self, limit: int = 100, offset: int = 0) -> list[Candidate]:
        stmt = select(Candidate).options(defer(Candidate.raw_text)).limit(limit).offset(offset)
        return list(self._session.scalars(stmt).all())

    def search(self, query: str, limit: int = 50) -> list[Candidate]:
        like = f"%{query}%"
        stmt = (
            select(Candidate)
            .options(defer(Candidate.raw_text))
            .where(
                or_(
                    Candidate.full_name.ilike(like),
                    Candidate.email.ilike(like),
                    Candidate.current_position.ilike(like),
                )
            )
            .limit(limit)
        )
        return list(self._session.scalars(stmt).all())
