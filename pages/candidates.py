"""صفحة عرض وبحث المرشحين، مع فتح بطاقة المرشح الموحّدة عند اختيار صف."""

import pandas as pd
import streamlit as st

from database.database import get_db_session
from models.candidate import Candidate
from pages import candidate_profile
from services.candidate_service import CandidateService
from services.export_service import ExportService

_MAX_SKILLS_IN_TABLE = None  # الحد الأقصى لعدد المهارات التي سيتم عرضها في الجدول، أو None لعرض جميع المهارات


def _join(items: list[str] | None, limit: int | None = None) -> str:
    items = items or []
    return ", ".join(items[:limit]) if items else "-"


def _education_text(items: list[dict] | None) -> str:
    lines = []
    for e in items or []:
        line = " — ".join(p for p in (e.get("degree"), e.get("major"), e.get("institution")) if p)
        if line:
            lines.append(line)
    return "; ".join(lines) if lines else "-"

def _to_row(c: Candidate) -> dict:
    years = c.total_experience_years
    return {
        "الكود": c.candidate_code or "-",
        "الاسم": c.full_name,
        "البريد": c.email or "-",
        "الهاتف": c.phone or "-",
        "العمر": str(c.age) if c.age is not None else "-",
        "LinkedIn": c.linkedin_url or "-",
        "الموقع": c.location or "-",
        "المسمى الحالي": c.current_position or "-",
        "الوظيفة المستهدفة": c.applied_job or "-",
        "الحالة": c.status or "New",
        "التقييم": c.rating or "-",
        "الخبرة (سنة)": f"{years:g}" if years is not None else "-",
        "الراتب المتوقع": f"{c.expected_salary:,.0f}" if c.expected_salary else "-",
        "فترة الإشعار (يوم)": c.notice_period_days or "-",
        "الحالة الاجتماعية": c.marital_status or "-",
        "موقف التجنيد": c.military_status or "-",
        "اللغات": _join(c.languages),
        "التعليم": _education_text(c.education),
        "المهارات الفنية": _join(c.technical_skills, _MAX_SKILLS_IN_TABLE),
        "مهارات الكمبيوتر": _join(c.computer_skills, _MAX_SKILLS_IN_TABLE),
        "المهارات الإدارية": _join(c.managerial_skills, _MAX_SKILLS_IN_TABLE),
        "المهارات الشخصية": _join(c.soft_skills, _MAX_SKILLS_IN_TABLE),
        "المسميات السابقة": _join(c.previous_positions),
        "مجالات العمل السابقة": _join(c.industries),
        "الشركات السابقة": _join(c.previous_companies),
        "ملاحظات": c.recruiter_notes or "-",
        "مصدر الملف": c.source_filename or "إدخال يدوي",
    }

def _render_manual_form() -> None:
    with st.expander("➕ إضافة مرشح يدوياً"):
        with st.form("manual_candidate_form"):
            full_name = st.text_input("الاسم الكامل *")
            email = st.text_input("البريد الإلكتروني")
            phone = st.text_input("الهاتف")
            age = st.number_input("العمر", min_value=0, max_value=100, step=1)
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
                        age=int(age) or None,
                        current_position=current_position or None,
                        total_experience_years=experience or None,
                        skills=[s.strip() for s in skills_raw.split(",") if s.strip()],
                    )
                st.success("تمت إضافة المرشح. يمكنك تصنيف مهاراته من بطاقته > تعديل.")
                st.rerun()
            except Exception as exc:  # noqa: BLE001 - عرض أي خطأ تحقق للمستخدم مباشرة
                st.error(str(exc))

def render() -> None:
    st.header("👥 المرشحون")

    _render_manual_form()

    query = st.text_input("بحث بالاسم / البريد / المسمى الوظيفي", "")

    with get_db_session() as session:
        candidates = CandidateService(session).search(query)
        candidate_ids = [c.id for c in candidates]
        rows = [_to_row(c) for c in candidates]
        export_df = ExportService.candidates_to_dataframe(candidates)

    if not rows:
        st.info("لا يوجد مرشحون بعد. ابدأ برفع سيرة ذاتية من صفحة «رفع سيرة ذاتية».")
        return

    csv_col, xlsx_col, _ = st.columns([1, 1, 4])
    with csv_col:
        st.download_button(
            "⬇️ CSV", ExportService.to_csv_bytes(export_df),
            file_name="candidates.csv", mime="text/csv", width="stretch",
        )
    with xlsx_col:
        st.download_button(
            "⬇️ Excel", ExportService.to_excel_bytes(export_df, "Candidates"),
            file_name="candidates.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )

    event = st.dataframe(
        pd.DataFrame(rows),
        width='stretch',
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="candidates_table",
    )
    st.caption(f"إجمالي النتائج: {len(rows)} — اضغط على أي صف لعرض بطاقة المرشح الكاملة.")

    selected_rows = event.selection.rows
    if selected_rows and selected_rows[0] < len(candidate_ids):
        st.divider()
        candidate_profile.render_profile(candidate_ids[selected_rows[0]])
