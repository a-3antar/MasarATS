"""صفحة العروض والتعيين بتصميم لوحة احترافية: مؤشرات + مسار التوظيف، فلاتر، جدول/بطاقات مع ترقيم صفحات،
ثم نسبة القبول والنشاط الأخير والإجراءات السريعة. التعيين قرار بشري ويزيد current_headcount للمسمى المرتبط."""

import html
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from core.constants import DEFAULT_SALARY_CURRENCY, OFFER_STATUSES
from core.exceptions import SmartATSError
from database.database import get_db_session
from services.application_service import ApplicationService
from services.export_service import ExportService
from services.offer_service import EXPIRED, EXPIRING_SOON, EXPIRING_SOON_DAYS, OfferService
from services.report_service import ReportService
from ui import charts
from ui import components
from ui.navigation import OFFER_PREFILL_APP, OFFER_PREFILL_CANDIDATE, go_to


_DRAFT, _SENT, _ACCEPTED, _DECLINED, _WITHDRAWN = OFFER_STATUSES
_HIRED = "Hired"
_PENDING_STATES = (_SENT, EXPIRING_SOON)

_STATUS_LABELS = {
    _DRAFT: "مسودة", _SENT: "مُرسل", _ACCEPTED: "مقبول", _DECLINED: "مرفوض",
    _WITHDRAWN: "مسحوب", EXPIRING_SOON: "ينتهي قريباً", EXPIRED: "منتهي",
}
_STATUS_COLORS = {
    _DRAFT: "#64748b", _SENT: "#3b82f6", _ACCEPTED: "#16a34a", _DECLINED: "#dc2626",
    _WITHDRAWN: "#94a3b8", EXPIRING_SOON: "#d97706", EXPIRED: "#ea580c",
}
_FILTER_STATUSES = [_DRAFT, _SENT, EXPIRING_SOON, EXPIRED, _ACCEPTED, _DECLINED, _WITHDRAWN]

_DATE_FILTERS = {"كل الأوقات": None, "آخر 7 أيام": 7, "آخر 30 يوماً": 30, "آخر 90 يوماً": 90}
_VIEW_TABLE, _VIEW_GRID = "📋 جدول", "🗂️ بطاقات"
_TABLE_WEIGHTS = [3, 2.2, 1.6, 1.4, 1.7, 1.5, 1.4, 1.5, 0.6]
_TABLE_HEADERS = ["المرشح", "الوظيفة", "القسم", "تاريخ العرض", "الراتب", "الحالة", "الانتهاء", "المسؤول", ""]
_GRID_COLUMNS = 3
_PAGE_SIZE = 8
_PAGE_KEY, _SIGNATURE_KEY = "of_page", "of_signature"
_TREND_DAYS = 30
_ACTIVITY_LIMIT = 5
_DEFAULT_EXPIRY_DAYS = 14
_DATE_FORMAT, _DATETIME_FORMAT = "%Y-%m-%d", "%Y-%m-%d %H:%M"
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_NAV_KEY, _REPORTS_PAGE = "nav_page", "📈 التقارير"

_OFFER_APP_KEY = "new_offer_app"

_CSS = """<style>
.of-card{border:1px solid rgba(128,128,128,.25);border-radius:12px;padding:14px 16px;
  background:rgba(128,128,128,.05);height:100%}
.of-card-title{font-weight:700;margin-bottom:10px}
.of-kpi{display:flex;gap:12px;align-items:center;border:1px solid rgba(128,128,128,.25);
  border-radius:12px;padding:12px 14px;background:rgba(128,128,128,.05);height:100%}
.of-kpi-icon{width:42px;height:42px;flex:0 0 42px;border-radius:50%;display:grid;place-items:center;
  font-size:1.15rem;background:color-mix(in srgb,var(--c) 18%,transparent)}
.of-kpi-label{font-size:.78rem;opacity:.75}
.of-kpi-value{font-size:1.6rem;font-weight:700;line-height:1.2}
.of-kpi-pct{font-size:.74rem;font-weight:600;margin-inline-start:8px;opacity:.7}
.of-kpi-sub{font-size:.7rem;opacity:.65}
.of-pipeline{display:flex;align-items:center;justify-content:space-between;gap:4px}
.of-stage{text-align:center}
.of-circle{width:42px;height:42px;border-radius:50%;display:grid;place-items:center;color:#fff;
  font-weight:700;background:var(--c);margin:0 auto}
.of-stage-label{font-size:.72rem;margin-top:4px;opacity:.8}
.of-arrow{opacity:.45}
.of-th{font-size:.75rem;font-weight:700;opacity:.7;padding:6px 0;border-bottom:1px solid rgba(128,128,128,.3)}
.of-cell{font-size:.82rem}
.of-cand{display:flex;gap:10px;align-items:center}
.of-avatar{width:36px;height:36px;flex:0 0 36px;border-radius:50%;display:grid;place-items:center;
  font-weight:700;font-size:.78rem;background:rgba(37,99,235,.16);color:#2563eb}
.of-name{font-weight:600;font-size:.85rem;line-height:1.2}
.of-sub{font-size:.7rem;opacity:.6;word-break:break-all}
.of-badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:.74rem;font-weight:700;
  color:var(--c);border:1px solid var(--c);background:color-mix(in srgb,var(--c) 14%,transparent);white-space:nowrap}
.of-hr{border:none;border-top:1px solid rgba(128,128,128,.18);margin:2px 0 4px}
.of-page{text-align:center;font-size:.85rem;padding-top:6px}
.of-legend-row{display:flex;justify-content:space-between;font-size:.82rem;padding:4px 0}
.of-dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-inline-end:6px;background:var(--c)}
.of-act{display:flex;gap:10px;font-size:.8rem;padding:6px 0}
.of-act-dot{width:9px;height:9px;border-radius:50%;margin-top:5px;flex:0 0 9px;background:var(--c)}
.of-act-time{font-size:.7rem;opacity:.6}
.of-line{font-size:.8rem;margin:2px 0}
</style>"""


# ------------------------------------------------------------ أدوات عامة

def _inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def _esc(value: str | None) -> str:
    return html.escape(value or "")


def _user_name() -> str | None:
    return (st.session_state.get("user") or {}).get("full_name")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _naive(value: datetime) -> datetime:
    """SQLite يعيد التاريخ بدون tzinfo أحياناً؛ نوحّد المقارنة على UTC بدون tzinfo."""
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _fmt(value) -> str:
    return value.strftime(_DATETIME_FORMAT) if value else "-"


def _fmt_date(value) -> str:
    return value.strftime(_DATE_FORMAT) if value else "-"


def _salary_text(salary: float | None) -> str:
    return f"{salary:,.0f} {DEFAULT_SALARY_CURRENCY}" if salary else "-"


def _initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "؟"


def _badge(status: str) -> str:
    color = _STATUS_COLORS.get(status, "#64748b")
    return f'<span class="of-badge" style="--c:{color}">{_esc(_STATUS_LABELS.get(status, status))}</span>'


def _candidate_cell(o: dict) -> str:
    return (
        f'<div class="of-cand"><div class="of-avatar">{_esc(_initials(o["candidate"]))}</div>'
        f'<div><div class="of-name">{_esc(o["candidate"])}</div>'
        f'<div class="of-sub">{_esc(o["email"])}</div></div></div>'
    )


def _invalidate() -> None:
    """التعيين يغيّر الهيكل والتقارير والمرشحين: نمسح كاشها حتى لا تظهر أرقام قديمة."""
    for module_name, cache_fn in (("jobs", "_invalidate_job_related_caches"), ("candidates", "invalidate_cache"),
                                  ("dashboard", "clear_cache")):
        try:
            module = __import__(f"views.{module_name}", fromlist=[cache_fn])
            getattr(module, cache_fn)()
        except Exception:  # noqa: BLE001 - فشل مسح كاش صفحة لا يوقف العملية
            pass


def _run(action, success: str) -> None:
    try:
        with get_db_session() as session:
            action(session)
    except SmartATSError as exc:
        st.error(str(exc))
        return
    _invalidate()
    st.toast(success)
    st.rerun()


def _set_page(page: int) -> None:
    st.session_state[_PAGE_KEY] = page


def _go_to_reports() -> None:
    st.session_state[_NAV_KEY] = _REPORTS_PAGE

def _prefill_choice(eligible: list[dict]) -> int:
    """التقديم المحدَّد مسبقاً في نافذة العرض: بالتقديم أولاً ثم بالمرشح، وإلا أول تقديم مؤهل."""
    app_id = st.session_state.pop(OFFER_PREFILL_APP, None)
    candidate_id = st.session_state.pop(OFFER_PREFILL_CANDIDATE, None)
    for e in eligible:
        if app_id and e["application_id"] == app_id:
            return e["application_id"]
    for e in eligible:
        if candidate_id and e.get("candidate_id") == candidate_id:
            return e["application_id"]
    return eligible[0]["application_id"]

# ------------------------------------------------------------ نوافذ إنشاء/تعديل عرض

@st.dialog("➕ عرض جديد", width="large")
def _create_dialog() -> None:
    with get_db_session() as session:
        eligible = OfferService(session).eligible_applications()
    if not eligible:
        st.info("لا يوجد مرشحون جاهزون لعرض. يصبح المرشح مؤهلاً عند وصوله إلى القائمة المختصرة أو المقابلة، ولا يكون له عرض نشط.")
        st.button("🧭 فتح مسار التوظيف", key="of_dlg_to_pipeline", on_click=go_to, args=("pipeline",))
        return

    by_app = {e["application_id"]: e for e in eligible}
    if st.session_state.get(_OFFER_APP_KEY) not in by_app:
        st.session_state[_OFFER_APP_KEY] = _prefill_choice(eligible)

    application_id = st.selectbox(
        "المرشح والوظيفة", list(by_app), key=_OFFER_APP_KEY,
        format_func=lambda a: f"{by_app[a]['candidate']} — {by_app[a]['job']} ({by_app[a]['status']})",
    )
    with st.form("new_offer_form"):
        col_salary, col_start, col_expiry = st.columns(3)
        salary = col_salary.number_input("الراتب المعروض", min_value=0.0, step=500.0)
        start = col_start.date_input("تاريخ البدء المقترح", value=None)
        expires = col_expiry.date_input(
            "آخر موعد للرد", value=date.today() + timedelta(days=_DEFAULT_EXPIRY_DAYS), min_value=date.today()
        )
        notes = st.text_area("ملاحظات", height=70)
        submitted = st.form_submit_button("➕ إنشاء العرض (مسودة)", type="primary")
    st.caption("يُنشأ العرض كمسودة ولا يُرسل للمرشح تلقائياً. بعد مراجعته سجّل الإرسال من قائمة «⋯» في الجدول.")

    if submitted:
        st.session_state.pop(_OFFER_APP_KEY, None)
        _run(
            lambda s: OfferService(s).create_offer(application_id, salary or None, start, notes, _user_name(), expires),
            "تم إنشاء العرض ونُقل المرشح إلى مرحلة «العرض» ✅",
        )

@st.dialog("✏️ تعديل العرض", width="large")
def _edit_dialog(o: dict) -> None:
    oid = o["id"]
    st.caption(f"{o['candidate']} — {o['job']}")
    with st.form(f"edit_offer_form_{oid}"):
        col_salary, col_start, col_expiry = st.columns(3)
        salary = col_salary.number_input("الراتب", min_value=0.0, step=500.0, value=float(o["salary"] or 0.0))
        start = col_start.date_input("تاريخ البدء", value=o["start_date"])
        expires = col_expiry.date_input("آخر موعد للرد", value=o["expires_at"])
        notes = st.text_area("ملاحظات", value=o["notes"] or "")
        saved = st.form_submit_button("💾 حفظ", type="primary")
    if saved:
        _run(lambda s: OfferService(s).update_offer(oid, salary or None, start, notes, expires), "تم الحفظ ✅")


# ------------------------------------------------------------ المؤشرات ومسار التوظيف

def _trend_text(offers: list[dict]) -> str:
    now = _now()
    recent_from, previous_from = now - timedelta(days=_TREND_DAYS), now - timedelta(days=2 * _TREND_DAYS)
    recent = sum(1 for o in offers if _naive(o["created_at"]) >= recent_from)
    previous = sum(1 for o in offers if previous_from <= _naive(o["created_at"]) < recent_from)
    if not previous:
        return f"{recent} عرض خلال آخر {_TREND_DAYS} يوماً"
    change = (recent - previous) / previous * 100
    return f"{'▲' if change >= 0 else '▼'} {abs(change):.0f}% عن الفترة السابقة"


def _kpi_card(icon: str, label: str, value: int, share: str, sub: str, color: str) -> str:
    return (
        f'<div class="of-kpi"><div class="of-kpi-icon" style="--c:{color}">{icon}</div><div>'
        f'<div class="of-kpi-label">{_esc(label)}</div>'
        f'<div class="of-kpi-value">{value}<span class="of-kpi-pct">{_esc(share)}</span></div>'
        f'<div class="of-kpi-sub">{_esc(sub)}</div></div></div>'
    )


def _pipeline_card(stages: list[tuple[str, int, str]]) -> str:
    parts: list[str] = []
    for index, (label, count, color) in enumerate(stages):
        if index:
            parts.append('<span class="of-arrow">→</span>')
        parts.append(
            f'<div class="of-stage"><div class="of-circle" style="--c:{color}">{count}</div>'
            f'<div class="of-stage-label">{_esc(label)}</div></div>'
        )
    return f'<div class="of-card"><div class="of-card-title">مسار التوظيف</div><div class="of-pipeline">{"".join(parts)}</div></div>'


def _render_summary(offers: list[dict], interview_count: int) -> None:
    total = len(offers)
    count = lambda *states: sum(1 for o in offers if o["display_status"] in states)  # noqa: E731
    share = lambda n: f"{n / total * 100:.0f}%" if total else "-"  # noqa: E731
    pending, accepted, declined, expiring = count(*_PENDING_STATES), count(_ACCEPTED), count(_DECLINED), count(EXPIRING_SOON)

    cards = [
        _kpi_card("📄", "إجمالي العروض", total, "", _trend_text(offers), "#2563eb"),
        _kpi_card("🕒", "بانتظار الرد", pending, share(pending), "بانتظار رد المرشح", "#3b82f6"),
        _kpi_card("✅", "مقبولة", accepted, share(accepted), "قبل المرشح العرض", "#16a34a"),
        _kpi_card("❌", "مرفوضة", declined, share(declined), "رفض المرشح العرض", "#dc2626"),
        _kpi_card("⚠️", "تنتهي قريباً", expiring, share(expiring), f"خلال {EXPIRING_SOON_DAYS} أيام", "#d97706"),
    ]
    stages = [
        ("مقابلة", interview_count, "#64748b"),
        ("عرض", sum(1 for o in offers if o["status"] in (_DRAFT, _SENT)), "#2563eb"),
        ("مقبول", accepted, "#16a34a"),
        ("تعيين", sum(1 for o in offers if o["app_status"] == _HIRED), "#7c3aed"),
    ]
    for col, card in zip(st.columns([1, 1, 1, 1, 1, 1.7]), [*cards, _pipeline_card(stages)]):
        col.markdown(card, unsafe_allow_html=True)


# ------------------------------------------------------------ الفلاتر

def _render_filters(offers: list[dict]) -> dict:
    jobs = sorted({o["job"] for o in offers if o["job"]})
    departments = sorted({o["department"] for o in offers if o["department"]})
    recruiters = sorted({o["created_by"] for o in offers if o["created_by"]})

    col_q, col_status, col_job, col_dept, col_rec, col_date, col_view = st.columns([3, 1.4, 1.6, 1.5, 1.5, 1.5, 1.6])
    query = col_q.text_input(
        "بحث", key="of_q", label_visibility="collapsed", placeholder="🔎 ابحث بالمرشح أو الوظيفة أو البريد..."
    )
    status = col_status.selectbox(
        "الحالة", [None, *_FILTER_STATUSES], key="of_f_status",
        format_func=lambda v: "الكل" if v is None else _STATUS_LABELS[v],
    )
    job = col_job.selectbox("الوظيفة", [None, *jobs], key="of_f_job", format_func=lambda v: "الكل" if v is None else v)
    department = col_dept.selectbox(
        "القسم", [None, *departments], key="of_f_dept", format_func=lambda v: "الكل" if v is None else v
    )
    recruiter = col_rec.selectbox(
        "المسؤول", [None, *recruiters], key="of_f_rec", format_func=lambda v: "الكل" if v is None else v
    )
    period = col_date.selectbox("الفترة", list(_DATE_FILTERS), key="of_f_date")
    view = col_view.radio("العرض", [_VIEW_TABLE, _VIEW_GRID], key="of_view", horizontal=True)
    return {
        "query": query, "status": status, "job": job, "department": department,
        "recruiter": recruiter, "days": _DATE_FILTERS[period], "view": view,
    }


def _apply_filters(offers: list[dict], f: dict) -> list[dict]:
    needle = f["query"].strip().lower()
    since = _now() - timedelta(days=f["days"]) if f["days"] else None
    result = []
    for o in offers:
        haystack = f"{o['candidate']} {o['job']} {o['email'] or ''}".lower()
        if needle and needle not in haystack:
            continue
        if f["status"] and o["display_status"] != f["status"]:
            continue
        if f["job"] and o["job"] != f["job"]:
            continue
        if f["department"] and o["department"] != f["department"]:
            continue
        if f["recruiter"] and o["created_by"] != f["recruiter"]:
            continue
        if since and _naive(o["created_at"]) < since:
            continue
        result.append(o)
    return result


# ------------------------------------------------------------ إجراءات العرض (قائمة ⋯)

def _render_actions(o: dict) -> None:
    oid = o["id"]
    with st.popover("⋯"):
        st.caption(f"{o['candidate']} — {o['job']}")
        if o["status"] in (_DRAFT, _SENT) and st.button("✏️ تعديل البيانات", key=f"of_edit_{oid}", width="stretch"):
            _edit_dialog(o)

        actions = {
            _DRAFT: [("📤 تسجيل الإرسال", _SENT), ("↩️ سحب", _WITHDRAWN)],
            _SENT: [("✅ قبل المرشح", _ACCEPTED), ("❌ رفض المرشح", _DECLINED), ("↩️ سحب", _WITHDRAWN)],
            _ACCEPTED: [("↩️ سحب", _WITHDRAWN)],
        }.get(o["status"], [])
        for text, target in actions:
            if st.button(text, key=f"of_{target}_{oid}", width="stretch"):
                _run(lambda s, t=target: OfferService(s).set_status(oid, t), "تم تحديث حالة العرض ✅")

        if o["notes"]:
            st.caption(f"📝 {o['notes']}")
        if o["status"] in (_DRAFT, _WITHDRAWN, _DECLINED) and st.button(
            "🗑️ حذف", key=f"of_del_{oid}", width="stretch"
        ):
            _run(lambda s: OfferService(s).delete_offer(oid), "تم الحذف 🗑️")


# ------------------------------------------------------------ الجدول والبطاقات

def _render_table_header() -> None:
    for col, label in zip(st.columns(_TABLE_WEIGHTS), _TABLE_HEADERS):
        col.markdown(f'<div class="of-th">{_esc(label)}</div>', unsafe_allow_html=True)


def _render_table_row(o: dict) -> None:
    cols = st.columns(_TABLE_WEIGHTS, vertical_alignment="center")
    cells = [
        _candidate_cell(o),
        f'<div class="of-cell">{_esc(o["job"])}</div>',
        f'<div class="of-cell">{_esc(o["department"] or "-")}</div>',
        f'<div class="of-cell">{_fmt_date(o["created_at"])}</div>',
        f'<div class="of-cell">{_esc(_salary_text(o["salary"]))}</div>',
        _badge(o["display_status"]),
        f'<div class="of-cell">{_fmt_date(o["expires_at"])}</div>',
        f'<div class="of-cell">{_esc(o["created_by"] or "-")}</div>',
    ]
    for col, cell in zip(cols, cells):
        col.markdown(cell, unsafe_allow_html=True)
    with cols[-1]:
        _render_actions(o)
    st.markdown('<hr class="of-hr">', unsafe_allow_html=True)


def _render_offer_card(o: dict) -> None:
    with st.container(border=True):
        st.markdown(_candidate_cell(o), unsafe_allow_html=True)
        st.markdown(
            f'<div class="of-line"><b>{_esc(o["job"])}</b> · {_esc(o["department"] or "-")}</div>'
            f'<div class="of-line">💰 {_esc(_salary_text(o["salary"]))}</div>'
            f'<div class="of-line">📅 {_fmt_date(o["created_at"])} ← ⏳ {_fmt_date(o["expires_at"])}</div>'
            f'<div class="of-line">👤 {_esc(o["created_by"] or "-")}</div>',
            unsafe_allow_html=True,
        )
        col_badge, col_actions = st.columns([2, 1], vertical_alignment="center")
        col_badge.markdown(_badge(o["display_status"]), unsafe_allow_html=True)
        with col_actions:
            _render_actions(o)


def _render_pagination(total: int, pages: int, page: int, start: int, shown: int) -> None:
    col_info, col_nav = st.columns([3, 2])
    col_info.caption(f"عرض {start + 1}–{start + shown} من {total} عرض")
    with col_nav:
        col_prev, col_label, col_next = st.columns([1, 2, 1])
        col_prev.button("◀", key="of_prev", on_click=_set_page, args=(page - 1,), disabled=page <= 1, width="stretch")
        col_label.markdown(f'<div class="of-page">{page} / {pages}</div>', unsafe_allow_html=True)
        col_next.button("▶", key="of_next", on_click=_set_page, args=(page + 1,), disabled=page >= pages, width="stretch")


def _render_list(rows: list[dict], view: str) -> None:
    if not rows:
        st.info("لا توجد عروض مطابقة.")
        return
    pages = max(1, -(-len(rows) // _PAGE_SIZE))
    page = min(max(st.session_state.get(_PAGE_KEY, 1), 1), pages)
    st.session_state[_PAGE_KEY] = page
    start = (page - 1) * _PAGE_SIZE
    page_rows = rows[start:start + _PAGE_SIZE]

    if view == _VIEW_TABLE:
        _render_table_header()
        for o in page_rows:
            _render_table_row(o)
    else:
        columns = st.columns(_GRID_COLUMNS)
        for index, o in enumerate(page_rows):
            with columns[index % _GRID_COLUMNS]:
                _render_offer_card(o)
    _render_pagination(len(rows), pages, page, start, len(page_rows))


# ------------------------------------------------------------ اللوحات السفلية

def _acceptance_card(offers: list[dict]) -> None:
    total = len(offers)
    count = lambda *states: sum(1 for o in offers if o["display_status"] in states)  # noqa: E731
    items = [
        ("مقبول", count(_ACCEPTED), _STATUS_COLORS[_ACCEPTED]),
        ("بانتظار الرد", count(*_PENDING_STATES), _STATUS_COLORS[_SENT]),
        ("مرفوض", count(_DECLINED), _STATUS_COLORS[_DECLINED]),
        ("منتهي", count(EXPIRED), _STATUS_COLORS[EXPIRED]),
    ]
    with st.container(border=True):
        st.markdown("**📊 نسبة قبول العروض**")
        if not total:
            st.caption("لا توجد عروض بعد.")
            return
        col_chart, col_legend = st.columns([1, 1])
        center = f"{items[0][1] / total * 100:.0f}%"
        col_chart.plotly_chart(charts.donut_chart(items, center), width="stretch")
        rows = "".join(
            f'<div class="of-legend-row"><span><span class="of-dot" style="--c:{color}"></span>{_esc(label)}</span>'
            f'<span>{value} · {value / total * 100:.0f}%</span></div>'
            for label, value, color in items
        )
        col_legend.markdown(f'<div style="padding-top:40px">{rows}</div>', unsafe_allow_html=True)


def _activity_events(offers: list[dict]) -> list[tuple[datetime, str, str]]:
    responded_text = {_ACCEPTED: "قبل {name} العرض", _DECLINED: "رفض {name} العرض", _WITHDRAWN: "تم سحب عرض {name}"}
    events: list[tuple[datetime, str, str]] = []
    for o in offers:
        name = o["candidate"]
        events.append((o["created_at"], f"تم إنشاء عرض لـ {name}", _STATUS_COLORS[_DRAFT]))
        if o["sent_at"]:
            events.append((o["sent_at"], f"تم تسجيل إرسال العرض إلى {name}", _STATUS_COLORS[_SENT]))
        if o["responded_at"] and o["status"] in responded_text:
            events.append((o["responded_at"], responded_text[o["status"]].format(name=name), _STATUS_COLORS[o["status"]]))
    events.sort(key=lambda e: _naive(e[0]), reverse=True)
    return events[:_ACTIVITY_LIMIT]


def _activity_card(offers: list[dict]) -> None:
    with st.container(border=True):
        st.markdown("**🕘 آخر نشاط على العروض**")
        events = _activity_events(offers)
        if not events:
            st.caption("لا يوجد نشاط بعد.")
        for moment, text, color in events:
            st.markdown(
                f'<div class="of-act"><div class="of-act-dot" style="--c:{color}"></div><div>'
                f'<div>{_esc(text)}</div><div class="of-act-time">{_fmt(moment)}</div></div></div>',
                unsafe_allow_html=True,
            )


def _offers_dataframe(offers: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "المرشح": o["candidate"], "البريد": o["email"] or "", "الوظيفة": o["job"],
            "القسم": o["department"] or "", "تاريخ العرض": _fmt_date(o["created_at"]),
            "الراتب": o["salary"], "الحالة": _STATUS_LABELS.get(o["display_status"], o["display_status"]),
            "الانتهاء": _fmt_date(o["expires_at"]), "المسؤول": o["created_by"] or "",
        }
        for o in offers
    ])


def _quick_actions_card(filtered: list[dict]) -> None:
    with st.container(border=True):
        st.markdown("**⚡ إجراءات سريعة**")
        if st.button("➕ إنشاء عرض جديد", key="of_q_new", width="stretch"):
            _create_dialog()
        st.download_button(
            "⬇️ تصدير تقرير العروض (Excel)", ExportService.to_excel_bytes(_offers_dataframe(filtered), "Offers"),
            file_name="offers_report.xlsx", mime=_XLSX_MIME, key="of_q_export", width="stretch",
            disabled=not filtered,
        )
        st.button("📈 فتح صفحة التقارير", key="of_q_reports", on_click=_go_to_reports, width="stretch")
        st.caption("التصدير يشمل نتائج الفلاتر الحالية.")


# ------------------------------------------------------------ تبويب العروض

def _render_offers_tab(offers: list[dict]) -> None:
    f = _render_filters(offers)
    signature = tuple(f.values())
    if st.session_state.get(_SIGNATURE_KEY) != signature:  # تغيّر فلتر: نرجع للصفحة الأولى
        st.session_state[_SIGNATURE_KEY] = signature
        st.session_state[_PAGE_KEY] = 1

    filtered = _apply_filters(offers, f)
    _render_list(filtered, f["view"])

    st.write("")
    col_rate, col_activity, col_quick = st.columns([1.3, 1.5, 1])
    with col_rate:
        _acceptance_card(offers)
    with col_activity:
        _activity_card(offers)
    with col_quick:
        _quick_actions_card(filtered)


# ------------------------------------------------------------ تبويب التعيين

def _render_time_to_hire() -> None:
    with get_db_session() as session:
        tth = ReportService(session).time_to_hire()
    if tth["enough"]:
        st.metric("⏱️ وقت التعيين (متوسط / وسيط)", f"{tth['average']:g} / {tth['median']:g} يوم")
    else:
        st.caption(
            f"وقت التعيين غير معروض: عدد التعيينات ({tth['count']}) أقل من الحد الأدنى ({tth['minimum']}) لنتيجة مستقرة."
        )


def _render_hiring_tab(offers: list[dict]) -> None:
    st.caption("التعيين قرار بشري: يظهر هنا من قبل العرض فقط، وتأكيده يزيد «العدد الحالي» للمسمى المرتبط بالوظيفة في الهيكل التنظيمي.")
    _render_time_to_hire()
    pending = [o for o in offers if o["status"] == _ACCEPTED and o["app_status"] != _HIRED]
    if not pending:
        st.info("لا توجد عروض مقبولة بانتظار التعيين.")
    for o in pending:
        with st.container(border=True):
            st.markdown(f"**{o['candidate']}** — {o['job']}")
            st.caption(f"الراتب: {o['salary']:,.0f} · بدء: {o['start_date'] or '-'}" if o["salary"] else f"بدء: {o['start_date'] or '-'}")
            confirm = st.checkbox("أؤكد تعيين هذا المرشح", key=f"hire_ok_{o['id']}")
            if st.button("🎉 تأكيد التعيين", key=f"hire_{o['id']}", type="primary", disabled=not confirm):
                _run(lambda s: OfferService(s).hire(o["id"], _user_name()), "تم التعيين وتحديث الهيكل التنظيمي ✅")

    hired = [o for o in offers if o["app_status"] == _HIRED]
    if hired:
        st.markdown("**تم تعيينهم**")
        st.dataframe(
            pd.DataFrame([{"المرشح": o["candidate"], "الوظيفة": o["job"], "الراتب": o["salary"], "بدء": o["start_date"]} for o in hired]),
            hide_index=True, width="stretch",
        )
    st.caption("لتصحيح تعيين خاطئ: انقل التقديم من لوحة «المطابقة» إلى مرحلة أخرى وسينقص العدد الحالي تلقائياً.")


# ------------------------------------------------------------ تبويب السجل

def _render_history_tab() -> None:
    with get_db_session() as session:
        rows = ApplicationService(session).recent_history(100)
    if not rows:
        st.info("لا توجد انتقالات مسجّلة بعد. تُسجَّل الانتقالات من لحظة تفعيل هذه الميزة فقط.")
        return
    st.dataframe(
        pd.DataFrame([
            {"الوقت": _fmt(r["at"]), "المرشح": r["candidate"], "الوظيفة": r["job"],
             "من": r["from"] or "-", "إلى": r["to"], "بواسطة": r["by"] or "-", "ملاحظة": r["note"] or ""}
            for r in rows
        ]),
        hide_index=True, width="stretch",
    )


# ------------------------------------------------------------ الصفحة
def render() -> None:
    _inject_css()
    if st.session_state.pop("open_create_offer", False):
        st.session_state.pop(_OFFER_APP_KEY, None)  # الاختيار يأتي من التحديد المسبق لا من فتح سابق
        _create_dialog()
    col_title, col_new = st.columns([5, 1])
    with col_title:
        st.header("📨 العروض والتعيين")
        st.caption("أصدر العروض وتابع ردود المرشحين، ثم أكّد التعيين بنفسك.")
    with col_new:
        st.write("")
        if st.button("➕ عرض جديد", key="of_new_btn", type="primary", width="stretch"):
            st.session_state.pop(_OFFER_APP_KEY, None)
            _create_dialog()

    with get_db_session() as session:
        service = OfferService(session)
        offers = service.list_offers()
        interview_count = service.interview_stage_count()

    if not offers:
        components.empty_state(
            "📨", "لا توجد عروض بعد",
            "عندما ينجح مرشح في المقابلة أنشئ له عرضاً من هنا أو من ملفه أو من مسار التوظيف.",
            [("🧭 فتح مسار التوظيف", "pipeline", None), ("🗓️ المقابلات", "interviews", None)],
            key="of_empty",
        )
        tab_hiring, tab_history = st.tabs(["🎉 التعيين", "🕘 سجل المراحل"])
        with tab_hiring:
            _render_hiring_tab(offers)
        with tab_history:
            _render_history_tab()
        return

    _render_summary(offers, interview_count)
    st.write("")

    tab_offers, tab_hiring, tab_history = st.tabs(["📨 العروض", "🎉 التعيين", "🕘 سجل المراحل"])
    with tab_offers:
        _render_offers_tab(offers)
    with tab_hiring:
        _render_hiring_tab(offers)
    with tab_history:
        _render_history_tab()