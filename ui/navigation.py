"""عناوين صفحات التنقل ومساعد الانتقال بينها (callback) - مصدر واحد للأسماء بدل تكرارها في كل صفحة."""

import streamlit as st

NAV_KEY = "nav_page"  # مفتاح radio التنقل في app.py

# ترتيب الصفحات يتبع رحلة التوظيف: سيرة ← مرشح ← وظيفة ← بحث عن مرشحين ← مقابلة ← عرض.
# العناوين نفسها المستخدمة في الصفحات الأخرى (candidate_profile / jobs / organization / offers)
# عند الانتقال البرمجي، فلا تغيّرها دون تحديث تلك الصفحات.

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
}
_LABEL_BY_KEY = {key: label for label, key in PAGES.items()}

# أعلام تفتح نافذة الإنشاء فور الوصول للصفحة (تستهلكها jobs.render و offers.render)
OPEN_CREATE_JOB = "open_create_job"
OPEN_CREATE_OFFER = "open_create_offer"

OFFER_PREFILL_APP = "offer_prefill_app"              # معرّف التقديم المراد إنشاء عرض له
OFFER_PREFILL_CANDIDATE = "offer_prefill_candidate"  # معرّف المرشح (يُختار أول تقديم مؤهل له)


def go_to(page_key: str, **state) -> None:
    """
    ينقل المستخدم لصفحة ويضبط أي قيم session_state إضافية (فلاتر، أعلام...).
    يُستخدم كـ on_click فقط، لأن تعديل مفتاح radio لا يجوز بعد رسمه في نفس الدورة.
    """
    st.session_state[NAV_KEY] = _LABEL_BY_KEY[page_key]
    st.session_state.update(state)
