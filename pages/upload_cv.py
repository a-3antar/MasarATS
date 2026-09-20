"""صفحة رفع السيرة الذاتية وإنشاء مرشح تلقائياً منها، مع عرض البيانات المستخرجة كبطاقات قابلة للتعديل."""

import tempfile
from pathlib import Path

import streamlit as st

from config.settings import get_settings
from core.exceptions import DuplicateCandidateError, SmartATSError, ValidationError
from database.database import get_db_session
from pages import candidate_profile
from services.candidate_service import CandidateService

# مفتاح حفظ نتائج الرفع في session_state حتى لا تختفي البطاقات عند أي rerun (مثل حفظ تعديل)
_RESULTS_KEY = "upload_cv_results"


def _render_results() -> None:
    """يعرض بطاقة قابلة للتعديل لكل مرشح تم استخلاصه في هذه الجلسة."""
    results: list[dict] = st.session_state.get(_RESULTS_KEY, [])
    if not results:
        return

    st.divider()
    header_col, clear_col = st.columns([4, 1])
    with header_col:
        st.subheader(f"📋 البيانات المستخرجة ({len(results)})")
        st.caption("راجع البيانات، ويمكنك تعديلها من تبويب «✏️ تعديل» داخل كل بطاقة (وأيضاً لاحقاً من صفحة المرشحين).")
    with clear_col:
        if st.button("🗑️ إخفاء النتائج", width="stretch"):
            st.session_state[_RESULTS_KEY] = []
            st.rerun()

    for item in results:
        label = f"👤 {item['name']}  —  📎 {item['filename']}"
        with st.expander(label, expanded=len(results) == 1):
            candidate_profile.render_profile(item["id"])


def render() -> None:
    st.header("📄 رفع سيرة ذاتية")

    if not get_settings().gemini_api_key:
        st.warning(
            "لم يتم ضبط GEMINI_API_KEY بعد — سيتم استخلاص البيانات بشكل أساسي جداً "
            "(بريد/هاتف فقط) بدون فهم ذكي للمحتوى. يمكنك مراجعة البيانات وتعديلها يدوياً بعد الرفع.",
            icon="ℹ️",
        )

    uploaded_files = st.file_uploader(
        "اختر ملف أو أكثر (PDF / DOCX / PPTX / TXT)",
        type=["pdf", "docx", "pptx", "txt"],
        accept_multiple_files=True,
    )
        
    if uploaded_files and st.button("بدء المعالجة", type="primary"):
        progress = st.progress(0.0, text="جاري المعالجة...")
        completed, errors = 0, 0
        new_results: list[dict] = []

        for i, uploaded_file in enumerate(uploaded_files, start=1):
            suffix = Path(uploaded_file.name).suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(uploaded_file.getbuffer())
                tmp_path = tmp.name

            try:
                with get_db_session() as session:
                    candidate = CandidateService(session).process_cv_file(tmp_path, uploaded_file.name)
                new_results.append(
                    {"id": candidate.id, "name": candidate.full_name, "filename": uploaded_file.name}
                )
                completed += 1
            except DuplicateCandidateError as exc:
                st.warning(f"⚠️ {uploaded_file.name}: {exc}")
            except (ValidationError, SmartATSError) as exc:
                st.error(f"❌ {uploaded_file.name}: {exc}")
                errors += 1
            finally:
                Path(tmp_path).unlink(missing_ok=True)

            progress.progress(i / len(uploaded_files), text=f"تمت معالجة {i} / {len(uploaded_files)}")

        st.session_state[_RESULTS_KEY] = new_results
        st.info(f"انتهت المعالجة — نجاح: {completed} | أخطاء: {errors}")

    _render_results()