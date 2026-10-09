"""
SmartATS AI - نقطة الدخول الرئيسية.

تحتوي هذه الطبقة على:
- تهيئة قاعدة البيانات
- تسجيل الدخول / إنشاء حساب جديد / نسيت كلمة المرور (مع خيار "تذكرني")
- الشريط الجانبي (التنقل + قائمة «＋ جديد» العامة) وتوجيه الصفحات

لا تحتوي هذه الطبقة (app.py) على أي منطق أعمال أو استعلامات قاعدة بيانات
مباشرة — كل ذلك يمر عبر services/ كما تنص المعمارية.
"""

import importlib
import time
import json
import streamlit as st

from core.enums import UserRole
from core.exceptions import AuthenticationError, InactiveUserError, SmartATSError, UserAlreadyExistsError
from core.logging import setup_logging
from database.database import get_db_session, init_db
from services.auth_service import REMEMBER_TOKEN_DAYS, AuthService
from ui.navigation import NAV_KEY, OPEN_CREATE_JOB, OPEN_CREATE_OFFER, PAGES, go_to
from ui.assistant import render_sidebar_assistant
from core.permissions import can_access_page, can_modify


st.set_page_config(page_title="SmartATS AI", page_icon="🧩", layout="wide")


@st.cache_resource
def _bootstrap() -> None:
    """تُنفَّذ مرة واحدة فقط عند أول تشغيل للتطبيق (بفضل cache_resource)."""
    setup_logging()
    init_db()


_bootstrap()


# ---------------------------------------------------------- كوكيز "تذكرني"
try:
    from streamlit_cookies_controller import CookieController

    _cookies = CookieController(key="smartats_cookie_controller")
    _COOKIES_AVAILABLE = True
except ImportError:
    _cookies = None
    _COOKIES_AVAILABLE = False

_COOKIE_AUTH = "smartats_auth"
_PENDING_REMEMBER_KEY = "_pending_remember"
_RESET_EMAIL_KEY = "_reset_email"

# إجراءات قائمة «＋ جديد»: (النص، مفتاح الصفحة، قيم session_state). لا نعرض إلا ما هو مدعوم فعلاً.
_NEW_ACTIONS = [
    ("📄 رفع سيرة ذاتية", "upload_cv", {}),
    ("👤 إضافة مرشح", "candidates", {}),
    ("💼 إنشاء وظيفة", "jobs", {OPEN_CREATE_JOB: True}),
    ("🗓️ جدولة مقابلة", "interviews", {}),
    ("📨 إنشاء عرض", "offers", {OPEN_CREATE_OFFER: True}),
]


def _session_user(user) -> dict:
    """بيانات المستخدم المحفوظة في session_state (بما فيها الصفحات المخصصة إن وُجدت)."""
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
        "allowed_pages": user.allowed_pages,
    }


def _set_remember_cookie(user_id: int, token: str) -> bool:
    """يكتب كوكيز "تذكرني". يرجع False إن لم يكن الـ controller جاهزاً بعد (يُعاد المحاولة في الدورة التالية)."""
    if not _COOKIES_AVAILABLE:
        return True

    # getAll() تُهيّئ القاموس الداخلي للـ controller؛ قبلها يكون None ويفشل set() بـ TypeError
    if _cookies.getAll() is None:
        return False

    max_age = REMEMBER_TOKEN_DAYS * 24 * 3600
    payload = json.dumps(
        {"uid": int(user_id), "token": token},
        separators=(",", ":"),
    )

    try:
        _cookies.set(_COOKIE_AUTH, payload, max_age=max_age)
    except TypeError:
        return False
    return True


def _clear_remember_cookie() -> None:
    if not _COOKIES_AVAILABLE:
        return

    _cookies.remove(_COOKIE_AUTH)


def _apply_pending_remember_cookie() -> None:
    pending = st.session_state.get(_PENDING_REMEMBER_KEY)
    if not pending:
        return

    if _set_remember_cookie(*pending):
        st.session_state.pop(_PENDING_REMEMBER_KEY, None)
        time.sleep(0.5)
        st.rerun()
    # غير ذلك: نُبقي القيمة المعلّقة، وسيُعاد المحاولة تلقائياً عند الـ rerun
    # التالي الذي يُطلقه المكوّن بعد وصول الكوكيز من المتصفح.


def _try_auto_login() -> None:
    """يحاول تسجيل الدخول تلقائياً من كوكيز "تذكرني" إن وُجدت وكانت صالحة."""
    if not _COOKIES_AVAILABLE or st.session_state.get("user") is not None:
        return

    all_cookies = _cookies.getAll() or {}

    raw_auth = all_cookies.get(_COOKIE_AUTH)
    if not raw_auth:
        return

    try:
        payload = json.loads(raw_auth)
        uid = int(payload["uid"])
        token = str(payload["token"])

        if not uid or not token:
            return

        with get_db_session() as session:
            user = AuthService(session).authenticate_by_token(uid, token)
            if user is not None:
                st.session_state.user = _session_user(user)
            else:
                _clear_remember_cookie()

    except (ValueError, TypeError, KeyError, json.JSONDecodeError, SmartATSError):
        _clear_remember_cookie()


def _init_session_state() -> None:
    if "user" not in st.session_state:
        st.session_state.user = None
    _apply_pending_remember_cookie()
    _try_auto_login()


def _forgot_password_view() -> None:
    """خطوتان: (1) إرسال كود للبريد  (2) إدخال الكود وكلمة المرور الجديدة."""
    email = st.session_state.get(_RESET_EMAIL_KEY)

    if not email:
        with st.form("forgot_form"):
            entered = st.text_input("البريد الإلكتروني المسجّل")
            submitted = st.form_submit_button("📧 إرسال كود الاستعادة", width='stretch')
        if submitted:
            try:
                with get_db_session() as session:
                    AuthService(session).request_password_reset(entered)
                st.session_state[_RESET_EMAIL_KEY] = entered.strip().lower()
                st.rerun()
            except SmartATSError as exc:
                st.error(str(exc))
        return

    st.info(f"إن كان «{email}» مسجّلاً فقد أُرسل إليه كود من 6 أرقام (صالح 30 دقيقة).")
    with st.form("reset_form"):
        code = st.text_input("الكود المرسل للبريد")
        new_password = st.text_input("كلمة المرور الجديدة", type="password")
        confirm = st.text_input("تأكيد كلمة المرور الجديدة", type="password")
        submitted = st.form_submit_button("🔑 تعيين كلمة المرور", width='stretch')
    if submitted:
        if new_password != confirm:
            st.error("كلمتا المرور غير متطابقتين.")
        else:
            try:
                with get_db_session() as session:
                    AuthService(session).reset_password_with_code(email, code, new_password)
                st.session_state.pop(_RESET_EMAIL_KEY, None)
                st.success("تم تغيير كلمة المرور ✅ يمكنك تسجيل الدخول الآن من تبويب «تسجيل الدخول».")
            except SmartATSError as exc:
                st.error(str(exc))
    if st.button("↩️ إرسال كود جديد / تغيير البريد", key="reset_back"):
        st.session_state.pop(_RESET_EMAIL_KEY, None)
        st.rerun()


def _login_view() -> None:
    st.title("🧩 SmartATS AI")
    st.caption("نظام إدارة التوظيف المدعوم بالذكاء الاصطناعي")

    tab_login, tab_register, tab_forgot = st.tabs(["تسجيل الدخول", "إنشاء حساب جديد", "نسيت كلمة المرور"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("اسم المستخدم")
            password = st.text_input("كلمة المرور", type="password")
            remember_me = st.checkbox(
                "تذكرني على هذا الجهاز",
                value=True,
                disabled=not _COOKIES_AVAILABLE,
                help=None if _COOKIES_AVAILABLE else "ثبّت streamlit-cookies-controller لتفعيل هذا الخيار.",
            )
            submitted = st.form_submit_button("دخول", width='stretch')

        if submitted:
            try:
                with get_db_session() as session:
                    auth_service = AuthService(session)
                    user = auth_service.authenticate(username, password)
                    st.session_state.user = _session_user(user)
                    token = None
                    if remember_me and _COOKIES_AVAILABLE:
                        token = auth_service.create_remember_token(user.id)
                        user_id = user.id
                if token:
                    st.session_state[_PENDING_REMEMBER_KEY] = (user_id, token)
                st.rerun()
            except (AuthenticationError, InactiveUserError) as exc:
                st.error(str(exc))
            except SmartATSError as exc:
                st.error(f"حدث خطأ: {exc}")

    with tab_register:
        with st.form("register_form"):
            full_name = st.text_input("الاسم الكامل").title()
            new_username = st.text_input("اسم المستخدم (بالإنجليزية، بدون مسافات)")
            new_email = st.text_input("البريد الإلكتروني")
            new_password = st.text_input("كلمة المرور", type="password")
            new_password_confirm = st.text_input("تأكيد كلمة المرور", type="password")
            register_submitted = st.form_submit_button("إنشاء الحساب", width='stretch')

        if register_submitted:
            if new_password != new_password_confirm:
                st.error("كلمتا المرور غير متطابقتين.")
            else:
                try:
                    with get_db_session() as session:
                        auth_service = AuthService(session)
                        role = UserRole.ADMIN if not auth_service.has_any_user() else UserRole.RECRUITER
                        auth_service.register_user(
                            username=new_username,
                            email=new_email,
                            full_name=full_name,
                            password=new_password,
                            role=role,
                        )
                    st.success("تم إنشاء الحساب بنجاح. يمكنك تسجيل الدخول الآن من التبويب المجاور.")
                except UserAlreadyExistsError as exc:
                    st.error(str(exc))
                except SmartATSError as exc:
                    st.error(str(exc))

    with tab_forgot:
        _forgot_password_view()


def _render_new_menu() -> None:
    """قائمة «＋ جديد» العامة: وصول مباشر لأهم الإجراءات من أي صفحة."""
    with st.popover("＋ جديد"):
        for index, (label, page_key, state) in enumerate(_NEW_ACTIONS):
            st.button(label, key=f"new_action_{index}", on_click=go_to, args=(page_key,), kwargs=state)


def main() -> None:
    _init_session_state()
    if st.session_state.user is None:
        _login_view()
    else:
        _authenticated_view()


def _authenticated_view() -> None:
    user = st.session_state.user
    role = user["role"]
    allowed = user.get("allowed_pages")
    pages = {label: key for label, key in PAGES.items() if can_access_page(role, key, allowed)}

    current = st.session_state.get(NAV_KEY)
    if current not in pages:
        if current in PAGES:  # انتقال برمجي (go_to) لصفحة غير مسموحة
            st.toast("ليست لديك صلاحية الوصول لهذه الصفحة.")
        st.session_state[NAV_KEY] = next(iter(pages))

    with st.sidebar:
        st.markdown(f"**{user['full_name']}**")
        st.caption(f"@{user['username']} · {role}")
        if can_modify(role):
            _render_new_menu()
            render_sidebar_assistant()
        st.divider()
        selected_page = st.radio("التنقل", list(pages), label_visibility="collapsed", key=NAV_KEY)
        st.divider()
        if st.button("تسجيل الخروج", width='stretch'):
            _clear_remember_cookie()
            st.session_state.user = None
            st.rerun()

    # اسم الصفحة = اسم الوحدة داخل views/ وكلها تعرّف render()
    importlib.import_module(f"views.{pages[selected_page]}").render()


if __name__ == "__main__":
    main()