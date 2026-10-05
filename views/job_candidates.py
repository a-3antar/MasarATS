"""أفضل المرشحين داخل صفحة الوظيفة: ملخص + بطاقات مع شرح الدرجة + إجراءات مباشرة.
لا منطق مطابقة هنا: القراءة من جدول applications (نتائج MatchingService المحفوظة)،
والحساب يتم فقط عند ضغط زر «بحث» عبر MatchingService نفسه."""

import html

import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import defer

from core.constants import MATCH_HIGH_THRESHOLD, SEARCH_MAX_CANDIDATES
from core.exceptions import SmartATSError
from database.database import get_db_session
from models.application import Application
from models.candidate import Candidate
from models.interview import Interview
from services.application_service import ApplicationService
from services.candidate_service import CandidateService
from services.job_service import JobService
from services.matching_service import MatchingService
from ui import components
from ui.navigation import go_to

_TTL = 30
_SHOW_OPTIONS = [5, 10, 25]
_DEFAULT_SHOW = 10
_COLOR_GOOD, _COLOR_MID, _COLOR_BAD = "#22c55e", "#f59e0b", "#ef4444"
_GOOD, _MID = 75, 50
_SHORTLIST_FROM = ("New", "Screening")
_NO_RECOMMEND_STAGES = ("Rejected", "Hired", "Offer", "Interview")
_BREAKDOWN_LABELS = {
    "skills": "المهارات", "experience": "الخبرة", "location": "الموقع",
    "education": "التعليم", "semantic": "التشابه العام",
}


def _color(value: float) -> str:
    return _COLOR_GOOD if value >= _GOOD else _COLOR_MID if value >= _MID else _COLOR_BAD


def _clean(text: str) -> str:
    return text.lstrip("✓✔⚠❌\ufe0f ").strip()


@st.cache_data(ttl=_TTL, show_spinner=False)
def _load(job_id: int) -> list[dict]:
    """التقديمات المحفوظة لوظيفة (مرتبة حسب الدرجة) كقواميس بسيطة قابلة للتخزين في الكاش."""
    stmt = (
        select(Application, Candidate)
        .join(Candidate, Candidate.id == Application.candidate_id)
        .where(Application.job_id == job_id, Application.match_score.is_not(None))
        .options(defer(Candidate.raw_text), defer(Candidate.embedding))
        .order_by(Application.match_score.desc())
    )
    with get_db_session() as session:
        rows = session.execute(stmt).all()
        app_ids = [a.id for a, _ in rows]
        interviewed = set(session.scalars(
            select(Interview.application_id).where(Interview.application_id.in_(app_ids or [0]))
        ))
        return [
            {
                "app_id": a.id, "candidate_id": c.id, "name": c.full_name,
                "position": c.current_position or "-", "years": c.total_experience_years,
                "location": c.location or "-", "status": a.status, "score": a.match_score,
                "detail": a.match_breakdown or {}, "interviewed": a.id in interviewed,
            }
            for a, c in rows
        ]


def _clear_caches() -> None:
    """بعد أي تغيير: نمسح كل ما يعرض هذه البيانات حتى لا تظهر أرقام قديمة."""
    _load.clear()
    for module_name, fn_name in (("jobs", "_invalidate_job_related_caches"), ("candidates", "invalidate_cache"),
                                 ("dashboard", "clear_cache")):
        try:
            module = __import__(f"views.{module_name}", fromlist=[fn_name])
            getattr(module, fn_name)()
        except Exception:  # noqa: BLE001 - فشل مسح كاش صفحة لا يوقف العملية
            pass


def _shortlist(app_id: int) -> None:
    """callback: نقل التقديم للقائمة المختصرة (قرار المسؤول، عبر ApplicationService)."""
    try:
        user = (st.session_state.get("user") or {}).get("full_name")
        with get_db_session() as session:
            ApplicationService(session).change_status(app_id, "Shortlisted", changed_by=user)
        _clear_caches()
        st.toast("تمت الإضافة للقائمة المختصرة ✅")
    except SmartATSError as exc:
        st.toast(str(exc))


def _run_matching(job_id: int) -> None:
    """يشغّل المطابقة الحالية (MatchingService) لكل المرشحين ضد هذه الوظيفة ويحفظ النتائج."""
    try:
        with st.spinner("جاري البحث عن أفضل المرشحين..."):
            with get_db_session() as session:
                job = JobService(session).get_by_id(job_id)
                candidates = CandidateService(session).list_all(limit=SEARCH_MAX_CANDIDATES)
                if job is not None and candidates:
                    MatchingService(session).match_all_candidates_to_job(job, candidates)
        _clear_caches()
        st.rerun()
    except SmartATSError as exc:
        st.error(str(exc))


def _render_summary(rows: list[dict]) -> None:
    strong = [r for r in rows if r["score"] >= MATCH_HIGH_THRESHOLD]
    recommended = [
        r for r in strong if not r["interviewed"] and r["status"] not in _NO_RECOMMEND_STAGES
    ]
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("👥 مرشحون تمت مطابقتهم", len(rows))
    col_b.metric("⭐ مطابقة قوية", len(strong), help=f"درجة {MATCH_HIGH_THRESHOLD:g}% فأكثر")
    col_c.metric("🗓️ يُنصح بمقابلتهم", len(recommended), help="مطابقة قوية ولم تُجدول لهم مقابلة بعد")


def _render_explanation(r: dict) -> None:
    """شرح الدرجة: لا تُعرض النسبة وحدها (التفصيل من نتيجة MatchingService المحفوظة)."""
    detail = r["detail"]
    breakdown = detail.get("breakdown") or {}
    for key, label in _BREAKDOWN_LABELS.items():
        if key in breakdown:
            value = max(0.0, min(100.0, float(breakdown[key])))
            st.caption(f"{label}: {value:g}%")
            st.progress(value / 100)
    strengths = detail.get("strengths") or []
    gaps = detail.get("gaps") or []
    if strengths:
        st.markdown("**لماذا يناسب الوظيفة**")
        for line in strengths:
            st.write(f"✓ {_clean(line)}")
    if gaps:
        st.markdown("**مهارات تحتاج تحققاً**")
        for line in gaps:
            st.write(f"⚠ {_clean(line)}")
    st.caption("تقدير آلي مبني على السيرة الذاتية — القرار النهائي لك.")


def _render_card(r: dict, job_id: int, job_title: str) -> None:
    score = float(r["score"])
    meta = " · ".join(p for p in (
        r["position"], f"{r['years']:g} سنة خبرة" if r["years"] is not None else None,
        r["location"] if r["location"] != "-" else None,
    ) if p)
    with st.container(border=True):
        col_info, col_score = st.columns([4, 1], vertical_alignment="center")
        col_info.markdown(f"**{html.escape(r['name'])}** — {r['status']}")
        col_info.caption(meta or "-")
        col_score.markdown(
            f'<div style="text-align:center;font-size:1.3rem;font-weight:800;color:{_color(score)}">{score:g}%</div>',
            unsafe_allow_html=True,
        )
        with st.expander("لماذا هذه النسبة؟"):
            _render_explanation(r)

        col_view, col_short, col_iv = st.columns(3)
        col_view.button(
            "👤 عرض الملف", key=f"jc_view_{job_id}_{r['app_id']}", on_click=go_to, args=("candidates",),
            kwargs={"candidates_query": r["name"], "candidates_smart_toggle": False}, width="stretch",
        )
        col_short.button(
            "⭐ قائمة مختصرة", key=f"jc_short_{job_id}_{r['app_id']}", on_click=_shortlist, args=(r["app_id"],),
            disabled=r["status"] not in _SHORTLIST_FROM, width="stretch",
        )
        iv_label = f"{r['name']} · مطابقة {r['score']}% · {r['status']}"
        col_iv.button(
            "🗓️ جدولة مقابلة", key=f"jc_iv_{job_id}_{r['app_id']}", on_click=go_to, args=("interviews",),
            kwargs={"iv_job_select": f"{job_title} (#{job_id})", "iv_app_select": iv_label},
            type="primary" if r["status"] == "Shortlisted" else "secondary", width="stretch",
        )


def render_best_candidates(job_id: int, job_title: str) -> None:
    """القسم الرئيسي في صفحة الوظيفة: الإجراء الأساسي = عرض/تحديث أفضل المرشحين."""
    st.markdown(f"### 🎯 أفضل المرشحين — {job_title}")
    rows = _load(job_id)

    if not CandidateService.__name__:  # pragma: no cover - يحافظ على الاستيراد للتحقق من التحميل
        return

    if not rows:
        with get_db_session() as session:
            has_candidates = bool(CandidateService(session).list_all(limit=1))
        if not has_candidates:
            components.empty_state(
                "👥", "لا يوجد مرشحون بعد", "ارفع سيراً ذاتية أولاً ثم عُد للبحث عن أنسب المرشحين لهذه الوظيفة.",
                [("📄 رفع سيرة ذاتية", "upload_cv", None)], key=f"jc_empty_{job_id}",
            )
            return
        st.info("لم يتم البحث عن مرشحين لهذه الوظيفة بعد.")
        if st.button("🔍 ابحث عن أفضل المرشحين", key=f"jc_run_{job_id}", type="primary", width="stretch"):
            _run_matching(job_id)
        return

    _render_summary(rows)
    col_show, col_refresh = st.columns([1, 2], vertical_alignment="bottom")
    shown = col_show.selectbox("عدد المعروض", _SHOW_OPTIONS, index=_SHOW_OPTIONS.index(_DEFAULT_SHOW),
                               key=f"jc_show_{job_id}")
    if col_refresh.button("🔄 تحديث المطابقة", key=f"jc_run_{job_id}", type="primary", width="stretch",
                          help="يعيد حساب الدرجات بعد إضافة مرشحين جدد أو تعديل متطلبات الوظيفة."):
        _run_matching(job_id)

    for r in rows[:shown]:
        _render_card(r, job_id, job_title)
    if len(rows) > shown:
        st.caption(f"يوجد {len(rows) - shown} مرشح آخر — زد «عدد المعروض» لرؤيتهم.")