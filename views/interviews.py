"""صفحة إدارة المقابلات: اختيار وظيفة ثم تقديم (مرشح) ثم جدولة/تعديل/حذف مقابلاته.
الأسئلة مخزّنة في بنك أسئلة مرتبط بالوظيفة (job_questions) وقابل لإعادة الاستخدام مع أي مرشح
متقدم لنفس الوظيفة. إجابات كل مرشح على هذه الأسئلة مخزّنة بشكل مستقل لكل مقابلة (interview_answers)
مع تقييم بالذكاء الاصطناعي أو يدوي لكل إجابة، ودرجة نهائية للمقابلة.
يمكن تصدير الأسئلة إلى Word لتعبئة الإجابات خارج البرنامج، ثم رفع الملف لتقييمها دفعة واحدة."""

from datetime import datetime, timezone

import streamlit as st

from core.constants import INTERVIEW_STATUSES, INTERVIEW_TYPES
from core.exceptions import SmartATSError
from database.database import get_db_session
from repositories.application_repository import ApplicationRepository
from services.candidate_service import CandidateService
from services.interview_export_service import export_questions_docx, parse_answers_docx
from services.interview_service import InterviewService
from services.job_service import JobService
from services.question_bank_service import QuestionBankService

# قائمة الوظائف لا تتغيّر كل ثانية - كاش بسيط يقلّل استعلامات القاعدة عند التنقل بين التبويبات
_LIST_CACHE_TTL = 30

_MANUAL_OPTIONS = [0, 1, 2, 3, 4, 5]
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# رسالة تُعرض بعد st.rerun() (مثل نتيجة الاستيراد) لأن أي رسالة تُكتب قبل rerun تختفي
_FLASH_KEY = "interviews_flash"


@st.cache_data(ttl=_LIST_CACHE_TTL, show_spinner=False)
def _cached_jobs() -> list:
    with get_db_session() as session:
        return JobService(session).list_all()


def _flash(level: str, message: str) -> None:
    st.session_state[_FLASH_KEY] = (level, message)


def _show_flash() -> None:
    flash = st.session_state.pop(_FLASH_KEY, None)
    if flash:
        level, message = flash
        getattr(st, level)(message)


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
        key=f"{key}_questions", height=80,
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


# ------------------------------------------------------------ بنك أسئلة الوظيفة

def _render_bank_question_row(q) -> None:
    with st.container(border=True):
        st.caption(f"{QuestionBankService.category_label(q.category)} · #{q.id}")
        new_text = st.text_area("السؤال", value=q.question, key=f"bank_q_{q.id}", height=60)
        col_save, col_del = st.columns(2)
        with col_save:
            if st.button("💾 حفظ", key=f"bank_save_{q.id}", width="stretch"):
                try:
                    with get_db_session() as session:
                        QuestionBankService(session).update_question(q.id, new_text)
                    st.toast("تم الحفظ ✅")
                    st.rerun()
                except SmartATSError as exc:
                    st.error(str(exc))
        with col_del:
            if st.button("🗑️ حذف", key=f"bank_del_{q.id}", width="stretch"):
                try:
                    with get_db_session() as session:
                        QuestionBankService(session).delete_question(q.id)
                    st.toast("تم الحذف 🗑️")
                    st.rerun()
                except SmartATSError as exc:
                    st.error(str(exc))


def _render_export_questions(job, questions: list) -> None:
    """زر تنزيل ملف Word فيه كل أسئلة الوظيفة وتحت كل سؤال مساحة لكتابة الإجابة."""
    st.markdown("**📄 تصدير الأسئلة إلى Word**")
    if not questions:
        st.caption("لا توجد أسئلة لتصديرها بعد.")
        return
    try:
        file_bytes = export_questions_docx(job, questions)
    except SmartATSError as exc:
        st.error(str(exc))
        return
    st.download_button(
        "⬇️ تنزيل ملف الأسئلة (Word)", file_bytes,
        file_name=f"interview_questions_job_{job.id}.docx", mime=_DOCX_MIME,
        key=f"export_docx_{job.id}",
    )
    st.caption(
        "اكتب الإجابات تحت كل سؤال ثم ارفع الملف من داخل بطاقة المقابلة "
        "(قسم «استيراد الإجابات من Word») ليتم تصحيحها."
    )


def _render_question_bank(job) -> None:
    job_id = job.id
    with st.expander("🗂️ بنك أسئلة الوظيفة (مشترك لكل المرشحين المتقدمين لهذه الوظيفة)"):
        with get_db_session() as session:
            questions = QuestionBankService(session).list_for_job(job_id)

        if questions:
            for q in questions:
                _render_bank_question_row(q)
        else:
            st.caption("لا توجد أسئلة بعد. أضفها يدوياً أدناه، أو ولّدها بالذكاء الاصطناعي من قسم جدولة مقابلة.")

        st.markdown("**➕ إضافة أسئلة جديدة**")
        raw = st.text_area(
            "اكتب سؤالاً أو أكثر — افصل بينها بسطر جديد أو علامة استفهام",
            key=f"bank_add_{job_id}", height=100,
        )
        if st.button("➕ إضافة", key=f"bank_add_btn_{job_id}"):
            try:
                with get_db_session() as session:
                    added = QuestionBankService(session).add_questions_from_text(job_id, raw)
                st.toast(f"تمت إضافة {len(added)} سؤال ✅")
                st.rerun()
            except SmartATSError as exc:
                st.error(str(exc))

        st.divider()
        _render_export_questions(job, questions)


# ------------------------------------------------------------ جدولة مقابلة جديدة

def _render_add_interview(application_id: int, candidate, job) -> None:
    with st.expander("➕ جدولة مقابلة جديدة"):
        if st.button(
            "🤖 توليد أسئلة إضافية بالذكاء الاصطناعي (بناءً على سيرة هذا المرشح)",
            key=f"gen_ai_{application_id}",
        ):
            try:
                from ai.interview_generator import generate_interview_questions

                with st.spinner("جاري توليد الأسئلة..."):
                    result = generate_interview_questions(candidate, job)
                with get_db_session() as session:
                    added = QuestionBankService(session).add_ai_questions(job.id, result)
                st.toast(f"تمت إضافة {len(added)} سؤال لبنك أسئلة الوظيفة ✅")
                st.rerun()
            except SmartATSError as exc:
                st.error(str(exc))

        with st.form(f"new_interview_{application_id}", clear_on_submit=True):
            values = _interview_form_fields(f"new_{application_id}")
            submitted = st.form_submit_button("حفظ المقابلة", type="primary")
        if submitted:
            try:
                with get_db_session() as session:
                    InterviewService(session).schedule(application_id, **values)
                st.toast("تمت جدولة المقابلة ✅")
                st.rerun()
            except SmartATSError as exc:
                st.error(str(exc))


# ------------------------------------------------------------ إجابات المرشح وتقييمها

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
                        session.flush()  # لتظهر الإجابة المحفوظة للتو ضمن السياق المرجعي
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
        st.caption("لا توجد أسئلة في بنك هذه الوظيفة بعد. أضفها من قسم «بنك أسئلة الوظيفة» أعلاه.")
        return

    for idx, q in enumerate(bank_questions, start=1):
        _render_answer_row(interview_id, q, answers_map.get(q.id), job, idx)


# ------------------------------------------------------------ استيراد الإجابات من Word

def _render_import_answers(interview, job) -> None:
    """يرفع ملف Word المعبّأ، يحفظ الإجابات، يقيّمها بالذكاء الاصطناعي، ثم يحسب الدرجة النهائية."""
    st.markdown("**📥 استيراد الإجابات من ملف Word**")
    st.caption(
        "ارفع نفس الملف الذي صدّرته من بنك الأسئلة بعد كتابة الإجابات. ستُحفظ الإجابات (وتستبدل "
        "إجابات نفس الأسئلة الموجودة) ثم تُقيَّم، وتُقارَن كل إجابة بباقي إجابات المقابلة كسياق. "
        "الأسئلة التي لم تُكتب لها إجابة في الملف لا تتأثر."
    )
    uploaded = st.file_uploader(
        "ملف الإجابات (.docx)", type=["docx"], key=f"import_file_{interview.id}"
    )
    if uploaded is None:
        return
    if not st.button(
        "🤖 استيراد الإجابات وتقييمها", key=f"import_btn_{interview.id}", type="primary"
    ):
        return

    try:
        answers = parse_answers_docx(uploaded.getvalue(), expected_job_id=job.id)
        if not answers:
            st.warning("لم يتم العثور على أي إجابة مكتوبة في الملف.")
            return

        progress = st.progress(0.0, text="جاري تقييم الإجابات...")

        def _on_progress(done: int, total: int) -> None:
            progress.progress(done / total, text=f"تم تقييم {done} / {total}")

        with get_db_session() as session:
            result = InterviewService(session).import_answers(interview.id, job, answers, _on_progress)
    except SmartATSError as exc:
        st.error(str(exc))
        return

    # أي widget له key محفوظ في session_state يتجاهل value= الجديد، فنحذف مفاتيح الأسئلة المستوردة
    # ليُعاد رسمها من القاعدة (وإلا ظهرت الإجابات القديمة، أو أُعيد تطبيق تقييم يدوي قديم)
    for question_id in answers:
        st.session_state.pop(f"ans_{interview.id}_{question_id}", None)
        st.session_state.pop(f"ans_manual_{interview.id}_{question_id}", None)

    message = f"تم استيراد {result['saved']} إجابة وتقييم {result['evaluated']} منها."
    if result["overall_score"] is not None:
        message += f" الدرجة النهائية: {result['overall_score']:g} / 100."
    if result["unknown"]:
        message += f" تم تجاهل {len(result['unknown'])} سؤال غير موجود في بنك الوظيفة الحالي."
    if result["failed"]:
        _flash("warning", message + f" تعذّر تقييم {len(result['failed'])} إجابة (حُفظت بدون درجة، "
                                    "يمكنك تقييمها من زر الذكاء الاصطناعي تحت كل سؤال).")
    else:
        _flash("success", message)
    st.rerun()


# ------------------------------------------------------------ التقييم النهائي

def _render_final_score(interview) -> None:
    st.markdown("**🏁 التقييم النهائي للمقابلة**")
    with get_db_session() as session:
        scored, written = InterviewService(session).answered_stats(interview.id)

    col_score, col_info = st.columns([1, 2])
    with col_score:
        if interview.overall_score is not None:
            st.metric("الدرجة النهائية", f"{interview.overall_score:g} / 100")
        else:
            st.caption("لم تُحسب الدرجة النهائية بعد.")
    with col_info:
        if interview.overall_score is not None:
            source = "معدَّلة يدوياً من المُقابِل" if interview.overall_method == "manual" else "محسوبة تلقائياً"
            st.caption(f"المصدر: {source}")
        st.caption(f"إجابات مقيَّمة: {scored} من {written} مكتوبة (الدرجة = متوسط التقييمات × 20).")

    if st.button("🧮 احسب التقييم النهائي", key=f"final_calc_{interview.id}"):
        try:
            with get_db_session() as session:
                score = InterviewService(session).finalize_score(interview.id)
            if score is None:
                st.warning("لا توجد إجابات مقيَّمة لحساب الدرجة. قيّم إجابة واحدة على الأقل.")
            else:
                st.toast(f"الدرجة النهائية: {score:g} / 100 ✅")
                st.rerun()
        except SmartATSError as exc:
            st.error(str(exc))

    with st.form(f"final_override_{interview.id}"):
        current = float(interview.overall_score or 0.0)
        new_score = st.number_input(
            "تعديل الدرجة النهائية يدوياً (0 إلى 100)", min_value=0.0, max_value=100.0, step=1.0,
            value=current, key=f"final_score_{interview.id}",
        )
        notes = st.text_area(
            "ملاحظات التقييم النهائي", value=interview.overall_notes or "", key=f"final_notes_{interview.id}"
        )
        saved = st.form_submit_button("💾 حفظ التقييم النهائي")
    if saved:
        try:
            with get_db_session() as session:
                # إن لم تتغير الدرجة نحدّث الملاحظات فقط فلا تُوسَم الدرجة المحسوبة بأنها يدوية
                InterviewService(session).set_overall(
                    interview.id, new_score if new_score != current else None, notes
                )
            st.toast("تم حفظ التقييم النهائي ✅")
            st.rerun()
        except SmartATSError as exc:
            st.error(str(exc))


# ------------------------------------------------------------ بطاقة المقابلة

def _render_interview_card(interview, candidate, job) -> None:
    label = f"{interview.interview_type} · {interview.status}"
    if interview.scheduled_at:
        label += f" · {interview.scheduled_at.strftime('%Y-%m-%d %H:%M')}"
    if interview.overall_score is not None:
        label += f" · 🏁 {interview.overall_score:g}/100"

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
        _render_import_answers(interview, job)

        st.divider()
        _render_interview_answers(interview.id, job)

        st.divider()
        _render_final_score(interview)

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


def render() -> None:
    st.header("🗓️ المقابلات")
    _show_flash()

    jobs = _cached_jobs()

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

    st.divider()
    _render_question_bank(job)

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
            _render_interview_card(interview, candidate, job)
    else:
        st.caption("لا توجد مقابلات مجدولة لهذا التقديم بعد.")
