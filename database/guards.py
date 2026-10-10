"""شبكة أمان على مستوى قاعدة البيانات: تمنع الكتابة عن القراءة-فقط وتحدّ الحذف الكمي لغير الأدمن."""

from sqlalchemy import event

from core.auth_context import get_current_role
from core.constants import BULK_DELETE_LIMIT
from core.exceptions import PermissionDeniedError
from core.permissions import can_bulk, can_modify

_ACCOUNT_TABLE = "users"  # المستخدم يغيّر كلمة مروره/آخر دخول حتى لو Viewer


def _has_real_changes(session) -> bool:
    return bool(session.new or session.deleted or any(session.is_modified(o) for o in session.dirty))


def _only_account_changes(session) -> bool:
    changed = [*session.new, *session.deleted, *(o for o in session.dirty if session.is_modified(o))]
    return all(getattr(o, "__tablename__", None) == _ACCOUNT_TABLE for o in changed)


def _check_flush(session, flush_context, instances) -> None:
    role = get_current_role()
    if role is None:  # عملية نظام (خلفية/سكربت/قبل الدخول)
        return
    if not can_modify(role):
        if _has_real_changes(session) and not _only_account_changes(session):
            raise PermissionDeniedError("ليست لديك صلاحية تعديل البيانات (قراءة فقط).")
        return
    if not can_bulk(role) and len(session.deleted) > BULK_DELETE_LIMIT:
        raise PermissionDeniedError("حذف مجموعة كبيرة من السجلات من صلاحيات الأدمن فقط.")


def register_session_guards(session_factory) -> None:
    event.listen(session_factory, "before_flush", _check_flush)