"""
خدمة المصادقة (Authentication Service).
الطبقة الوحيدة التي تتعامل معها الواجهة لتسجيل الدخول، إنشاء الحساب، تغيير كلمة المرور،
استعادتها بالبريد، وإدارة المستخدمين وصلاحياتهم (للأدمن).
"""

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.enums import UserRole
from core.exceptions import (
    AuthenticationError, InactiveUserError, UserAlreadyExistsError, ValidationError,
)
from core.logging import get_logger
from core.security import hash_password, verify_password
from models.user import User
from repositories.user_repository import UserRepository
from services.email_service import EmailService

logger = get_logger(__name__)

# مدة صلاحية "تذكرني" - بعدها يُطلب تسجيل الدخول من جديد حتى لو كانت الكوكيز موجودة
REMEMBER_TOKEN_DAYS = 30
MIN_PASSWORD_LENGTH = 6
RESET_CODE_MINUTES = 30
RESET_CODE_DIGITS = 6
MAX_RESET_ATTEMPTS = 5
_VALID_ROLES = {role.value for role in UserRole}


def _aware(value: datetime) -> datetime:
    """SQLite يعيد التاريخ بدون tzinfo؛ نطبّعه كـ UTC قبل المقارنة."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class AuthService:
    """منطق العمل الخاص بتسجيل المستخدمين ومصادقتهم وإدارتهم."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._users = UserRepository(session)

    # ---------------------------------------------------------- التسجيل والدخول

    @staticmethod
    def _validate_password(password: str) -> None:
        if len(password or "") < MIN_PASSWORD_LENGTH:
            raise ValidationError(f"يجب ألا تقل كلمة المرور عن {MIN_PASSWORD_LENGTH} أحرف.")

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
            raise ValidationError("كل الحقول مطلوبة.")
        self._validate_password(password)

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
        if expires is not None and _aware(expires) < datetime.now(timezone.utc):
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

    # ---------------------------------------------------------- تغيير كلمة المرور

    def _set_password(self, user: User, new_password: str) -> None:
        """يضبط كلمة مرور جديدة ويُبطل "تذكرني" وأي كود استعادة قائم."""
        self._validate_password(new_password)
        user.password_hash = hash_password(new_password)
        user.remember_token_hash = None
        user.remember_token_expires = None
        user.reset_code_hash = None
        user.reset_code_expires = None
        user.reset_attempts = 0

    def change_password(self, user_id: int, current_password: str, new_password: str) -> None:
        """تغيير المستخدم كلمة مروره بنفسه (يتطلب كلمة المرور الحالية)."""
        user = self._get_or_raise(user_id)
        if not verify_password(current_password or "", user.password_hash):
            raise AuthenticationError("كلمة المرور الحالية غير صحيحة.")
        if current_password == new_password:
            raise ValidationError("كلمة المرور الجديدة يجب أن تختلف عن الحالية.")
        self._set_password(user, new_password)
        logger.info("User %s changed own password", user.username)

    def admin_set_password(self, user_id: int, new_password: str) -> None:
        """إعادة تعيين كلمة مرور مستخدم بواسطة الأدمن."""
        user = self._get_or_raise(user_id)
        self._set_password(user, new_password)
        logger.info("Password reset by admin for user %s", user.username)

    # ---------------------------------------------------------- نسيت كلمة المرور (بالبريد)

    def request_password_reset(self, email: str) -> None:
        """
        يرسل كود من 6 أرقام للبريد إن كان مسجّلاً. لا يكشف إن كان البريد موجوداً أم لا
        (يعود بصمت). يرفع ConfigurationError إن لم يُضبط SMTP.
        """
        user = self._users.get_by_email((email or "").strip().lower())
        if user is None or not user.is_active:
            logger.warning("Password reset requested for unknown/inactive email")
            return

        code = "".join(str(secrets.randbelow(10)) for _ in range(RESET_CODE_DIGITS))
        user.reset_code_hash = hash_password(code)
        user.reset_code_expires = datetime.now(timezone.utc) + timedelta(minutes=RESET_CODE_MINUTES)
        user.reset_attempts = 0

        EmailService.send(
            user.email,
            "SmartATS AI - كود استعادة كلمة المرور",
            f"مرحباً {user.full_name},\n\n"
            f"كود استعادة كلمة المرور: {code}\n"
            f"صالح لمدة {RESET_CODE_MINUTES} دقيقة.\n\n"
            "إن لم تطلب هذا الكود فتجاهل الرسالة.",
        )
        logger.info("Password reset code sent to user %s", user.username)

    def reset_password_with_code(self, email: str, code: str, new_password: str) -> None:
        """يتحقق من الكود ويضبط كلمة المرور الجديدة. رسالة خطأ موحّدة لأي فشل."""
        invalid = AuthenticationError("الكود غير صحيح أو منتهي الصلاحية.")
        user = self._users.get_by_email((email or "").strip().lower())
        if user is None or not user.reset_code_hash or user.reset_code_expires is None:
            raise invalid

        if _aware(user.reset_code_expires) < datetime.now(timezone.utc):
            raise invalid
        if (user.reset_attempts or 0) >= MAX_RESET_ATTEMPTS:
            raise AuthenticationError("تجاوزت عدد المحاولات المسموح. اطلب كوداً جديداً.")

        if not verify_password((code or "").strip(), user.reset_code_hash):
            user.reset_attempts = (user.reset_attempts or 0) + 1
            self._session.commit()  # نحفظ عداد المحاولات رغم رفع الاستثناء
            raise invalid

        self._set_password(user, new_password)
        logger.info("Password reset via email code for user %s", user.username)

    # ---------------------------------------------------------- إدارة المستخدمين (للأدمن)

    def list_users(self) -> list[User]:
        return self._users.list_all(limit=1000)

    def _active_admin_count(self) -> int:
        stmt = select(func.count()).select_from(User).where(
            User.role == UserRole.ADMIN.value, User.is_active.is_(True)
        )
        return self._session.scalar(stmt) or 0

    def update_user_access(
        self, user_id: int, *, role: str, is_active: bool,
        allowed_pages: list[str] | None, acting_user_id: int,
    ) -> User:
        """
        يغيّر دور المستخدم وحالته وصفحاته المسموحة (None = الافتراضي حسب الدور).
        يمنع الأدمن من تعطيل نفسه أو إزالة آخر أدمن نشط.
        """
        user = self._get_or_raise(user_id)
        if role not in _VALID_ROLES:
            raise ValidationError(f"دور غير صالح: {role}")

        losing_admin = user.role == UserRole.ADMIN.value and (role != UserRole.ADMIN.value or not is_active)
        if user.id == acting_user_id and losing_admin:
            raise ValidationError("لا يمكنك تغيير دورك أو تعطيل حسابك بنفسك.")
        if losing_admin and self._active_admin_count() <= 1:
            raise ValidationError("لا يمكن إزالة آخر أدمن نشط في النظام.")

        user.role = role
        user.is_active = is_active
        user.allowed_pages = list(allowed_pages) if allowed_pages is not None else None
        if not is_active:
            user.remember_token_hash = None
            user.remember_token_expires = None
        logger.info("Access updated for user %s: role=%s active=%s", user.username, role, is_active)
        return user

    def _get_or_raise(self, user_id: int) -> User:
        user = self._users.get_by_id(user_id)
        if user is None:
            raise ValidationError("المستخدم غير موجود.")
        return user