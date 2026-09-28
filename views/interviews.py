"""صفحة المقابلات كـ Interview Workspace: ترويسة المقابلة، بطاقة المرشح (رحلته + مقابلاته السابقة)،
متصفح أسئلة (سؤال واحد في كل مرة) مع الإجابة وتحليل الذكاء الاصطناعي وتقييم المُقابِل،
ثم الكفاءات والتقييم النهائي والقرار (بشري). الأسئلة في بنك مرتبط بالوظيفة، ويمكن نسخه بين الوظائف."""

from datetime import datetime, timezone

import streamlit as st

from core.constants import (
    APPLICATION_STATUSES, INTERVIEW_DECISIONS, INTERVIEW_STATUSES, INTERVIEW_TYPES,
    QUESTION_DIFFICULTIES, QUESTION_TYPES,
)
from core.exceptions import SmartATSError
from database.database import get_db_session
from repositories.application_repository import ApplicationRepository
from services.candidate_service import CandidateService
from services.interview_export_service import export_questions_docx, parse_answers_docx
from services.interview_service import InterviewService
from services.job_service import JobService
from services.question_bank_service import QuestionBankService, split_options
from ui import charts
from views import candidate_profile

_LIST_CACHE_TTL = 30
_MANUAL_OPTIONS = [0, 1, 2, 3, 4, 5]
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_FLASH_KEY = "interviews_flash"
_PENDING_SELECT_KEY = "iv_pending_select"
_OTHER = "أخرى"
_HISTORY_MAX_ROWS = 8

_TYPE_LABELS = {"text": "نصي", "choice": "اختيار من متعدد", "rating": "تقييم 1-5"}
_DECISION_LABELS = {
    "Continue": "الانتقال للمرحلة التالية", "Additional": "مقابلة إضافية",
    "Hold": "تعليق", "Not Selected": "غير مختار",
}
_DIMENSION_LABELS = {
    "technical_knowledge": "المعرفة الفنية", "problem_solving": "حل المشكلات",
    "communication": "التواصل", "practical_experience": "الخبرة العملية",
}


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


def _run(action, success: str | None = None, rerun: bool = True) -> bool:
    """ينفّذ عملية على الخدمات داخل جلسة، ويعرض الخطأ للمستخدم. يرجع True عند النجاح."""
    try:
        with get_db_session() as session:
            action(session)
    except SmartATSError as exc:
        st.error(str(exc))
        return False
    if success:
        st.toast(success)
    if rerun:
        st.rerun()
    return True


# ------------------------------------------------------------ بنك أسئلة الوظيفة

def _render_bank_question_row(q) -> None:
    with st.container(border=True):
        st.caption(
            f"{QuestionBankService.category_label(q.category)} · {_TYPE_LABELS.get(q.question_type or 'text')} · #{q.id}"
        )
        text = st.text_area("السؤال", value=q.question, key=f"bank_q_{q.id}", height=60)
        col_comp, col_diff = st.columns(2)
        with col_comp:
            competency = st.text_input("الكفاءة", value=q.competency or "", key=f"bank_c_{q.id}")
        with col_diff:
            options = [""] + QUESTION_DIFFICULTIES
            difficulty = st.selectbox(
                "الصعوبة", options, index=options.index(q.difficulty) if q.difficulty in options else 0,
                key=f"bank_d_{q.id}",
            )
        col_save, col_del = st.columns(2)
        with col_save:
            if st.button("💾 حفظ", key=f"bank_save_{q.id}", width="stretch"):
                _run(lambda s: QuestionBankService(s).update_question(
                    q.id, text, competency=competency, difficulty=difficulty), "تم الحفظ ✅")
        with col_del:
            if st.button("🗑️ حذف", key=f"bank_del_{q.id}", width="stretch"):
                _run(lambda s: QuestionBankService(s).delete_question(q.id), "تم الحذف 🗑️")


def _render_add_question_form(job_id: int) -> None:
    st.markdown("**➕ إضافة سؤال**")
    with st.form(f"bank_add_form_{job_id}", clear_on_submit=True):
        text = st.text_area("نص السؤال", height=70)
        col1, col2, col3 = st.columns(3)
        with col1:
            qtype = st.selectbox("النوع", QUESTION_TYPES, format_func=_TYPE_LABELS.get)
        with col2:
            competency = st.text_input("الكفاءة (اختياري)")
        with col3:
            difficulty = st.selectbox("الصعوبة", [""] + QUESTION_DIFFICULTIES)
        options_raw = st.text_input("الخيارات (لسؤال الاختيار فقط، مفصولة بفاصلة)")
        submitted = st.form_submit_button("إضافة", type="primary")
    if submitted:
        _run(lambda s: QuestionBankService(s).add_question(
            job_id, text, question_type=qtype, options=split_options(options_raw),
            competency=competency, difficulty=difficulty), "تمت إضافة السؤال ✅")


def _render_bank_tools(job, candidate) -> None:
    """توليد بالذكاء الاصطناعي، نسخ من وظيفة أخرى (قالب)، وأوزان الكفاءات."""
    if candidate is not None and st.button(
        "🤖 توليد أسئلة بالذكاء الاصطناعي (بناءً على سيرة المرشح المختار)", key=f"gen_ai_{job.id}"
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

    others = {f"{j.title} (#{j.id})": j.id for j in _cached_jobs() if j.id != job.id}
    if others:
        col_pick, col_btn = st.columns([3, 1])
        with col_pick:
            source_label = st.selectbox("نسخ أسئلة من وظيفة أخرى (قالب)", list(others), key=f"copy_src_{job.id}")
        with col_btn:
            st.write("")
            if st.button("📋 نسخ", key=f"copy_btn_{job.id}", width="stretch"):
                try:
                    with get_db_session() as session:
                        copied = QuestionBankService(session).copy_from_job(job.id, others[source_label])
                    _flash("success", f"تم نسخ {copied} سؤال.")
                    st.rerun()
                except SmartATSError as exc:
                    st.error(str(exc))

    with get_db_session() as session:
        weights_text = QuestionBankService(session).competency_weights_text(job.id)
    raw = st.text_area(
        "أوزان الكفاءات (سطر لكل كفاءة، مثال: Leadership: 20). اتركها فارغة لمتوسط بسيط.",
        value=weights_text, key=f"weights_{job.id}", height=90,
    )
    if st.button("💾 حفظ الأوزان", key=f"weights_save_{job.id}"):
        _run(lambda s: QuestionBankService(s).set_competency_weights(job.id, raw), "تم حفظ الأوزان ✅")


def _render_export_questions(job, questions: list) -> None:
    if not questions:
        return
    try:
        file_bytes = export_questions_docx(job, questions)
    except SmartATSError as exc:
        st.error(str(exc))
        return
    st.download_button(
        "⬇️ تصدير الأسئلة (Word) لتعبئة الإجابات خارج البرنامج", file_bytes,
        file_name=f"interview_questions_job_{job.id}.docx", mime=_DOCX_MIME, key=f"export_docx_{job.id}",
    )


def _render_question_bank(job, candidate) -> None:
    with st.expander("🗂️ بنك أسئلة الوظيفة (مشترك لكل المرشحين لهذه الوظيفة)"):
        with get_db_session() as session:
            questions = QuestionBankService(session).list_for_job(job.id)
        for q in questions:
            _render_bank_question_row(q)
        if not questions:
            st.caption("لا توجد أسئلة بعد. أضفها يدوياً أو ولّدها بالذكاء الاصطناعي أو انسخها من وظيفة أخرى.")
        _render_add_question_form(job.id)
        st.divider()
        _render_bank_tools(job, candidate)
        st.divider()
        _render_export_questions(job, questions)


# ------------------------------------------------------------ ترويسة المقابلة

def _header_fields(key: str, interview=None) -> dict:
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
            "المُقابِل(ون)", value=(interview.interviewer or "") if interview else "", key=f"{key}_interviewer"
        )
        location = st.text_input(
            "المكان / رابط الاجتماع", value=(interview.location or "") if interview else "", key=f"{key}_location"
        )
        next_action = st.text_input(
            "الإجراء التالي", value=(interview.next_action or "") if interview else "", key=f"{key}_next"
        )
    return {
        "interview_type": itype,
        "status": status,
        "scheduled_at": datetime.combine(date_input, time_input).replace(tzinfo=timezone.utc),
        "interviewer": interviewer.strip() or None,
        "location": location.strip() or None,
        "next_action": next_action.strip() or None,
    }


def _render_new_interview(application_id: int) -> None:
    st.subheader("➕ مقابلة جديدة")
    with st.form(f"new_interview_{application_id}"):
        values = _header_fields(f"new_{application_id}")
        submitted = st.form_submit_button("إنشاء المقابلة", type="primary")
    if submitted:
        try:
            with get_db_session() as session:
                interview = InterviewService(session).schedule(application_id, **values)
                interview_id = interview.id
            st.session_state[_PENDING_SELECT_KEY] = (application_id, interview_id)
            st.rerun()
        except SmartATSError as exc:
            st.error(str(exc))


def _render_header(interview, job, candidate) -> None:
    st.subheader(f"🗓️ {interview.code or f'#{interview.id}'} — {job.title}")
    when = interview.scheduled_at.strftime("%Y-%m-%d %H:%M") if interview.scheduled_at else "-"
    cols = st.columns(5)
    cols[0].metric("المرشح", candidate.full_name)
    cols[1].metric("الموعد", when)
    cols[2].metric("النوع", interview.interview_type)
    cols[3].metric("المُقابِل", interview.interviewer or "-")
    cols[4].metric("الحالة", interview.status)

    col_start, col_done, _ = st.columns([1, 1, 3])
    with col_start:
        if interview.status == "Scheduled" and st.button("▶️ بدء المقابلة", key=f"start_{interview.id}", width="stretch"):
            _run(lambda s: InterviewService(s).update(interview.id, status="In Progress"))
    with col_done:
        if interview.status in ("Scheduled", "In Progress") and st.button(
            "✅ إنهاء المقابلة", key=f"complete_{interview.id}", width="stretch"
        ):
            _run(lambda s: InterviewService(s).update(interview.id, status="Completed"))

    with st.expander("✏️ تعديل بيانات المقابلة"):
        with st.form(f"edit_interview_{interview.id}"):
            values = _header_fields(f"edit_{interview.id}", interview)
            saved = st.form_submit_button("💾 حفظ", type="primary")
        if saved:
            _run(lambda s: InterviewService(s).update(interview.id, **values), "تم حفظ التعديلات ✅")
        confirm = st.checkbox("تأكيد حذف هذه المقابلة", key=f"confirm_del_{interview.id}")
        if st.button("🗑️ حذف المقابلة", disabled=not confirm, key=f"del_{interview.id}"):
            _run(lambda s: InterviewService(s).delete(interview.id), "تم حذف المقابلة 🗑️")


# ------------------------------------------------------------ بطاقة المرشح

def _journey_lines(status: str) -> list[str]:
    stages = [s for s in APPLICATION_STATUSES if s != "Rejected"]
    if status == "Rejected":
        return ["❌ Rejected"]
    current = stages.index(status) if status in stages else 0
    return [("✓ " if i < current else "● " if i == current else "○ ") + s for i, s in enumerate(stages)]


def _render_candidate_panel(interview, candidate, app_status: str, score, history: list[dict]) -> None:
    with st.container(border=True):
        st.markdown(f"### {candidate.full_name}")
        st.caption(candidate.current_position or "بدون مسمى")
        if candidate.total_experience_years is not None:
            st.write(f"⏳ {candidate.total_experience_years:g} سنة خبرة")
        if score is not None:
            st.metric("مطابقة ATS", f"{score}%")
        st.markdown("**رحلة المرشح**")
        for line in _journey_lines(app_status):
            st.caption(line)

    if history:
        st.markdown("**المقابلات السابقة**")
        st.dataframe(
            [{"التاريخ": h["date"], "النوع": h["type"], "الوظيفة": h["job"], "الدرجة": h["score"] if h["score"] is not None else "-"}
             for h in history[:_HISTORY_MAX_ROWS]],
            hide_index=True, width="stretch",
        )
    with st.expander("📄 عرض السيرة الذاتية الكاملة"):
        candidate_profile.render_profile(candidate.id)


# ------------------------------------------------------------ مساحة السؤال

def _step(key: str, delta: int, last: int) -> None:
    st.session_state[key] = min(max(st.session_state.get(key, 0) + delta, 0), last)


def _render_navigator(interview_id: int, questions: list, answers: dict) -> int:
    key = f"iv_nav_{interview_id}"
    last = len(questions) - 1
    st.session_state[key] = min(st.session_state.get(key, 0), last)

    def label(i: int) -> str:
        answer = answers.get(questions[i].id)
        return f"{'●' if answer and (answer.answer or '').strip() else '○'} {i + 1:02d}"

    st.radio("الأسئلة", list(range(len(questions))), format_func=label, horizontal=True, key=key,
             label_visibility="collapsed")
    col_prev, col_next, _ = st.columns([1, 1, 4])
    col_prev.button("◀ السابق", on_click=_step, args=(key, -1, last), key=f"prev_{interview_id}", width="stretch")
    col_next.button("التالي ▶", on_click=_step, args=(key, 1, last), key=f"next_{interview_id}", width="stretch")
    return st.session_state[key]


def _answer_input(interview_id: int, question, current: str) -> str:
    key = f"ans_{interview_id}_{question.id}"
    qtype = question.question_type or "text"
    if qtype == "choice" and question.options:
        choices = list(question.options) + [_OTHER]
        index = choices.index(current) if current in choices else (len(choices) - 1 if current else None)
        picked = st.radio("إجابة المرشح", choices, index=index, key=f"{key}_c")
        if picked == _OTHER:
            return st.text_input("اكتب الإجابة", value="" if current in choices else current, key=f"{key}_o")
        return picked or ""
    if qtype == "rating":
        choices = ["1", "2", "3", "4", "5"]
        picked = st.radio(
            "تقييم المرشح لنفسه", choices, index=choices.index(current) if current in choices else None,
            horizontal=True, key=f"{key}_r",
        )
        return picked or ""
    return st.text_area("إجابة المرشح", value=current, key=key, height=160, placeholder="اكتب إجابة المرشح هنا...")


def _render_ai_analysis(answer, interview_id: int, job, question_id: int) -> None:
    if answer is None or answer.ai_score is None:
        return
    with st.container(border=True):
        st.markdown(f"**🤖 تحليل الذكاء الاصطناعي — {answer.ai_score * 20}/100**")
        dims = answer.ai_dimensions or {}
        if dims:
            for col, (name, value) in zip(st.columns(len(dims)), dims.items()):
                col.metric(_DIMENSION_LABELS.get(name, name), f"{value}%")
        if answer.eval_feedback:
            st.caption(answer.eval_feedback)
        for s in answer.eval_strengths or []:
            st.write(f"✔️ {s}")
        for c in answer.eval_concerns or []:
            st.write(f"⚠️ يحتاج تحققاً: {c}")
        if answer.ai_followup:
            st.info(f"💬 سؤال متابعة مقترح: {answer.ai_followup}")
            if st.button("➕ أضفه لبنك الأسئلة", key=f"followup_{interview_id}_{question_id}"):
                _run(lambda s: QuestionBankService(s).add_question(
                    job.id, answer.ai_followup, source="ai", category="cv_specific"), "تمت إضافة سؤال المتابعة ✅")


def _render_interviewer_review(interview_id: int, question_id: int, answer) -> None:
    with st.container(border=True):
        st.markdown("**🧑 تقييم المُقابِل**")
        current = (answer.manual_score if answer else None) or 0
        col_score, col_notes = st.columns([1, 2])
        with col_score:
            score = st.selectbox(
                "تقييمي", _MANUAL_OPTIONS, index=_MANUAL_OPTIONS.index(current),
                key=f"rv_score_{interview_id}_{question_id}",
                format_func=lambda v: "بدون تقييم" if v == 0 else f"{v}/5",
            )
        with col_notes:
            notes = st.text_area(
                "ملاحظاتي", value=(answer.interviewer_notes if answer else "") or "",
                key=f"rv_notes_{interview_id}_{question_id}", height=80,
            )
        if st.button("💾 حفظ تقييمي", key=f"rv_save_{interview_id}_{question_id}"):
            _run(lambda s: InterviewService(s).set_interviewer_review(
                interview_id, question_id, score or None, notes), "تم الحفظ ✅")
        if answer and answer.eval_score is not None:
            source = "تقييم المُقابِل" if answer.eval_method == "manual" else "تحليل الذكاء الاصطناعي"
            st.caption(f"الدرجة الفعلية لهذا السؤال: **{answer.eval_score}/5** (المصدر: {source})")


def _render_question_workspace(interview, job, question, answer, index: int, total: int) -> None:
    iid, qid = interview.id, question.id
    st.markdown(f"#### سؤال {index + 1} من {total}")
    meta = [QuestionBankService.category_label(question.category), _TYPE_LABELS.get(question.question_type or "text", "")]
    if question.competency:
        meta.append(f"🎯 {question.competency}")
    if question.difficulty:
        meta.append(question.difficulty)
    st.caption(" · ".join(m for m in meta if m))
    st.write(f"**{question.question}**")
    if question.rationale:
        st.caption(f"💡 {question.rationale}")

    answer_text = _answer_input(iid, question, (answer.answer if answer else "") or "")

    col_save, col_ai = st.columns(2)
    with col_save:
        if st.button("💾 حفظ الإجابة", key=f"ans_save_{iid}_{qid}", width="stretch"):
            _run(lambda s: InterviewService(s).save_answer(iid, qid, answer_text), "تم الحفظ ✅")
    with col_ai:
        if st.button("🤖 تحليل بالذكاء الاصطناعي", key=f"ans_ai_{iid}_{qid}", width="stretch"):
            def analyze(session) -> None:
                service = InterviewService(session)
                service.save_answer(iid, qid, answer_text)
                session.flush()  # لتظهر الإجابة المحفوظة للتو ضمن السياق المرجعي
                service.evaluate_answer(iid, qid, job)
            _run(analyze, "تم التحليل ✅")

    _render_ai_analysis(answer, iid, job, qid)
    _render_interviewer_review(iid, qid, answer)


# ------------------------------------------------------------ الكفاءات والتقييم النهائي

def _render_evaluation(interview, job) -> None:
    with get_db_session() as session:
        service = InterviewService(session)
        report = service.competency_report(interview.id, job)
        scored, written = service.answered_stats(interview.id)

    st.subheader("🏁 التقييم النهائي")
    if report["scores"]:
        st.plotly_chart(charts.bar_chart(report["scores"], "درجات الكفاءات (من 100)"), width="stretch")
        st.caption("الدرجة الكلية للكفاءات تُحسب على الكفاءات المُقيَّمة فقط، بأوزان الوظيفة إن وُجدت.")
    else:
        st.caption("اربط الأسئلة بكفاءات من بنك الأسئلة لتظهر درجات الكفاءات هنا.")

    col_score, col_info = st.columns([1, 2])
    with col_score:
        if interview.overall_score is not None:
            st.metric("الدرجة النهائية", f"{interview.overall_score:g} / 100")
        else:
            st.caption("لم تُحسب الدرجة النهائية بعد.")
    with col_info:
        if interview.overall_score is not None:
            source = "معدَّلة يدوياً" if interview.overall_method == "manual" else "محسوبة تلقائياً"
            st.caption(f"المصدر: {source}")
        st.caption(f"أسئلة مقيَّمة: {scored} من {written} مجابة.")

    if st.button("🧮 احسب التقييم النهائي", key=f"final_calc_{interview.id}"):
        try:
            with get_db_session() as session:
                score = InterviewService(session).finalize_score(interview.id)
            if score is None:
                st.warning("لا توجد إجابات مقيَّمة. قيّم إجابة واحدة على الأقل.")
            else:
                st.toast(f"الدرجة النهائية: {score:g} / 100 ✅")
                st.rerun()
        except SmartATSError as exc:
            st.error(str(exc))

    with st.form(f"final_form_{interview.id}"):
        decision = st.radio(
            "القرار (بشري فقط)", INTERVIEW_DECISIONS, format_func=_DECISION_LABELS.get, horizontal=True,
            index=INTERVIEW_DECISIONS.index(interview.decision) if interview.decision in INTERVIEW_DECISIONS else None,
            key=f"final_decision_{interview.id}",
        )
        current = float(interview.overall_score or 0.0)
        new_score = st.number_input(
            "تعديل الدرجة النهائية يدوياً (0 إلى 100)", min_value=0.0, max_value=100.0, step=1.0,
            value=current, key=f"final_score_{interview.id}",
        )
        interviewer_notes = st.text_area(
            "ملاحظات المُقابِل (ملاحظات شخصية لا يستنتجها الذكاء الاصطناعي)",
            value=interview.notes or "", key=f"final_inotes_{interview.id}",
        )
        notes = st.text_area("ملاحظات التقييم النهائي", value=interview.overall_notes or "", key=f"final_notes_{interview.id}")
        saved = st.form_submit_button("💾 حفظ التقييم النهائي", type="primary")
    if saved:
        def save_final(session) -> None:
            service = InterviewService(session)
            # إن لم تتغير الدرجة نحدّث الملاحظات فقط فلا تُوسَم الدرجة المحسوبة بأنها يدوية
            service.set_overall(interview.id, new_score if new_score != current else None, notes, decision)
            service.update(interview.id, notes=interviewer_notes.strip() or None)
        _run(save_final, "تم حفظ التقييم النهائي ✅")


# ------------------------------------------------------------ استيراد الإجابات من Word

def _render_import_answers(interview, job) -> None:
    """يرفع ملف Word المعبّأ، يحفظ الإجابات، يقيّمها بالذكاء الاصطناعي، ثم يحسب الدرجة النهائية."""
    with st.expander("📥 استيراد الإجابات من ملف Word"):
        st.caption(
            "ارفع نفس الملف المُصدَّر من بنك الأسئلة بعد كتابة الإجابات. ستُحفظ الإجابات (وتستبدل "
            "إجابات نفس الأسئلة) ثم تُقيَّم. الأسئلة التي لم تُكتب لها إجابة لا تتأثر، وتقييمات المُقابِل تبقى كما هي."
        )
        uploaded = st.file_uploader("ملف الإجابات (.docx)", type=["docx"], key=f"import_file_{interview.id}")
        if uploaded is None or not st.button(
            "🤖 استيراد الإجابات وتحليلها", key=f"import_btn_{interview.id}", type="primary"
        ):
            return

        try:
            answers = parse_answers_docx(uploaded.getvalue(), expected_job_id=job.id)
            if not answers:
                st.warning("لم يتم العثور على أي إجابة مكتوبة في الملف.")
                return

            progress = st.progress(0.0, text="جاري تحليل الإجابات...")

            def _on_progress(done: int, total: int) -> None:
                progress.progress(done / total, text=f"تم تحليل {done} / {total}")

            with get_db_session() as session:
                result = InterviewService(session).import_answers(interview.id, job, answers, _on_progress)
        except SmartATSError as exc:
            st.error(str(exc))
            return

        # أي widget له key محفوظ في session_state يتجاهل value= الجديد، فنحذف مفاتيح الأسئلة المستوردة
        for question_id in answers:
            for suffix in ("", "_c", "_o", "_r"):
                st.session_state.pop(f"ans_{interview.id}_{question_id}{suffix}", None)
            st.session_state.pop(f"rv_score_{interview.id}_{question_id}", None)

        message = f"تم استيراد {result['saved']} إجابة وتحليل {result['evaluated']} منها."
        if result["overall_score"] is not None:
            message += f" الدرجة النهائية: {result['overall_score']:g} / 100."
        if result["unknown"]:
            message += f" تم تجاهل {len(result['unknown'])} سؤال غير موجود في بنك الوظيفة."
        if result["failed"]:
            _flash("warning", message + f" تعذّر تحليل {len(result['failed'])} إجابة (حُفظت بدون درجة).")
        else:
            _flash("success", message)
        st.rerun()


# ------------------------------------------------------------ الصفحة الرئيسية

def _render_workspace(interview, job, candidate, app_status: str, score) -> None:
    with get_db_session() as session:
        questions = QuestionBankService(session).list_for_job(job.id)
        service = InterviewService(session)
        answers = service.answers_map(interview.id)
        history = service.history_for_candidate(candidate.id, exclude_id=interview.id)

    _render_header(interview, job, candidate)
    st.divider()

    col_left, col_right = st.columns([1, 2])
    with col_left:
        _render_candidate_panel(interview, candidate, app_status, score, history)
    with col_right:
        if not questions:
            st.info("لا توجد أسئلة في بنك هذه الوظيفة بعد. أضفها من «بنك أسئلة الوظيفة» أعلاه.")
        else:
            index = _render_navigator(interview.id, questions, answers)
            _render_question_workspace(interview, job, questions[index], answers.get(questions[index].id), index, len(questions))

    st.divider()
    _render_evaluation(interview, job)
    _render_import_answers(interview, job)


def render() -> None:
    st.header("🗓️ المقابلات")
    _show_flash()

    jobs = _cached_jobs()
    if not jobs:
        st.info("أضف وظيفة أولاً من صفحة «الوظائف».")
        return

    job_labels = {f"{j.title} (#{j.id})": j.id for j in jobs}
    job_id = job_labels[st.selectbox("الوظيفة", list(job_labels), key="iv_job_select")]

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
        _render_question_bank(job, None)
        st.info("لا يوجد مرشحون مطابَقون لهذه الوظيفة بعد. شغّل المطابقة من صفحة «المطابقة» أولاً.")
        return

    st.caption("المرشحون مرتبون حسب نسبة المطابقة (الأعلى أولاً).")
    app_labels = {
        (f"{c.full_name} · مطابقة {score}% · {status}" if score is not None else f"{c.full_name} · {status}"): (app_id, c, status, score)
        for app_id, c, status, score in app_rows
    }
    application_id, candidate, app_status, score = app_labels[
        st.selectbox("المرشح", list(app_labels), key="iv_app_select")
    ]

    _render_question_bank(job, candidate)

    with get_db_session() as session:
        interviews = InterviewService(session).list_for_application(application_id)
    by_id = {iv.id: iv for iv in interviews}

    select_key = f"iv_sel_{application_id}"
    pending = st.session_state.get(_PENDING_SELECT_KEY)
    if pending and pending[0] == application_id:
        st.session_state[select_key] = pending[1]
        st.session_state.pop(_PENDING_SELECT_KEY)

    def _label(interview_id) -> str:
        if interview_id is None:
            return "➕ مقابلة جديدة"
        iv = by_id[interview_id]
        when = iv.scheduled_at.strftime("%Y-%m-%d") if iv.scheduled_at else "-"
        return f"{iv.code or f'#{iv.id}'} · {iv.interview_type} · {iv.status} · {when}"

    options = [None] + list(by_id)
    selected = st.selectbox(
        "المقابلة", options, index=1 if by_id else 0, format_func=_label, key=select_key
    )

    st.divider()
    if selected is None:
        _render_new_interview(application_id)
    else:
        _render_workspace(by_id[selected], job, candidate, app_status, score)