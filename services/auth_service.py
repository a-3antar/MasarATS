"""
خدمة المصادقة (Authentication Service).
هذه هي الطبقة الوحيدة التي يجب أن تتعامل معها واجهة Streamlit لتسجيل الدخول
أو إنشاء حساب — لا تحتوي الواجهة على أي استعلام قاعدة بيانات مباشر.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.enums import UserRole
from core.exceptions import AuthenticationError, InactiveUserError, UserAlreadyExistsError
from core.logging import get_logger
from core.security import hash_password, verify_password
from models.user import User
from repositories.user_repository import UserRepository

logger = get_logger(__name__)


class AuthService:
    """منطق العمل الخاص بتسجيل المستخدمين ومصادقتهم."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._users = UserRepository(session)

    def register_user(
        self,
        username: str,
        email: str,
        full_name: str,
        password: str,
        role: UserRole = UserRole.RECRUITER,
    ) -> User:
        """
        تسجيل مستخدم جديد.
        يرفع UserAlreadyExistsError إذا كان اسم المستخدم أو البريد مستخدماً مسبقاً.
        """
        username = username.strip().lower()
        email = email.strip().lower()

        if not username or not email or not full_name or not password:
            from core.exceptions import ValidationError
            raise ValidationError("كل الحقول مطلوبة.")

        if len(password) < 6:
            from core.exceptions import ValidationError
            raise ValidationError("يجب ألا تقل كلمة المرور عن 6 أحرف.")

        if self._users.username_or_email_exists(username, email):
            raise UserAlreadyExistsError("اسم المستخدم أو البريد الإلكتروني مستخدم بالفعل.")

        user = User(
            username=username,
            email=email,
            full_name=full_name.strip(),
            password_hash=hash_password(password),
            role=role.value,
            is_active=True,
        )
        self._users.add(user)
        logger.info("New user registered: %s", username)
        return user

    def authenticate(self, username: str, password: str) -> User:
        """
        التحقق من بيانات الدخول. يرجع المستخدم عند النجاح.
        يرفع AuthenticationError عند بيانات خاطئة، أو InactiveUserError إذا كان الحساب معطلاً.
        """
        username = username.strip().lower()
        user = self._users.get_by_username(username)

        if user is None or not verify_password(password, user.password_hash):
            logger.warning("Failed login attempt for username: %s", username)
            raise AuthenticationError("اسم المستخدم أو كلمة المرور غير صحيحة.")

        if not user.is_active:
            raise InactiveUserError("هذا الحساب معطّل. تواصل مع المسؤول.")

        user.last_login_at = datetime.now(timezone.utc)
        logger.info("User logged in: %s", username)
        return user

    def has_any_user(self) -> bool:
        """هل يوجد أي مستخدم مسجّل بعد؟ تُستخدم لعرض شاشة إنشاء أول حساب Admin."""
        return len(self._users.list_all(limit=1)) > 0
