"""صفحة «حسابي»: تغيير كلمة المرور للمستخدم الحالي."""

import streamlit as st

from core.exceptions import SmartATSError
from database.database import get_db_session
from services.auth_service import AuthService


def render() -> None:
    st.header("🔑 حسابي")
    user = st.session_state.get("user") or {}
    st.caption(f"{user.get('full_name', '')} · @{user.get('username', '')} · {user.get('role', '')}")

    st.subheader("تغيير كلمة المرور")
    with st.form("change_password_form", clear_on_submit=True):
        current = st.text_input("كلمة المرور الحالية", type="password")
        new = st.text_input("كلمة المرور الجديدة", type="password")
        confirm = st.text_input("تأكيد كلمة المرور الجديدة", type="password")
        submitted = st.form_submit_button("💾 تغيير", type="primary")

    if not submitted:
        return
    if new != confirm:
        st.error("كلمتا المرور الجديدتان غير متطابقتين.")
        return
    try:
        with get_db_session() as session:
            AuthService(session).change_password(user["id"], current, new)
        st.success("تم تغيير كلمة المرور ✅ (سيُطلب تسجيل الدخول من جديد على الأجهزة التي اخترت «تذكرني» فيها).")
    except SmartATSError as exc:
        st.error(str(exc))