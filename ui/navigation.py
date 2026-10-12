
import streamlit as st

NAV_KEY = "nav_page"


PAGES: dict[str, str] = {
    "🏠 الرئيسية": "home",
    "📄 رفع سيرة ذاتية": "upload_cv",
    "👥 المرشحون": "candidates",
    "💼 الوظائف": "jobs",
    "🧭 مسار التوظيف": "pipeline",
    "🎯 المطابقة": "matching",
    "🗓️ المقابلات": "interviews",
    "📑 العروض": "offers",
    "🏢 الهيكل التنظيمي": "organization",
    "📊 لوحة المعلومات": "dashboard",
    "📈 التقارير": "reports",
    "🔑 حسابي": "account",
    "👥 المستخدمون": "users",
}
_LABEL_BY_KEY = {key: label for label, key in PAGES.items()}

OPEN_CREATE_JOB = "open_create_job"
OPEN_CREATE_OFFER = "open_create_offer"

OFFER_PREFILL_APP = "offer_prefill_app"
OFFER_PREFILL_CANDIDATE = "offer_prefill_candidate"


def go_to(page_key: str, **state) -> None:
    st.session_state[NAV_KEY] = _LABEL_BY_KEY[page_key]
    st.session_state.update(state)
