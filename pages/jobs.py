"""صفحة إنشاء وعرض الوظائف الشاغرة."""

import pandas as pd
import streamlit as st

from database.database import get_db_session
from services.job_service import JobService


def render() -> None:
    st.header("💼 الوظائف")

    with st.expander("➕ إضافة وظيفة جديدة", expanded=False):
        with st.form("new_job_form"):
            title = st.text_input("مسمى الوظيفة *")
            department = st.text_input("القسم")
            location = st.text_input("الموقع")
            required_experience = st.number_input("سنوات الخبرة المطلوبة", min_value=0.0, step=0.5)
            skills_raw = st.text_input("المهارات المطلوبة (مفصولة بفاصلة)")
            description = st.text_area("وصف الوظيفة")
            submitted = st.form_submit_button("حفظ الوظيفة", type="primary")

        if submitted:
            try:
                with get_db_session() as session:
                    JobService(session).create_job(
                        title=title,
                        department=department or None,
                        location=location or None,
                        required_experience_years=required_experience or None,
                        required_skills=[s.strip() for s in skills_raw.split(",") if s.strip()],
                        description=description or None,
                    )
                st.success("تمت إضافة الوظيفة.")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))

    with get_db_session() as session:
        jobs = JobService(session).list_all()

        if not jobs:
            st.info("لا توجد وظائف بعد.")
            return

        rows = [
            {
                "id": j.id,
                "المسمى": j.title,
                "القسم": j.department or "-",
                "الموقع": j.location or "-",
                "الخبرة المطلوبة": j.required_experience_years or "-",
                "المهارات": ", ".join(j.required_skills[:5]) if j.required_skills else "-",
                "الحالة": j.status,
            }
            for j in jobs
        ]

    st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)
