"""مساعدات صلاحيات للصفحات (تعتمد على المستخدم الحالي في الجلسة)."""

from core.auth_context import get_current_role
from core.enums import UserRole
from core.permissions import can_modify


def can_edit() -> bool:
    return can_modify(get_current_role())


def is_admin() -> bool:
    return get_current_role() == UserRole.ADMIN.value