"""صفحة المطابقة: (1) وظيفة ← أفضل المرشحين (لوحة Kanban حسب مرحلة التوظيف)، (2) مرشح ← أفضل الوظائف."""

import streamlit as st

from database.database import get_db_session
from services.candidate_service import CandidateService
from services.job_service import JobService
from services.matching_service import MatchingService
from core.constants import APPLICATION_STATUSES
from core.exceptions import SmartATSError
from services.application_service import ApplicationService


# حفظ النتائج في session_state حتى لا تختفي عند تغيير الفلتر (أي rerun)
_JOB_RESULTS_KEY = "matching_results"
_CANDIDATE_RESULTS_KEY = "matching_candidate_results"

# مدة الكاش بالثواني لقوائم الوظائف/المرشحين الأساسية - تسريع التنقل بين التبويبات
# (Streamlit يعيد تشغيل الصفحة كاملة في كل تفاعل، وهذه الاستعلامات لا تتغير كل ثانية)
_LIST_CACHE_TTL = 30


@st.cache_data(ttl=_LIST_CACHE_TTL, show_spinner=False)
def _cached_jobs() -> list:
    with get_db_session() as session:
        return JobService(session).list_all()


@st.cache_data(ttl=_LIST_CACHE_TTL, show_spinner=False)
def _cached_candidates() -> list:
    with get_db_session() as session:
        return CandidateService(session).list_all()


def _invalidate_list_caches() -> None:
    """تُستدعى بعد أي عملية تغيّر حالة (مثل نقل تقديم) حتى لا تُعرض بيانات قديمة."""
    _cached_jobs.clear()
    _cached_candidates.clear()


def _render_match_details(r: dict) -> None:
    """تفاصيل الدرجة (مشتركة بين الاتجاهين)."""
    with st.expander("تفاصيل الدرجة"):
        b = r["breakdown"]
        st.write(
            f"المهارات: {b['skills']}% · الخبرة: {b['experience']}% · "
            f"الموقع: {b['location']}% · التعليم: {b['education']}%"
        )
        if r["strengths"]:
            st.markdown("**نقاط القوة:**")
            for s in r["strengths"]:
                st.write(s)
        if r["gaps"]:
            st.markdown("**فجوات محتملة:**")
            for g in r["gaps"]:
                st.write(g)


def _change_application_status(application_id: int, new_status: str) -> None:
    """ينقل تقديماً إلى مرحلة جديدة ويعيد تحميل النتائج المخزّنة في session_state لتعكس النقل فوراً."""
    try:
        with get_db_session() as session:
            ApplicationService(session).change_status(application_id, new_status)

        state = st.session_state.get(_JOB_RESULTS_KEY)
        if state:
            for r in state["results"]:
                if r["application"].id == application_id:
                    r["application"].status = new_status
                    break

        st.toast("تم تحديث مرحلة التوظيف ✅")
        st.rerun()
    except SmartATSError as exc:
        st.error(str(exc))


def _render_kanban_card(r: dict, status: str) -> None:
    candidate = r["candidate"]
    idx = APPLICATION_STATUSES.index(status)

    with st.container(border=True):
        st.markdown(f"**{candidate.full_name}**")
        st.caption(candidate.current_position or "لا يوجد مسمى وظيفي مسجّل")
        st.write(f"🎯 {r['score']}%")
        _render_match_details(r)

        col_back, col_fwd = st.columns(2)
        with col_back:
            if idx > 0 and st.button(
                "◀◀", key=f"kanban_back_{r['application'].id}", width="stretch"
            ):
                _change_application_status(r["application"].id, APPLICATION_STATUSES[idx - 1])
        with col_fwd:
            if idx < len(APPLICATION_STATUSES) - 1 and st.button(
                "▶▶", key=f"kanban_fwd_{r['application'].id}", width="stretch"
            ):
                _change_application_status(r["application"].id, APPLICATION_STATUSES[idx + 1])


def _render_kanban_board(results: list[dict]) -> None:
    """لوحة Kanban: عمود لكل مرحلة من مراحل خط التوظيف، بدل قائمة selectbox لتغيير الحالة."""
    grouped: dict[str, list[dict]] = {status: [] for status in APPLICATION_STATUSES}
    for r in results:
        status = r["application"].status
        if status not in grouped:
            status = APPLICATION_STATUSES[0]
        grouped[status].append(r)

    columns = st.columns(len(APPLICATION_STATUSES))
    for col, status in zip(columns, APPLICATION_STATUSES):
        with col:
            st.markdown(f"##### {status} ({len(grouped[status])})")
            for r in grouped[status]:
                _render_kanban_card(r, status)


def _render_candidate_result(r: dict) -> None:
    candidate = r["candidate"]
    with st.container(border=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.subheader(f"{candidate.full_name}")
            st.caption(candidate.current_position or "لا يوجد مسمى وظيفي مسجّل")
        with col2:
            st.metric("درجة المطابقة", f"{r['score']}%")
        _render_match_details(r)


def _render_job_to_candidates() -> None:
    jobs = _cached_jobs()

    if not jobs:
        st.info("أضف وظيفة أولاً من صفحة «الوظائف».")
        return

    job_titles = {f"{j.title} (#{j.id})": j.id for j in jobs}
    selected_label = st.selectbox("اختر الوظيفة", list(job_titles.keys()), key="m_job_select")
    job_id = job_titles[selected_label]

    min_score = st.slider(
        "الحد الأدنى لنسبة المطابقة (%)", min_value=0, max_value=100, value=0, step=5,
        help="لن تظهر إلا المرشحون الذين تساوي درجتهم هذا الحد أو تزيد عليه.",
        key="m_job_min_score",
    )

    if st.button("🔍 ابحث عن مرشحين مطابقين", type="primary", key="m_job_btn"):
        with get_db_session() as session:
            job = JobService(session).get_by_id(job_id)
            candidates = CandidateService(session).list_all()

            if not candidates:
                st.info("لا يوجد مرشحون بعد لمطابقتهم.")
                return

            results = MatchingService(session).match_all_candidates_to_job(job, candidates)

        st.session_state[_JOB_RESULTS_KEY] = {"job_id": job_id, "results": results}

    state = st.session_state.get(_JOB_RESULTS_KEY)
    if not state or state["job_id"] != job_id:
        return

    all_results = state["results"]
    filtered = [r for r in all_results if r["score"] >= min_score]
    st.caption(f"عرض {len(filtered)} من {len(all_results)} مرشح (الحد الأدنى: {min_score}%)")

    if not filtered:
        st.warning("لا يوجد مرشحون بهذه النسبة أو أعلى. خفّض الحد الأدنى لعرض المزيد.")
        return

    _render_kanban_board(filtered)


def _render_job_result(r: dict) -> None:
    job = r["job"]
    with st.container(border=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.subheader(f"{job.title}")
            st.caption(
                f"{job.department or 'بدون قسم'} · {job.location or 'بدون موقع'} · الحالة: {job.status}"
            )
        with col2:
            st.metric("درجة المطابقة", f"{r['score']}%")
        _render_match_details(r)


def _render_candidate_to_jobs() -> None:
    candidates = _cached_candidates()

    if not candidates:
        st.info("لا يوجد مرشحون بعد. ارفع سيرة ذاتية أولاً.")
        return

    candidate_labels = {
        f"{c.full_name} ({c.candidate_code or f'#{c.id}'})": c.id for c in candidates
    }
    selected_label = st.selectbox("اختر المرشح", list(candidate_labels.keys()), key="m_cand_select")
    candidate_id = candidate_labels[selected_label]

    col_open, col_score = st.columns([1, 2])
    with col_open:
        open_only = st.checkbox("الوظائف المفتوحة فقط", value=True, key="m_cand_open_only")
    with col_score:
        min_score = st.slider(
            "الحد الأدنى لنسبة المطابقة (%)", min_value=0, max_value=100, value=0, step=5,
            help="لن تظهر إلا الوظائف التي تساوي درجتها هذا الحد أو تزيد عليه.",
            key="m_cand_min_score",
        )

    if st.button("🔍 ابحث عن أفضل الوظائف", type="primary", key="m_cand_btn"):
        with get_db_session() as session:
            candidate = CandidateService(session).get_by_id(candidate_id)
            job_service = JobService(session)
            jobs = job_service.list_open() if open_only else job_service.list_all()

            if not jobs:
                st.info("لا توجد وظائف مطابقة للشرط. أضف وظيفة أو ألغِ خيار «المفتوحة فقط».")
                return

            results = MatchingService(session).match_candidate_to_all_jobs(candidate, jobs)

        st.session_state[_CANDIDATE_RESULTS_KEY] = {"candidate_id": candidate_id, "results": results}

    state = st.session_state.get(_CANDIDATE_RESULTS_KEY)
    if not state or state["candidate_id"] != candidate_id:
        return

    all_results = state["results"]
    filtered = [r for r in all_results if r["score"] >= min_score]
    st.caption(f"عرض {len(filtered)} من {len(all_results)} وظيفة (الحد الأدنى: {min_score}%)")

    if not filtered:
        st.warning("لا توجد وظائف بهذه النسبة أو أعلى. خفّض الحد الأدنى لعرض المزيد.")
        return

    for r in filtered:
        _render_job_result(r)


def render() -> None:
    st.header("🎯 المطابقة")

    tab_job, tab_candidate = st.tabs(["💼 وظيفة ← مرشحون", "👤 مرشح ← وظائف"])
    with tab_job:
        _render_job_to_candidates()
    with tab_candidate:
        _render_candidate_to_jobs()
