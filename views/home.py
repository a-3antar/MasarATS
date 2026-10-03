"""الصفحة الرئيسية كمركز قيادة للتوظيف: سؤال/بحث بلغة طبيعية، إجراءات سريعة، مؤشرات، مسار التوظيف،
وما يحتاج انتباهك. الأرقام كلها من HomeService (القاعدة الفعلية) والبحث يعيد استخدام SearchService
عبر دوال صفحة المرشحين المخزّنة مؤقتاً - لا منطق أعمال ولا نظام بحث ثانٍ هنا."""

import streamlit as st

from ai.schemas import CandidateSearchFilters
from core.exceptions import AIServiceError
from database.database import get_db_session
from services.home_service import AttentionItem, HomeService
from ui import components
from ui import job_components as jobs_ui
from ui.navigation import OPEN_CREATE_JOB, OPEN_CREATE_OFFER, go_to

_CACHE_TTL = 15
_ASK_KEY = "home_ask_query"
_MAX_ASK_RESULTS = 5
_ACTION_COLUMNS = 3

# (أيقونة، عنوان، توضيح، مفتاح الصفحة، قيم session_state، إجراء أساسي؟)
_QUICK_ACTIONS = [
    ("📄", "إضافة سيرة ذاتية", "ارفع ملفات PDF أو Word وسيستخرج النظام البيانات تلقائياً.", "upload_cv", {}, True),
    ("💼", "إنشاء وظيفة", "حدّد الوظيفة المطلوبة ومتطلباتها.", "jobs", {OPEN_CREATE_JOB: True}, False),
    ("🎯", "البحث عن مرشحين", "اعرض أنسب المرشحين لكل وظيفة مع شرح الدرجة.", "matching", {}, False),
    ("🗓️", "جدولة مقابلة", "اختر المرشح والوظيفة وحدّد الموعد.", "interviews", {}, False),
    ("📨", "إنشاء عرض", "أصدر عرضاً لمرشح وصل لمرحلة متقدمة.", "offers", {OPEN_CREATE_OFFER: True}, False),
    ("👤", "إضافة مرشح", "أدخل بيانات مرشح يدوياً.", "candidates", {}, False),
]


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def _home_data() -> dict:
    with get_db_session() as session:
        return HomeService(session).overview()


# ------------------------------------------------------------ اسأل SmartATS

def _search(query: str) -> tuple[list[tuple], str | None, dict]:
    """
    بحث بلغة طبيعية عبر نفس دوال صفحة المرشحين (SearchService + كاش Gemini)،
    مع الرجوع للبحث النصي العادي إن فشل الفهم الذكي. يرجع (النتائج [(مرشح، سبب)]، وصف الفلاتر أو None، ملخص المطابقة).
    """
    from views import candidates as candidates_view

    data = candidates_view._load_data()
    candidates = data["candidates"]
    try:
        found = candidates_view._smart_search(query)
    except AIServiceError:
        rows = [(c, "") for c in candidates if candidates_view._text_match(c, query)]
        return rows, None, data["summary"]

    by_id = {c.id: c for c in candidates}
    rows = [(by_id[cid], reason) for cid, reason in found["results"] if cid in by_id]
    description = candidates_view._describe_filters(CandidateSearchFilters(**found["filters"]))
    return rows, description, data["summary"]


def _clear_ask() -> None:
    st.session_state.pop(_ASK_KEY, None)


def _render_ask_results(query: str) -> None:
    rows, interpreted, summary = _search(query)
    with st.container(border=True):
        if interpreted is None:
            st.caption("تعذّر الفهم الذكي للطلب، فتم استخدام البحث النصي العادي.")
        else:
            st.caption(f"🔎 فهمنا طلبك هكذا: {interpreted}")

        if not rows:
            components.empty_state(
                "🔎", "لم نجد مرشحين مطابقين", "جرّب وصفاً أبسط، أو أضف سيراً ذاتية جديدة لقاعدة المرشحين.",
                [("📄 رفع سيرة ذاتية", "upload_cv", None)], key="home_ask_empty",
            )
            st.button("✖ إخفاء", key="home_ask_clear_empty", on_click=_clear_ask)
            return

        st.markdown(f"**وُجد {len(rows)} مرشح**")
        for candidate, reason in rows[:_MAX_ASK_RESULTS]:
            best = (summary.get(candidate.id) or {}).get("best")
            details = [
                candidate.current_position,
                f"{candidate.total_experience_years:g} سنة خبرة" if candidate.total_experience_years is not None else None,
                f"أفضل مطابقة {best:g}%" if best is not None else None,
                reason or None,
            ]
            col_info, col_open = st.columns([5, 1])
            col_info.markdown(f"**{candidate.full_name}**")
            col_info.caption(" · ".join(d for d in details if d) or "-")
            col_open.button(
                "عرض", key=f"home_ask_open_{candidate.id}", on_click=go_to, args=("candidates",), width="stretch",
                kwargs={"candidates_query": candidate.candidate_code or candidate.full_name,
                        "candidates_smart_toggle": False},
            )

        col_all, col_hide, _ = st.columns([2, 1, 3])
        if len(rows) > _MAX_ASK_RESULTS:
            col_all.button(
                f"عرض كل النتائج ({len(rows)})", key="home_ask_all", on_click=go_to, args=("candidates",),
                kwargs={"candidates_query": query, "candidates_smart_toggle": True}, type="primary",
            )
        col_hide.button("✖ إخفاء", key="home_ask_clear", on_click=_clear_ask)


def _render_ask_box() -> None:
    with st.form("home_ask_form"):
        col_query, col_submit = st.columns([6, 1])
        query = col_query.text_input(
            "اسأل SmartATS", label_visibility="collapsed",
            placeholder="ابحث عن مرشحين... مثال: مدير إنتاج بخبرة أكثر من 10 سنوات في البلاستيك والحقن والبثق",
        )
        submitted = col_submit.form_submit_button("🔍 بحث", type="primary", width="stretch")
    if submitted and query.strip():
        st.session_state[_ASK_KEY] = query.strip()

    active = st.session_state.get(_ASK_KEY)
    if active:
        _render_ask_results(active)


# ------------------------------------------------------------ الأقسام

def _render_quick_actions() -> None:
    st.markdown("#### ⚡ ابدأ من هنا")
    columns = st.columns(_ACTION_COLUMNS)
    for index, (icon, title, hint, page, state, primary) in enumerate(_QUICK_ACTIONS):
        with columns[index % _ACTION_COLUMNS], st.container(border=True):
            st.markdown(f"**{icon} {title}**")
            st.caption(hint)
            st.button(
                "ابدأ", key=f"home_qa_{index}", on_click=go_to, args=(page,), kwargs=state,
                type="primary" if primary else "secondary", width="stretch",
            )


def _render_onboarding() -> None:
    """ترحيب لمساحة عمل فارغة. الحالة مشتقة من البيانات نفسها (لا مرشحين ولا وظائف) فلا نخزّن شيئاً."""
    with st.container(border=True):
        st.markdown("### 👋 مرحباً بك في SmartATS AI")
        st.write("ابنِ مسار التوظيف الخاص بك في 3 خطوات:")
        st.markdown(
            "1. **أضف المرشحين** — ارفع سيرهم الذاتية أو أدخلهم يدوياً.\n"
            "2. **أنشئ وظيفة** — حدّد المطلوب وسيقترح النظام المتطلبات.\n"
            "3. **افرز المرشحين وقابلهم** — راجع الأنسب، ثم جدول المقابلات."
        )
        st.markdown("**هل لديك سير ذاتية جاهزة؟**")
        col_yes, col_no = st.columns(2)
        col_yes.button(
            "✅ نعم — رفع السير الذاتية", key="home_onb_yes", on_click=go_to, args=("upload_cv",),
            type="primary", width="stretch",
        )
        col_no.button(
            "➕ لا — أنشئ وظيفة أولاً", key="home_onb_no", on_click=go_to, args=("jobs",),
            kwargs={OPEN_CREATE_JOB: True}, width="stretch",
        )


def _render_metrics(kpis: dict) -> None:
    items = [
        ("👥 المرشحون", "total_candidates"), ("💼 وظائف مفتوحة", "open_jobs"),
        ("🗓️ مقابلات مجدولة", "scheduled_interviews"), ("📨 عروض", "offers"), ("✅ تم تعيينهم", "hired"),
    ]
    for column, (label, key) in zip(st.columns(len(items)), items):
        column.metric(label, kpis[key])


def _render_pipeline(pipeline: list[tuple[str, int]]) -> None:
    with st.container(border=True):
        st.markdown("**🔻 مسار التوظيف**")
        st.markdown(jobs_ui.funnel_html(pipeline), unsafe_allow_html=True)
        st.caption("عدد المرشحين في كل مرحلة حالياً.")


def _render_attention(items: list[AttentionItem]) -> None:
    st.markdown("#### 🔔 تحتاج انتباهك")
    if not items:
        st.success("لا توجد عناصر تحتاج إجراءً الآن ✅")
        return
    for index, item in enumerate(items):
        with st.container(border=True):
            col_text, col_action = st.columns([4, 1], vertical_alignment="center")
            col_text.markdown(f"{item.icon} {item.message}")
            col_action.button(
                item.action_label, key=f"home_attn_{index}", on_click=go_to, args=(item.target,), width="stretch",
            )


# ------------------------------------------------------------ الصفحة

def render() -> None:
    jobs_ui.inject_css()
    user = st.session_state.get("user") or {}
    data = _home_data()

    st.title("🧩 SmartATS AI")
    st.markdown(f"### مرحباً {user.get('full_name', '')} 👋 — ماذا تريد أن تفعل اليوم؟")
    _render_ask_box()
    _render_quick_actions()

    if data["is_new_workspace"]:
        _render_onboarding()
        return

    st.divider()
    _render_metrics(data["kpis"])
    _render_pipeline(data["pipeline"])
    _render_attention(data["attention"])
