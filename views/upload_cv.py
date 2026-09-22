"""صفحة رفع السيرة الذاتية وإنشاء مرشح تلقائياً منها، مع عرض البيانات المستخرجة كبطاقات قابلة للتعديل."""

import concurrent.futures
import tempfile
from pathlib import Path

import streamlit as st

from config.settings import get_settings
from core.exceptions import DuplicateCandidateError, SmartATSError, ValidationError
from database.database import get_db_session
from views import candidate_profile
from services.candidate_service import CandidateService

# مفتاح حفظ نتائج الرفع في session_state حتى لا تختفي البطاقات عند أي rerun (مثل حفظ تعديل)
_RESULTS_KEY = "upload_cv_results"

# عدد الملفات المعالَجة بالتوازي. أكبر من هذا قد يضغط على حصة (quota) Gemini
# أو يزيد تعارض الكتابة على SQLite بدل تسريع المعالجة.
_MAX_WORKERS = 4


def _process_one(tmp_path: str, filename: str) -> dict:
    """يعالج ملفاً واحداً في جلسة قاعدة بيانات مستقلة. يعمل داخل Thread منفصل - لا ينادي أي دالة Streamlit."""
    try:
        with get_db_session() as session:
            candidate = CandidateService(session).process_cv_file(tmp_path, filename)
        return {
            "ok": True,
            "filename": filename,
            "id": candidate.id,
            "name": candidate.full_name,
            "warning": getattr(candidate, "duplicate_warning", None),
        }
    except DuplicateCandidateError as exc:
        return {"ok": False, "duplicate": True, "filename": filename, "message": str(exc)}
    except (ValidationError, SmartATSError) as exc:
        return {"ok": False, "duplicate": False, "filename": filename, "message": str(exc)}
    finally:
        Path(tmp_path).unlink(missing_ok=True)


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
            if item.get("warning"):
                st.warning(f"⚠️ قد يكون مكرراً: {item['warning']}")
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
        # نكتب كل الملفات المؤقتة في الخيط الرئيسي أولاً (أسرع وأأمن من الكتابة داخل الـ threads)
        tmp_jobs: list[tuple[str, str]] = []
        for uploaded_file in uploaded_files:
            suffix = Path(uploaded_file.name).suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(uploaded_file.getbuffer())
                tmp_jobs.append((tmp.name, uploaded_file.name))

        total = len(tmp_jobs)
        progress = st.progress(0.0, text="جاري المعالجة...")
        completed, errors, done = 0, 0, 0
        new_results: list[dict] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, total)) as executor:
            futures = [executor.submit(_process_one, path, name) for path, name in tmp_jobs]
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                done += 1

                if result["ok"]:
                    new_results.append(
                        {
                            "id": result["id"],
                            "name": result["name"],
                            "filename": result["filename"],
                            "warning": result["warning"],
                        }
                    )
                    completed += 1
                elif result.get("duplicate"):
                    st.warning(f"⚠️ {result['filename']}: {result['message']}")
                else:
                    st.error(f"❌ {result['filename']}: {result['message']}")
                    errors += 1

                progress.progress(done / total, text=f"تمت معالجة {done} / {total}")

        st.session_state[_RESULTS_KEY] = new_results
        st.info(f"انتهت المعالجة — نجاح: {completed} | أخطاء: {errors}")

    _render_results()