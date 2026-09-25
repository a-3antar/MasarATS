"""صفحة التقارير: تقرير توظيف لوظيفة، توفر المهارات، والوظائف التي تحتاج مرشحين، مع تصدير Excel."""

import pandas as pd
import streamlit as st

from database.database import get_db_session
from services.export_service import ExportService
from services.job_service import JobService
from services.report_service import ReportService
from ui import charts

_REPORT_LABELS = {
    "total_cvs": "إجمالي السير", "qualified": "مؤهلون", "shortlisted": "قائمة مختصرة",
    "interviewed": "مقابلات", "offers": "عروض", "hired": "تعيين",
}


def _download(df: pd.DataFrame, name: str, key: str) -> None:
    st.download_button(
        "⬇️ Excel", ExportService.to_excel_bytes(df, name[:30]),
        file_name=f"{name}.xlsx", key=key,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _render_job_report() -> None:
    with get_db_session() as session:
        jobs = JobService(session).list_all()
    if not jobs:
        st.info("أضف وظيفة أولاً.")
        return

    labels = {f"{j.title} (#{j.id})": j.id for j in jobs}
    job_id = labels[st.selectbox("الوظيفة", list(labels), key="rep_job")]
    with get_db_session() as session:
        report = ReportService(session).recruitment_report(job_id)

    for col, (key, label) in zip(st.columns(len(_REPORT_LABELS)), _REPORT_LABELS.items()):
        col.metric(label, report[key])
    st.plotly_chart(charts.funnel_chart([(_REPORT_LABELS[k], v) for k, v in report.items()], "قمع الوظيفة"),
                    width="stretch")
    st.caption("«مؤهلون» = درجة المطابقة 60% فأكثر. وقت التعيين غير متاح لأن النظام لا يسجّل تاريخ تغيير المرحلة بعد.")
    _download(pd.DataFrame([{_REPORT_LABELS[k]: v for k, v in report.items()}]), "job_report", "dl_job_report")


def _render_skills_report() -> None:
    with get_db_session() as session:
        rows = ReportService(session).required_skills_availability()
    if not rows:
        st.info("لا توجد مهارات مطلوبة في وظائف مفتوحة.")
        return
    st.plotly_chart(charts.availability_chart(rows), width="stretch")
    df = pd.DataFrame(rows).rename(columns={
        "skill": "المهارة", "jobs_requiring": "عدد الوظائف الطالبة", "candidates_with_skill": "عدد المرشحين",
    })
    st.dataframe(df, hide_index=True, width="stretch")
    _download(df, "skill_availability", "dl_skills")


def _render_jobs_gap() -> None:
    with get_db_session() as session:
        rows = ReportService(session).jobs_needing_candidates()
    if not rows:
        st.success("كل الوظائف المفتوحة لديها عدد كافٍ من المرشحين.")
        return
    df = pd.DataFrame(rows).rename(columns={"job": "الوظيفة", "department": "القسم", "candidates": "المرشحون"})
    st.dataframe(df, hide_index=True, width="stretch")
    _download(df, "jobs_need_candidates", "dl_jobs_gap")


def render() -> None:
    st.header("📈 التقارير")
    tab_job, tab_skills, tab_gap = st.tabs(["💼 تقرير وظيفة", "🛠️ توفر المهارات", "⚠️ وظائف تحتاج مرشحين"])
    with tab_job:
        _render_job_report()
    with tab_skills:
        _render_skills_report()
    with tab_gap:
        _render_jobs_gap()
