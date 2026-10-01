"""صفحة المطابقة بتصميم احترافي: لوحتان متجاورتان
(1) وظيفة ← مرشحون: ملخص المراحل + لوحة Kanban ببطاقات مرشحين.
(2) مرشح ← وظائف: بطاقات وظائف مرتبة حسب المطابقة.
المنطق (الكاش، session_state، نقل التقديم) كما هو؛ التغيير في العرض فقط."""

import base64
import html
from pathlib import Path

import streamlit as st

from core.constants import APPLICATION_STATUSES
from core.exceptions import SmartATSError
from database.database import get_db_session
from services.application_service import ApplicationService
from services.candidate_service import CandidateService
from services.job_service import JobService
from services.matching_service import MatchingService

_JOB_RESULTS_KEY = "matching_results"
_CANDIDATE_RESULTS_KEY = "matching_candidate_results"
_LIST_CACHE_TTL = 30

_GOOD_THRESHOLD, _MID_THRESHOLD = 75, 50
_COLOR_GOOD, _COLOR_MID, _COLOR_BAD = "#22c55e", "#f59e0b", "#ef4444"
_KANBAN_COLUMN_MIN_PX = 235

_STAGE_COLORS = {
    "New": "#2f8fb5", "Screening": "#2e9e6b", "Shortlisted": "#d9a21b", "Interview": "#3b82f6",
    "Offer": "#d9487a", "Hired": "#7c3aed", "Rejected": "#b91c1c",
}
_DEFAULT_STAGE_COLOR = "#64748b"
_BREAKDOWN_LABELS = {
    "skills": "المهارات", "experience": "الخبرة", "location": "الموقع",
    "education": "التعليم", "semantic": "دلالي",
}

_CSS = f"""
<style>
.m-panel-title{{font-size:1.15rem;font-weight:700;padding-bottom:6px;margin-bottom:10px;
  border-bottom:2px solid #14b8a6;display:inline-block}}
.m-sub{{font-size:.75rem;opacity:.65;margin:8px 0 6px;letter-spacing:.04em}}
.m-stages{{display:grid;grid-template-columns:repeat(auto-fit,minmax(105px,1fr));gap:10px;margin:4px 0 14px}}
.m-stage{{border-radius:12px;padding:10px 14px;color:#fff;background:var(--c);
  box-shadow:0 2px 8px rgba(0,0,0,.25)}}
.m-stage-name{{font-size:.78rem;font-weight:600;opacity:.95}}
.m-stage-count{{font-size:1.55rem;font-weight:800;line-height:1.15}}
.m-col-head{{display:flex;justify-content:space-between;align-items:center;font-weight:700;
  font-size:.85rem;padding:6px 10px;margin-bottom:8px;border-radius:8px;
  border-top:3px solid var(--c);background:rgba(128,128,128,.10)}}
.m-col-count{{font-size:.75rem;padding:1px 9px;border-radius:999px;background:var(--c);color:#fff}}
.m-head{{display:flex;gap:10px;align-items:center}}
.m-avatar{{width:44px;height:44px;flex:0 0 44px;border-radius:50%;overflow:hidden;display:grid;
  place-items:center;font-weight:700;color:#fff;background:linear-gradient(135deg,#14b8a6,#3b82f6);
  border:2px solid rgba(255,255,255,.25)}}
.m-avatar img{{width:100%;height:100%;object-fit:cover}}
.m-name{{font-weight:700;font-size:.92rem;line-height:1.2}}
.m-pos{{font-size:.72rem;opacity:.65;line-height:1.3}}
.m-score{{display:flex;align-items:center;gap:8px;margin:10px 0 4px}}
.m-track{{flex:1;height:7px;border-radius:999px;background:rgba(128,128,128,.25);overflow:hidden}}
.m-fill{{height:100%;border-radius:999px}}
.m-score-val{{font-size:.8rem;font-weight:700;min-width:44px;text-align:end}}
.m-mini{{margin-bottom:6px}}
.m-mini-head{{display:flex;justify-content:space-between;font-size:.72rem;margin-bottom:2px}}
.st-key-m-kanban [data-testid="stHorizontalBlock"]{{overflow-x:auto;flex-wrap:nowrap;padding-bottom:8px}}
.st-key-m-kanban [data-testid="stColumn"]{{min-width:{_KANBAN_COLUMN_MIN_PX}px}}
[data-testid="stVerticalBlockBorderWrapper"]{{border-radius:12px}}
</style>
"""


# ------------------------------------------------------------ كاش القوائم

@st.cache_data(ttl=_LIST_CACHE_TTL, show_spinner=False)
def _cached_jobs() -> list:
    with get_db_session() as session:
        return JobService(session).list_all()


@st.cache_data(ttl=_LIST_CACHE_TTL, show_spinner=False)
def _cached_candidates() -> list:
    with get_db_session() as session:
        return CandidateService(session).list_all()


def _invalidate_list_caches() -> None:
    _cached_jobs.clear()
    _cached_candidates.clear()


# ------------------------------------------------------------ مكوّنات HTML صغيرة

def _score_color(value: float) -> str:
    if value >= _GOOD_THRESHOLD:
        return _COLOR_GOOD
    return _COLOR_MID if value >= _MID_THRESHOLD else _COLOR_BAD


def _clean_line(text: str) -> str:
    return text.lstrip("✓✔⚠❌\ufe0f ").strip()


def _initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "؟"


@st.cache_data(show_spinner=False, max_entries=512)
def _photo_data_uri(path: str, mtime: float) -> str | None:
    """الصورة كـ data URI لعرضها دائرية داخل HTML (mtime في المفتاح لتحديث الكاش عند تغيّر الصورة)."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(data).decode()


def _avatar_html(candidate) -> str:
    photo = CandidateService.photo_absolute_path(candidate)
    uri = _photo_data_uri(str(photo), photo.stat().st_mtime) if photo else None
    inner = f'<img src="{uri}" alt="">' if uri else html.escape(_initials(candidate.full_name))
    return f'<div class="m-avatar">{inner}</div>'


def _score_bar_html(score: float) -> str:
    pct = max(0.0, min(100.0, float(score)))
    return (
        f'<div class="m-score"><div class="m-track"><div class="m-fill" '
        f'style="width:{pct}%;background:{_score_color(pct)}"></div></div>'
        f'<span class="m-score-val" style="color:{_score_color(pct)}">{pct:g}%</span></div>'
    )


def _head_html(avatar: str, title: str, subtitle: str, score: float) -> str:
    return (
        f'<div class="m-head">{avatar}<div><div class="m-name">{html.escape(title)}</div>'
        f'<div class="m-pos">{html.escape(subtitle)}</div></div></div>{_score_bar_html(score)}'
    )


def _mini_bar(label: str, value: float) -> str:
    pct = max(0.0, min(100.0, float(value)))
    return (
        f'<div class="m-mini"><div class="m-mini-head"><span>{html.escape(label)}</span>'
        f'<span>{pct:g}%</span></div><div class="m-track"><div class="m-fill" '
        f'style="width:{pct}%;background:{_score_color(pct)}"></div></div></div>'
    )


def _panel_title(text: str) -> None:
    st.markdown(f'<div class="m-panel-title">{html.escape(text)}</div>', unsafe_allow_html=True)


def _stage_color(status: str) -> str:
    return _STAGE_COLORS.get(status, _DEFAULT_STAGE_COLOR)


def _scroll_container(key: str):
    """حاوية بمفتاح (للتمرير الأفقي عبر CSS). على إصدارات Streamlit القديمة تعمل كحاوية عادية."""
    try:
        return st.container(key=key)
    except TypeError:
        return st.container()


# ------------------------------------------------------------ تفاصيل الدرجة

def _render_match_details(r: dict) -> None:
    with st.expander("تفاصيل الدرجة"):
        bars = "".join(
            _mini_bar(label, r["breakdown"][key])
            for key, label in _BREAKDOWN_LABELS.items() if key in r["breakdown"]
        )
        st.markdown(bars, unsafe_allow_html=True)

        st.markdown("**نقاط القوة**")
        if r["strengths"]:
            for s in r["strengths"]:
                st.write(f"✔️ {_clean_line(s)}")
        else:
            st.caption("لا توجد نقاط قوة مسجّلة.")

        st.markdown("**فجوات محتملة**")
        if r["gaps"]:
            for g in r["gaps"]:
                st.write(f"❌ {_clean_line(g)}")
        else:
            st.caption("لا توجد فجوات.")


# ------------------------------------------------------------ نقل التقديم (Kanban)

def _change_application_status(application_id: int, new_status: str) -> None:
    try:
        with get_db_session() as session:
            user = (st.session_state.get("user") or {}).get("full_name")
            ApplicationService(session).change_status(application_id, new_status, changed_by=user)
            

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
    application_id = r["application"].id
    idx = APPLICATION_STATUSES.index(status)

    with st.container(border=True):
        st.markdown(
            _head_html(
                _avatar_html(candidate), candidate.full_name,
                candidate.current_position or "لا يوجد مسمى وظيفي مسجّل", r["score"],
            ),
            unsafe_allow_html=True,
        )
        _render_match_details(r)

        col_back, col_fwd = st.columns(2)
        with col_back:
            if st.button("◀◀", key=f"kanban_back_{application_id}", disabled=idx == 0, width="stretch"):
                _change_application_status(application_id, APPLICATION_STATUSES[idx - 1])
        with col_fwd:
            last = idx == len(APPLICATION_STATUSES) - 1
            if st.button("▶▶", key=f"kanban_fwd_{application_id}", disabled=last, width="stretch"):
                _change_application_status(application_id, APPLICATION_STATUSES[idx + 1])


def _render_stage_summary(grouped: dict[str, list[dict]]) -> None:
    cards = "".join(
        f'<div class="m-stage" style="--c:{_stage_color(status)}">'
        f'<div class="m-stage-name">{html.escape(status)}</div>'
        f'<div class="m-stage-count">{len(grouped[status])}</div></div>'
        for status in APPLICATION_STATUSES
    )
    st.markdown('<div class="m-sub">APPLICATION STATUSES</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="m-stages">{cards}</div>', unsafe_allow_html=True)


def _render_kanban_board(results: list[dict]) -> None:
    grouped: dict[str, list[dict]] = {status: [] for status in APPLICATION_STATUSES}
    for r in results:
        status = r["application"].status
        grouped[status if status in grouped else APPLICATION_STATUSES[0]].append(r)

    _render_stage_summary(grouped)

    with _scroll_container("m-kanban"):
        for col, status in zip(st.columns(len(APPLICATION_STATUSES)), APPLICATION_STATUSES):
            with col:
                st.markdown(
                    f'<div class="m-col-head" style="--c:{_stage_color(status)}"><span>{html.escape(status)}</span>'
                    f'<span class="m-col-count">{len(grouped[status])}</span></div>',
                    unsafe_allow_html=True,
                )
                for r in grouped[status]:
                    _render_kanban_card(r, status)


# ------------------------------------------------------------ اللوحة 1: وظيفة ← مرشحون

def _render_job_to_candidates() -> None:
    jobs = _cached_jobs()
    if not jobs:
        st.info("أضف وظيفة أولاً من صفحة «الوظائف».")
        return

    job_titles = {f"{j.title} (#{j.id})": j.id for j in jobs}
    col_job, col_score = st.columns([2, 1.5])
    with col_job:
        selected_label = st.selectbox("اختيار الوظيفة", list(job_titles.keys()), key="m_job_select")
    with col_score:
        min_score = st.slider(
            "الحد الأدنى لنسبة المطابقة (%)", 0, 100, 0, 5, key="m_job_min_score",
            help="لن يظهر إلا المرشحون الذين تساوي درجتهم هذا الحد أو تزيد عليه.",
        )
    job_id = job_titles[selected_label]

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


# ------------------------------------------------------------ اللوحة 2: مرشح ← وظائف

def _render_job_result(r: dict) -> None:
    job = r["job"]
    subtitle = f"{job.department or 'بدون قسم'} · {job.location or 'بدون موقع'} · {job.status}"
    avatar = f'<div class="m-avatar">{html.escape(_initials(job.title))}</div>'
    with st.container(border=True):
        st.markdown(_head_html(avatar, job.title, subtitle, r["score"]), unsafe_allow_html=True)
        _render_match_details(r)


def _render_candidate_to_jobs() -> None:
    candidates = _cached_candidates()
    if not candidates:
        st.info("لا يوجد مرشحون بعد. ارفع سيرة ذاتية أولاً.")
        return

    candidate_labels = {f"{c.full_name} ({c.candidate_code or f'#{c.id}'})": c.id for c in candidates}
    selected_label = st.selectbox("اختيار المرشح", list(candidate_labels.keys()), key="m_cand_select")
    candidate_id = candidate_labels[selected_label]

    open_only = st.checkbox("الوظائف المفتوحة فقط", value=True, key="m_cand_open_only")
    min_score = st.slider(
        "الحد الأدنى لنسبة المطابقة (%)", 0, 100, 0, 5, key="m_cand_min_score",
        help="لن تظهر إلا الوظائف التي تساوي درجتها هذا الحد أو تزيد عليه.",
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


# ------------------------------------------------------------ الصفحة

def render() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    st.header("🎯 المطابقة")

    col_main, col_side = st.columns([3, 1.35], gap="medium")
    with col_main:
        with st.container(border=True):
            _panel_title("💼 وظيفة ← مرشحون")
            _render_job_to_candidates()
    with col_side:
        with st.container(border=True):
            _panel_title("👤 مرشح ← وظائف")
            _render_candidate_to_jobs()
