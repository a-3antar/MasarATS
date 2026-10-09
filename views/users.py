"""إدارة المستخدمين (للأدمن): الدور، التفعيل، الصفحات المسموحة، إعادة تعيين كلمة المرور، وإنشاء مستخدم."""

import pandas as pd
import streamlit as st

from core.enums import UserRole
from core.exceptions import SmartATSError
from database.database import get_db_session
from services.auth_service import AuthService
from ui.navigation import PAGES

_ROLE_LABELS = {
    UserRole.ADMIN.value: "أدمن (كل الصلاحيات)",
    UserRole.RECRUITER.value: "مسؤول توظيف",
    UserRole.VIEWER.value: "قراءة فقط",
}
_ROLES = list(_ROLE_LABELS)
# الصفحات القابلة للتخصيص (صفحتا «حسابي» و«المستخدمون» لهما قواعد ثابتة)
_CONFIGURABLE = {label: key for label, key in PAGES.items() if key not in ("account", "users")}
_LABEL_BY_KEY = {key: label for label, key in _CONFIGURABLE.items()}


def _run(action, success: str) -> None:
    try:
        with get_db_session() as session:
            action(AuthService(session))
    except SmartATSError as exc:
        st.error(str(exc))
        return
    st.toast(success)
    st.rerun()


def _render_create_user() -> None:
    with st.expander("➕ إنشاء مستخدم جديد"):
        with st.form("admin_create_user", clear_on_submit=True):
            full_name = st.text_input("الاسم الكامل")
            username = st.text_input("اسم المستخدم (بالإنجليزية)")
            email = st.text_input("البريد الإلكتروني")
            password = st.text_input("كلمة المرور المبدئية", type="password")
            role = st.selectbox("الدور", _ROLES, index=_ROLES.index(UserRole.RECRUITER.value),
                                format_func=_ROLE_LABELS.get)
            submitted = st.form_submit_button("إنشاء", type="primary")
        if submitted:
            _run(lambda s: s.register_user(username, email, full_name, password, UserRole(role)),
                 "تم إنشاء المستخدم ✅")


def _render_access_form(user, acting_id: int) -> None:
    uid = user.id
    with st.form(f"access_form_{uid}"):
        role = st.selectbox("الدور", _ROLES, index=_ROLES.index(user.role) if user.role in _ROLES else 1,
                            format_func=_ROLE_LABELS.get, key=f"u_role_{uid}")
        active = st.checkbox("الحساب مفعّل", value=user.is_active, key=f"u_active_{uid}")
        custom = st.checkbox("تخصيص الصفحات المسموحة (بدل الافتراضي حسب الدور)",
                             value=user.allowed_pages is not None, key=f"u_custom_{uid}")
        picked = st.multiselect(
            "الصفحات المسموحة", list(_CONFIGURABLE),
            default=[_LABEL_BY_KEY[k] for k in (user.allowed_pages or []) if k in _LABEL_BY_KEY],
            key=f"u_pages_{uid}",
        )
        st.caption("الأدمن يصل لكل الصفحات دائماً. «حسابي» متاحة للجميع. التغيير يسري عند تسجيل دخول المستخدم القادم.")
        saved = st.form_submit_button("💾 حفظ الصلاحيات", type="primary")
    if saved:
        pages = [_CONFIGURABLE[label] for label in picked] if custom else None
        _run(lambda s: s.update_user_access(uid, role=role, is_active=active,
                                            allowed_pages=pages, acting_user_id=acting_id),
             "تم حفظ الصلاحيات ✅")


def _render_password_form(user) -> None:
    with st.form(f"admin_pw_form_{user.id}", clear_on_submit=True):
        new = st.text_input("كلمة مرور جديدة للمستخدم", type="password")
        submitted = st.form_submit_button("🔑 إعادة تعيين كلمة المرور")
    if submitted:
        _run(lambda s: s.admin_set_password(user.id, new), "تم تغيير كلمة المرور ✅")


def render() -> None:
    st.header("👥 المستخدمون والصلاحيات")
    current = st.session_state.get("user") or {}
    if current.get("role") != UserRole.ADMIN.value:
        st.error("هذه الصفحة للأدمن فقط.")
        return

    with get_db_session() as session:
        users = AuthService(session).list_users()

    st.dataframe(
        pd.DataFrame([
            {"المستخدم": u.username, "الاسم": u.full_name, "البريد": u.email,
             "الدور": _ROLE_LABELS.get(u.role, u.role), "مفعّل": "✅" if u.is_active else "⛔",
             "صفحات مخصصة": "نعم" if u.allowed_pages is not None else "-"}
            for u in users
        ]),
        hide_index=True, width="stretch",
    )

    _render_create_user()

    labels = {f"{u.full_name} (@{u.username})": u for u in users}
    chosen = labels[st.selectbox("اختر مستخدماً للتعديل", list(labels), key="users_pick")]
    col_access, col_pw = st.columns(2)
    with col_access, st.container(border=True):
        _render_access_form(chosen, current["id"])
    with col_pw, st.container(border=True):
        _render_password_form(chosen)