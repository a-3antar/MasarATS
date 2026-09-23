"""
خدمة المصادقة (Authentication Service).
هذه هي الطبقة الوحيدة التي يجب أن تتعامل معها واجهة Streamlit لتسجيل الدخول
أو إنشاء حساب — لا تحتوي الواجهة على أي استعلام قاعدة بيانات مباشر.
"""

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from core.enums import UserRole
from core.exceptions import AuthenticationError, InactiveUserError, UserAlreadyExistsError
from core.logging import get_logger
from core.security import hash_password, verify_password
from models.user import User
from repositories.user_repository import UserRepository

logger = get_logger(__name__)

# مدة صلاحية "تذكرني" - بعدها يُطلب تسجيل الدخول من جديد حتى لو كانت الكوكيز موجودة
REMEMBER_TOKEN_DAYS = 30


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

    # ---------------------------------------------------------- "تذكرني"

    def create_remember_token(self, user_id: int) -> str:
        """
        يولّد توكن عشوائي جديد للمستخدم ويخزّن نسخته المشفّرة فقط (bcrypt) في القاعدة.
        يُرجع التوكن الخام مرة واحدة فقط - هذا ما يُخزَّن في كوكيز المتصفح.
        """
        user = self._get_or_raise(user_id)
        token = secrets.token_urlsafe(32)
        user.remember_token_hash = hash_password(token)
        user.remember_token_expires = datetime.now(timezone.utc) + timedelta(days=REMEMBER_TOKEN_DAYS)
        return token

    def authenticate_by_token(self, user_id: int, token: str) -> User | None:
        """يتحقق من توكن "تذكرني" القادم من الكوكيز. يرجع None بصمت عند أي فشل (لا يرفع استثناء)."""
        user = self._users.get_by_id(user_id)
        if user is None or not user.is_active or not user.remember_token_hash:
            return None

        expires = user.remember_token_expires
        if expires is not None:
            # SQLite لا يخزّن معلومة المنطقة الزمنية فعلياً حتى لو كان العمود DateTime(timezone=True)،
            # فقد يعود التاريخ بدون tzinfo (naive) رغم أنه كان aware عند الحفظ. نطبّعه هنا كـ UTC
            # قبل المقارنة لتفادي TypeError: can't compare offset-naive and offset-aware datetimes.
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires < datetime.now(timezone.utc):
                return None

        if not verify_password(token, user.remember_token_hash):
            return None
        return user
        

    def clear_remember_token(self, user_id: int) -> None:
        """إبطال توكن "تذكرني" الحالي (تسجيل الخروج الكامل، أو عند الاشتباه بمشكلة أمنية)."""
        user = self._users.get_by_id(user_id)
        if user is not None:
            user.remember_token_hash = None
            user.remember_token_expires = None

    def _get_or_raise(self, user_id: int) -> User:
        user = self._users.get_by_id(user_id)
        if user is None:
            from core.exceptions import ValidationError
            raise ValidationError("المستخدم غير موجود.")
        return user
