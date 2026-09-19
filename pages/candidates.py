"""صفحة عرض وبحث المرشحين."""

import pandas as pd
import streamlit as st

from database.database import get_db_session
from services.candidate_service import CandidateService


def render() -> None:
    st.header("👥 المرشحون")

    query = st.text_input("بحث بالاسم / البريد / المسمى الوظيفي", "")

    with get_db_session() as session:
        candidates = CandidateService(session).search(query)

        if not candidates:
            st.info("لا يوجد مرشحون بعد. ابدأ برفع سيرة ذاتية من صفحة «رفع سيرة ذاتية».")
            return

        rows = [
            {
                "الاسم": c.full_name.title(),
                "البريد": c.email or "-",
                "الهاتف": c.phone or "-",
                "المسمى الحالي": c.current_position or "-",
                "الخبرة (سنة)": c.total_experience_years or "-",
                "المهارات": ", ".join(c.skills[:5]) if c.skills else "-",
                "مصدر الملف": c.source_filename or "إدخال يدوي",
            }
            for c in candidates
        ]

    st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)
    st.caption(f"إجمالي النتائج: {len(rows)}")

    with st.expander("➕ إضافة مرشح يدوياً"):
        with st.form("manual_candidate_form"):
            full_name = st.text_input("الاسم الكامل *").title()
            email = st.text_input("البريد الإلكتروني")
            phone = st.text_input("الهاتف")
            current_position = st.text_input("المسمى الوظيفي الحالي")
            experience = st.number_input("سنوات الخبرة", min_value=0.0, step=0.5)
            skills_raw = st.text_input("المهارات (مفصولة بفاصلة)")
            submitted = st.form_submit_button("حفظ")

        if submitted:
            try:
                with get_db_session() as session:
                    CandidateService(session).create_manual(
                        full_name=full_name,
                        email=email or None,
                        phone=phone or None,
                        current_position=current_position or None,
                        total_experience_years=experience or None,
                        skills=[s.strip() for s in skills_raw.split(",") if s.strip()],
                    )
                st.success("تمت إضافة المرشح.")
                st.rerun()
            except Exception as exc:  # noqa: BLE001 - عرض أي خطأ تحقق للمستخدم مباشرة
                st.error(str(exc))
