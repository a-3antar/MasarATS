"""صفحة المرشحين بتخطيط Master-Detail: جدول مركّز + شريط فلاتر ذكي + لوحة جانبية لبطاقة المرشح.
الأداء: تحميل واحد مخزّن مؤقتاً لكل المرشحين، فلترة وترتيب في الذاكرة، وترقيم صفحات (الصور تُحمَّل لصفحة واحدة فقط)."""

import base64
import hashlib
import html
import io
from collections import Counter

import pandas as pd
import streamlit as st

from ai.schemas import CandidateSearchFilters
from core.constants import CANDIDATE_STATUSES, SEARCH_MAX_CANDIDATES
from core.exceptions import AIServiceError
from database.database import get_db_session
from matching.skill_normalizer import canonical_skill_set, has_skill
from models.candidate import Candidate
from services.candidate_service import CandidateService
from services.export_service import ExportService
from services.search_service import SearchService
from ui import components
from views import candidate_profile

_LIST_TTL = 30                  # ثوانٍ - كاش قائمة المرشحين
_THUMB_PX = 48                  # حجم الصورة الرمزية في الجدول
_EXP_MAX = 30                   # أقصى قيمة في شريط الخبرة (30 = "30 فأكثر")
_TOP_SKILLS_OPTIONS = 60        # عدد المهارات المعروضة في فلتر المهارات
_TOP_LOCATIONS_OPTIONS = 60
_TABLE_HEIGHT = 620
_DRAWER_HEIGHT = 780
_PAGE_SIZES = [10, 25, 50, 100]
_DEFAULT_PAGE_SIZE = 25
_SMART_CACHE_TTL = 3600
_NO_NEXT_ACTION = "—"

_STATUS_ICONS = {
    "New": "⚪", "Screening": "🔵", "Shortlisted": "🟢", "Interview": "🟠",
    "Offer": "🟣", "Hired": "✅", "Rejected": "🔴",
}
_SORT_OPTIONS = ["الأحدث", "الأعلى مطابقة", "الأكثر خبرة", "الاسم"]
_SEARCH_MODE_LABELS = {False: "🔍 بحث عادي", True: "🤖 بحث ذكي"}

_TABLE_VER_KEY = "cand_table_ver"
_SMART_KEY = "candidates_smart_toggle"   # يضبطه home.py عبر go_to - لا تغيّر الاسم
_FILTER_DEFAULTS = {
    "cand_f_status": [], "cand_f_level": [], "cand_f_exp": (0, _EXP_MAX),
    "cand_f_loc": [], "cand_f_skills": [], "cand_sort": _SORT_OPTIONS[0], "candidates_query": "",
}


# ------------------------------------------------------------ تحميل البيانات (مخزّن مؤقتاً)

@st.cache_data(ttl=_LIST_TTL, show_spinner=False)
def _load_data() -> dict:
    """كل المرشحين + ملخص المطابقة + خيارات الفلاتر - استعلام واحد لكل مدة الكاش."""
    with get_db_session() as session:
        service = CandidateService(session)
        candidates = service.list_all(limit=SEARCH_MAX_CANDIDATES)
        summary = service.match_summary()
        photos = {c.id: service.photo_absolute_path(c) for c in candidates}

    skills: Counter[str] = Counter()
    locations: Counter[str] = Counter()
    levels: set[str] = set()
    for c in candidates:
        skills.update(s.strip() for s in c.all_skills if s.strip())
        if c.location:
            locations[c.location.strip()] += 1
        level = ((c.ai_analysis or {}).get("career_level") or "").strip()
        if level:
            levels.add(level)

    return {
        "candidates": candidates,
        "summary": summary,
        "photos": {cid: str(p) if p else None for cid, p in photos.items()},
        "top_skills": [s for s, _ in skills.most_common(_TOP_SKILLS_OPTIONS)],
        "locations": [l for l, _ in locations.most_common(_TOP_LOCATIONS_OPTIONS)],
        "levels": sorted(levels),
    }


@st.cache_data(show_spinner=False, max_entries=2000)
def _thumb_uri(path: str) -> str | None:
    """صورة رمزية مصغّرة كـ data URI لعرضها داخل الجدول."""
    try:
        from PIL import Image

        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail((_THUMB_PX, _THUMB_PX))
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=80)
        return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()
    except Exception:  # noqa: BLE001 - صورة تالفة لا توقف الصفحة
        return None


@st.cache_data(show_spinner="🤖 جاري فهم طلب البحث...", ttl=_SMART_CACHE_TTL)
def _smart_search(query: str) -> dict:
    """بحث بلغة طبيعية: {filters, results: [(candidate_id, reason)]}. مخزّن حتى لا يُستدعى Gemini عند كل rerun."""
    filters = SearchService.parse_query(query)
    with get_db_session() as session:
        found = SearchService(session).search(filters)
    return {
        "filters": filters.model_dump(),
        "results": [(r["candidate"].id, " · ".join(r["reasons"]) or "-") for r in found],
    }


@st.cache_data(ttl=_LIST_TTL, show_spinner="جاري تجهيز الملف...")
def _export(kind: str, ids: tuple[int, ...]) -> bytes:
    wanted = set(ids)
    selected = [c for c in _load_data()["candidates"] if c.id in wanted]
    if kind == "csv":
        return ExportService.to_csv_bytes(ExportService.candidates_to_dataframe(selected))
    if kind == "xlsx":
        return ExportService.to_excel_bytes(ExportService.candidates_to_dataframe(selected), "Candidates")
    return ExportService.candidates_to_organized_workbook_bytes(selected)


def invalidate_cache() -> None:
    """مسح كاش القائمة بعد إضافة/تعديل مرشح."""
    _load_data.clear()
    _export.clear()
    try:
        from views import matching as _matching
        _matching._cached_candidates.clear()
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------ الفلترة والترتيب (في الذاكرة)

def _describe_filters(f: CandidateSearchFilters) -> str:
    """وصف نصي للفلاتر المستخرجة (تستخدمه صفحة الرئيسية أيضاً)."""
    parts = []
    if f.role:
        parts.append(f"المسمى: {f.role}")
    if f.experience_min is not None:
        parts.append(f"خبرة ≥ {f.experience_min:g}")
    if f.experience_max is not None:
        parts.append(f"خبرة ≤ {f.experience_max:g}")
    if f.industry:
        parts.append(f"المجال: {f.industry}")
    if f.skills:
        parts.append("المهارات: " + ", ".join(f.skills))
    if f.location:
        parts.append(f"الموقع: {f.location}")
    return " | ".join(parts) or "لم يُستخرج أي فلتر من الطلب"


def _filters_chips_html(f: CandidateSearchFilters) -> str:
    """الفلاتر المفهومة من الطلب كشارات مختصرة (المسمى / الخبرة / المجال / المهارات / الموقع)."""
    items: list[str] = []
    if f.role:
        items.append(f"المسمى: {f.role}")
    if f.experience_min is not None and f.experience_max is not None:
        items.append(f"الخبرة: {f.experience_min:g}–{f.experience_max:g} سنة")
    elif f.experience_min is not None:
        items.append(f"الخبرة: {f.experience_min:g}+ سنة")
    elif f.experience_max is not None:
        items.append(f"الخبرة: حتى {f.experience_max:g} سنة")
    if f.industry:
        items.append(f"المجال: {f.industry}")
    if f.skills:
        items.append("المهارات: " + "، ".join(f.skills))
    if f.location:
        items.append(f"الموقع: {f.location}")
    if not items:
        return "<span style='opacity:.7'>لم يُستخرج أي فلتر من الطلب</span>"
    style = ("display:inline-block;padding:2px 10px;margin:0 0 6px 6px;border-radius:999px;font-size:.78rem;"
             "border:1px solid rgba(59,130,246,.35);background:rgba(59,130,246,.10)")
    return "".join(f'<span style="{style}">{html.escape(i)}</span>' for i in items)


def _text_match(c: Candidate, query: str) -> bool:
    haystack = " ".join(
        str(v) for v in (
            c.full_name, c.email, c.phone, c.candidate_code, c.current_position, c.applied_job,
            " ".join(c.all_skills), " ".join(c.previous_companies or []),
        ) if v
    ).lower()
    return all(token in haystack for token in query.lower().split())


def _passes_filters(c: Candidate, f: dict) -> bool:
    if f["status"] and (c.status or "New") not in f["status"]:
        return False
    if f["level"] and ((c.ai_analysis or {}).get("career_level") or "") not in f["level"]:
        return False
    low, high = f["exp"]
    years = c.total_experience_years
    if low > 0 or high < _EXP_MAX:
        if years is None or years < low or (high < _EXP_MAX and years > high):
            return False
    if f["loc"] and (c.location or "").strip() not in f["loc"]:
        return False
    if f["skills"]:
        keys = canonical_skill_set(c.all_skills)
        if not all(has_skill(s, keys) for s in f["skills"]):
            return False
    return True


def _sort(items: list[Candidate], summary: dict, mode: str) -> list[Candidate]:
    if mode == "الأعلى مطابقة":
        return sorted(items, key=lambda c: (summary.get(c.id) or {}).get("best") or -1, reverse=True)
    if mode == "الأكثر خبرة":
        return sorted(items, key=lambda c: c.total_experience_years or -1, reverse=True)
    if mode == "الاسم":
        return sorted(items, key=lambda c: c.full_name.lower())
    return sorted(items, key=lambda c: c.id, reverse=True)


# ------------------------------------------------------------ مكوّنات الواجهة

def _reset_filters() -> None:
    for key, value in _FILTER_DEFAULTS.items():
        st.session_state[key] = value


def _close_drawer() -> None:
    st.session_state[_TABLE_VER_KEY] = st.session_state.get(_TABLE_VER_KEY, 0) + 1  # مفتاح جديد = تصفير التحديد


def _render_manual_form() -> None:
    with st.form("manual_candidate_form"):
        full_name = st.text_input("الاسم الكامل *")
        email = st.text_input("البريد الإلكتروني")
        phone = st.text_input("الهاتف")
        age = st.number_input("العمر", min_value=0, max_value=100, step=1)
        current_position = st.text_input("المسمى الوظيفي الحالي")
        experience = st.number_input("سنوات الخبرة", min_value=0.0, step=0.5)
        skills_raw = st.text_input("المهارات (مفصولة بفاصلة)")
        submitted = st.form_submit_button("حفظ", type="primary")

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
            invalidate_cache()
            st.toast("تمت إضافة المرشح ✅")
            st.rerun()
        except Exception as exc:  # noqa: BLE001 - عرض أي خطأ تحقق للمستخدم مباشرة
            st.error(str(exc))


def _render_toolbar(data: dict) -> tuple[str, bool]:
    """الصف الأول: وضع البحث + مربع البحث + إضافة. الصف الثاني: الفلاتر. يرجع (نص البحث، هل البحث الذكي مفعّل)."""
    with st.container(border=True):
        col_mode, col_search, col_add = st.columns([2.4, 5, 1.3], vertical_alignment="bottom")
        smart = col_mode.radio(
            "طريقة البحث", [False, True], key=_SMART_KEY, horizontal=True, label_visibility="collapsed",
            format_func=_SEARCH_MODE_LABELS.get,
            help="البحث الذكي: صف المرشح المطلوب بجملة عادية، مثال: مدير إنتاج بخبرة أكثر من 10 سنوات في البلاستيك والحقن والبثق.",
        )
        query = col_search.text_input(
            "بحث", key="candidates_query", label_visibility="collapsed",
            placeholder="صف المرشح الذي تحتاجه بجملة عادية..." if smart
            else "ابحث بالاسم أو البريد أو الهاتف أو المسمى الوظيفي...",
        )
        with col_add.popover("➕ إضافة مرشح"):
            _render_manual_form()

        c1, c2, c3, c4, c5, c6 = st.columns([1.3, 1.3, 1.6, 1.3, 1.6, 1.2])
        c1.multiselect("الحالة", CANDIDATE_STATUSES, key="cand_f_status", placeholder="الحالة")
        c2.multiselect("المستوى", data["levels"], key="cand_f_level", placeholder="المستوى الوظيفي")
        c3.slider("الخبرة (سنة)", 0, _EXP_MAX, key="cand_f_exp", value=_FILTER_DEFAULTS["cand_f_exp"])
        c4.multiselect("الموقع", data["locations"], key="cand_f_loc", placeholder="الموقع")
        c5.multiselect("المهارات", data["top_skills"], key="cand_f_skills", placeholder="المهارات")
        c6.selectbox("الترتيب", _SORT_OPTIONS, key="cand_sort")
    return query.strip(), bool(smart)


def _render_export(ids: list[int]) -> None:
    with st.popover("⬇️ تصدير"):
        st.caption(f"{len(ids)} مرشح (كل النتائج الحالية وليس الصفحة فقط)")
        if not ids:
            return
        if st.toggle("تجهيز ملفات التصدير", key="cand_export_toggle"):
            key = tuple(ids)
            st.download_button("📄 CSV", _export("csv", key), file_name="candidates.csv",
                               mime="text/csv", width="stretch", key="dl_cand_csv")
            st.download_button(
                "📊 Excel", _export("xlsx", key), file_name="candidates.xlsx", width="stretch", key="dl_cand_xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            st.download_button(
                "🗂️ Excel منظّم", _export("organized", key), file_name="candidates_organized.xlsx",
                width="stretch", key="dl_cand_org",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )


def _selected_id(table_key: str, page_ids: list[int]) -> int | None:
    """المرشح المحدد في الجدول من الدورة السابقة (نحتاجه قبل رسم الجدول لتحديد التخطيط)."""
    try:
        rows = st.session_state[table_key]["selection"]["rows"]
    except (KeyError, TypeError):
        return None
    return page_ids[rows[0]] if rows and rows[0] < len(page_ids) else None


def _next_action_label(status: str) -> str:
    """نص الإجراء التالي المقترح لمرحلة المرشح (نفس مصدر بطاقة المرشح)."""
    step = candidate_profile._NEXT_ACTIONS.get(status)
    return step[0] if step else _NO_NEXT_ACTION


def _build_rows(page_items: list[Candidate], data: dict, reasons: dict[int, str]) -> list[dict]:
    """صفوف الجدول بترتيب القرار: من هو؟ ما خبرته؟ أين هو في المسار؟ ماذا أفعل بعد ذلك؟"""
    rows = []
    for c in page_items:
        photo = data["photos"].get(c.id)
        status = c.status or "New"
        row = {
            "الصورة": _thumb_uri(photo) if photo else None,
            "الاسم": c.full_name,
            "الوظيفة الحالية": c.current_position or "-",
            "الخبرة": c.total_experience_years,
            "الموقع": c.location or "-",
            "الحالة": f"{_STATUS_ICONS.get(status, '⚪')} {status}",
            "المطابقة": (data["summary"].get(c.id) or {}).get("best"),
            "الإجراء التالي": _next_action_label(status),
        }
        if reasons:
            row["سبب التطابق"] = reasons.get(c.id, "-")
        rows.append(row)
    return rows


_COLUMN_CONFIG = {
    "الصورة": st.column_config.ImageColumn("", width="small"),
    "الاسم": st.column_config.TextColumn("الاسم", width="medium"),
    "الحالة": st.column_config.TextColumn("الحالة", width="small"),
    "المطابقة": st.column_config.ProgressColumn("المطابقة", min_value=0, max_value=100, format="%.0f%%"),
    "الخبرة": st.column_config.NumberColumn("الخبرة", format="%.1f سنة", width="small"),
    "الإجراء التالي": st.column_config.TextColumn("الإجراء التالي", width="medium"),
}


def _render_empty_database() -> None:
    """لا يوجد أي مرشح في النظام: نقترح الخطوة التالية بدل رسالة «لا توجد بيانات»."""
    components.empty_state(
        "👥", "لا يوجد مرشحون بعد", "ابدأ ببناء قاعدة المرشحين: ارفع سيراً ذاتية وسيستخرج النظام بياناتها تلقائياً.",
        [("📄 رفع سيرة ذاتية", "upload_cv", None)], key="cand_empty_db",
    )
    with st.popover("👤 أو أضف مرشحاً يدوياً"):
        _render_manual_form()


def render() -> None:
    st.header("👥 المرشحون")

    data = _load_data()
    candidates: list[Candidate] = data["candidates"]
    summary: dict = data["summary"]

    if not candidates:
        _render_empty_database()
        return

    query, smart = _render_toolbar(data)

    # ---- البحث
    reasons: dict[int, str] = {}
    pool = candidates
    if smart and query:
        try:
            found = _smart_search(query)
            st.markdown("🔎 فهمنا طلبك هكذا: " + _filters_chips_html(CandidateSearchFilters(**found["filters"])),
                        unsafe_allow_html=True)
            by_id = {c.id: c for c in candidates}
            reasons = dict(found["results"])
            pool = [by_id[cid] for cid, _ in found["results"] if cid in by_id]
        except AIServiceError as exc:
            st.warning(f"تعذّر الفهم الذكي للطلب ({exc}) — تم استخدام البحث النصي العادي.")
            pool = [c for c in candidates if _text_match(c, query)]
    elif query:
        pool = [c for c in candidates if _text_match(c, query)]

    # ---- الفلاتر والترتيب
    f = {k: st.session_state.get(f"cand_f_{k}", _FILTER_DEFAULTS[f"cand_f_{k}"])
         for k in ("status", "level", "exp", "loc", "skills")}
    filtered = [c for c in pool if _passes_filters(c, f)]
    if not (smart and query and reasons):  # نتائج البحث الذكي تبقى مرتبة حسب الصلة
        filtered = _sort(filtered, summary, st.session_state.get("cand_sort", _SORT_OPTIONS[0]))

    # ---- شريط الأدوات فوق الجدول
    info_col, clear_col, export_col = st.columns([5, 1.2, 1.2])
    info_col.caption(f"النتائج: **{len(filtered)}** من {len(candidates)} مرشح")
    clear_col.button("🧹 مسح الفلاتر", on_click=_reset_filters, width="stretch")
    with export_col:
        _render_export([c.id for c in filtered])

    if not filtered:
        st.info("لا توجد نتائج مطابقة. جرّب وصفاً أبسط أو اضغط «🧹 مسح الفلاتر».")
        return

    # ---- ترقيم الصفحات (القيم تُقرأ من session_state قبل رسم أدواتها أسفل الجدول)
    page_size = st.session_state.get("cand_page_size", _DEFAULT_PAGE_SIZE)
    pages = max(1, -(-len(filtered) // page_size))
    page = min(max(st.session_state.get("cand_page", 1), 1), pages)
    st.session_state["cand_page"] = page
    start = (page - 1) * page_size
    page_items = filtered[start:start + page_size]
    page_ids = [c.id for c in page_items]

    signature = hashlib.md5(",".join(map(str, page_ids)).encode()).hexdigest()[:8]
    table_key = f"cand_tbl_{st.session_state.get(_TABLE_VER_KEY, 0)}_{signature}"
    selected_id = _selected_id(table_key, page_ids)

    # ---- Master-Detail: الجدول + اللوحة الجانبية
    if selected_id is not None:
        table_area, drawer_area = st.columns([5, 4], gap="medium")
    else:
        table_area, drawer_area = st.container(), None

    with table_area:
        st.dataframe(
            pd.DataFrame(_build_rows(page_items, data, reasons)),
            width="stretch", hide_index=True, height=_TABLE_HEIGHT,
            on_select="rerun", selection_mode="single-row", key=table_key,
            column_config=_COLUMN_CONFIG,
        )
        col_info, col_size, col_page = st.columns([3, 1, 1])
        col_info.caption(
            f"عرض {start + 1}–{start + len(page_items)} من {len(filtered)} — "
            "اضغط على صف لفتح ملف المرشح والإجراء التالي المقترح."
        )
        col_size.selectbox("لكل صفحة", _PAGE_SIZES, index=_PAGE_SIZES.index(_DEFAULT_PAGE_SIZE), key="cand_page_size")
        col_page.number_input("الصفحة", min_value=1, max_value=pages, step=1, key="cand_page")

    if drawer_area is not None:
        with drawer_area:
            st.button("✖ إغلاق البطاقة", on_click=_close_drawer, key="cand_close_drawer")
            with st.container(height=_DRAWER_HEIGHT, border=True):
                candidate_profile.render_drawer(selected_id, summary.get(selected_id))