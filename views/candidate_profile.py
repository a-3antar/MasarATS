"""بطاقة المرشح الموحّدة: ترويسة + أزرار سريعة + مؤشرات + تبويبات (نظرة عامة، خبرات، تفاصيل، وظائف، تعديل).
render_drawer تُستخدم كلوحة جانبية في صفحة المرشحين، و render_profile للاستخدام داخل expander (رفع السير، المقابلات)."""

import html
import re

import streamlit as st

from core.constants import CANDIDATE_STATUSES
from core.exceptions import SmartATSError
from database.database import get_db_session
from models.candidate import Candidate
from services.candidate_service import CandidateService
from services.job_service import JobService
from services import background_analysis

_SKILL_SECTIONS: list[tuple[str, str]] = [
    ("🛠️ المهارات الفنية", "technical_skills"),
    ("💻 مهارات الكمبيوتر", "computer_skills"),
    ("📊 المهارات الإدارية", "managerial_skills"),
    ("🤝 المهارات الشخصية (Soft Skills)", "soft_skills"),
    ("➕ مهارات أخرى", "skills"),
]
_BACKGROUND_SECTIONS: list[tuple[str, str]] = [
    ("🧾 المسميات الوظيفية السابقة", "previous_positions"),
    ("🏭 مجالات العمل السابقة", "industries"),
    ("🏢 الشركات السابقة", "previous_companies"),
]
_LANGUAGES_SECTION: tuple[str, str] = ("🌐 اللغات", "languages")
_PHOTO_WIDTH_PX = 96
_MAX_RESPONSIBILITIES_SHOWN = 8
_LANG_OPTIONS = {"English": "en", "العربية": "ar"}
_NOT_MENTIONED = "غير مذكور في السيرة الذاتية"
_MAX_SUITABLE_JOBS = 5
_POLL_SECONDS = 3
_SUITABLE_JOBS_CACHE_TTL = 60
_NAV_KEY = "nav_page"                       # مفتاح radio التنقل في app.py
_INTERVIEWS_PAGE_LABEL = "🗓️ المقابلات"

_STATUS_COLORS = {
    "New": "#64748b", "Screening": "#3b82f6", "Shortlisted": "#22c55e", "Interview": "#f59e0b",
    "Offer": "#a855f7", "Hired": "#14b8a6", "Rejected": "#ef4444",
}

_CSS = """
<style>
.cp-badge{display:inline-block;padding:2px 12px;border-radius:999px;font-size:.78rem;font-weight:700;
  color:var(--c);border:1px solid var(--c);background:color-mix(in srgb,var(--c) 14%,transparent)}
.cp-chip{display:inline-block;padding:2px 10px;margin:0 4px 6px 0;border-radius:999px;font-size:.76rem;
  border:1px solid rgba(59,130,246,.35);background:rgba(59,130,246,.10)}
.cp-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(105px,1fr));gap:8px;margin:8px 0 4px}
.cp-kpi{padding:9px 12px;border:1px solid rgba(128,128,128,.25);border-radius:10px;background:rgba(128,128,128,.06)}
.cp-kpi-l{font-size:.7rem;opacity:.65}
.cp-kpi-v{font-size:1.05rem;font-weight:700}
.cp-title{font-size:.95rem;font-weight:700;margin:14px 0 6px}
</style>
"""


def _inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


# ------------------------------------------------------------ أدوات صغيرة

def _chips(items: list[str]) -> str:
    return "".join(f'<span class="cp-chip">{html.escape(item)}</span>' for item in items)


def _badge(text: str, color: str) -> str:
    return f'<span class="cp-badge" style="--c:{color}">{html.escape(text)}</span>'


def _kpi_html(items: list[tuple[str, str]]) -> str:
    cells = "".join(
        f'<div class="cp-kpi"><div class="cp-kpi-l">{html.escape(label)}</div>'
        f'<div class="cp-kpi-v">{html.escape(value)}</div></div>'
        for label, value in items
    )
    return f'<div class="cp-kpis">{cells}</div>'


def _split_items(raw: str) -> list[str]:
    """تقسيم نص مفصول بفاصلة (إنجليزية أو عربية) أو أسطر إلى قائمة نظيفة."""
    return [part.strip() for part in re.split(r"[,،\n]", raw or "") if part.strip()]


def _positions_from_experience(candidate: Candidate) -> list[str]:
    """المسميات السابقة من قائمة الخبرات (للسجلات القديمة التي لا تحمل previous_positions)."""
    positions: list[str] = []
    seen: set[str] = set()
    for item in candidate.experience or []:
        value = (item.get("position") or "").strip()
        if value and value.lower() not in seen:
            seen.add(value.lower())
            positions.append(value)
    return positions


def _value(candidate: Candidate, attr: str, lang: str):
    """قيمة الحقل باللغة المطلوبة: الترجمة إن وُجدت، وإلا الأصل."""
    if lang == "ar":
        translated = ((candidate.translations or {}).get("ar") or {}).get(attr)
        if translated:
            return translated
    value = getattr(candidate, attr)
    if attr == "previous_positions" and not value:
        return _positions_from_experience(candidate)
    return value


def clear_related_caches() -> None:
    """تُستدعى بعد أي تعديل على مرشح/وظيفة حتى لا تُعرض بيانات قديمة من الكاش."""
    clear_suitable_jobs_cache()
    try:
        from views import candidates as _candidates
        _candidates.invalidate_cache()
    except Exception:  # noqa: BLE001
        pass


@st.cache_data(ttl=_SUITABLE_JOBS_CACHE_TTL, show_spinner=False)
def _cached_suitable_jobs(candidate_id: int, open_only: bool) -> list[dict]:
    """نتيجة مطابقة مرشح واحد ضد الوظائف - مخزّنة مؤقتاً حسب (candidate_id, open_only)."""
    from services.matching_service import MatchingService

    with get_db_session() as session:
        candidate = CandidateService(session).get_by_id(candidate_id)
        job_service = JobService(session)
        jobs = job_service.list_open() if open_only else job_service.list_all()
        if candidate is None or not jobs:
            return []
        return MatchingService(session).rank_jobs_for_candidate(candidate, jobs)[:_MAX_SUITABLE_JOBS]


def clear_suitable_jobs_cache() -> None:
    _cached_suitable_jobs.clear()


# ------------------------------------------------------------ الترويسة والأزرار السريعة

def _go_to_interviews() -> None:
    st.session_state[_NAV_KEY] = _INTERVIEWS_PAGE_LABEL


def _render_header(candidate: Candidate, photo_path, lang: str) -> None:
    col_photo, col_info = st.columns([1, 3])
    with col_photo:
        if photo_path:
            st.image(str(photo_path), width=_PHOTO_WIDTH_PX)
        else:
            st.markdown("## 👤")
    with col_info:
        status = candidate.status or "New"
        st.markdown(f"### {candidate.full_name}")
        st.markdown(_badge(status, _STATUS_COLORS.get(status, "#64748b")), unsafe_allow_html=True)
        position = _value(candidate, "current_position", lang)
        st.caption(" · ".join(p for p in (position, f"🆔 {candidate.candidate_code}" if candidate.candidate_code else None) if p))

    contact = [
        f"📧 {html.escape(candidate.email)}" if candidate.email else None,
        f"📞 {html.escape(candidate.phone)}" if candidate.phone else None,
        f"📍 {html.escape(_value(candidate, 'location', lang))}" if _value(candidate, "location", lang) else None,
    ]
    if candidate.linkedin_url:
        url = candidate.linkedin_url if candidate.linkedin_url.startswith("http") else f"https://{candidate.linkedin_url}"
        contact.append(f'🔗 <a href="{html.escape(url, quote=True)}" target="_blank">LinkedIn</a>')
    line = "  ·  ".join(c for c in contact if c)
    if line:
        st.markdown(f'<div style="font-size:.85rem">{line}</div>', unsafe_allow_html=True)


def _render_actions(candidate: Candidate) -> None:
    cid = candidate.id
    col_iv, col_mail, col_stage, col_cv = st.columns(4)
    col_iv.button("📅 مقابلة", key=f"act_iv_{cid}", on_click=_go_to_interviews, width="stretch",
                  help="ينقلك لصفحة المقابلات (اختر الوظيفة والمرشح هناك).")
    col_mail.link_button("✉️ بريد", f"mailto:{candidate.email}" if candidate.email else "#",
                         disabled=not candidate.email, width="stretch")
    with col_stage.popover("🔄 المرحلة"):
        current = candidate.status if candidate.status in CANDIDATE_STATUSES else CANDIDATE_STATUSES[0]
        new_status = st.selectbox("المرحلة الجديدة", CANDIDATE_STATUSES,
                                  index=CANDIDATE_STATUSES.index(current), key=f"act_stage_{cid}")
        if st.button("تطبيق", key=f"act_stage_btn_{cid}", type="primary"):
            try:
                with get_db_session() as session:
                    CandidateService(session).update_candidate(cid, status=new_status)
                clear_related_caches()
                st.toast("تم تغيير المرحلة ✅")
                st.rerun()
            except SmartATSError as exc:
                st.error(str(exc))
    col_cv.download_button(
        "📥 السيرة", candidate.raw_text or "", file_name=f"{candidate.candidate_code or cid}_cv.txt",
        disabled=not candidate.raw_text, key=f"act_cv_{cid}", width="stretch",
        help="نص السيرة المستخرج (الملف الأصلي غير محفوظ).",
    )


def _kpis(candidate: Candidate, summary: dict | None) -> list[tuple[str, str]]:
    years = candidate.total_experience_years
    items = [("الخبرة", f"{years:g} سنة" if years is not None else "-")]
    if summary is not None:
        best = summary.get("best")
        items += [("أفضل مطابقة", f"{best:g}%" if best is not None else "-"), ("التقديمات", str(summary.get("apps", 0)))]
    items += [
        ("التقييم", f"{candidate.rating}/5" if candidate.rating else "-"),
        ("فترة الإشعار", f"{candidate.notice_period_days} يوم" if candidate.notice_period_days else "-"),
        ("الراتب المتوقع", f"{candidate.expected_salary:,.0f}" if candidate.expected_salary else "-"),
    ]
    return items


def _choose_language(candidate: Candidate) -> str:
    """اختيار لغة العرض؛ إن لم توجد ترجمة عربية يعرض زر الترجمة ويرجع الإنجليزية."""
    cid = candidate.id
    label = st.radio("🌐 لغة العرض", list(_LANG_OPTIONS), horizontal=True, key=f"lang_{cid}", label_visibility="collapsed")
    lang = _LANG_OPTIONS[label]
    if lang == "ar" and not (candidate.translations or {}).get("ar"):
        st.info("لا توجد ترجمة عربية بعد (تُعرض الإنجليزية مؤقتاً).")
        if st.button("🌐 ترجمة البيانات إلى العربية", key=f"translate_{cid}"):
            try:
                with st.spinner("جاري الترجمة..."):
                    with get_db_session() as session:
                        CandidateService(session).translate_candidate(cid, "ar")
                clear_related_caches()
                st.rerun()
            except SmartATSError as exc:
                st.error(str(exc))
        return "en"
    return lang


# ------------------------------------------------------------ التبويبات

def _render_overview(candidate: Candidate, lang: str) -> None:
    st.markdown('<div class="cp-title">📝 الملخص</div>', unsafe_allow_html=True)
    st.write(_value(candidate, "summary", lang) or _NOT_MENTIONED)

    st.markdown('<div class="cp-title">🧠 المهارات</div>', unsafe_allow_html=True)
    shown = False
    for title, attr in _SKILL_SECTIONS:
        items = _value(candidate, attr, lang) or []
        if items:
            shown = True
            st.caption(title)
            st.markdown(_chips(items), unsafe_allow_html=True)
    if not shown:
        st.caption(_NOT_MENTIONED)

    st.divider()
    _render_ai_analysis(candidate.id)


def _render_experience(candidate: Candidate, lang: str, collapsible: bool) -> None:
    """بطاقات خبرات؛ قابلة للطي في اللوحة الجانبية، وثابتة داخل expander (لا يجوز تداخل expanders)."""
    experience = _value(candidate, "experience", lang) or []
    if not experience:
        st.caption(_NOT_MENTIONED)
        return
    for index, item in enumerate(experience):
        heading = " — ".join(p for p in (item.get("position"), item.get("company")) if p) or "غير محدد"
        period = " → ".join(p for p in (item.get("start_date"), item.get("end_date")) if p)
        holder = st.expander(f"💼 {heading}", expanded=index == 0) if collapsible else st.container(border=True)
        with holder:
            if not collapsible:
                st.markdown(f"**{heading}**")
            if period:
                st.caption(period)
            for line in (item.get("responsibilities") or [])[:_MAX_RESPONSIBILITIES_SHOWN]:
                st.write(f"• {line}")


def _render_details(candidate: Candidate, lang: str) -> None:
    st.markdown('<div class="cp-title">🎓 التعليم</div>', unsafe_allow_html=True)
    education = _value(candidate, "education", lang) or []
    for item in education:
        line = " — ".join(p for p in (item.get("degree"), item.get("major"), item.get("institution")) if p)
        year = item.get("graduation_year")
        st.write(f"• {line or 'غير محدد'}" + (f" ({year})" if year else ""))
    if not education:
        st.caption(_NOT_MENTIONED)

    st.markdown('<div class="cp-title">🧍 بيانات شخصية</div>', unsafe_allow_html=True)
    st.write(
        f"العمر: {candidate.age if candidate.age is not None else 'غير مذكور'}  ·  "
        f"الحالة الاجتماعية: {_value(candidate, 'marital_status', lang) or 'غير مذكور'}  ·  "
        f"موقف التجنيد: {_value(candidate, 'military_status', lang) or 'غير مذكور'}"
    )
    languages = _value(candidate, _LANGUAGES_SECTION[1], lang) or []
    st.caption(_LANGUAGES_SECTION[0])
    st.markdown(_chips(languages) if languages else _NOT_MENTIONED, unsafe_allow_html=True)

    for title, attr in _BACKGROUND_SECTIONS:
        items = _value(candidate, attr, lang) or []
        st.caption(title)
        st.markdown(_chips(items) if items else _NOT_MENTIONED, unsafe_allow_html=True)

    st.markdown('<div class="cp-title">🎯 بيانات التوظيف</div>', unsafe_allow_html=True)
    st.write(f"الوظيفة المستهدفة: {candidate.applied_job or '-'}")
    if candidate.recruiter_notes:
        st.caption(f"📝 ملاحظات: {candidate.recruiter_notes}")
    st.caption(f"📎 المصدر: {candidate.source_filename or 'إدخال يدوي'}")


def _render_suitable_jobs(candidate_id: int) -> None:
    """أفضل الوظائف لهذا المرشح مع شرح الدرجة (بدون expander لأن البطاقة قد تكون داخل expander)."""
    open_only = st.checkbox("الوظائف المفتوحة فقط", value=True, key=f"jobs_open_only_{candidate_id}")
    results = _cached_suitable_jobs(candidate_id, open_only)

    if not results:
        st.info("لا توجد وظائف متاحة للمطابقة. أضف وظيفة من صفحة «الوظائف».")
        return

    for r in results:
        job = r["job"]
        with st.container(border=True):
            col_info, col_score = st.columns([3, 1])
            with col_info:
                st.markdown(f"**{job.title}**")
                st.caption(f"{job.department or 'بدون قسم'} · {job.location or 'بدون موقع'} · {job.status}")
            with col_score:
                st.metric("المطابقة", f"{r['score']}%")

            b = r["breakdown"]
            st.caption(
                f"المهارات: {b['skills']}% · الخبرة: {b['experience']}% · "
                f"الموقع: {b['location']}% · التعليم: {b['education']}%"
                + (f" · دلالي: {b['semantic']}%" if "semantic" in b else "")
            )
            for line in r["strengths"]:
                st.write(line)
            for line in r["gaps"]:
                st.write(line)


# ------------------------------------------------------------ تحليل الذكاء الاصطناعي

def _render_ai_analysis(candidate_id: int) -> None:
    st.markdown("**🤖 تحليل الذكاء الاصطناعي**")
    polling = background_analysis.is_pending(candidate_id)
    # التحديث الدوري يعمل فقط أثناء الانتظار، وعند الانتهاء نعيد تشغيل الصفحة لإيقافه
    st.fragment(_analysis_panel, run_every=_POLL_SECONDS if polling else None)(candidate_id, polling)


def _analysis_panel(candidate_id: int, polling: bool) -> None:
    with get_db_session() as session:
        candidate = CandidateService(session).get_by_id(candidate_id)
    if candidate is None:
        return

    in_memory = background_analysis.is_pending(candidate_id)
    if polling and not in_memory:
        st.rerun()

    analysis = candidate.ai_analysis or {}
    status, error = candidate.analysis_status, candidate.analysis_error
    if status == "pending" and not in_memory:  # بقيت pending بعد إعادة تشغيل التطبيق
        status, error = "failed", "انقطعت المعالجة قبل اكتمالها. أعد التحليل."

    if in_memory:
        st.info("⏳ جاري التحليل في الخلفية (يتحدث تلقائياً).")
    else:
        if status == "failed":
            st.error(f"❌ فشل التحليل: {error or 'سبب غير معروف'}")
        elif not analysis:
            st.caption("لم يتم توليد تحليل الذكاء الاصطناعي لهذا المرشح بعد.")
        label = "🔄 إعادة التحليل" if analysis else "🤖 توليد التحليل"
        if st.button(label, key=f"analysis_btn_{candidate_id}"):
            try:
                with st.spinner("جاري التحليل..."):
                    with get_db_session() as session:
                        CandidateService(session).generate_ai_analysis(candidate_id, force=bool(analysis))
                clear_related_caches()
                st.rerun()
            except SmartATSError as exc:
                st.error(str(exc))

    if not analysis:
        return
    if analysis.get("career_level"):
        st.write(f"📈 المستوى الوظيفي: **{analysis['career_level']}**")
    if analysis.get("strengths"):
        st.markdown("**نقاط القوة:**")
        for s in analysis["strengths"]:
            st.write(f"✓ {s}")
    if analysis.get("potential_gaps"):
        st.markdown("**فجوات محتملة:**")
        for g in analysis["potential_gaps"]:
            st.write(f"⚠ {g}")
    if analysis.get("suitable_functions"):
        st.markdown("**الأقسام/الوظائف المناسبة:**")
        st.markdown(_chips(analysis["suitable_functions"]), unsafe_allow_html=True)
    meta = analysis.get("meta") or {}
    if meta:
        st.caption(f" {meta.get('created_at', '')[:16]}")


# ------------------------------------------------------------ تعديل

def _render_edit_form(candidate: Candidate, photo_path) -> None:
    cid = candidate.id
    st.caption("التعديل يتم على النسخة الإنجليزية (الأصل). عند تعديل محتوى مترجَم تُمسح الترجمة القديمة ويمكن إعادة ترجمتها.")
    with st.form(f"edit_candidate_form_{cid}"):
        full_name = st.text_input("الاسم الكامل *", value=candidate.full_name, key=f"name_{cid}")
        email = st.text_input("البريد الإلكتروني", value=candidate.email or "", key=f"email_{cid}")
        phone = st.text_input("الهاتف", value=candidate.phone or "", key=f"phone_{cid}")
        linkedin = st.text_input("رابط LinkedIn", value=candidate.linkedin_url or "", key=f"lin_{cid}")
        location = st.text_input("الموقع", value=candidate.location or "", key=f"loc_{cid}")
        age = st.number_input(
            "العمر", min_value=0, max_value=100, step=1,
            value=int(candidate.age or 0), key=f"age_{cid}",
        )
        position = st.text_input("المسمى الوظيفي الحالي", value=candidate.current_position or "", key=f"pos_{cid}")
        experience = st.number_input(
            "سنوات الخبرة", min_value=0.0, step=0.5,
            value=float(candidate.total_experience_years or 0.0), key=f"exp_{cid}",
        )
        marital = st.text_input("الحالة الاجتماعية", value=candidate.marital_status or "", key=f"mar_{cid}")
        military = st.text_input("موقف التجنيد", value=candidate.military_status or "", key=f"mil_{cid}")
        summary = st.text_area("النبذة", value=candidate.summary or "", key=f"sum_{cid}")

        raw_lists: dict[str, str] = {}
        for label, attr in _SKILL_SECTIONS + _BACKGROUND_SECTIONS + [_LANGUAGES_SECTION]:
            raw_lists[attr] = st.text_area(
                f"{label} (مفصولة بفاصلة)",
                value=", ".join(_value(candidate, attr, "en") or []),
                key=f"{attr}_{cid}",
                height=80,
            )

        st.markdown("**🎯 بيانات التوظيف**")
        applied_job = st.text_input("الوظيفة المستهدفة", value=candidate.applied_job or "", key=f"job_{cid}")
        current_status = candidate.status if candidate.status in CANDIDATE_STATUSES else CANDIDATE_STATUSES[0]
        status = st.selectbox(
            "الحالة", CANDIDATE_STATUSES, index=CANDIDATE_STATUSES.index(current_status), key=f"status_{cid}"
        )
        rating = st.number_input(
            "التقييم (1 إلى 5، صفر = بدون)", min_value=0, max_value=5, step=1,
            value=int(candidate.rating or 0), key=f"rating_{cid}",
        )
        salary = st.number_input(
            "الراتب المتوقع", min_value=0.0, step=500.0,
            value=float(candidate.expected_salary or 0.0), key=f"salary_{cid}",
        )
        notice = st.number_input(
            "فترة الإشعار (بالأيام)", min_value=0, step=5,
            value=int(candidate.notice_period_days or 0), key=f"notice_{cid}",
        )
        notes = st.text_area("ملاحظات المقابلة والتقييم", value=candidate.recruiter_notes or "", key=f"notes_{cid}")

        new_photo = st.file_uploader("استبدال الصورة", type=["png", "jpg", "jpeg"], key=f"photo_{cid}")
        remove_photo = st.checkbox("حذف الصورة الحالية", key=f"rmphoto_{cid}") if photo_path else False

        submitted = st.form_submit_button("💾 حفظ التعديلات", type="primary")

    if not submitted:
        return

    try:
        with get_db_session() as session:
            service = CandidateService(session)
            service.update_candidate(
                cid,
                full_name=full_name,
                email=email.strip() or None,
                phone=phone.strip() or None,
                linkedin_url=linkedin.strip() or None,
                location=location.strip() or None,
                age=int(age) or None,
                current_position=position.strip() or None,
                total_experience_years=experience or None,
                marital_status=marital.strip() or None,
                military_status=military.strip() or None,
                summary=summary.strip() or None,
                applied_job=applied_job.strip() or None,
                status=status,
                rating=rating or None,
                expected_salary=salary or None,
                notice_period_days=notice or None,
                recruiter_notes=notes.strip() or None,
                **{attr: _split_items(raw) for attr, raw in raw_lists.items()},
            )
            if remove_photo:
                service.remove_photo(cid)
            elif new_photo is not None:
                service.set_photo(cid, new_photo.getvalue())
        clear_related_caches()  # بيانات المرشح تغيّرت - أي كاش له أصبح قديماً
        st.toast("تم حفظ التعديلات ✅")
        st.rerun()
    except SmartATSError as exc:
        st.error(str(exc))


# ------------------------------------------------------------ نقاط الدخول

def render_drawer(candidate_id: int, summary: dict | None = None, *, embedded: bool = False) -> None:
    """
    بطاقة المرشح الكاملة.
    embedded=True: للاستخدام داخل expander (لا أزرار سريعة، ولا expanders متداخلة).
    summary: {"best": أفضل مطابقة، "apps": عدد التقديمات} لإظهار مؤشرات المطابقة (اختياري).
    """
    with get_db_session() as session:
        service = CandidateService(session)
        candidate = service.get_by_id(candidate_id)
        if candidate is None:
            st.warning("المرشح غير موجود.")
            return
        photo_path = service.photo_absolute_path(candidate)

    _inject_css()
    lang = _choose_language(candidate)
    _render_header(candidate, photo_path, lang)
    if not embedded:
        _render_actions(candidate)
    st.markdown(_kpi_html(_kpis(candidate, None if embedded else summary)), unsafe_allow_html=True)

    tab_overview, tab_exp, tab_details, tab_jobs, tab_edit = st.tabs(
        ["📋 نظرة عامة", "💼 الخبرات", "🎓 التفاصيل", "🎯 الوظائف المناسبة", "✏️ تعديل"]
    )
    with tab_overview:
        _render_overview(candidate, lang)
    with tab_exp:
        _render_experience(candidate, lang, collapsible=not embedded)
    with tab_details:
        _render_details(candidate, lang)
    with tab_jobs:
        _render_suitable_jobs(candidate_id)
    with tab_edit:
        _render_edit_form(candidate, photo_path)


def render_profile(candidate_id: int) -> None:
    """واجهة قديمة تستخدمها صفحتا رفع السير والمقابلات (داخل expander)."""
    render_drawer(candidate_id, embedded=True)
