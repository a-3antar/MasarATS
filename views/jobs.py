"""صفحة إدارة الوظائف: إضافة / عرض / تعديل / حذف - بنفس فئات مهارات المرشحين، مع توليد تلقائي بالذكاء الاصطناعي."""

import re

import pandas as pd
import streamlit as st

from core.constants import JOB_STATUSES
from core.exceptions import AIServiceError, SmartATSError
from database.database import get_db_session
from models.job import Job
from services.job_service import JobService
from services.export_service import ExportService


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


def _invalidate_job_related_caches() -> None:
    """
    قوائم الوظائف مخزّنة مؤقتاً في أكثر من صفحة (المطابقة، المقابلات)، ونتيجة
    "الوظائف المناسبة" مخزّنة في بطاقة المرشح. يجب مسحها كلها عند أي تغيير في الوظائف
    حتى لا تظهر بيانات قديمة بعد الحفظ مباشرة.
    """
    try:
        from views import matching as _matching
        _matching._cached_jobs.clear()
    except Exception:
        pass
    try:
        from views import interviews as _interviews
        _interviews._cached_jobs.clear()
    except Exception:
        pass
    try:
        from views import candidate_profile as _profile
        _profile.clear_suitable_jobs_cache()
    except Exception:
        pass


def _split_items(raw: str) -> list[str]:
    """تقسيم نص مفصول بفاصلة (إنجليزية أو عربية) أو أسطر إلى قائمة نظيفة."""
    return [part.strip() for part in re.split(r"[,،\n]", raw or "") if part.strip()]


def _join(items: list[str] | None) -> str:
    return ", ".join(items) if items else "-"


def _form_values_from(job: Job | None, draft: dict | None = None) -> dict:
    """
    القيم المبدئية لحقول النموذج، مفتاحها لاحقة اسم الحقل (title, dept, exp...).
    أولوية القيمة: نتيجة الذكاء الاصطناعي (إن وُجدت وغير فارغة) ثم بيانات الوظيفة الحالية ثم الفراغ.
    """
    draft = draft or {}

    def pick(field: str, current, empty=""):
        return draft.get(field) or current or empty

    values = {
        "title": pick("title", job.title if job else None),
        "dept": pick("department", job.department if job else None),
        "loc": pick("location", job.location if job else None),
        "desc": pick("description", job.description if job else None),
        "exp": float(pick("required_experience_years", job.required_experience_years if job else None, 0.0)),
        "status": job.status if job and job.status in JOB_STATUSES else JOB_STATUSES[_DEFAULT_STATUS_INDEX],
    }
    for _, attr in _LIST_FIELDS:
        items = draft.get(attr) or (getattr(job, attr, None) if job else None) or []
        values[attr] = ", ".join(items)
    return values


def _apply_values_to_state(key: str, values: dict, only_non_empty: bool = False) -> None:
    """يكتب القيم في session_state بمفاتيح الحقول. only_non_empty=True لا يمسح الحقول المعبّأة بقيم فارغة."""
    for suffix, value in values.items():
        if only_non_empty and value in ("", 0.0, None):
            continue
        st.session_state[f"{key}_{suffix}"] = value


def _seed_form_state(key: str, job: Job | None) -> None:
    """يهيّئ حقول النموذج من بيانات الوظيفة مرة واحدة فقط (أول رسم)، حتى لا تُستبدل تعديلات المستخدم."""
    seeded_flag = f"{key}_seeded"
    if st.session_state.get(seeded_flag):
        return
    _apply_values_to_state(key, _form_values_from(job))
    st.session_state[seeded_flag] = True


def _render_ai_job_generator(key: str) -> None:
    """
    زر توليد بيانات الوظيفة تلقائياً من وصف حر عبر الذكاء الاصطناعي.
    يُستدعى قبل رسم النموذج، والنتيجة تُكتب مباشرة في حالة حقوله (session_state).
    """
    with st.expander("🤖 توليد بيانات الوظيفة تلقائياً من وصف حر"):
        raw_description = st.text_area(
            "الصق وصف الوظيفة هنا (نص غير منظم)",
            key=f"{key}_ai_raw_desc",
            height=100,
            placeholder="مثال: نحتاج مدير إنتاج لمصنع بلاستيك بخبرة في الحقن والبثق...",
        )
        if st.button("🤖 توليد تلقائياً", key=f"{key}_ai_generate_btn"):
            if not raw_description.strip():
                st.warning("الصق وصف الوظيفة أولاً.")
                return
            try:
                from ai.job_analyzer import analyze_job_description

                with st.spinner("جاري تحليل الوصف..."):
                    result = analyze_job_description(raw_description.strip())
                _apply_values_to_state(key, _form_values_from(None, result.model_dump()), only_non_empty=True)
                st.toast("تم التوليد — راجع الحقول وعدّلها قبل الحفظ")
                st.rerun()
            except AIServiceError as exc:
                st.error(str(exc))


def _job_form_fields(key: str) -> dict:
    """
    يرسم حقول نموذج الوظيفة (للإضافة أو التعديل) ويرجع القيم المُدخلة.
    القيم المبدئية تأتي من session_state (تُهيَّأ عبر _seed_form_state)، لذلك لا نمرّر value= هنا.
    """
    title = st.text_input("مسمى الوظيفة *", key=f"{key}_title")
    department = st.text_input("القسم", key=f"{key}_dept")
    location = st.text_input("الموقع", key=f"{key}_loc")
    experience = st.number_input("سنوات الخبرة المطلوبة", min_value=0.0, step=0.5, key=f"{key}_exp")
    status = st.selectbox("حالة الوظيفة", JOB_STATUSES, key=f"{key}_status")

    raw_lists: dict[str, str] = {}
    for label, attr in _LIST_FIELDS:
        raw_lists[attr] = st.text_area(
            f"{label} (مفصولة بفاصلة)",
            key=f"{key}_{attr}",
            height=80,
        )

    description = st.text_area("وصف الوظيفة", key=f"{key}_desc")

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
        _seed_form_state("new", None)
        _render_ai_job_generator("new")
        with st.form("new_job_form"):
            values = _job_form_fields("new")
            submitted = st.form_submit_button("حفظ الوظيفة", type="primary")

        if submitted:
            try:
                with get_db_session() as session:
                    JobService(session).create_job(**values)
                # مسح حالة النموذج ليُهيَّأ فارغاً في الرسم التالي
                for state_key in [k for k in st.session_state if str(k).startswith("new_")]:
                    del st.session_state[state_key]
                _invalidate_job_related_caches()
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

    edit_key = f"edit_{job_id}"
    st.subheader(f"✏️ تعديل: {job.title}")
    _seed_form_state(edit_key, job)
    _render_ai_job_generator(edit_key)
    with st.form(f"edit_job_form_{job_id}"):
        values = _job_form_fields(edit_key)
        saved = st.form_submit_button("💾 حفظ التعديلات", type="primary")

    if saved:
        try:
            with get_db_session() as session:
                JobService(session).update_job(job_id, **values)
            # نمسح التهيئة ليُعاد تحميل القيم المحفوظة من القاعدة في الرسم التالي
            for state_key in [k for k in st.session_state if str(k).startswith(f"{edit_key}_")]:
                del st.session_state[state_key]
            _invalidate_job_related_caches()
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
            _invalidate_job_related_caches()
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

    query = st.text_input("بحث بالمسمى / القسم / الموقع", "", key="jobs_search")

    with get_db_session() as session:
        jobs = JobService(session).search(query)
        job_ids = [j.id for j in jobs]
        rows = [_to_row(j) for j in jobs]
        export_df = ExportService.jobs_to_dataframe(jobs)

    if not rows:
        st.info("لا توجد وظائف مطابقة." if query else "لا توجد وظائف بعد.")
        return

    csv_col, xlsx_col, _ = st.columns([1, 1, 4])
    with csv_col:
        st.download_button(
            "⬇️ CSV", ExportService.to_csv_bytes(export_df),
            file_name="jobs.csv", mime="text/csv", width="stretch",
        )
    with xlsx_col:
        st.download_button(
            "⬇️ Excel", ExportService.to_excel_bytes(export_df, "Jobs"),
            file_name="jobs.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )

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