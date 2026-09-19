"""صفحة رفع السيرة الذاتية وإنشاء مرشح تلقائياً منها."""

import tempfile
from pathlib import Path

import streamlit as st

from config.settings import get_settings
from core.exceptions import DuplicateCandidateError, SmartATSError, ValidationError
from database.database import get_db_session
from services.candidate_service import CandidateService


def render() -> None:
    st.header("📄 رفع سيرة ذاتية")

    if not get_settings().gemini_api_key:
        st.warning(
            "لم يتم ضبط GEMINI_API_KEY بعد — سيتم استخلاص البيانات بشكل أساسي جداً "
            "(بريد/هاتف فقط) بدون فهم ذكي للمحتوى. يمكنك مراجعة البيانات وتعديلها يدوياً بعد الرفع.",
            icon="ℹ️",
        )

    uploaded_files = st.file_uploader(
        "اختر ملف أو أكثر (PDF / DOCX / TXT)",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
    )

    if uploaded_files and st.button("بدء المعالجة", type="primary"):
        progress = st.progress(0.0, text="جاري المعالجة...")
        completed, errors = 0, 0

        for i, uploaded_file in enumerate(uploaded_files, start=1):
            suffix = Path(uploaded_file.name).suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(uploaded_file.getbuffer())
                tmp_path = tmp.name

            try:
                with get_db_session() as session:
                    candidate = CandidateService(session).process_cv_file(tmp_path, uploaded_file.name)
                st.success(f"✅ {uploaded_file.name} → تمت إضافة المرشح: {candidate.full_name}")
                completed += 1
            except DuplicateCandidateError as exc:
                st.warning(f"⚠️ {uploaded_file.name}: {exc}")
            except (ValidationError, SmartATSError) as exc:
                st.error(f"❌ {uploaded_file.name}: {exc}")
                errors += 1
            finally:
                Path(tmp_path).unlink(missing_ok=True)

            progress.progress(i / len(uploaded_files), text=f"تمت معالجة {i} / {len(uploaded_files)}")

        st.info(f"انتهت المعالجة — نجاح: {completed} | أخطاء: {errors}")
