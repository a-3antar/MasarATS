"""صفحة الوظائف: مؤشرات، بحث وفلاتر، جدول/بطاقات، لوحة تفاصيل، تحليل توظيف وقمع لكل وظيفة.
الإضافة والتعديل داخل نوافذ (dialog) تحمل نموذج الوظيفة وتوليد الذكاء الاصطناعي وبنك الأسئلة.
القسم والمسمى الوظيفي يُختاران من الهيكل التنظيمي (department_id / position_id)."""

import re
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from core.constants import (
    CAREER_LEVELS, DEFAULT_SALARY_CURRENCY, DEFAULT_VACANCIES, EMPLOYMENT_TYPES,
    JOB_STATUSES, MIN_CANDIDATES_PER_JOB,
)
from core.exceptions import AIServiceError, SmartATSError
from database.database import get_db_session
from models.job import Job
from services.export_service import ExportService
from services.job_insights_service import JobInsightsService, JobStats
from services.job_service import JobService
from services.organization_service import OrganizationService
from services.question_bank_service import QuestionBankService
from ui import job_components as ui

# نفس فئات مهارات المرشح حتى تكون المطابقة متناسقة
_LIST_FIELDS: list[tuple[str, str]] = [
    ("🛠️ المهارات الفنية المطلوبة", "required_technical_skills"),
    ("💻 مهارات الكمبيوتر المطلوبة", "required_computer_skills"),
    ("📊 المهارات الإدارية المطلوبة", "required_managerial_skills"),
    ("🤝 المهارات الشخصية المطلوبة", "required_soft_skills"),
    ("➕ مهارات أخرى مطلوبة", "required_skills"),
    ("🏭 مجالات العمل المفضلة", "preferred_industries"),
]
_DEFAULT_STATUS_INDEX = 1  # "Open"

_STATUS_LABELS = {"Draft": "مسودة", "Open": "مفتوحة", "On Hold": "معلّقة", "Closed": "مغلقة"}
_STATUS_ICONS = {"Draft": "⚪", "Open": "🟢", "On Hold": "🟡", "Closed": "🔴"}
_EMPLOYMENT_LABELS = {
    "Full-time": "دوام كامل", "Part-time": "دوام جزئي", "Contract": "عقد",
    "Internship": "تدريب", "Temporary": "مؤقت",
}
_LEVEL_LABELS = {
    "Intern": "متدرب", "Junior": "مبتدئ", "Mid-Level": "متوسط", "Senior": "خبير",
    "Manager": "مدير", "Director": "مدير إدارة", "Executive": "تنفيذي",
}
_DATE_FILTERS = {"كل الأوقات": None, "آخر 7 أيام": 7, "آخر 30 يوماً": 30, "آخر 90 يوماً": 90}
_NONE_LABEL = "— غير محدد —"
_NO_DEPARTMENT = "بدون قسم"

_CACHE_TTL = 30
_CARD_COLUMNS = 3
_SELECTED_KEY = "jobs_selected_id"
_VIEW_LIST, _VIEW_CARDS = "📋 قائمة", "🗂️ بطاقات"
_NAV_KEY, _MATCHING_PAGE, _MATCHING_JOB_KEY = "nav_page", "🎯 المطابقة", "m_job_select"
_AI_DRAFT_KEYS = {"title", "dept", "loc", "desc", "exp"} | {attr for _, attr in _LIST_FIELDS}


# ------------------------------------------------------------ أدوات عامة

def _invalidate_job_related_caches() -> None:
    """
    قوائم الوظائف مخزّنة مؤقتاً في أكثر من صفحة (المطابقة، المقابلات، الهيكل التنظيمي)، ونتيجة
    "الوظائف المناسبة" مخزّنة في بطاقة المرشح. يجب مسحها كلها عند أي تغيير في الوظائف
    حتى لا تظهر بيانات قديمة بعد الحفظ مباشرة.
    """
    _page_data.clear()
    _cached_insight.clear()
    _export_bytes.clear()
    _org_options.clear()
    try:
        from views import matching as _matching
        _matching._cached_jobs.clear()
    except Exception:
        pass
    try:
        from views import interviews as _interviews
        _interviews._cached_jobs.clear()
    except Exception:
        pass
    try:
        from views import candidate_profile as _profile
        _profile.clear_suitable_jobs_cache()
    except Exception:
        pass
    try:
        from views import organization as _organization
        _organization._overview.clear()
    except Exception:
        pass


def _split_items(raw: str) -> list[str]:
    """تقسيم نص مفصول بفاصلة (إنجليزية أو عربية) أو أسطر إلى قائمة نظيفة."""
    return [part.strip() for part in re.split(r"[,،\n]", raw or "") if part.strip()]


def _experience_text(years: float | None) -> str:
    return f"{years:g}+ سنة" if years else "-"


def _salary_text(low: float | None, high: float | None) -> str:
    if low and high:
        return f"{low:,.0f} – {high:,.0f} {DEFAULT_SALARY_CURRENCY}"
    if low or high:
        return f"{(low or high):,.0f} {DEFAULT_SALARY_CURRENCY}"
    return "-"


def _status_label(status: str) -> str:
    return _STATUS_LABELS.get(status, status)


# ------------------------------------------------------------ تحميل البيانات (مخزّنة مؤقتاً)

def _job_to_row(job: Job) -> dict:
    """نسخة بسيطة من الوظيفة (dict) قابلة للتخزين في كاش Streamlit."""
    return {
        "id": job.id, "title": job.title, "department": job.department, "location": job.location,
        "department_id": job.department_id, "position_id": job.position_id,
        "employment_type": job.employment_type, "career_level": job.career_level,
        "reports_to": job.reports_to, "education": job.education,
        "salary_min": job.salary_min, "salary_max": job.salary_max,
        "vacancies": job.vacancies or DEFAULT_VACANCIES,
        "experience": job.required_experience_years, "status": job.status,
        "skills": job.all_required_skills, "created_at": job.created_at,
        "updated_at": job.updated_at or job.created_at,
    }


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def _page_data() -> dict:
    with get_db_session() as session:
        insights = JobInsightsService(session)
        jobs = sorted(JobService(session).list_all(), key=lambda j: j.updated_at or j.created_at, reverse=True)
        return {
            "jobs": [_job_to_row(j) for j in jobs],
            "stats": insights.stats_by_job(),
            "kpis": insights.kpis(),
        }


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def _org_options() -> dict:
    """أقسام ومسميات الهيكل التنظيمي لقوائم الاختيار في نموذج الوظيفة."""
    with get_db_session() as session:
        overview = OrganizationService(session).overview()
    return {"departments": overview["departments"], "positions": overview["positions"]}


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def _cached_insight(job_id: int):
    with get_db_session() as session:
        return JobInsightsService(session).job_insight(job_id)


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def _export_bytes(job_ids: tuple[int, ...]) -> tuple[bytes, bytes]:
    with get_db_session() as session:
        wanted = set(job_ids)
        df = ExportService.jobs_to_dataframe([j for j in JobService(session).list_all() if j.id in wanted])
    return ExportService.to_csv_bytes(df), ExportService.to_excel_bytes(df, "Jobs")


# ------------------------------------------------------------ نموذج الوظيفة (إضافة / تعديل)

def _select_index(options: list[str], value: str | None) -> str:
    return value if value in options else ""


def _department_id_for(name: str | None, departments: list[dict]) -> int | None:
    """معرّف القسم الذي يطابق اسمه النص المعطى (بدون حساسية لحالة الأحرف)، أو None."""
    needle = (name or "").strip().lower()
    if not needle:
        return None
    return next((d["id"] for d in departments if d["name"].strip().lower() == needle), None)


def _form_values_from(job: Job | None, draft: dict | None = None) -> dict:
    """
    القيم المبدئية لحقول النموذج، مفتاحها لاحقة اسم الحقل (title, dept, exp...).
    أولوية القيمة: نتيجة الذكاء الاصطناعي (إن وُجدت وغير فارغة) ثم بيانات الوظيفة الحالية ثم الفراغ.
    "dept" و"pos" يحملان معرّف القسم والمسمى في الهيكل التنظيمي.
    """
    draft = draft or {}
    departments = _org_options()["departments"]

    def pick(field: str, current, empty=""):
        return draft.get(field) or current or empty

    dept_id = _department_id_for(draft.get("department"), departments)
    if dept_id is None and job:
        dept_id = job.department_id or _department_id_for(job.department, departments)

    values = {
        "title": pick("title", job.title if job else None),
        "dept": dept_id,
        "pos": job.position_id if job else None,
        "loc": pick("location", job.location if job else None),
        "desc": pick("description", job.description if job else None),
        "exp": float(pick("required_experience_years", job.required_experience_years if job else None, 0.0)),
        "status": job.status if job and job.status in JOB_STATUSES else JOB_STATUSES[_DEFAULT_STATUS_INDEX],
        "type": _select_index(EMPLOYMENT_TYPES, job.employment_type if job else None),
        "level": _select_index(CAREER_LEVELS, job.career_level if job else None),
        "reports": (job.reports_to if job else None) or "",
        "edu": (job.education if job else None) or "",
        "smin": float((job.salary_min if job else None) or 0.0),
        "smax": float((job.salary_max if job else None) or 0.0),
        "vac": int((job.vacancies if job else None) or DEFAULT_VACANCIES),
    }
    for _, attr in _LIST_FIELDS:
        items = draft.get(attr) or (getattr(job, attr, None) if job else None) or []
        values[attr] = ", ".join(items)
    return values


def _apply_values_to_state(key: str, values: dict, only_non_empty: bool = False) -> None:
    """يكتب القيم في session_state بمفاتيح الحقول. only_non_empty=True لا يمسح الحقول المعبّأة بقيم فارغة."""
    for suffix, value in values.items():
        if only_non_empty and value in ("", 0.0, None):
            continue
        st.session_state[f"{key}_{suffix}"] = value


def _seed_form_state(key: str, job: Job | None) -> None:
    """
    يهيّئ حقول النموذج من بيانات الوظيفة عند غياب مفتاح الحقل فقط، ثم يطبّق مسودة الذكاء
    الاصطناعي المعلّقة (إن وُجدت) قبل رسم الحقول مباشرة (الوقت الوحيد الآمن لتعديل قيمها).
    """
    for suffix, value in _form_values_from(job).items():
        st.session_state.setdefault(f"{key}_{suffix}", value)

    pending = st.session_state.pop(f"{key}_pending_draft", None)
    if pending:
        _apply_values_to_state(key, pending, only_non_empty=True)


def _render_ai_job_generator(key: str) -> None:
    """توليد بيانات الوظيفة من وصف حر. يعمل داخل dialog، فنعيد تشغيل الـ fragment فقط ليبقى مفتوحاً."""
    with st.expander("🤖 توليد بيانات الوظيفة تلقائياً من وصف حر"):
        raw_description = st.text_area(
            "الصق وصف الوظيفة هنا (نص غير منظم)",
            key=f"{key}_ai_raw_desc",
            height=100,
            placeholder="مثال: نحتاج مدير إنتاج لمصنع بلاستيك بخبرة في الحقن والبثق...",
        )
        if st.button("🤖 توليد تلقائياً", key=f"{key}_ai_generate_btn"):
            if not raw_description.strip():
                st.warning("الصق وصف الوظيفة أولاً.")
                return
            try:
                from ai.job_analyzer import analyze_job_description

                with st.spinner("جاري تحليل الوصف..."):
                    result = analyze_job_description(raw_description.strip())
                draft = _form_values_from(None, result.model_dump())
                st.session_state[f"{key}_pending_draft"] = {k: v for k, v in draft.items() if k in _AI_DRAFT_KEYS}
                note = ""
                if result.department and draft["dept"] is None:
                    note = f" — القسم المقترح «{result.department}» غير موجود في الهيكل، اختره يدوياً"
                st.toast("تم التوليد — راجع الحقول وعدّلها قبل الحفظ" + note)
                st.rerun(scope="fragment")
            except AIServiceError as exc:
                st.error(str(exc))


def _job_form_fields(key: str) -> dict:
    """يرسم حقول نموذج الوظيفة ويرجع القيم المُدخلة (القيم المبدئية من session_state عبر _seed_form_state)."""
    org = _org_options()
    dept_names = {d["id"]: d["name"] for d in org["departments"]}
    position_labels = {
        p["id"]: f"{p['title']} — {p['department'] or _NO_DEPARTMENT}" for p in org["positions"]
    }

    title = st.text_input("مسمى الوظيفة *", key=f"{key}_title")
    col_dept, col_pos = st.columns(2)
    with col_dept:
        department_id = st.selectbox(
            "القسم (من الهيكل التنظيمي)", [None, *dept_names], key=f"{key}_dept",
            format_func=lambda v: dept_names.get(v, _NONE_LABEL),
        )
    with col_pos:
        position_id = st.selectbox(
            "المسمى في الهيكل التنظيمي", [None, *position_labels], key=f"{key}_pos",
            format_func=lambda v: position_labels.get(v, _NONE_LABEL),
        )
    st.caption("إن اخترت مسمى بدون قسم يُؤخذ قسمه تلقائياً. أضف الأقسام والمسميات من صفحة «الهيكل التنظيمي».")

    col1, col2 = st.columns(2)
    with col1:
        employment = st.selectbox(
            "نوع التوظيف", [""] + EMPLOYMENT_TYPES, key=f"{key}_type",
            format_func=lambda v: _EMPLOYMENT_LABELS.get(v, _NONE_LABEL),
        )
        reports_to = st.text_input("يتبع لـ (Reports To)", key=f"{key}_reports")
        salary_min = st.number_input("الراتب الأدنى", min_value=0.0, step=500.0, key=f"{key}_smin")
        experience = st.number_input("سنوات الخبرة المطلوبة", min_value=0.0, step=0.5, key=f"{key}_exp")
    with col2:
        location = st.text_input("الموقع", key=f"{key}_loc")
        level = st.selectbox(
            "المستوى الوظيفي", [""] + CAREER_LEVELS, key=f"{key}_level",
            format_func=lambda v: _LEVEL_LABELS.get(v, _NONE_LABEL),
        )
        education = st.text_input("المؤهل الدراسي", key=f"{key}_edu")
        salary_max = st.number_input("الراتب الأعلى", min_value=0.0, step=500.0, key=f"{key}_smax")
        vacancies = st.number_input("عدد الشواغر", min_value=1, step=1, key=f"{key}_vac")
    status = st.selectbox("حالة الوظيفة", JOB_STATUSES, key=f"{key}_status", format_func=_status_label)

    raw_lists: dict[str, str] = {}
    for label, attr in _LIST_FIELDS:
        raw_lists[attr] = st.text_area(f"{label} (مفصولة بفاصلة)", key=f"{key}_{attr}", height=80)

    description = st.text_area("وصف الوظيفة", key=f"{key}_desc")

    return {
        "title": title,
        "department_id": department_id,
        "position_id": position_id,
        "location": location.strip() or None,
        "employment_type": employment or None,
        "career_level": level or None,
        "reports_to": reports_to.strip() or None,
        "education": education.strip() or None,
        "salary_min": salary_min or None,
        "salary_max": salary_max or None,
        "vacancies": int(vacancies),
        "required_experience_years": experience or None,
        "status": status,
        "description": description.strip() or None,
        **{attr: _split_items(raw) for attr, raw in raw_lists.items()},
    }


@st.dialog("➕ إضافة وظيفة جديدة", width="large")
def _create_dialog() -> None:
    _seed_form_state("new", None)
    _render_ai_job_generator("new")
    with st.form("new_job_form"):
        values = _job_form_fields("new")
        submitted = st.form_submit_button("حفظ الوظيفة", type="primary")

    if submitted:
        try:
            with get_db_session() as session:
                JobService(session).create_job(**values)
            for state_key in [k for k in st.session_state if str(k).startswith("new_")]:
                del st.session_state[state_key]
            _invalidate_job_related_caches()
            st.toast("تمت إضافة الوظيفة ✅")
            st.rerun()
        except SmartATSError as exc:
            st.error(str(exc))


def _render_job_details_tab(job_id: int, job: Job) -> None:
    edit_key = f"edit_{job_id}"
    _seed_form_state(edit_key, job)
    _render_ai_job_generator(edit_key)
    with st.form(f"edit_job_form_{job_id}"):
        values = _job_form_fields(edit_key)
        saved = st.form_submit_button("💾 حفظ التعديلات", type="primary")

    if saved:
        try:
            with get_db_session() as session:
                JobService(session).update_job(job_id, **values)
            for state_key in [k for k in st.session_state if str(k).startswith(f"{edit_key}_")]:
                del st.session_state[state_key]
            _invalidate_job_related_caches()
            st.toast("تم حفظ التعديلات ✅")
            st.rerun()
        except SmartATSError as exc:
            st.error(str(exc))

    st.divider()
    confirm = st.checkbox(
        "أؤكد حذف هذه الوظيفة وكل التقديمات المرتبطة بها نهائياً", key=f"confirm_delete_{job_id}"
    )
    if st.button("🗑️ حذف الوظيفة", disabled=not confirm, key=f"delete_job_{job_id}"):
        try:
            with get_db_session() as session:
                JobService(session).delete_job(job_id)
            st.session_state.pop(_SELECTED_KEY, None)
            _invalidate_job_related_caches()
            st.toast("تم حذف الوظيفة 🗑️")
            st.rerun()
        except SmartATSError as exc:
            st.error(str(exc))


def _render_job_questions_tab(job_id: int, job: Job) -> None:
    st.caption(
        "هذه الأسئلة تُحفظ في بنك أسئلة هذه الوظيفة، ويمكن إعادة استخدامها مع أي مرشح "
        "يتقدّم لها لاحقاً من صفحة «المقابلات». كل سؤال في سطر مستقل (أو افصل بينها بعلامة استفهام)."
    )

    with get_db_session() as session:
        current_text = QuestionBankService(session).as_text(job_id)

    text_key = f"job_q_bulk_{job_id}"
    edited_text = st.text_area(
        "أسئلة الوظيفة", value=current_text, height=220, key=text_key,
        placeholder="اكتب سؤالاً في كل سطر...",
    )

    col_save, col_regen = st.columns(2)
    with col_save:
        if st.button("💾 حفظ بنك الأسئلة", key=f"job_q_save_{job_id}", type="primary", width="stretch"):
            try:
                with get_db_session() as session:
                    summary = QuestionBankService(session).sync_bulk_text(job_id, edited_text)
                parts = []
                if summary["updated"]:
                    parts.append(f"تعديل {summary['updated']}")
                if summary["added"]:
                    parts.append(f"إضافة {summary['added']}")
                if summary["removed"]:
                    parts.append(f"حذف {summary['removed']}")
                st.toast("تم الحفظ ✅ " + (" · ".join(parts) if parts else ""))
                st.session_state.pop(text_key, None)
                st.rerun(scope="fragment")
            except SmartATSError as exc:
                st.error(str(exc))
    with col_regen:
        if st.button(
            "🔄 إعادة توليد الأسئلة بالذكاء الاصطناعي", key=f"job_q_regen_{job_id}", width="stretch"
        ):
            try:
                from ai.interview_generator import generate_questions_for_job

                with st.spinner("جاري توليد الأسئلة..."):
                    result = generate_questions_for_job(job)
                with get_db_session() as session:
                    added = QuestionBankService(session).add_ai_questions(job_id, result)
                st.toast(f"تمت إضافة {len(added)} سؤال جديد بالذكاء الاصطناعي ✅")
                st.session_state.pop(text_key, None)  # ليُعاد تحميل النص بالأسئلة الجديدة
                st.rerun(scope="fragment")
            except SmartATSError as exc:
                st.error(str(exc))

    st.caption(
        "ملاحظة: التوليد بالذكاء الاصطناعي يُضيف أسئلة جديدة للبنك الحالي ولا يحذف أو "
        "يستبدل الأسئلة الموجودة ولا إجابات المرشحين المسجّلة عليها."
    )


@st.dialog("✏️ تعديل الوظيفة", width="large")
def _edit_dialog(job_id: int) -> None:
    with get_db_session() as session:
        job = JobService(session).get_by_id(job_id)
    if job is None:
        st.warning("الوظيفة غير موجودة.")
        return
    st.subheader(job.title)
    tab_details, tab_questions = st.tabs(["✏️ بيانات الوظيفة", "🗂️ بنك أسئلة المقابلة"])
    with tab_details:
        _render_job_details_tab(job_id, job)
    with tab_questions:
        _render_job_questions_tab(job_id, job)


# ------------------------------------------------------------ إجراءات سريعة

def _select_job(job_id: int) -> None:
    st.session_state[_SELECTED_KEY] = job_id


def _go_to_matching(job_id: int, title: str) -> None:
    """callback: ينقل المستخدم لصفحة المطابقة مع اختيار هذه الوظيفة."""
    st.session_state[_NAV_KEY] = _MATCHING_PAGE
    st.session_state[_MATCHING_JOB_KEY] = f"{title} (#{job_id})"


def _quick_action(action, success: str) -> None:
    try:
        with get_db_session() as session:
            action(JobService(session))
    except SmartATSError as exc:
        st.error(str(exc))
        return
    _invalidate_job_related_caches()
    st.toast(success)
    st.rerun()


# ------------------------------------------------------------ المؤشرات والفلاتر

def _render_kpis(k: dict) -> None:
    month = lambda n: (f"▲ +{n} وظيفة أُنشئت هذا الشهر", "up") if n else ("لا وظائف جديدة هذا الشهر", "muted")  # noqa: E731
    open_sub, open_tone = month(k["open_new_month"])
    draft_sub, draft_tone = month(k["draft_new_month"])
    cards = [
        ("💼", "وظائف مفتوحة", k["open_jobs"], open_sub, open_tone, k["open_trend"]),
        ("📝", "وظائف مسودة", k["draft_jobs"], draft_sub, draft_tone, k["draft_trend"]),
        ("👥", "مرشحون مطلوبون", k["candidates_needed"], "إجمالي شواغر الوظائف المفتوحة", "muted", None),
        ("⚠️", "وظائف تحتاج مرشحين", k["jobs_needing_candidates"],
         f"أقل من {MIN_CANDIDATES_PER_JOB} مرشحين مطابَقين", "down", None),
    ]
    for col, (icon, label, value, sub, tone, trend) in zip(st.columns(len(cards)), cards):
        col.markdown(ui.kpi_card(icon, label, value, sub, tone, trend), unsafe_allow_html=True)


def _unique_options(rows: list[dict], key: str) -> list[str]:
    return sorted({r[key] for r in rows if r[key]})


def _render_filter_bar(rows: list[dict]) -> dict:
    cols = st.columns(6)
    with cols[0]:
        status = st.multiselect("الحالة", JOB_STATUSES, key="jf_status", format_func=_status_label)
    with cols[1]:
        department = st.multiselect("القسم", _unique_options(rows, "department"), key="jf_dept")
    with cols[2]:
        location = st.multiselect("الموقع", _unique_options(rows, "location"), key="jf_loc")
    with cols[3]:
        employment = st.multiselect(
            "نوع التوظيف", EMPLOYMENT_TYPES, key="jf_type", format_func=_EMPLOYMENT_LABELS.get
        )
    with cols[4]:
        level = st.multiselect("المستوى", CAREER_LEVELS, key="jf_level", format_func=_LEVEL_LABELS.get)
    with cols[5]:
        created = st.selectbox("تاريخ الإنشاء", list(_DATE_FILTERS), key="jf_date")
    return {
        "status": status, "department": department, "location": location,
        "employment_type": employment, "career_level": level, "days": _DATE_FILTERS[created],
    }


def _apply_filters(rows: list[dict], query: str, f: dict) -> list[dict]:
    needle = query.strip().lower()
    since = (
        datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=f["days"]) if f["days"] else None
    )
    result = []
    for r in rows:
        haystack = " ".join([r["title"], r["department"] or "", r["location"] or "", *r["skills"]]).lower()
        if needle and needle not in haystack:
            continue
        if any(f[k] and r[k] not in f[k] for k in ("status", "department", "location", "employment_type", "career_level")):
            continue
        if since and r["created_at"].replace(tzinfo=None) < since:
            continue
        result.append(r)
    return result


# ------------------------------------------------------------ الجدول والبطاقات

def _render_table(rows: list[dict], stats: dict[int, JobStats]) -> None:
    data = []
    for r in rows:
        s = stats.get(r["id"], JobStats())
        data.append({
            "المسمى": r["title"],
            "القسم": r["department"] or "-",
            "الموقع": r["location"] or "-",
            "النوع": _EMPLOYMENT_LABELS.get(r["employment_type"], "-"),
            "الخبرة": _experience_text(r["experience"]),
            "المرشحون": s.applicants,
            "المؤهلون": s.qualified,
            "نسبة التأهل": round(s.qualified / s.applicants * 100) if s.applicants else 0,
            "الحالة": f"{_STATUS_ICONS.get(r['status'], '')} {_status_label(r['status'])}",
            "آخر تحديث": ui.relative_time(r["updated_at"]),
        })
    event = st.dataframe(
        pd.DataFrame(data), width="stretch", hide_index=True,
        on_select="rerun", selection_mode="single-row", key="jobs_table",
        column_config={
            "نسبة التأهل": st.column_config.ProgressColumn("نسبة التأهل", format="%d%%", min_value=0, max_value=100),
        },
    )
    picked = event.selection.rows
    if picked and picked[0] < len(rows):
        st.session_state[_SELECTED_KEY] = rows[picked[0]]["id"]


def _render_cards(rows: list[dict], stats: dict[int, JobStats]) -> None:
    columns = st.columns(_CARD_COLUMNS)
    selected_id = st.session_state.get(_SELECTED_KEY)
    for index, r in enumerate(rows):
        s = stats.get(r["id"], JobStats())
        subtitle = " · ".join(p for p in (r["department"], r["location"]) if p) or "-"
        with columns[index % _CARD_COLUMNS], st.container(border=True):
            st.markdown(
                ui.job_card_html(
                    ("▶ " if r["id"] == selected_id else "") + r["title"], subtitle,
                    ui.status_badge(r["status"], _status_label(r["status"])),
                    _experience_text(r["experience"]), s.applicants, s.qualified,
                ),
                unsafe_allow_html=True,
            )
            st.button(
                "عرض التفاصيل", key=f"card_select_{r['id']}", on_click=_select_job,
                args=(r["id"],), width="stretch",
            )


def _resolve_selected(rows: list[dict]) -> dict:
    """الوظيفة المختارة إن كانت ضمن النتائج الحالية، وإلا أول وظيفة."""
    by_id = {r["id"]: r for r in rows}
    return by_id.get(st.session_state.get(_SELECTED_KEY)) or rows[0]


# ------------------------------------------------------------ تحليل التوظيف والقمع (أسفل الجدول)

def _render_insight_section(job: dict) -> None:
    insight = _cached_insight(job["id"])
    s = insight.stats
    col_ai, col_funnel = st.columns(2)

    with col_ai, st.container(border=True):
        st.markdown(f"**🧠 تحليل التوظيف** — {job['title']}")
        st.caption("محسوب بقواعد ثابتة قابلة للتفسير (بدون استدعاء ذكاء اصطناعي).")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("محلَّلون", s.applicants)
        m2.metric("مؤهلون", s.qualified)
        m3.metric("قائمة مختصرة", s.shortlisted)
        m4.metric("مقابلات", s.interviewed)

        col_top, col_gap = st.columns(2)
        with col_top:
            st.markdown("**✅ أبرز المهارات المتطابقة**")
            for skill in insight.top_skills:
                st.write(f"✔️ {skill}")
            if not insight.top_skills:
                st.caption("لا توجد بيانات كافية.")
        with col_gap:
            st.markdown("**⚠️ فجوات محتملة**")
            for skill in insight.gap_skills:
                st.write(f"• {skill}")
            if not insight.gap_skills:
                st.caption("لا فجوات ظاهرة.")
            st.caption("«غير موثّقة» في السير لا تعني «غير موجودة».")
        st.button(
            "عرض المرشحين المطابقين ←", key=f"insight_match_{job['id']}", type="primary", width="stretch",
            on_click=_go_to_matching, args=(job["id"], job["title"]),
        )

    with col_funnel, st.container(border=True):
        st.markdown("**🔻 قمع التوظيف**")
        st.markdown(ui.funnel_html(s.funnel()), unsafe_allow_html=True)
        st.markdown("**توزيع المطابقة**")
        st.markdown(ui.distribution_html(s.high, s.medium, s.low), unsafe_allow_html=True)
        st.markdown("**💡 ملاحظات سريعة**")
        for note in insight.quick:
            st.write(f"• {note}")


# ------------------------------------------------------------ لوحة تفاصيل الوظيفة (يمين)

def _render_detail_panel(job: dict, stats: dict[int, JobStats]) -> None:
    s = stats.get(job["id"], JobStats())
    position_titles = {p["id"]: p["title"] for p in _org_options()["positions"]}
    with st.container(border=True):
        st.markdown(
            f'<div class="jb"><div class="jb-title">{job["title"]}</div>'
            f'{ui.status_badge(job["status"], _status_label(job["status"]))}</div>',
            unsafe_allow_html=True,
        )
        col_edit, col_copy, col_close = st.columns(3)
        with col_edit:
            if st.button("✏️ تعديل", key=f"edit_{job['id']}", type="primary", width="stretch"):
                _edit_dialog(job["id"])
        with col_copy:
            if st.button("📄 نسخ", key=f"dup_{job['id']}", width="stretch"):
                _quick_action(lambda svc: svc.duplicate_job(job["id"]), "تم إنشاء نسخة كمسودة ✅")
        with col_close:
            if st.button("🔒 إغلاق", key=f"close_{job['id']}", disabled=job["status"] == "Closed", width="stretch"):
                _quick_action(lambda svc: svc.close_job(job["id"]), "تم إغلاق الوظيفة 🔒")

        st.markdown('<div class="jb jb-section">📋 معلومات الوظيفة</div>', unsafe_allow_html=True)
        st.markdown(ui.info_rows([
            ("القسم", job["department"]), ("المسمى في الهيكل", position_titles.get(job["position_id"], "-")),
            ("يتبع لـ", job["reports_to"]), ("الموقع", job["location"]),
            ("نوع التوظيف", _EMPLOYMENT_LABELS.get(job["employment_type"], "-")),
            ("الراتب", _salary_text(job["salary_min"], job["salary_max"])),
            ("الشواغر", str(job["vacancies"])),
        ]), unsafe_allow_html=True)

        st.markdown('<div class="jb jb-section">🎓 المتطلبات</div>', unsafe_allow_html=True)
        st.markdown(ui.info_rows([
            ("الخبرة", _experience_text(job["experience"])), ("المؤهل", job["education"]),
            ("المستوى", _LEVEL_LABELS.get(job["career_level"], "-")),
        ]), unsafe_allow_html=True)

        st.markdown('<div class="jb jb-section">🛠️ المهارات المطلوبة</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="jb">{ui.skill_chips(job["skills"])}</div>', unsafe_allow_html=True)

        st.markdown('<div class="jb jb-section">🔻 قمع التوظيف</div>', unsafe_allow_html=True)
        st.markdown(ui.funnel_html(s.funnel(), size=38), unsafe_allow_html=True)


# ------------------------------------------------------------ الصفحة الرئيسية

def render() -> None:
    ui.inject_css()

    col_title, col_create = st.columns([4, 1])
    with col_title:
        st.header("💼 الوظائف")
        st.caption("إدارة الشواغر والمتطلبات ومسار المرشحين")
    with col_create:
        st.write("")
        if st.button("➕ إنشاء وظيفة", type="primary", width="stretch", key="jobs_create_btn"):
            _create_dialog()

    data = _page_data()
    _render_kpis(data["kpis"])

    if not data["jobs"]:
        st.info("لا توجد وظائف بعد. اضغط «إنشاء وظيفة» للبدء.")
        return

    query = st.text_input(
        "بحث", key="jobs_search", label_visibility="collapsed",
        placeholder="🔎 ابحث بالمسمى أو القسم أو المهارة أو الموقع...",
    )
    filters = _render_filter_bar(data["jobs"])
    rows = _apply_filters(data["jobs"], query, filters)

    view = st.radio("طريقة العرض", [_VIEW_LIST, _VIEW_CARDS], horizontal=True, key="jobs_view")
    if not rows:
        st.info("لا توجد وظائف مطابقة للبحث والفلاتر الحالية.")
        return

    stats: dict[int, JobStats] = data["stats"]
    main, side = st.columns([3, 1.15], gap="medium")
    with main:
        csv_bytes, xlsx_bytes = _export_bytes(tuple(r["id"] for r in rows))
        csv_col, xlsx_col, _ = st.columns([1, 1, 4])
        csv_col.download_button("⬇️ CSV", csv_bytes, file_name="jobs.csv", mime="text/csv", width="stretch")
        xlsx_col.download_button(
            "⬇️ Excel", xlsx_bytes, file_name="jobs.xlsx", width="stretch",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        if view == _VIEW_LIST:
            _render_table(rows, stats)
            st.caption(f"إجمالي الوظائف: {len(rows)} — اضغط على أي صف لعرض تفاصيله وتحليله.")
        else:
            _render_cards(rows, stats)

        selected = _resolve_selected(rows)
        _render_insight_section(selected)
    with side:
        _render_detail_panel(selected, stats)