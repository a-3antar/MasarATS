"""صفحة العروض والتعيين: إصدار العروض وتتبع الرد عليها، تأكيد التعيين (بقرار بشري)، وسجل تغيير المراحل.
التعيين يزيد current_headcount للمسمى المرتبط بالوظيفة، ويغذي تقرير وقت التعيين."""

import pandas as pd
import streamlit as st

from core.constants import OFFER_STATUSES
from core.exceptions import SmartATSError
from database.database import get_db_session
from services.application_service import ApplicationService
from services.offer_service import OfferService
from services.report_service import ReportService

_DRAFT, _SENT, _ACCEPTED, _DECLINED, _WITHDRAWN = OFFER_STATUSES
_STATUS_LABELS = {
    _DRAFT: "⚪ مسودة", _SENT: "📤 مُرسل", _ACCEPTED: "✅ مقبول", _DECLINED: "❌ مرفوض من المرشح", _WITHDRAWN: "↩️ مسحوب",
}
_HISTORY_LIMIT = 100
_DATE_FORMAT = "%Y-%m-%d %H:%M"


def _user_name() -> str | None:
    return (st.session_state.get("user") or {}).get("full_name")


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


def _fmt(value) -> str:
    return value.strftime(_DATE_FORMAT) if value else "-"


# ------------------------------------------------------------ المؤشرات

def _render_metrics(offers: list[dict]) -> None:
    with get_db_session() as session:
        tth = ReportService(session).time_to_hire()
    active = sum(1 for o in offers if o["status"] in (_DRAFT, _SENT))
    awaiting = sum(1 for o in offers if o["status"] == _ACCEPTED and o["app_status"] != "Hired")
    hired = sum(1 for o in offers if o["app_status"] == "Hired")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📨 عروض قيد الرد", active)
    c2.metric("✅ مقبولة بانتظار التعيين", awaiting)
    c3.metric("🎉 تم تعيينهم", hired)
    if tth["enough"]:
        c4.metric("⏱️ وقت التعيين (متوسط / وسيط)", f"{tth['average']:g} / {tth['median']:g} يوم")
    else:
        c4.metric("⏱️ وقت التعيين", "-")
        st.caption(f"وقت التعيين غير معروض: عدد التعيينات ({tth['count']}) أقل من الحد الأدنى ({tth['minimum']}) لنتيجة مستقرة.")


# ------------------------------------------------------------ تبويب العروض

def _render_create_form() -> None:
    with get_db_session() as session:
        eligible = OfferService(session).eligible_applications()
    if not eligible:
        st.info("لا توجد تقديمات مؤهلة لعرض (قائمة مختصرة / مقابلة) أو أن لكلٍّ منها عرضاً نشطاً.")
        return
    labels = {f"{e['candidate']} — {e['job']} ({e['status']})": e["application_id"] for e in eligible}
    with st.form("new_offer_form", clear_on_submit=True):
        label = st.selectbox("المرشح والوظيفة", list(labels))
        col_salary, col_start = st.columns(2)
        salary = col_salary.number_input("الراتب المعروض", min_value=0.0, step=500.0)
        start = col_start.date_input("تاريخ البدء المقترح", value=None)
        notes = st.text_area("ملاحظات", height=70)
        submitted = st.form_submit_button("➕ إنشاء عرض (مسودة)", type="primary")
    if submitted:
        _run(lambda s: OfferService(s).create_offer(labels[label], salary or None, start, notes, _user_name()),
             "تم إنشاء العرض ✅")


def _render_offer_card(o: dict) -> None:
    oid = o["id"]
    editable = o["status"] in (_DRAFT, _SENT)
    with st.container(border=True):
        st.markdown(f"**{o['candidate']}** — {o['job']}  ·  {_STATUS_LABELS[o['status']]}")
        st.caption(
            f"الراتب: {o['salary']:,.0f}" if o["salary"] else "الراتب: -"
        )
        st.caption(f"بدء: {o['start_date'] or '-'} · أُرسل: {_fmt(o['sent_at'])} · الرد: {_fmt(o['responded_at'])}")
        if o["notes"]:
            st.caption(f"📝 {o['notes']}")

        if editable:
            with st.popover("✏️ تعديل"):
                salary = st.number_input("الراتب", min_value=0.0, step=500.0, value=float(o["salary"] or 0.0), key=f"of_sal_{oid}")
                start = st.date_input("تاريخ البدء", value=o["start_date"], key=f"of_start_{oid}")
                notes = st.text_area("ملاحظات", value=o["notes"] or "", key=f"of_notes_{oid}")
                if st.button("حفظ", key=f"of_save_{oid}", type="primary"):
                    _run(lambda s: OfferService(s).update_offer(oid, salary or None, start, notes), "تم الحفظ ✅")

        actions = {
            _DRAFT: [("📤 تسجيل الإرسال", _SENT), ("↩️ سحب", _WITHDRAWN)],
            _SENT: [("✅ قبل المرشح", _ACCEPTED), ("❌ رفض المرشح", _DECLINED), ("↩️ سحب", _WITHDRAWN)],
            _ACCEPTED: [("↩️ سحب", _WITHDRAWN)],
        }.get(o["status"], [])
        for col, (text, target) in zip(st.columns(len(actions) or 1), actions):
            if col.button(text, key=f"of_{target}_{oid}", width="stretch"):
                _run(lambda s, t=target: OfferService(s).set_status(oid, t), "تم تحديث حالة العرض ✅")
        if o["status"] in (_DRAFT, _WITHDRAWN, _DECLINED) and st.button("🗑️ حذف", key=f"of_del_{oid}"):
            _run(lambda s: OfferService(s).delete_offer(oid), "تم الحذف 🗑️")


def _render_offers_tab(offers: list[dict]) -> None:
    with st.expander("➕ عرض جديد", expanded=not offers):
        _render_create_form()
    status_filter = st.multiselect("تصفية بالحالة", OFFER_STATUSES, format_func=_STATUS_LABELS.get, key="of_filter")
    shown = [o for o in offers if not status_filter or o["status"] in status_filter]
    if not shown:
        st.info("لا توجد عروض مطابقة.")
    for o in shown:
        _render_offer_card(o)


# ------------------------------------------------------------ تبويب التعيين

def _render_hiring_tab(offers: list[dict]) -> None:
    st.caption("التعيين قرار بشري: يظهر هنا من قبل العرض فقط، وتأكيده يزيد «العدد الحالي» للمسمى المرتبط بالوظيفة في الهيكل التنظيمي.")
    pending = [o for o in offers if o["status"] == _ACCEPTED and o["app_status"] != "Hired"]
    if not pending:
        st.info("لا توجد عروض مقبولة بانتظار التعيين.")
    for o in pending:
        with st.container(border=True):
            st.markdown(f"**{o['candidate']}** — {o['job']}")
            st.caption(f"الراتب: {o['salary']:,.0f} · بدء: {o['start_date'] or '-'}" if o["salary"] else f"بدء: {o['start_date'] or '-'}")
            confirm = st.checkbox("أؤكد تعيين هذا المرشح", key=f"hire_ok_{o['id']}")
            if st.button("🎉 تأكيد التعيين", key=f"hire_{o['id']}", type="primary", disabled=not confirm):
                _run(lambda s: OfferService(s).hire(o["id"], _user_name()), "تم التعيين وتحديث الهيكل التنظيمي ✅")

    hired = [o for o in offers if o["app_status"] == "Hired"]
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
        rows = ApplicationService(session).recent_history(_HISTORY_LIMIT)
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


def render() -> None:
    st.header("📨 العروض والتعيين")
    with get_db_session() as session:
        offers = OfferService(session).list_offers()
    _render_metrics(offers)
    tab_offers, tab_hiring, tab_history = st.tabs(["📨 العروض", "🎉 التعيين", "🕘 سجل المراحل"])
    with tab_offers:
        _render_offers_tab(offers)
    with tab_hiring:
        _render_hiring_tab(offers)
    with tab_history:
        _render_history_tab()
