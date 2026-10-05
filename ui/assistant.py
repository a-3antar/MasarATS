"""مساعد SmartATS العام في الشريط الجانبي: بحث بلغة طبيعية من أي صفحة.
لا نظام بحث ثانٍ: يعيد استخدام بحث الصفحة الرئيسية (SearchService + الرجوع للبحث النصي).
البحث يُنفَّذ عند الإرسال فقط، والنتائج المختصرة تُحفظ في session_state حتى لا يُعاد الحساب مع كل rerun."""

import streamlit as st

from core.exceptions import SmartATSError
from ui.navigation import NAV_KEY, go_to

_RESULTS_KEY = "sb_ask_results"
_MAX_RESULTS = 5
_HOME_LABEL = "🏠 الرئيسية"  # الرئيسية فيها مربع «اسأل SmartATS» نفسه


def _run_search(query: str) -> None:
    """ينفّذ البحث ويحفظ نتائج مختصرة: {query, interpreted, total, items: [...]}."""
    from views import home as home_view

    try:
        rows, interpreted, summary = home_view._search(query)
    except SmartATSError as exc:
        st.session_state[_RESULTS_KEY] = {"query": query, "error": str(exc)}
        return

    items = []
    for candidate, reason in rows[:_MAX_RESULTS]:
        best = (summary.get(candidate.id) or {}).get("best")
        details = [
            candidate.current_position,
            f"{candidate.total_experience_years:g} سنة خبرة" if candidate.total_experience_years is not None else None,
            f"أفضل مطابقة {best:g}%" if best is not None else None,
            reason or None,
        ]
        items.append({
            "id": candidate.id, "name": candidate.full_name,
            "lookup": candidate.candidate_code or candidate.full_name,
            "details": " · ".join(d for d in details if d) or "-",
        })
    st.session_state[_RESULTS_KEY] = {
        "query": query, "interpreted": interpreted, "total": len(rows), "items": items,
    }


def _render_results(state: dict) -> None:
    if state.get("error"):
        st.error(state["error"])
        return
    if state["interpreted"] is None:
        st.caption("تعذّر الفهم الذكي للطلب، فتم استخدام البحث النصي العادي.")
    else:
        st.caption(f"🔎 فهمنا طلبك: {state['interpreted']}")

    if not state["items"]:
        st.info("لم نجد مرشحين مطابقين. جرّب وصفاً أبسط.")
        st.button("📄 رفع سيرة ذاتية", key="sb_ask_upload", on_click=go_to, args=("upload_cv",), width="stretch")
        return

    st.markdown(f"**وُجد {state['total']} مرشح**")
    for item in state["items"]:
        st.markdown(f"**{item['name']}**")
        st.caption(item["details"])
        st.button(
            "عرض الملف", key=f"sb_ask_open_{item['id']}", on_click=go_to, args=("candidates",),
            kwargs={"candidates_query": item["lookup"], "candidates_smart_toggle": False}, width="stretch",
        )
    if state["total"] > len(state["items"]):
        st.button(
            f"عرض كل النتائج ({state['total']})", key="sb_ask_all", on_click=go_to, args=("candidates",),
            kwargs={"candidates_query": state["query"], "candidates_smart_toggle": True}, type="primary",
            width="stretch",
        )


def render_sidebar_assistant() -> None:
    """زر «اسأل SmartATS» في الشريط الجانبي (يختفي في الصفحة الرئيسية)."""
    if st.session_state.get(NAV_KEY) == _HOME_LABEL:
        return
    with st.popover("🤖 اسأل SmartATS", width="stretch"):
        with st.form("sb_ask_form"):
            query = st.text_area(
                "اسأل", label_visibility="collapsed", height=90,
                placeholder="مثال: مدير إنتاج بخبرة أكثر من 10 سنوات في البلاستيك",
            )
            submitted = st.form_submit_button("🔍 بحث", type="primary")
        if submitted and query.strip():
            with st.spinner("جاري البحث..."):
                _run_search(query.strip())

        state = st.session_state.get(_RESULTS_KEY)
        if state:
            _render_results(state)
            st.button("✖ مسح", key="sb_ask_clear", on_click=lambda: st.session_state.pop(_RESULTS_KEY, None))