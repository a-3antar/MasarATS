"""صفحة إدارة المقابلات: اختيار وظيفة ثم تقديم (مرشح) ثم جدولة/تعديل/حذف مقابلاته، مع توليد أسئلة بالذكاء الاصطناعي."""

from datetime import datetime, timezone

import streamlit as st

from core.constants import INTERVIEW_STATUSES, INTERVIEW_TYPES
from core.exceptions import SmartATSError
from database.database import get_db_session
from repositories.application_repository import ApplicationRepository
from services.candidate_service import CandidateService
from services.interview_service import InterviewService
from services.job_service import JobService


def _interview_form_fields(key: str, interview=None, default_questions: str | None = None) -> dict:
    col1, col2 = st.columns(2)
    with col1:
        itype = st.selectbox(
            "نوع المقابلة", INTERVIEW_TYPES,
            index=INTERVIEW_TYPES.index(interview.interview_type)
            if interview and interview.interview_type in INTERVIEW_TYPES else 0,
            key=f"{key}_type",
        )
        date_default = interview.scheduled_at.date() if interview and interview.scheduled_at else datetime.now().date()
        time_default = (
            interview.scheduled_at.time() if interview and interview.scheduled_at
            else datetime.now().time().replace(second=0, microsecond=0)
        )
        date_input = st.date_input("التاريخ", value=date_default, key=f"{key}_date")
        time_input = st.time_input("الوقت", value=time_default, key=f"{key}_time")
    with col2:
        status = st.selectbox(
            "الحالة", INTERVIEW_STATUSES,
            index=INTERVIEW_STATUSES.index(interview.status) if interview and interview.status in INTERVIEW_STATUSES else 0,
            key=f"{key}_status",
        )
        interviewer = st.text_input(
            "المحاور", value=(interview.interviewer or "") if interview else "", key=f"{key}_interviewer"
        )
        location = st.text_input(
            "المكان / رابط الاجتماع", value=(interview.location or "") if interview else "", key=f"{key}_location"
        )

    questions_value = default_questions if default_questions is not None else ((interview.questions or "") if interview else "")
    questions = st.text_area("الأسئلة", value=questions_value, key=f"{key}_questions", height=150)
    notes = st.text_area("ملاحظات", value=(interview.notes or "") if interview else "", key=f"{key}_notes")
    feedback = st.text_area(
        "التقييم النصي (Feedback)", value=(interview.feedback or "") if interview else "", key=f"{key}_feedback"
    )
    evaluation = st.number_input(
        "التقييم الرقمي (1 إلى 5، صفر = بدون)", min_value=0, max_value=5, step=1,
        value=int(interview.evaluation or 0) if interview else 0, key=f"{key}_evaluation",
    )
    next_action = st.text_input(
        "الإجراء التالي", value=(interview.next_action or "") if interview else "", key=f"{key}_next_action"
    )

    scheduled_at = datetime.combine(date_input, time_input).replace(tzinfo=timezone.utc)

    return {
        "interview_type": itype,
        "status": status,
        "scheduled_at": scheduled_at,
        "interviewer": interviewer.strip() or None,
        "location": location.strip() or None,
        "questions": questions.strip() or None,
        "notes": notes.strip() or None,
        "feedback": feedback.strip() or None,
        "evaluation": evaluation or None,
        "next_action": next_action.strip() or None,
    }


def _render_ai_questions_summary(result) -> str:
    """يحوّل نتيجة الذكاء الاصطناعي إلى نص واحد جاهز لحقل الأسئلة."""
    lines: list[str] = []
    sections = [
        ("أسئلة خاصة بالسيرة الذاتية", result.cv_specific),
        ("أسئلة تقنية", result.technical),
        ("أسئلة سلوكية", result.behavioral),
        ("أسئلة قيادية", result.leadership),
    ]
    for title, items in sections:
        if items:
            lines.append(f"{title}:")
            lines.extend(f"- {q.question}" for q in items)
            lines.append("")
    if result.risk_areas:
        lines.append("نقاط يجب التحقق منها:")
        lines.extend(f"- {r}" for r in result.risk_areas)
    return "\n".join(lines).strip()


def _render_interview_card(interview) -> None:
    label = f"{interview.interview_type} · {interview.status}"
    if interview.scheduled_at:
        label += f" · {interview.scheduled_at.strftime('%Y-%m-%d %H:%M')}"

    with st.expander(label):
        with st.form(f"edit_interview_{interview.id}"):
            values = _interview_form_fields(f"edit_{interview.id}", interview)
            saved = st.form_submit_button("💾 حفظ", type="primary")
        if saved:
            try:
                with get_db_session() as session:
                    InterviewService(session).update(interview.id, **values)
                st.toast("تم حفظ التعديلات ✅")
                st.rerun()
            except SmartATSError as exc:
                st.error(str(exc))

        st.divider()
        confirm = st.checkbox("تأكيد حذف هذه المقابلة", key=f"confirm_del_{interview.id}")
        if st.button("🗑️ حذف المقابلة", disabled=not confirm, key=f"del_{interview.id}"):
            try:
                with get_db_session() as session:
                    InterviewService(session).delete(interview.id)
                st.toast("تم حذف المقابلة 🗑️")
                st.rerun()
            except SmartATSError as exc:
                st.error(str(exc))


def _render_add_interview(application_id: int, candidate, job) -> None:
    ai_key = f"ai_questions_{application_id}"

    with st.expander("➕ جدولة مقابلة جديدة"):
        if st.button("🤖 توليد أسئلة مقابلة بالذكاء الاصطناعي", key=f"gen_ai_{application_id}"):
            try:
                from ai.interview_generator import generate_interview_questions

                with st.spinner("جاري توليد الأسئلة..."):
                    result = generate_interview_questions(candidate, job)
                st.session_state[ai_key] = _render_ai_questions_summary(result)
                st.rerun()
            except SmartATSError as exc:
                st.error(str(exc))

        with st.form(f"new_interview_{application_id}", clear_on_submit=True):
            values = _interview_form_fields(
                f"new_{application_id}", default_questions=st.session_state.get(ai_key)
            )
            submitted = st.form_submit_button("حفظ المقابلة", type="primary")
        if submitted:
            try:
                with get_db_session() as session:
                    InterviewService(session).schedule(application_id, **values)
                st.session_state.pop(ai_key, None)
                st.toast("تمت جدولة المقابلة ✅")
                st.rerun()
            except SmartATSError as exc:
                st.error(str(exc))


def render() -> None:
    st.header("🗓️ المقابلات")

    with get_db_session() as session:
        jobs = JobService(session).list_all()

    if not jobs:
        st.info("أضف وظيفة أولاً من صفحة «الوظائف».")
        return

    job_labels = {f"{j.title} (#{j.id})": j.id for j in jobs}
    selected_job_label = st.selectbox("اختر الوظيفة", list(job_labels.keys()), key="iv_job_select")
    job_id = job_labels[selected_job_label]

    with get_db_session() as session:
        job = JobService(session).get_by_id(job_id)
        applications = ApplicationRepository(session).get_for_job(job_id)
        candidate_service = CandidateService(session)
        app_rows = [
            (app.id, candidate, app.status, app.match_score)
            for app in applications
            if (candidate := candidate_service.get_by_id(app.candidate_id)) is not None
        ]

    if not app_rows:
        st.info("لا يوجد مرشحون مطابَقون لهذه الوظيفة بعد. شغّل المطابقة من صفحة «المطابقة» أولاً.")
        return

    app_labels = {
        (f"{c.full_name} · {status} · {score}%" if score is not None else f"{c.full_name} · {status}"): (app_id, c)
        for app_id, c, status, score in app_rows
    }
    selected_app_label = st.selectbox("اختر المرشح (التقديم)", list(app_labels.keys()), key="iv_app_select")
    application_id, candidate = app_labels[selected_app_label]

    with get_db_session() as session:
        interviews = InterviewService(session).list_for_application(application_id)

    st.divider()
    _render_add_interview(application_id, candidate, job)

    if interviews:
        st.subheader(f"المقابلات المجدولة ({len(interviews)})")
        for interview in interviews:
            _render_interview_card(interview)
    else:
        st.caption("لا توجد مقابلات مجدولة لهذا التقديم بعد.")