"""صفحة إدارة الوظائف: إضافة / عرض / تعديل / حذف - بنفس فئات مهارات المرشحين."""

import re

import pandas as pd
import streamlit as st

from core.constants import JOB_STATUSES
from core.exceptions import SmartATSError
from database.database import get_db_session
from models.job import Job
from services.job_service import JobService

# نفس فئات مهارات المرشح حتى تكون المطابقة متناسقة
_LIST_FIELDS: list[tuple[str, str]] = [
    ("🛠️ المهارات الفنية المطلوبة", "required_technical_skills"),
    ("💻 مهارات الكمبيوتر المطلوبة", "required_computer_skills"),
    ("📊 المهارات الإدارية المطلوبة", "required_managerial_skills"),
    ("🤝 المهارات الشخصية المطلوبة", "required_soft_skills"),
    ("➕ مهارات أخرى مطلوبة", "required_skills"),
    ("🏭 مجالات العمل المفضلة", "preferred_industries"),
]
_DEFAULT_STATUS_INDEX = 1  # "Open"


def _split_items(raw: str) -> list[str]:
    """تقسيم نص مفصول بفاصلة (إنجليزية أو عربية) أو أسطر إلى قائمة نظيفة."""
    return [part.strip() for part in re.split(r"[,،\n]", raw or "") if part.strip()]


def _join(items: list[str] | None) -> str:
    return ", ".join(items) if items else "-"


def _job_form_fields(key: str, job: Job | None = None) -> dict:
    """يرسم حقول نموذج الوظيفة (للإضافة أو التعديل) ويرجع القيم المُدخلة."""
    title = st.text_input("مسمى الوظيفة *", value=job.title if job else "", key=f"{key}_title")
    department = st.text_input("القسم", value=(job.department or "") if job else "", key=f"{key}_dept")
    location = st.text_input("الموقع", value=(job.location or "") if job else "", key=f"{key}_loc")
    experience = st.number_input(
        "سنوات الخبرة المطلوبة", min_value=0.0, step=0.5,
        value=float(job.required_experience_years or 0.0) if job else 0.0, key=f"{key}_exp",
    )
    status_index = (
        JOB_STATUSES.index(job.status) if job and job.status in JOB_STATUSES else _DEFAULT_STATUS_INDEX
    )
    status = st.selectbox("حالة الوظيفة", JOB_STATUSES, index=status_index, key=f"{key}_status")

    raw_lists: dict[str, str] = {}
    for label, attr in _LIST_FIELDS:
        raw_lists[attr] = st.text_area(
            f"{label} (مفصولة بفاصلة)",
            value=", ".join(getattr(job, attr) or []) if job else "",
            key=f"{key}_{attr}",
            height=80,
        )

    description = st.text_area(
        "وصف الوظيفة", value=(job.description or "") if job else "", key=f"{key}_desc"
    )

    return {
        "title": title,
        "department": department.strip() or None,
        "location": location.strip() or None,
        "required_experience_years": experience or None,
        "status": status,
        "description": description.strip() or None,
        **{attr: _split_items(raw) for attr, raw in raw_lists.items()},
    }


def _render_add_form() -> None:
    with st.expander("➕ إضافة وظيفة جديدة", expanded=False):
        with st.form("new_job_form", clear_on_submit=True):
            values = _job_form_fields("new")
            submitted = st.form_submit_button("حفظ الوظيفة", type="primary")

        if submitted:
            try:
                with get_db_session() as session:
                    JobService(session).create_job(**values)
                st.toast("تمت إضافة الوظيفة ✅")
                st.rerun()
            except SmartATSError as exc:
                st.error(str(exc))


def _render_edit_panel(job_id: int) -> None:
    with get_db_session() as session:
        job = JobService(session).get_by_id(job_id)
    if job is None:
        st.warning("الوظيفة غير موجودة.")
        return

    st.subheader(f"✏️ تعديل: {job.title}")
    with st.form(f"edit_job_form_{job_id}"):
        values = _job_form_fields(f"edit_{job_id}", job)
        saved = st.form_submit_button("💾 حفظ التعديلات", type="primary")

    if saved:
        try:
            with get_db_session() as session:
                JobService(session).update_job(job_id, **values)
            st.toast("تم حفظ التعديلات ✅")
            st.rerun()
        except SmartATSError as exc:
            st.error(str(exc))

    st.divider()
    confirm = st.checkbox(
        "أؤكد حذف هذه الوظيفة وكل التقديمات المرتبطة بها نهائياً", key=f"confirm_delete_{job_id}"
    )
    if st.button("🗑️ حذف الوظيفة", disabled=not confirm, key=f"delete_job_{job_id}"):
        try:
            with get_db_session() as session:
                JobService(session).delete_job(job_id)
            st.toast("تم حذف الوظيفة 🗑️")
            st.rerun()
        except SmartATSError as exc:
            st.error(str(exc))


def _to_row(j: Job) -> dict:
    return {
        "المسمى": j.title,
        "القسم": j.department or "-",
        "الموقع": j.location or "-",
        "الخبرة المطلوبة": f"{j.required_experience_years:g}" if j.required_experience_years else "-",
        "المهارات الفنية": _join(j.required_technical_skills),
        "مهارات الكمبيوتر": _join(j.required_computer_skills),
        "المهارات الإدارية": _join(j.required_managerial_skills),
        "المهارات الشخصية": _join(j.required_soft_skills),
        "مهارات أخرى": _join(j.required_skills),
        "المجالات المفضلة": _join(j.preferred_industries),
        "الحالة": j.status,
    }


def render() -> None:
    st.header("💼 الوظائف")

    _render_add_form()

    with get_db_session() as session:
        jobs = JobService(session).list_all()
        job_ids = [j.id for j in jobs]
        rows = [_to_row(j) for j in jobs]

    if not rows:
        st.info("لا توجد وظائف بعد.")
        return

    event = st.dataframe(
        pd.DataFrame(rows),
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="jobs_table",
    )
    st.caption(f"إجمالي الوظائف: {len(rows)} — اضغط على أي صف لتعديل الوظيفة أو حذفها.")

    selected_rows = event.selection.rows
    if selected_rows and selected_rows[0] < len(job_ids):
        st.divider()
        _render_edit_panel(job_ids[selected_rows[0]])