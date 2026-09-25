"""لوحة المعلومات: مؤشرات رئيسية ورسوم تفاعلية للتوظيف."""

import streamlit as st

from database.database import get_db_session
from services.report_service import ReportService
from ui import charts

_CACHE_TTL = 30  # ثوانٍ - الأرقام لا تتغير كل ثانية


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def _dashboard_data() -> dict:
    with get_db_session() as session:
        service = ReportService(session)
        return {
            "kpis": service.kpis(),
            "funnel": service.funnel(),
            "by_status": service.applications_by_status(),
            "by_level": service.candidates_by_career_level(),
            "by_department": service.candidates_by_department(),
            "top_skills": service.top_skills(),
            "top_matches": service.top_matches(),
            "few_candidates": service.jobs_needing_candidates(),
        }


def clear_cache() -> None:
    _dashboard_data.clear()


def _chart_or_empty(fig_factory, data, empty_text: str) -> None:
    if data:
        st.plotly_chart(fig_factory(), width="stretch")
    else:
        st.info(empty_text)


def render() -> None:
    st.header("📊 لوحة المعلومات")
    if st.button("🔄 تحديث"):
        clear_cache()
        st.rerun()

    data = _dashboard_data()
    k = data["kpis"]

    labels = [
        ("👥 المرشحون", "total_candidates"), ("💼 وظائف مفتوحة", "open_jobs"),
        ("🗓️ مقابلات مجدولة", "scheduled_interviews"), (f"🆕 سير جديدة", "new_cvs"),
        ("⭐ قائمة مختصرة", "shortlisted"), ("📨 عروض", "offers"), ("✅ تعيين", "hired"),
    ]
    for col, (label, key) in zip(st.columns(len(labels)), labels):
        col.metric(label, k[key])
    st.caption("«سير جديدة» = مرشحون أُضيفوا خلال آخر 7 أيام.")

    col1, col2 = st.columns(2)
    with col1:
        _chart_or_empty(lambda: charts.funnel_chart(data["funnel"]),
                        any(n for _, n in data["funnel"]), "لا توجد تقديمات بعد. شغّل المطابقة من صفحة «المطابقة».")
    with col2:
        _chart_or_empty(lambda: charts.bar_chart(data["by_status"], "التقديمات حسب الحالة"),
                        any(data["by_status"].values()), "لا توجد تقديمات بعد.")

    col3, col4 = st.columns(2)
    with col3:
        _chart_or_empty(lambda: charts.pie_chart(data["by_level"], "المرشحون حسب المستوى الوظيفي"),
                        data["by_level"], "لا يوجد مرشحون بعد.")
    with col4:
        _chart_or_empty(lambda: charts.bar_chart(data["by_department"], "المرشحون حسب القسم"),
                        data["by_department"], "لا توجد تقديمات مرتبطة بأقسام بعد.")

    _chart_or_empty(lambda: charts.bar_chart(data["top_skills"], "أكثر المهارات تكراراً", horizontal=True),
                    data["top_skills"], "لا توجد مهارات مسجّلة بعد.")

    left, right = st.columns(2)
    with left:
        st.subheader("🏆 أفضل المطابقات")
        if data["top_matches"]:
            for m in data["top_matches"]:
                st.write(f"**{m['name']}** — {m['job']} · {m['score']}%")
                st.caption(m["position"])
        else:
            st.info("لم تُشغَّل المطابقة بعد.")
    with right:
        st.subheader("⚠️ وظائف مفتوحة تحتاج مرشحين")
        if data["few_candidates"]:
            for j in data["few_candidates"]:
                st.write(f"**{j['job']}** ({j['department']}) — {j['candidates']} مرشح")
        else:
            st.success("كل الوظائف المفتوحة لديها عدد كافٍ من المرشحين.")
