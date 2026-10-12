
from core.permissions import require_bulk


def get_current_role() -> str | None:
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
    role = get_current_role()
    if role is not None:
        require_bulk(role)
