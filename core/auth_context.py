"""المستخدم/الدور الحالي لأي كود (واجهة، خدمات، حدث قاعدة البيانات) دون تمرير الدور يدوياً.

خيوط الخلفية والسكربتات (بلا سياق Streamlit) تُعتبر عمليات نظام بلا قيود (role = None)،
والواجهة تمنع الوصول لها أصلاً.
"""

from core.permissions import require_bulk


def get_current_role() -> str | None:
    """دور المستخدم المسجَّل في جلسة Streamlit الحالية، أو None خارج أي جلسة/قبل تسجيل الدخول."""
    try:
        import streamlit as st
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        if get_script_run_ctx() is None:
            return None
        user = st.session_state.get("user")
    except Exception:  # noqa: BLE001
        return None
    return (user or {}).get("role")


def enforce_bulk() -> None:
    """يرفع PermissionDeniedError إن كان المستخدم الحالي ليس أدمن (يتجاهل عمليات النظام)."""
    role = get_current_role()
    if role is not None:
        require_bulk(role)