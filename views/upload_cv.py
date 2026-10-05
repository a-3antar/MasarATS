"""صفحة رفع السيرة الذاتية كمسار موجَّه من ثلاث خطوات: رفع ← معالجة (حالة لكل ملف) ← نتيجة وإجراء تالٍ."""

import concurrent.futures
import tempfile
from pathlib import Path

import streamlit as st

from config.settings import get_settings
from core.constants import MAX_WORKERS
from core.exceptions import DuplicateCandidateError, SmartATSError, ValidationError
from database.database import get_db_session
from services import background_analysis
from services.candidate_service import CandidateService
from ui.navigation import go_to
from views import candidate_profile

# نتائج الرفع تُحفظ في session_state حتى لا تختفي عند أي rerun
_RESULTS_KEY = "upload_cv_results"
_POLL_SECONDS = 3

_OK, _DUPLICATE, _FAILED = "ok", "duplicate", "failed"


def _process_one(tmp_path: str, filename: str) -> dict:
    """يعالج ملفاً واحداً في جلسة قاعدة بيانات مستقلة. يعمل داخل Thread - لا ينادي أي دالة Streamlit."""
    try:
        with get_db_session() as session:
            candidate = CandidateService(session).process_cv_file(tmp_path, filename)
        return {
            "status": _OK, "filename": filename, "id": candidate.id, "name": candidate.full_name,
            "warning": getattr(candidate, "duplicate_warning", None),
            "face_image": getattr(candidate, "pending_face_image", None),
        }
    except DuplicateCandidateError as exc:
        return {"status": _DUPLICATE, "filename": filename, "message": str(exc)}
    except (ValidationError, SmartATSError) as exc:
        return {"status": _FAILED, "filename": filename, "message": str(exc)}
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _file_status(item: dict) -> str:
    """نص حالة الملف الواحد للعرض."""
    if item["status"] == _DUPLICATE:
        return "⚠️ يحتاج مراجعة (مرشح مكرر)"
    if item["status"] == _FAILED:
        return "❌ فشلت المعالجة"
    if item.get("warning"):
        return "⚠️ تم الحفظ — قد يكون مكرراً"
    if background_analysis.is_pending(item["id"]):
        return "⏳ جاري التحليل بالذكاء الاصطناعي"
    return "✓ اكتمل"


def _summary_counts(results: list[dict]) -> tuple[int, int, int]:
    """(عدد المرشحين المضافين، عدد التحليلات المكتملة، عدد الملفات التي تحتاج مراجعة)."""
    added = [r for r in results if r["status"] == _OK]
    analyzed = sum(1 for r in added if not background_analysis.is_pending(r["id"]))
    review = sum(1 for r in results if r["status"] != _OK or r.get("warning"))
    return len(added), analyzed, review


def _status_panel() -> None:
    """جدول حالة كل ملف + ملخص. يُحدَّث دورياً أثناء التحليل الخلفي ويتوقف عند انتهائه."""
    results: list[dict] = st.session_state.get(_RESULTS_KEY, [])
    if not results:
        return

    added, analyzed, review = _summary_counts(results)
    still_running = analyzed < added
    if not still_running and st.session_state.get("_upload_polling"):
        st.session_state["_upload_polling"] = False
        st.rerun()

    st.markdown("#### 2️⃣ حالة الملفات")
    for item in results:
        col_file, col_state = st.columns([3, 2], vertical_alignment="center")
        col_file.write(f"📎 {item['filename']}")
        col_state.write(_file_status(item))
        if item["status"] != _OK:
            st.caption(item.get("message", ""))

    st.markdown("#### 3️⃣ النتيجة")
    with st.container(border=True):
        st.markdown(f"**{'تمت معالجة السير الذاتية' if not still_running else 'جاري إكمال التحليل...'}**")
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("👤 مرشحون أُضيفوا", added)
        col_b.metric("🤖 تحليلات مكتملة", analyzed)
        col_c.metric("⚠️ تحتاج مراجعة", review)
        if added:
            st.button(
                "👥 عرض المرشحين", key="upload_view_candidates", type="primary",
                on_click=go_to, args=("candidates",), width="stretch",
            )


def _render_status_with_polling() -> None:
    results = st.session_state.get(_RESULTS_KEY, [])
    added, analyzed, _ = _summary_counts(results) if results else (0, 0, 0)
    running = analyzed < added
    st.session_state["_upload_polling"] = running
    st.fragment(_status_panel, run_every=_POLL_SECONDS if running else None)()


def _render_cards() -> None:
    """بطاقة قابلة للتعديل لكل مرشح تم إنشاؤه (تفاصيل ثانوية داخل expander)."""
    added = [r for r in st.session_state.get(_RESULTS_KEY, []) if r["status"] == _OK]
    if not added:
        return
    st.divider()
    header_col, clear_col = st.columns([4, 1])
    header_col.subheader(f"📋 مراجعة البيانات المستخرجة ({len(added)})")
    if clear_col.button("🗑️ إخفاء النتائج", width="stretch"):
        st.session_state[_RESULTS_KEY] = []
        st.rerun()
    for item in added:
        with st.expander(f"👤 {item['name']}  —  📎 {item['filename']}", expanded=len(added) == 1):
            if item.get("warning"):
                st.warning(f"⚠️ قد يكون مكرراً: {item['warning']}")
            candidate_profile.render_profile(item["id"])


def _run_batch(uploaded_files) -> None:
    """يكتب الملفات المؤقتة، يعالجها بالتوازي مع شريط تقدم، ثم يجدول التحليل الخلفي."""
    tmp_jobs: list[tuple[str, str]] = []
    for uploaded_file in uploaded_files:
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_file.name).suffix) as tmp:
            tmp.write(uploaded_file.getbuffer())
            tmp_jobs.append((tmp.name, uploaded_file.name))

    total = len(tmp_jobs)
    progress = st.progress(0.0, text="جاري المعالجة...")
    results: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(MAX_WORKERS, total)) as executor:
        futures = [executor.submit(_process_one, path, name) for path, name in tmp_jobs]
        for done, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            results.append(future.result())
            progress.progress(done / total, text=f"تمت معالجة {done} / {total}")

    # بعد commit كل المرشحين نبدأ التحليل الشامل (لا ينافس الاستخلاص على حصة Gemini)
    for item in results:
        if item["status"] == _OK:
            background_analysis.submit(item["id"])
            background_analysis.submit_photo(item["id"], item.pop("face_image", None))  # لا نخزّن الصور في session_state
        else:
            item.pop("face_image", None)

    st.session_state[_RESULTS_KEY] = results
    try:
        from views import candidates as candidates_view
        candidates_view.invalidate_cache()
    except Exception:  # noqa: BLE001 - فشل مسح الكاش لا يوقف الصفحة
        pass
    st.rerun()


def render() -> None:
    st.header("📄 رفع سير ذاتية")
    st.caption("ارفع ملفات السير الذاتية وسيستخرج النظام بيانات المرشحين تلقائياً.")

    if not get_settings().gemini_api_key:
        st.warning(
            "لم يتم ضبط GEMINI_API_KEY — سيتم استخراج البريد والهاتف فقط بدون فهم ذكي للمحتوى. "
            "يمكنك مراجعة البيانات وتعديلها يدوياً بعد الرفع.",
            icon="ℹ️",
        )

    st.markdown("#### 1️⃣ اختر الملفات")
    uploaded_files = st.file_uploader(
        "اسحب الملفات هنا أو اضغط للاختيار  —  PDF • DOCX • PPTX • TXT",
        type=["pdf", "docx", "pptx", "txt"], accept_multiple_files=True,
    )
    if st.button("🤖 تحليل السير الذاتية", type="primary", disabled=not uploaded_files):
        _run_batch(uploaded_files)

    _render_status_with_polling()
    _render_cards()