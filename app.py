"""
SmartATS AI - نقطة الدخول الرئيسية.

هذه المرحلة (Phase 0/1) تحتوي فقط على:
- تهيئة قاعدة البيانات
- تسجيل الدخول / إنشاء حساب جديد (مع خيار "تذكرني")
- صفحة رئيسية بسيطة بعد الدخول

لا تحتوي هذه الطبقة (app.py) على أي منطق أعمال أو استعلامات قاعدة بيانات
مباشرة — كل ذلك يمر عبر services/auth_service.py كما تنص المعمارية.
"""

import streamlit as st

from core.enums import UserRole
from core.exceptions import AuthenticationError, InactiveUserError, SmartATSError, UserAlreadyExistsError
from core.logging import setup_logging
from database.database import get_db_session, init_db
from services.auth_service import REMEMBER_TOKEN_DAYS, AuthService

st.set_page_config(page_title="SmartATS AI", page_icon="🧩", layout="wide")


@st.cache_resource
def _bootstrap() -> None:
    """تُنفَّذ مرة واحدة فقط عند أول تشغيل للتطبيق (بفضل cache_resource)."""
    setup_logging()
    init_db()


_bootstrap()


# ---------------------------------------------------------- كوكيز "تذكرني"
# نستخدم مكتبة streamlit-cookies-controller (pip install streamlit-cookies-controller).
# لو غير مثبّتة، يستمر التطبيق بالعمل بشكل طبيعي لكن بدون خاصية "تذكرني".
try:
    from streamlit_cookies_controller import CookieController

    _cookies = CookieController()
    _COOKIES_AVAILABLE = True
except ImportError:
    _cookies = None
    _COOKIES_AVAILABLE = False

_COOKIE_UID = "smartats_uid"
_COOKIE_TOKEN = "smartats_rtoken"
_PENDING_REMEMBER_KEY = "_pending_remember"  # (user_id, token) بانتظار كتابتها في الكوكيز


def _set_remember_cookies(user_id: int, token: str) -> None:
    if not _COOKIES_AVAILABLE:
        return
    max_age = REMEMBER_TOKEN_DAYS * 24 * 3600
    _cookies.set(_COOKIE_UID, str(user_id), max_age=max_age)
    _cookies.set(_COOKIE_TOKEN, token, max_age=max_age)


def _clear_remember_cookies() -> None:
    if not _COOKIES_AVAILABLE:
        return
    _cookies.remove(_COOKIE_UID)
    _cookies.remove(_COOKIE_TOKEN)


def _apply_pending_remember_cookie() -> None:
    """
    يضبط كوكيز "تذكرني" الفعلية إن كانت مُجدولة من عملية دخول سابقة.
    تُنفَّذ عمداً في تشغيل منفصل (وليس في نفس تشغيل تسجيل الدخول الذي يليه st.rerun())،
    لأن مكوّن الكوكيز (streamlit-cookies-controller) يحتاج دورة عرض كاملة لتنفيذ
    الجافاسكربت الخاص به قبل أي rerun آخر - وإلا لا تُكتب الكوكيز في المتصفح فعلياً.
    """
    pending = st.session_state.pop(_PENDING_REMEMBER_KEY, None)
    if pending:
        _set_remember_cookies(*pending)


def _try_auto_login() -> None:
    """يحاول تسجيل الدخول تلقائياً من كوكيز "تذكرني" إن وُجدت وكانت صالحة."""
    if not _COOKIES_AVAILABLE or st.session_state.get("user") is not None:
        return

    uid = _cookies.get(_COOKIE_UID)
    token = _cookies.get(_COOKIE_TOKEN)
    if not uid or not token:
        return

    try:
        with get_db_session() as session:
            user = AuthService(session).authenticate_by_token(int(uid), token)
            if user is not None:
                st.session_state.user = {
                    "id": user.id,
                    "username": user.username,
                    "full_name": user.full_name,
                    "role": user.role,
                }
    except (ValueError, SmartATSError):
        # كوكيز تالفة أو مستخدم غير صالح - نتجاهلها بصمت ونطلب تسجيل دخول عادي
        _clear_remember_cookies()


def _init_session_state() -> None:
    if "user" not in st.session_state:
        st.session_state.user = None  # dict بسيط: id / username / full_name / role
    _apply_pending_remember_cookie()
    _try_auto_login()


def _login_view() -> None:
    st.title("🧩 SmartATS AI")
    st.caption("نظام إدارة التوظيف المدعوم بالذكاء الاصطناعي")

    tab_login, tab_register = st.tabs(["تسجيل الدخول", "إنشاء حساب جديد"])

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
                    st.session_state.user = {
                        "id": user.id,
                        "username": user.username,
                        "full_name": user.full_name,
                        "role": user.role,
                    }
                    token = None
                    if remember_me and _COOKIES_AVAILABLE:
                        token = auth_service.create_remember_token(user.id)
                        user_id = user.id
                # نجدول ضبط الكوكيز للتشغيل التالي بدل تنفيذه هنا مباشرة قبل rerun
                # (راجع _apply_pending_remember_cookie لسبب هذا التأجيل).
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
                        # أول مستخدم في النظام يصبح Admin تلقائياً، والباقي Recruiter افتراضياً
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


views = {
    "🏠 الرئيسية": "home",
    "📄 رفع سيرة ذاتية": "upload_cv",
    "👥 المرشحون": "candidates",
    "💼 الوظائف": "jobs",
    "🎯 المطابقة": "matching",
    "🗓️ المقابلات": "interviews",
}


def _render_home(user: dict) -> None:
    st.title("🧩 SmartATS AI")
    st.success(f"مرحباً {user['full_name']} 👋")
    st.markdown(
        """
1. **رفع سيرة ذاتية** — ارفع ملف PDF/DOCX/TXT وسيتم إنشاء مرشح تلقائياً.
2. **المرشحون** — تصفّح وابحث في المرشحين، أو أضف واحداً يدوياً.
3. **الوظائف** — أضف وظيفة شاغرة مع المهارات والخبرة المطلوبة.
4. **المطابقة** — اختر وظيفة واحصل على ترتيب المرشحين مع تفسير الدرجة.
        """
    )


def _authenticated_view() -> None:
    user = st.session_state.user

    with st.sidebar:
        st.markdown(f"**{user['full_name']}**")
        st.caption(f"@{user['username']} · {user['role']}")
        st.divider()
        selected_page = st.radio("التنقل", list(views.keys()), label_visibility="collapsed")
        st.divider()
        if st.button("تسجيل الخروج", width='stretch'):
            _clear_remember_cookies()
            st.session_state.user = None
            st.rerun()

    page_key = views[selected_page]

    if page_key == "home":
        _render_home(user)
    elif page_key == "upload_cv":
        from views import upload_cv
        upload_cv.render()
    elif page_key == "candidates":
        from views import candidates
        candidates.render()
    elif page_key == "jobs":
        from views import jobs
        jobs.render()
    elif page_key == "matching":
        from views import matching
        matching.render()
    elif page_key == "interviews":
        from views import interviews
        interviews.render()


def main() -> None:
    _init_session_state()
    if st.session_state.user is None:
        _login_view()
    else:
        _authenticated_view()


if __name__ == "__main__":
    main()