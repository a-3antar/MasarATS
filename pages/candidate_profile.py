"""بطاقة المرشح الموحّدة: شكل ثابت واحد لعرض كل السير الذاتية + تبويب تعديل + اختيار لغة العرض."""

import re

import streamlit as st

from core.constants import CANDIDATE_STATUSES
from core.exceptions import SmartATSError
from database.database import get_db_session
from models.candidate import Candidate
from services.candidate_service import CandidateService
from services.job_service import JobService
from services.matching_service import MatchingService

# ترتيب الأقسام ثابت لكل المرشحين - هذا ما يوحّد شكل السير الذاتية
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
_PHOTO_WIDTH_PX = 180
_MAX_RESPONSIBILITIES_SHOWN = 6
_LANG_OPTIONS = {"English": "en", "العربية": "ar"}
_NOT_MENTIONED = "غير مذكور في السيرة الذاتية"

_TOP_JOBS_COUNT = 5


def _tags(items: list[str]) -> str:
    return "  ".join(f"`{item.replace('`', chr(39))}`" for item in items)


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

def render_profile(candidate_id: int) -> None:
    with get_db_session() as session:
        service = CandidateService(session)
        candidate = service.get_by_id(candidate_id)
        if candidate is None:
            st.warning("المرشح غير موجود.")
            return
        photo_path = service.photo_absolute_path(candidate)

    lang_label = st.radio(
        "🌐 لغة عرض البيانات", list(_LANG_OPTIONS.keys()), horizontal=True, key=f"lang_{candidate_id}"
    )
    lang = _LANG_OPTIONS[lang_label]

    if lang == "ar" and not (candidate.translations or {}).get("ar"):
        st.info("لا توجد ترجمة عربية لهذا المرشح بعد (يتم عرض النسخة الإنجليزية مؤقتاً).")
        if st.button("🌐 ترجمة البيانات إلى العربية", key=f"translate_{candidate_id}"):
            try:
                with st.spinner("جاري الترجمة..."):
                    with get_db_session() as session:
                        CandidateService(session).translate_candidate(candidate_id, "ar")
                st.rerun()
            except SmartATSError as exc:
                st.error(str(exc))
        lang = "en"

    tab_card, tab_jobs, tab_edit = st.tabs(["📋 بطاقة المرشح", "🎯 أفضل الوظائف", "✏️ تعديل"])
    with tab_card:
        _render_card(candidate, photo_path, lang)
    with tab_jobs:
        _render_best_jobs(candidate_id)
    with tab_edit:
        _render_edit_form(candidate, photo_path)

def _render_best_jobs(candidate_id: int) -> None:
    """أفضل الوظائف المفتوحة لهذا المرشح مع تفسير الدرجة (للعرض فقط)."""
    with get_db_session() as session:
        candidate = CandidateService(session).get_by_id(candidate_id)
        jobs = JobService(session).list_open()
        results = (
            MatchingService(session).top_jobs_for_candidate(candidate, jobs, _TOP_JOBS_COUNT)
            if candidate is not None and jobs
            else []
        )

    if not jobs:
        st.info("لا توجد وظائف مفتوحة حالياً. أضف وظيفة من صفحة «الوظائف».")
        return

    st.caption(f"أفضل {len(results)} وظيفة مفتوحة مطابقة لهذا المرشح (حسب القواعد الحالية، وللمراجعة البشرية فقط).")
    for r in results:
        job = r["job"]
        with st.container(border=True):
            col_info, col_score = st.columns([3, 1])
            with col_info:
                st.markdown(f"**{job.title}**")
                st.caption(f"{job.department or 'بدون قسم'} · {job.location or 'بدون موقع'}")
            with col_score:
                st.metric("المطابقة", f"{r['score']}%")
            with st.expander("تفاصيل الدرجة"):
                b = r["breakdown"]
                st.write(
                    f"المهارات: {b['skills']}% · الخبرة: {b['experience']}% · "
                    f"الموقع: {b['location']}% · التعليم: {b['education']}%"
                )
                for line in r["strengths"] + r["gaps"]:
                    st.write(line)

def _render_card(candidate: Candidate, photo_path, lang: str) -> None:
    col_photo, col_info = st.columns([1, 3])
    with col_photo:
        if photo_path:
            st.image(str(photo_path), width=_PHOTO_WIDTH_PX)
        else:
            st.markdown("## 👤")
            st.caption("لا توجد صورة")
    with col_info:
        st.subheader(candidate.full_name)
        st.caption(f"🆔 {candidate.candidate_code or '-'}  ·  📌 الحالة: {candidate.status or 'New'}")
        position = _value(candidate, "current_position", lang)
        if position:
            st.markdown(f"**{position}**")
        st.write(
            f"📧 {candidate.email or '-'}  ·  📞 {candidate.phone or '-'}  ·  "
            f"📍 {_value(candidate, 'location', lang) or '-'}"
        )
        if candidate.linkedin_url:
            st.write(f"🔗 {candidate.linkedin_url}")
        if candidate.total_experience_years is not None:
            st.write(f"⏳ الخبرة: {candidate.total_experience_years:g} سنة")
        if candidate.age is not None:
            st.write(f"🎂 العمر: {candidate.age} سنة")

    st.markdown("**🎯 بيانات التوظيف**")
    salary = f"{candidate.expected_salary:,.0f}" if candidate.expected_salary else "-"
    rating = f"{candidate.rating}/5" if candidate.rating else "-"
    notice = f"{candidate.notice_period_days} يوم" if candidate.notice_period_days else "-"
    st.write(
        f"الوظيفة المستهدفة: {candidate.applied_job or '-'}  ·  التقييم: {rating}  ·  "
        f"الراتب المتوقع: {salary}  ·  فترة الإشعار: {notice}"
    )
    if candidate.recruiter_notes:
        st.caption(f"📝 ملاحظات: {candidate.recruiter_notes}")

    st.markdown("**🧍 الحالة الشخصية**")
    marital = _value(candidate, "marital_status", lang)
    military = _value(candidate, "military_status", lang)
    st.write(f"الحالة الاجتماعية: {marital or 'غير مذكور'}  ·  موقف التجنيد: {military or 'غير مذكور'}")
    languages = _value(candidate, _LANGUAGES_SECTION[1], lang) or []
    st.markdown(f"**{_LANGUAGES_SECTION[0]}**")
    if languages:
        st.markdown(_tags(languages))
    else:
        st.caption(_NOT_MENTIONED)

    st.markdown("**📝 نبذة**")
    st.write(_value(candidate, "summary", lang) or "غير مذكور")

    for title, attr in _SKILL_SECTIONS + _BACKGROUND_SECTIONS:
        st.markdown(f"**{title}**")
        items = _value(candidate, attr, lang) or []
        if items:
            st.markdown(_tags(items))
        else:
            st.caption(_NOT_MENTIONED)

    st.markdown("**💼 الخبرات العملية**")
    experience = _value(candidate, "experience", lang) or []
    for item in experience:
        heading = " — ".join(p for p in (item.get("position"), item.get("company")) if p) or "غير محدد"
        period = " → ".join(p for p in (item.get("start_date"), item.get("end_date")) if p)
        with st.container(border=True):
            st.markdown(f"**{heading}**")
            if period:
                st.caption(period)
            for line in (item.get("responsibilities") or [])[:_MAX_RESPONSIBILITIES_SHOWN]:
                st.write(f"• {line}")
    if not experience:
        st.caption(_NOT_MENTIONED)

    st.markdown("**🎓 التعليم**")
    education = _value(candidate, "education", lang) or []
    for item in education:
        line = " — ".join(p for p in (item.get("degree"), item.get("major"), item.get("institution")) if p)
        year = item.get("graduation_year")
        st.write(f"• {line or 'غير محدد'}" + (f" ({year})" if year else ""))
    if not education:
        st.caption(_NOT_MENTIONED)

    st.caption(f"📎 المصدر: {candidate.source_filename or 'إدخال يدوي'}")


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
        st.toast("تم حفظ التعديلات ✅")
        st.rerun()
    except SmartATSError as exc:
        st.error(str(exc))