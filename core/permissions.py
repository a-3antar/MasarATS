"""
صلاحيات الأدوار. مصدر واحد للحقيقة يستخدمه app.py، وتستطيع الخدمات استدعاء require_modify
لمنع التعديل من دور القراءة فقط.
مبدأ الأقل صلاحية: أي دور غير معروف يُعامَل كـ Viewer.
"""

from core.enums import UserRole
from core.exceptions import PermissionDeniedError

# None = كل الصفحات. القيم = مفاتيح الصفحات في ui/navigation.PAGES
_ROLE_PAGES: dict[str, frozenset[str] | None] = {
    UserRole.ADMIN.value: None,
    UserRole.RECRUITER.value: None,
    UserRole.VIEWER.value: frozenset({"home", "dashboard", "reports"}),
}
_VIEWER_PAGES = _ROLE_PAGES[UserRole.VIEWER.value]


def can_access_page(role: str | None, page_key: str) -> bool:
    allowed = _ROLE_PAGES.get(role or "", _VIEWER_PAGES)
    return allowed is None or page_key in allowed


def can_modify(role: str | None) -> bool:
    """هل يستطيع الدور إنشاء/تعديل/حذف البيانات؟"""
    return role in (UserRole.ADMIN.value, UserRole.RECRUITER.value)


def require_modify(role: str | None) -> None:
    if not can_modify(role):
        raise PermissionDeniedError("ليست لديك صلاحية تعديل البيانات.")
    