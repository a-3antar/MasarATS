"""مستودع المرشحين: استعلامات خاصة بجدول candidates."""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from models.candidate import Candidate
from repositories.base import BaseRepository


class CandidateRepository(BaseRepository[Candidate]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Candidate)

    def get_by_file_hash(self, file_hash: str) -> Candidate | None:
        stmt = select(Candidate).where(Candidate.file_hash == file_hash)
        return self._session.scalars(stmt).first()

    def search(self, query: str, limit: int = 50) -> list[Candidate]:
        """بحث نصي بسيط بالاسم أو البريد أو المسمى الوظيفي الحالي."""
        like = f"%{query}%"
        stmt = (
            select(Candidate)
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
