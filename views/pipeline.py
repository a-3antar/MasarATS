"""مسار التوظيف: لوحة واحدة لمراحل المرشحين (جديد ← فرز ← قائمة مختصرة ← مقابلة ← عرض ← تعيين).
لا منطق أعمال هنا: النقل عبر ApplicationService (يسجّل التاريخ ويزامن حالة المرشح)،
والتعيين يبقى حصراً من صفحة العروض بعد قبول العرض (قرار بشري)."""

import html

import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import defer

from core.constants import APPLICATION_STATUSES
from core.exceptions import SmartATSError
from database.database import get_db_session
from models.application import Application
from models.candidate import Candidate
from models.job import Job
from services.application_service import ApplicationService
from services.job_service import JobService
from ui import components
from views import job_candidates
from ui.navigation import OFFER_PREFILL_APP, go_to, OPEN_CREATE_OFFER


_TTL = 30
_REJECTED, _HIRED = "Rejected", "Hired"
_STAGES = [s for s in APPLICATION_STATUSES if s != _REJECTED]
_MAX_PER_COLUMN = 8
_ALL_JOBS = None

_STAGE_LABELS = {
    "New": "جديد", "Screening": "الفرز", "Shortlisted": "القائمة المختصرة", "Interview": "المقابلة",
    "Offer": "العرض", "Hired": "التعيين", "Rejected": "مرفوض",
}
_STAGE_COLORS = {
    "New": "#64748b", "Screening": "#3b82f6", "Shortlisted": "#d9a21b", "Interview": "#f59e0b",
    "Offer": "#d9487a", "Hired": "#16a34a", "Rejected": "#b91c1c",
}
# المرحلة ← (نص الإجراء التالي، المرحلة الجديدة أو None، صفحة الانتقال أو None، حالة session_state)
_NEXT = {
    "New": ("بدء الفرز", "Screening", None, {}),
    "Screening": ("قائمة مختصرة", "Shortlisted", None, {}),
    "Shortlisted": ("جدولة مقابلة", None, "interviews", {}),
    "Interview": ("إنشاء عرض", None, "offers", {OPEN_CREATE_OFFER: True}),
    "Offer": ("متابعة العرض", None, "offers", {}),
}

_CSS = """<style>
.pl-head{display:flex;justify-content:space-between;align-items:center;font-weight:700;font-size:.85rem;
  padding:6px 10px;margin-bottom:8px;border-radius:8px;border-top:3px solid var(--c);background:rgba(128,128,128,.10)}
.pl-count{font-size:.75rem;padding:1px 9px;border-radius:999px;background:var(--c);color:#fff}
.pl-name{font-weight:700;font-size:.88rem;line-height:1.25}
.pl-pos{font-size:.72rem;opacity:.65}
.pl-score{font-size:.78rem;font-weight:700}
.st-key-pl-board [data-testid="stHorizontalBlock"]{overflow-x:auto;flex-wrap:nowrap;padding-bottom:8px}
.st-key-pl-board [data-testid="stColumn"]{min-width:220px}
</style>"""


# ------------------------------------------------------------ بيانات (مخزّنة مؤقتاً)

@st.cache_data(ttl=_TTL, show_spinner=False)
def _jobs() -> list[tuple[int, str]]:
    with get_db_session() as session:
        return [(j.id, j.title) for j in JobService(session).list_all()]


@st.cache_data(ttl=_TTL, show_spinner=False)
def _load(job_id: int | None) -> list[dict]:
    """تقديمات وظيفة (أو كل الوظائف) مع المرشح، الأعلى مطابقة أولاً."""
    stmt = (
        select(Application, Candidate, Job.title)
        .join(Candidate, Candidate.id == Application.candidate_id)
        .join(Job, Job.id == Application.job_id)
        .options(defer(Candidate.raw_text), defer(Candidate.embedding))
        .order_by(Application.match_score.desc())
    )
    if job_id is not None:
        stmt = stmt.where(Application.job_id == job_id)
    with get_db_session() as session:
        return [
            {
                "app_id": a.id, "job_id": a.job_id, "job": title, "name": c.full_name,
                "position": c.current_position or "-", "score": a.match_score,
                "status": a.status if a.status in APPLICATION_STATUSES else APPLICATION_STATUSES[0],
            }
            for a, c, title in session.execute(stmt).all()
        ]


def _clear() -> None:
    _load.clear()
    job_candidates._clear_caches()


def _move(app_id: int, new_status: str) -> None:
    """callback: نقل التقديم عبر ApplicationService (تاريخ + مزامنة حالة المرشح + الهيكل)."""
    try:
        user = (st.session_state.get("user") or {}).get("full_name")
        with get_db_session() as session:
            ApplicationService(session).change_status(app_id, new_status, changed_by=user)
        _clear()
        st.toast(f"تم النقل إلى «{_STAGE_LABELS.get(new_status, new_status)}» ✅")
    except SmartATSError as exc:
        st.toast(str(exc))


# ------------------------------------------------------------ مكوّنات العرض

def _score_text(score: float | None) -> str:
    if score is None:
        return "—"
    color = "#22c55e" if score >= 75 else "#f59e0b" if score >= 50 else "#ef4444"
    return f'<span class="pl-score" style="color:{color}">{score:g}%</span>'


def _interview_state(r: dict) -> dict:
    """قيم صفحة المقابلات المطابقة لهذا التقديم (نفس صيغة عناوين تلك الصفحة)."""
    label = f"{r['name']} · مطابقة {r['score']}% · {r['status']}" if r["score"] is not None \
        else f"{r['name']} · {r['status']}"
    return {"iv_job_select": f"{r['job']} (#{r['job_id']})", "iv_app_select": label}

def _render_next_action(r: dict, prefix: str) -> None:
    step = _NEXT.get(r["status"])
    if step is None:
        return
    label, new_status, page, state = step
    key = f"{prefix}_next_{r['app_id']}"
    if new_status is not None:
        st.button(f"➡️ {label}", key=key, on_click=_move, args=(r["app_id"], new_status),
                  type="primary", width="stretch")
        return
    if page == "interviews":
        extra = _interview_state(r)
    elif page == "offers":
        extra = {**state, OFFER_PREFILL_APP: r["app_id"]}
    else:
        extra = state
    st.button(f"➡️ {label}", key=key, on_click=go_to, args=(page,), kwargs=extra,
              type="primary", width="stretch")

def _render_card(r: dict, prefix: str, show_job: bool) -> None:
    with st.container(border=True):
        st.markdown(
            f'<div class="pl-name">{html.escape(r["name"])}</div>'
            f'<div class="pl-pos">{html.escape(r["position"])}'
            f'{" · " + html.escape(r["job"]) if show_job else ""}</div>'
            f'<div>{_score_text(r["score"])}</div>',
            unsafe_allow_html=True,
        )
        _render_next_action(r, prefix)
        with st.popover("⋯", width="stretch"):
            options = [s for s in APPLICATION_STATUSES if s not in (r["status"], _HIRED)]
            target = st.selectbox("نقل إلى", options, format_func=lambda s: _STAGE_LABELS.get(s, s),
                                  key=f"{prefix}_to_{r['app_id']}")
            st.button("تطبيق", key=f"{prefix}_apply_{r['app_id']}", on_click=_move,
                      args=(r["app_id"], target), width="stretch")
            if r["status"] != _REJECTED:
                st.button("❌ رفض المرشح", key=f"{prefix}_rej_{r['app_id']}", on_click=_move,
                          args=(r["app_id"], _REJECTED), width="stretch")
            st.caption("التعيين يتم من صفحة «العروض» بعد قبول المرشح للعرض.")


def _render_board(rows: list[dict], show_job: bool) -> None:
    grouped: dict[str, list[dict]] = {s: [] for s in APPLICATION_STATUSES}
    for r in rows:
        grouped[r["status"]].append(r)

    with st.container(key="pl-board"):
        for col, stage in zip(st.columns(len(_STAGES)), _STAGES):
            with col:
                st.markdown(
                    f'<div class="pl-head" style="--c:{_STAGE_COLORS[stage]}"><span>{_STAGE_LABELS[stage]}</span>'
                    f'<span class="pl-count">{len(grouped[stage])}</span></div>',
                    unsafe_allow_html=True,
                )
                for r in grouped[stage][:_MAX_PER_COLUMN]:
                    _render_card(r, f"pl_{stage}", show_job)
                hidden = len(grouped[stage]) - _MAX_PER_COLUMN
                if hidden > 0:
                    st.caption(f"+ {hidden} آخرين (ضيّق القائمة بالوظيفة لرؤيتهم)")

    if grouped[_REJECTED]:
        with st.expander(f"❌ المرفوضون ({len(grouped[_REJECTED])})"):
            for r in grouped[_REJECTED]:
                col_info, col_back = st.columns([4, 1], vertical_alignment="center")
                col_info.write(f"{r['name']} — {r['job']}")
                col_back.button("↩️ استرجاع", key=f"pl_back_{r['app_id']}", on_click=_move,
                                args=(r["app_id"], APPLICATION_STATUSES[0]), width="stretch")


def render() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    st.header("🧭 مسار التوظيف")
    st.caption("تابع كل مرشح من أول فرز حتى التعيين. كل بطاقة تقترح الخطوة التالية، والقرار دائماً لك.")

    jobs = _jobs()
    if not jobs:
        components.empty_state(
            "💼", "لا توجد وظائف بعد", "أنشئ أول وظيفة وسيساعدك SmartATS في العثور على المرشحين المناسبين.",
            [("➕ إنشاء وظيفة", "jobs", {"open_create_job": True})], key="pl_empty_jobs",
        )
        return

    options = [_ALL_JOBS, *[j[0] for j in jobs]]
    titles = dict(jobs)
    job_id = st.selectbox("💼 الوظيفة", options, key="pl_job",
                          format_func=lambda v: "كل الوظائف" if v is None else f"{titles[v]} (#{v})")

    rows = _load(job_id)
    if not rows:
        components.empty_state(
            "🧭", "لا يوجد مرشحون في المسار", "ابحث عن مرشحين مناسبين لوظيفة لتظهر هنا ويمكنك متابعتهم.",
            [("🎯 البحث عن مرشحين", "jobs", None), ("📄 رفع سيرة ذاتية", "upload_cv", None)], key="pl_empty_rows",
        )
        return

    st.caption(f"إجمالي التقديمات: {len(rows)}")
    _render_board(rows, show_job=job_id is None)