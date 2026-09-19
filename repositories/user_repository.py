"""مستودع المستخدمين: استعلامات خاصة بجدول users لا يوفرها المستودع العام."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.user import User
from repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """عمليات قاعدة البيانات الخاصة بالمستخدمين."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, User)

    def get_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        return self._session.scalars(stmt).first()

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        return self._session.scalars(stmt).first()

    def username_or_email_exists(self, username: str, email: str) -> bool:
        return self.get_by_username(username) is not None or self.get_by_email(email) is not None
