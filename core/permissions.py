"""
صلاحيات الأدوار. مصدر واحد للحقيقة يستخدمه app.py، وتستطيع الخدمات استدعاء require_modify.
- الأدمن يصل لكل الصفحات دائماً (لا يمكن حبسه خارج النظام).
- allowed_pages (إن وُجدت للمستخدم) تتجاوز الافتراضي حسب الدور.
- صفحة «users» للأدمن فقط، وصفحة «account» متاحة للجميع.
مبدأ الأقل صلاحية: أي دور غير معروف يُعامَل كـ Viewer.
"""

from collections.abc import Iterable

from core.enums import UserRole
from core.exceptions import PermissionDeniedError

ADMIN_ONLY_PAGES = frozenset({"users"})
ALWAYS_ALLOWED_PAGES = frozenset({"account"})

# None = كل الصفحات. القيم = مفاتيح الصفحات في ui/navigation.PAGES
_ROLE_PAGES: dict[str, frozenset[str] | None] = {
    UserRole.ADMIN.value: None,
    UserRole.RECRUITER.value: None,
    UserRole.VIEWER.value: frozenset({"home", "dashboard", "reports"}),
}
_VIEWER_PAGES = _ROLE_PAGES[UserRole.VIEWER.value]


def can_access_page(role: str | None, page_key: str, allowed_pages: Iterable[str] | None = None) -> bool:
    if page_key in ALWAYS_ALLOWED_PAGES or role == UserRole.ADMIN.value:
        return True
    if page_key in ADMIN_ONLY_PAGES:
        return False
    if allowed_pages is not None:
        return page_key in set(allowed_pages)
    allowed = _ROLE_PAGES.get(role or "", _VIEWER_PAGES)
    return allowed is None or page_key in allowed


def can_modify(role: str | None) -> bool:
    """هل يستطيع الدور إنشاء/تعديل/حذف البيانات؟"""
    return role in (UserRole.ADMIN.value, UserRole.RECRUITER.value)


def require_modify(role: str | None) -> None:
    if not can_modify(role):
        raise PermissionDeniedError("ليست لديك صلاحية تعديل البيانات.")