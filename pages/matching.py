"""صفحة مطابقة المرشحين مع وظيفة محددة، مع شرح الدرجة (Explainable Match)."""

import streamlit as st

from database.database import get_db_session
from services.candidate_service import CandidateService
from services.job_service import JobService
from services.matching_service import MatchingService


def render() -> None:
    st.header("🎯 المطابقة")

    with get_db_session() as session:
        jobs = JobService(session).list_all()

    if not jobs:
        st.info("أضف وظيفة أولاً من صفحة «الوظائف».")
        return

    job_titles = {f"{j.title} (#{j.id})": j.id for j in jobs}
    selected_label = st.selectbox("اختر الوظيفة", list(job_titles.keys()))
    job_id = job_titles[selected_label]

    if st.button("🔍 ابحث عن مرشحين مطابقين", type="primary"):
        with get_db_session() as session:
            job = JobService(session).get_by_id(job_id)
            candidates = CandidateService(session).list_all()

            if not candidates:
                st.info("لا يوجد مرشحون بعد لمطابقتهم.")
                return

            results = MatchingService(session).match_all_candidates_to_job(job, candidates)

        for r in results:
            candidate = r["candidate"]
            with st.container(border=True):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.subheader(f"{candidate.full_name}")
                    st.caption(candidate.current_position or "لا يوجد مسمى وظيفي مسجّل")
                with col2:
                    st.metric("درجة المطابقة", f"{r['score']}%")

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
