"""بطاقة المرشح الموحّدة: شكل ثابت واحد لعرض كل السير الذاتية + تبويب تعديل."""

import re

import streamlit as st

from core.exceptions import SmartATSError
from database.database import get_db_session
from models.candidate import Candidate
from services.candidate_service import CandidateService

# ترتيب الأقسام ثابت لكل المرشحين - هذا ما يوحّد شكل السير الذاتية
_SKILL_SECTIONS: list[tuple[str, str]] = [
    ("🛠️ المهارات الفنية", "technical_skills"),
    ("💻 مهارات الكمبيوتر", "computer_skills"),
    ("📊 المهارات الإدارية", "managerial_skills"),
    ("🤝 المهارات الشخصية (Soft Skills)", "soft_skills"),
    ("➕ مهارات أخرى", "skills"),
]
_BACKGROUND_SECTIONS: list[tuple[str, str]] = [
    ("🏭 مجالات العمل السابقة", "industries"),
    ("🏢 الشركات السابقة", "previous_companies"),
]
_PHOTO_WIDTH_PX = 180
_MAX_RESPONSIBILITIES_SHOWN = 6


def _tags(items: list[str]) -> str:
    return "  ".join(f"`{item.replace('`', chr(39))}`" for item in items)


def _split_items(raw: str) -> list[str]:
    """تقسيم نص مفصول بفاصلة (إنجليزية أو عربية) أو أسطر إلى قائمة نظيفة."""
    return [part.strip() for part in re.split(r"[,،\n]", raw or "") if part.strip()]


def render_profile(candidate_id: int) -> None:
    with get_db_session() as session:
        service = CandidateService(session)
        candidate = service.get_by_id(candidate_id)
        if candidate is None:
            st.warning("المرشح غير موجود.")
            return
        photo_path = service.photo_absolute_path(candidate)

    tab_card, tab_edit = st.tabs(["📋 بطاقة المرشح", "✏️ تعديل"])
    with tab_card:
        _render_card(candidate, photo_path)
    with tab_edit:
        _render_edit_form(candidate, photo_path)


def _render_card(candidate: Candidate, photo_path) -> None:
    col_photo, col_info = st.columns([1, 3])
    with col_photo:
        if photo_path:
            st.image(str(photo_path), width=_PHOTO_WIDTH_PX)
        else:
            st.markdown("## 👤")
            st.caption("لا توجد صورة")
    with col_info:
        st.subheader(candidate.full_name)
        if candidate.current_position:
            st.markdown(f"**{candidate.current_position}**")
        st.write(
            f"📧 {candidate.email or '-'}  ·  📞 {candidate.phone or '-'}  ·  📍 {candidate.location or '-'}"
        )
        if candidate.total_experience_years is not None:
            st.write(f"⏳ الخبرة: {candidate.total_experience_years:g} سنة")

    st.markdown("**📝 نبذة**")
    st.write(candidate.summary or "غير مذكور")

    for title, attr in _SKILL_SECTIONS + _BACKGROUND_SECTIONS:
        st.markdown(f"**{title}**")
        items = getattr(candidate, attr) or []
        if items:
            st.markdown(_tags(items))
        else:
            st.caption("غير مذكور في السيرة الذاتية")

    st.markdown("**💼 الخبرات العملية**")
    for item in candidate.experience or []:
        heading = " — ".join(p for p in (item.get("position"), item.get("company")) if p) or "غير محدد"
        period = " → ".join(p for p in (item.get("start_date"), item.get("end_date")) if p)
        with st.container(border=True):
            st.markdown(f"**{heading}**")
            if period:
                st.caption(period)
            for line in (item.get("responsibilities") or [])[:_MAX_RESPONSIBILITIES_SHOWN]:
                st.write(f"• {line}")
    if not candidate.experience:
        st.caption("غير مذكور في السيرة الذاتية")

    st.markdown("**🎓 التعليم**")
    for item in candidate.education or []:
        line = " — ".join(p for p in (item.get("degree"), item.get("major"), item.get("institution")) if p)
        year = item.get("graduation_year")
        st.write(f"• {line or 'غير محدد'}" + (f" ({year})" if year else ""))
    if not candidate.education:
        st.caption("غير مذكور في السيرة الذاتية")

    st.caption(f"📎 المصدر: {candidate.source_filename or 'إدخال يدوي'}")


def _render_edit_form(candidate: Candidate, photo_path) -> None:
    cid = candidate.id
    with st.form(f"edit_candidate_form_{cid}"):
        full_name = st.text_input("الاسم الكامل *", value=candidate.full_name, key=f"name_{cid}")
        email = st.text_input("البريد الإلكتروني", value=candidate.email or "", key=f"email_{cid}")
        phone = st.text_input("الهاتف", value=candidate.phone or "", key=f"phone_{cid}")
        location = st.text_input("الموقع", value=candidate.location or "", key=f"loc_{cid}")
        position = st.text_input("المسمى الوظيفي الحالي", value=candidate.current_position or "", key=f"pos_{cid}")
        experience = st.number_input(
            "سنوات الخبرة", min_value=0.0, step=0.5,
            value=float(candidate.total_experience_years or 0.0), key=f"exp_{cid}",
        )
        summary = st.text_area("النبذة", value=candidate.summary or "", key=f"sum_{cid}")

        raw_lists: dict[str, str] = {}
        for label, attr in _SKILL_SECTIONS + _BACKGROUND_SECTIONS:
            raw_lists[attr] = st.text_area(
                f"{label} (مفصولة بفاصلة)",
                value=", ".join(getattr(candidate, attr) or []),
                key=f"{attr}_{cid}",
                height=80,
            )

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
                location=location.strip() or None,
                current_position=position.strip() or None,
                total_experience_years=experience or None,
                summary=summary.strip() or None,
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