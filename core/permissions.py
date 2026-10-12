
from collections.abc import Iterable

from core.enums import UserRole
from core.exceptions import PermissionDeniedError

ADMIN_ONLY_PAGES = frozenset({"users"})
ALWAYS_ALLOWED_PAGES = frozenset({"account"})

_VIEWER_PAGES = frozenset({
    "home", "dashboard", "reports", "candidates", "jobs", "pipeline",
    "interviews", "offers", "organization",
})

_ROLE_PAGES: dict[str, frozenset[str] | None] = {
    UserRole.ADMIN.value: None,
    UserRole.RECRUITER.value: None,
    UserRole.VIEWER.value: _VIEWER_PAGES,
}


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
    return role in (UserRole.ADMIN.value, UserRole.RECRUITER.value)


def can_bulk(role: str | None) -> bool:
    return role == UserRole.ADMIN.value


def require_modify(role: str | None) -> None:
    if not can_modify(role):
        raise PermissionDeniedError("ليست لديك صلاحية تعديل البيانات.")


def require_bulk(role: str | None) -> None:
    if not can_bulk(role):
        raise PermissionDeniedError("هذه العملية الكمية من صلاحيات الأدمن فقط.")
