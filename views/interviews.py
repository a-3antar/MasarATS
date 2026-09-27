"""صفحة إدارة المقابلات — مقسّمة إلى تبويبين:

📅 التقويم        : كل المقابلات (كل الوظائف والمرشحين) مُجمّعة حسب التاريخ، وكل مقابلة
                     تُفتح كبطاقة قابلة للتوسيع لتعديل بياناتها وتسجيل/تقييم إجابات المرشح.
➕ مقابلة جديدة   : اختيار الوظيفة ثم المرشح (التقديم)، ثم معالج بخطوتين:
                     (1) تفاصيل المقابلة  →  (2) إعداد أسئلة بنك الوظيفة.

الأسئلة مخزّنة في بنك مرتبط بالوظيفة (job_questions) وقابل لإعادة الاستخدام مع أي مرشح آخر
متقدم لنفس الوظيفة. إجابات كل مرشح على هذه الأسئلة مخزّنة بشكل مستقل لكل مقابلة
(interview_answers) مع تقييم بالذكاء الاصطناعي أو يدوي لكل إجابة."""

from collections import defaultdict
from datetime import datetime, timezone

import streamlit as st

from core.constants import INTERVIEW_STATUSES, INTERVIEW_TYPES
from core.exceptions import SmartATSError
from database.database import get_db_session
from repositories.application_repository import ApplicationRepository
from services.candidate_service import CandidateService
from services.interview_service import InterviewService
from services.job_service import JobService
from services.question_bank_service import QuestionBankService

_LIST_CACHE_TTL = 30  # ثوانٍ - قوائم الوظائف لا تتغيّر كل ثانية
_MANUAL_OPTIONS = [0, 1, 2, 3, 4, 5]

_STATUS_BADGES = {"Scheduled": "🟦 مجدولة", "Completed": "✅ مكتملة", "Cancelled": "❌ ملغاة"}
_WEEKDAYS_AR = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]


@st.cache_data(ttl=_LIST_CACHE_TTL, show_spinner=False)
def _cached_jobs() -> list:
    with get_db_session() as session:
        return JobService(session).list_all()


def _wizard_key(application_id: int) -> str:
    return f"iv_wizard_{application_id}"


# ============================================================== حقول نموذج المقابلة

def _interview_form_fields(key: str, interview=None) -> dict:
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

    questions = st.text_area(
        "ملاحظات عامة (اختياري)", value=(interview.questions or "") if interview else "",
        key=f"{key}_questions", height=70,
    )
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


# ============================================================== بنك أسئلة الوظيفة

def _render_question_bank_manager(job_id: int, key_prefix: str) -> None:
    """textarea واحدة تعرض/تحرر كل أسئلة الوظيفة دفعة واحدة (سؤال لكل سطر)، مع حفظ يحافظ
    على إجابات الأسئلة غير المتغيّرة، بالإضافة إلى حذف دقيق لأي سؤال محدد."""
    with get_db_session() as session:
        service = QuestionBankService(session)
        questions = service.list_for_job(job_id)
        bulk_text = service.questions_as_text(job_id)

    st.caption(
        "كل سؤال في سطر مستقل (أو افصل بينها بعلامة استفهام). تعديل نص سطر موجود يحافظ على "
        "إجاباته المسجّلة سابقاً، وإضافة سطر جديد في النهاية يضيف سؤالاً جديداً."
    )
    edited_text = st.text_area(
        "أسئلة الوظيفة", value=bulk_text, key=f"{key_prefix}_bulk_{job_id}", height=180,
        placeholder="اكتب سؤالاً في كل سطر...",
    )
    if st.button("💾 حفظ التعديلات", key=f"{key_prefix}_bulk_save_{job_id}", type="primary"):
        try:
            with get_db_session() as session:
                summary = QuestionBankService(session).sync_bulk_text(job_id, edited_text)
            parts = []
            if summary["updated"]:
                parts.append(f"تعديل {summary['updated']}")
            if summary["added"]:
                parts.append(f"إضافة {summary['added']}")
            if summary["removed"]:
                parts.append(f"حذف {summary['removed']}")
            st.toast("تم الحفظ ✅ " + (" · ".join(parts) if parts else ""))
            st.rerun()
        except SmartATSError as exc:
            st.error(str(exc))

    if questions:
        with st.expander(f"🗑️ حذف سؤال محدد ({len(questions)})"):
            for q in questions:
                col_text, col_del = st.columns([5, 1])
                with col_text:
                    label = QuestionBankService.category_label(q.category)
                    st.write(f"**#{q.id}** · {label} — {q.question}")
                with col_del:
                    if st.button("🗑️", key=f"{key_prefix}_del_{q.id}", width="stretch"):
                        try:
                            with get_db_session() as session:
                                QuestionBankService(session).delete_question(q.id)
                            st.toast("تم حذف السؤال 🗑️")
                            st.rerun()
                        except SmartATSError as exc:
                            st.error(str(exc))


def _render_question_bank(job_id: int) -> None:
    with st.expander("🗂️ بنك أسئلة الوظيفة (مشترك لكل المرشحين المتقدمين لهذه الوظيفة)"):
        _render_question_bank_manager(job_id, key_prefix="bank")


# ============================================================== معالج مقابلة جديدة (خطوتان)

def _render_new_interview_wizard(application_id: int, candidate, job) -> None:
    key = _wizard_key(application_id)
    wizard = st.session_state.get(key)

    if wizard is None:
        if st.button("➕ بدء جدولة المقابلة", key=f"new_iv_btn_{application_id}", type="primary"):
            st.session_state[key] = {"step": "details"}
            st.rerun()
        return

    if wizard["step"] == "details":
        _render_wizard_details_step(application_id, key)
        return

    if wizard["step"] == "questions":
        _render_wizard_questions_step(application_id, candidate, job, key, wizard["interview_id"])
        return


def _render_wizard_details_step(application_id: int, key: str) -> None:
    st.markdown("##### 1️⃣ تفاصيل المقابلة")
    with st.form(f"new_interview_{application_id}"):
        values = _interview_form_fields(f"new_{application_id}")
        col_next, col_cancel = st.columns(2)
        with col_next:
            submitted = st.form_submit_button("التالي: إعداد الأسئلة ▶", type="primary", width="stretch")
        with col_cancel:
            cancelled = st.form_submit_button("إلغاء", width="stretch")

    if cancelled:
        st.session_state.pop(key, None)
        st.rerun()

    if submitted:
        try:
            with get_db_session() as session:
                interview = InterviewService(session).schedule(application_id, **values)
            st.session_state[key] = {"step": "questions", "interview_id": interview.id}
            st.toast("تم حفظ تفاصيل المقابلة ✅")
            st.rerun()
        except SmartATSError as exc:
            st.error(str(exc))


def _render_wizard_questions_step(application_id: int, candidate, job, key: str, interview_id: int) -> None:
    st.markdown("##### 2️⃣ إعداد أسئلة المقابلة")
    st.caption(
        "هذه الأسئلة تُحفظ في بنك أسئلة الوظيفة ويمكن إعادة استخدامها مع أي مرشح آخر متقدم لنفس الوظيفة."
    )

    if st.button(
        "🤖 توليد أسئلة بالذكاء الاصطناعي (بناءً على سيرة هذا المرشح)",
        key=f"wiz_gen_ai_{application_id}",
    ):
        try:
            from ai.interview_generator import generate_interview_questions

            with st.spinner("جاري توليد الأسئلة..."):
                result = generate_interview_questions(candidate, job)
            with get_db_session() as session:
                added = QuestionBankService(session).add_ai_questions(job.id, result)
            st.toast(f"تمت إضافة {len(added)} سؤال ✅")
            st.rerun()
        except SmartATSError as exc:
            st.error(str(exc))

    _render_question_bank_manager(job.id, key_prefix=f"wiz_{interview_id}")

    st.divider()
    col_done, col_back = st.columns(2)
    with col_done:
        if st.button("✅ إنهاء وحفظ المقابلة", type="primary", key=f"wiz_done_{application_id}", width="stretch"):
            st.session_state.pop(key, None)
            st.toast("تمت جدولة المقابلة ✅")
            st.rerun()
    with col_back:
        if st.button("◀ رجوع لتفاصيل المقابلة", key=f"wiz_back_{application_id}", width="stretch"):
            st.session_state[key] = {"step": "details"}
            st.rerun()


# ============================================================== إجابات المرشح وتقييمها

def _render_answer_row(interview_id: int, question, answer, job, idx: int) -> None:
    qid = question.id
    with st.container(border=True):
        label = QuestionBankService.category_label(question.category)
        st.caption(f"{idx}. {label}" if label else f"سؤال {idx}")
        st.write(f"**{question.question}**")
        if question.rationale:
            st.caption(f"💡 {question.rationale}")

        answer_text = st.text_area(
            "إجابة المرشح", value=(answer.answer if answer else "") or "",
            key=f"ans_{interview_id}_{qid}", height=90, placeholder="اكتب إجابة المرشح هنا...",
        )

        col_save, col_ai, col_manual = st.columns([1, 1, 1])
        with col_save:
            if st.button("💾 حفظ الإجابة", key=f"ans_save_{interview_id}_{qid}", width="stretch"):
                try:
                    with get_db_session() as session:
                        InterviewService(session).save_answer(interview_id, qid, answer_text)
                    st.toast("تم الحفظ ✅")
                    st.rerun()
                except SmartATSError as exc:
                    st.error(str(exc))
        with col_ai:
            if st.button("🤖 تقييم بالذكاء الاصطناعي", key=f"ans_ai_{interview_id}_{qid}", width="stretch"):
                try:
                    with get_db_session() as session:
                        svc = InterviewService(session)
                        svc.save_answer(interview_id, qid, answer_text)
                        svc.evaluate_answer(interview_id, qid, job)
                    st.toast("تم التقييم بالذكاء الاصطناعي ✅")
                    st.rerun()
                except SmartATSError as exc:
                    st.error(str(exc))
        with col_manual:
            current_manual = answer.eval_score if answer and answer.eval_method == "manual" else 0
            manual_score = st.selectbox(
                "تقييم يدوي", _MANUAL_OPTIONS, index=_MANUAL_OPTIONS.index(current_manual),
                key=f"ans_manual_{interview_id}_{qid}",
                format_func=lambda v: "بدون تقييم يدوي" if v == 0 else f"{v}/5",
            )
            if manual_score != current_manual:
                try:
                    with get_db_session() as session:
                        InterviewService(session).set_manual_score(interview_id, qid, manual_score or None)
                    st.rerun()
                except SmartATSError as exc:
                    st.error(str(exc))

        if answer and answer.eval_score is not None:
            method_label = "🤖 تقييم الذكاء الاصطناعي" if answer.eval_method == "ai" else "🧑 تقييم يدوي"
            st.write(f"**{method_label}: {answer.eval_score}/5**")
            if answer.eval_feedback:
                st.caption(answer.eval_feedback)
            for s in answer.eval_strengths or []:
                st.write(f"✔️ {s}")
            for c in answer.eval_concerns or []:
                st.write(f"⚠️ {c}")


def _render_interview_answers(interview_id: int, job) -> None:
    st.markdown("**📋 أسئلة هذه المقابلة وإجابات المرشح**")
    with get_db_session() as session:
        bank_questions = QuestionBankService(session).list_for_job(job.id)
        answers_map = InterviewService(session).answers_map(interview_id)

    if not bank_questions:
        st.caption("لا توجد أسئلة في بنك هذه الوظيفة بعد. أضفها من قسم «بنك أسئلة الوظيفة».")
        return

    for idx, q in enumerate(bank_questions, start=1):
        _render_answer_row(interview_id, q, answers_map.get(q.id), job, idx)


# ============================================================== بطاقة مقابلة واحدة

def _interview_summary_line(interview, candidate, job) -> str:
    time_part = interview.scheduled_at.strftime("%H:%M") if interview.scheduled_at else "--:--"
    status_badge = _STATUS_BADGES.get(interview.status, interview.status)
    return f"🕐 {time_part}  ·  👤 {candidate.full_name}  ·  💼 {job.title}  ·  {interview.interview_type}  ·  {status_badge}"


def _render_interview_card(interview, candidate, job, *, show_summary: bool = False) -> None:
    label = _interview_summary_line(interview, candidate, job) if show_summary else (
        f"{interview.interview_type} · {_STATUS_BADGES.get(interview.status, interview.status)}"
        + (f" · {interview.scheduled_at.strftime('%Y-%m-%d %H:%M')}" if interview.scheduled_at else "")
    )

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
        _render_interview_answers(interview.id, job)

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


# ============================================================== تبويب 1: التقويم

def _render_calendar_tab() -> None:
    with get_db_session() as session:
        rows = InterviewService(session).list_all_with_context()

    if not rows:
        st.info("لا توجد مقابلات مجدولة بعد. استخدم تبويب «➕ مقابلة جديدة» لإضافة أول مقابلة.")
        return

    total = len(rows)
    now = datetime.now(timezone.utc)
    upcoming = sum(
        1 for iv, _, _ in rows
        if iv.status == "Scheduled" and iv.scheduled_at and iv.scheduled_at.replace(tzinfo=timezone.utc) >= now
    )
    completed = sum(1 for iv, _, _ in rows if iv.status == "Completed")
    cancelled = sum(1 for iv, _, _ in rows if iv.status == "Cancelled")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📋 الإجمالي", total)
    col2.metric("🟦 قادمة", upcoming)
    col3.metric("✅ مكتملة", completed)
    col4.metric("❌ ملغاة", cancelled)
    st.divider()

    status_filter = st.multiselect(
        "تصفية حسب الحالة", INTERVIEW_STATUSES, default=INTERVIEW_STATUSES, key="cal_status_filter",
    )
    filtered = [r for r in rows if r[0].status in status_filter]
    if not filtered:
        st.warning("لا توجد مقابلات مطابقة لهذا الفلتر.")
        return

    grouped: dict = defaultdict(list)
    for interview, candidate, job in filtered:
        day = interview.scheduled_at.date() if interview.scheduled_at else None
        grouped[day].append((interview, candidate, job))

    for day in sorted(grouped.keys(), key=lambda d: (d is None, d)):
        items = grouped[day]
        if day is None:
            st.markdown("##### 📌 بدون تاريخ محدد")
        else:
            weekday = _WEEKDAYS_AR[day.weekday()]
            st.markdown(f"##### 📅 {day.strftime('%Y-%m-%d')} — {weekday}  ·  {len(items)} مقابلة")
        for interview, candidate, job in sorted(items, key=lambda r: r[0].scheduled_at or datetime.min.replace(tzinfo=timezone.utc)):
            _render_interview_card(interview, candidate, job, show_summary=True)
        st.write("")


# ============================================================== تبويب 2: مقابلة جديدة

def _render_new_interview_tab() -> None:
    jobs = _cached_jobs()
    if not jobs:
        st.info("أضف وظيفة أولاً من صفحة «الوظائف».")
        return

    job_labels = {f"{j.title} (#{j.id})": j.id for j in jobs}
    selected_job_label = st.selectbox("1. اختر الوظيفة", list(job_labels.keys()), key="iv_job_select")
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

    st.divider()
    _render_question_bank(job_id)
    st.divider()

    if not app_rows:
        st.info("لا يوجد مرشحون مطابَقون لهذه الوظيفة بعد. شغّل المطابقة من صفحة «المطابقة» أولاً.")
        return

    app_labels = {
        (f"{c.full_name} · {status} · {score}%" if score is not None else f"{c.full_name} · {status}"): (app_id, c)
        for app_id, c, status, score in app_rows
    }
    selected_app_label = st.selectbox("2. اختر المرشح (التقديم)", list(app_labels.keys()), key="iv_app_select")
    application_id, candidate = app_labels[selected_app_label]

    st.divider()
    _render_new_interview_wizard(application_id, candidate, job)

    with get_db_session() as session:
        existing = InterviewService(session).list_for_application(application_id)
    if existing:
        st.divider()
        st.caption(f"لهذا المرشح {len(existing)} مقابلة مجدولة مسبقاً على هذه الوظيفة (تظهر في تبويب «📅 التقويم»).")


def render() -> None:
    st.header("🗓️ المقابلات")

    tab_calendar, tab_new = st.tabs(["📅 التقويم", "➕ مقابلة جديدة"])
    with tab_calendar:
        _render_calendar_tab()
    with tab_new:
        _render_new_interview_tab()
