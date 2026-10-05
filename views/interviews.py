"""صفحة المقابلات كـ Interview Workspace بتصميم منظّم في ثلاثة تبويبات:
🎙️ المقابلة (ترويسة + بطاقة المرشح + مساحة السؤال + التقييم النهائي)،
🗂️ بنك أسئلة الوظيفة، ⚙️ إدارة المقابلة (تعديل/تصدير/استيراد/حذف).
الأسئلة في بنك مرتبط بالوظيفة، ويمكن نسخه بين الوظائف. القرار النهائي بشري فقط."""

import html
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
from views import candidate_profile
from ui import components
from ui.navigation import OFFER_PREFILL_APP, OPEN_CREATE_JOB, OPEN_CREATE_OFFER, go_to


_LIST_CACHE_TTL = 30
_MANUAL_OPTIONS = [0, 1, 2, 3, 4, 5]
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_FLASH_KEY = "interviews_flash"
_PENDING_SELECT_KEY = "iv_pending_select"
_OTHER = "أخرى"
_HISTORY_MAX_ROWS = 8
_PHOTO_WIDTH_PX = 72

_TYPE_LABELS = {"text": "نصي", "choice": "اختيار من متعدد", "rating": "تقييم 1-5"}
_DECISION_LABELS = {
    "Continue": "الانتقال للمرحلة التالية", "Additional": "مقابلة إضافية",
    "Hold": "تعليق", "Not Selected": "غير مختار",
}
_DIMENSION_LABELS = {
    "technical_knowledge": "المعرفة الفنية", "problem_solving": "حل المشكلات",
    "communication": "التواصل", "practical_experience": "الخبرة العملية",
}
_STATUS_LABELS = {
    "Scheduled": "مجدولة", "In Progress": "جارية", "Completed": "مكتملة", "Cancelled": "ملغاة",
}
_STATUS_COLORS = {
    "Scheduled": "#3b82f6", "In Progress": "#f59e0b", "Completed": "#22c55e", "Cancelled": "#ef4444",
}
_COLOR_GOOD, _COLOR_MID, _COLOR_BAD = "#22c55e", "#f59e0b", "#ef4444"
_GOOD_THRESHOLD, _MID_THRESHOLD = 75, 50

_CSS = """
<style>
.ats-header{display:flex;flex-wrap:wrap;gap:8px 24px;align-items:center;padding:14px 18px;
  border:1px solid rgba(128,128,128,.25);border-radius:12px;background:rgba(128,128,128,.07)}
.ats-hcell{min-width:120px}
.ats-hlabel{font-size:.72rem;opacity:.65;margin-bottom:2px}
.ats-hvalue{font-size:.95rem;font-weight:600}
.ats-badge{display:inline-block;padding:3px 12px;border-radius:999px;font-size:.8rem;font-weight:700;
  color:var(--c);border:1px solid var(--c);background:color-mix(in srgb,var(--c) 14%,transparent)}
.ats-chip{display:inline-block;padding:2px 10px;margin:0 4px 4px 0;border-radius:999px;font-size:.75rem;
  border:1px solid rgba(128,128,128,.35);opacity:.9}
.ats-ring-wrap{display:flex;flex-direction:column;align-items:center;gap:6px;min-width:84px}
.ats-ring-box{position:relative;display:grid;place-items:center}
.ats-ring{position:absolute;inset:0;border-radius:50%;
  background:conic-gradient(var(--c) calc(var(--p)*1%),rgba(128,128,128,.22) 0);
  -webkit-mask:radial-gradient(farthest-side,transparent calc(100% - 7px),#000 calc(100% - 6px));
  mask:radial-gradient(farthest-side,transparent calc(100% - 7px),#000 calc(100% - 6px))}
.ats-ring-val{position:relative;font-weight:700}
.ats-ring-label{font-size:.75rem;opacity:.8;text-align:center}
.ats-rings{display:flex;flex-wrap:wrap;gap:18px}
.ats-journey{display:flex;padding:6px 0 2px}
.ats-step{flex:1;text-align:center;position:relative}
.ats-step::before{content:"";position:absolute;top:6px;left:-50%;width:100%;height:2px;
  background:rgba(128,128,128,.35)}
.ats-step:first-child::before{display:none}
.ats-step.done::before,.ats-step.current::before{background:#3b82f6}
.ats-dot{position:relative;width:14px;height:14px;margin:0 auto;border-radius:50%;
  border:2px solid rgba(128,128,128,.5);background:transparent;z-index:1}
.ats-step.done .ats-dot{background:#3b82f6;border-color:#3b82f6}
.ats-step.current .ats-dot{background:#fff;border-color:#3b82f6;box-shadow:0 0 0 3px rgba(59,130,246,.3)}
.ats-step-label{font-size:.68rem;margin-top:6px;opacity:.8}
.ats-step.current .ats-step-label{font-weight:700;opacity:1}
.ats-bar-row{margin-bottom:8px}
.ats-bar-head{display:flex;justify-content:space-between;font-size:.78rem;margin-bottom:3px}
.ats-bar-track{height:7px;border-radius:999px;background:rgba(128,128,128,.22);overflow:hidden}
.ats-bar-fill{height:100%;border-radius:999px}
.ats-section-title{font-size:1.02rem;font-weight:700;margin:2px 0 8px}
</style>
"""


def _inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


# ------------------------------------------------------------ مكوّنات عرض صغيرة

def _score_color(value: float) -> str:
    if value >= _GOOD_THRESHOLD:
        return _COLOR_GOOD
    return _COLOR_MID if value >= _MID_THRESHOLD else _COLOR_BAD


def _ring(value: float | None, label: str, size: int = 64) -> str:
    pct = max(0.0, min(100.0, float(value or 0)))
    return (
        f'<div class="ats-ring-wrap"><div class="ats-ring-box" style="width:{size}px;height:{size}px">'
        f'<div class="ats-ring" style="--p:{pct};--c:{_score_color(pct)}"></div>'
        f'<span class="ats-ring-val" style="font-size:{size // 4}px">{pct:g}</span></div>'
        f'<div class="ats-ring-label">{html.escape(label)}</div></div>'
    )


def _bar(label: str, value: float) -> str:
    pct = max(0.0, min(100.0, float(value)))
    return (
        f'<div class="ats-bar-row"><div class="ats-bar-head"><span>{html.escape(label)}</span>'
        f'<span>{pct:g}%</span></div><div class="ats-bar-track">'
        f'<div class="ats-bar-fill" style="width:{pct}%;background:{_score_color(pct)}"></div></div></div>'
    )


def _badge(text: str, color: str) -> str:
    return f'<span class="ats-badge" style="--c:{color}">{html.escape(text)}</span>'


def _journey_html(status: str) -> str:
    if status == "Rejected":
        return _badge("❌ مرفوض", _COLOR_BAD)
    stages = [s for s in APPLICATION_STATUSES if s != "Rejected"]
    current = stages.index(status) if status in stages else 0
    steps = "".join(
        f'<div class="ats-step {"done" if i < current else "current" if i == current else "todo"}">'
        f'<div class="ats-dot"></div><div class="ats-step-label">{html.escape(stage)}</div></div>'
        for i, stage in enumerate(stages)
    )
    return f'<div class="ats-journey">{steps}</div>'


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


# ------------------------------------------------------------ تبويب: بنك أسئلة الوظيفة

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


def _render_question_bank(job, candidate) -> None:
    st.caption("بنك أسئلة الوظيفة مشترك لكل المرشحين المتقدمين لها.")
    with get_db_session() as session:
        questions = QuestionBankService(session).list_for_job(job.id)
    if not questions:
        st.info("لا توجد أسئلة بعد. أضفها يدوياً أو ولّدها بالذكاء الاصطناعي أو انسخها من وظيفة أخرى.")
    for q in questions:
        _render_bank_question_row(q)
    _render_add_question_form(job.id)
    st.divider()
    _render_bank_tools(job, candidate)


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

def _render_new_interview(application_id: int, job) -> None:
    """نموذج جدولة مختصر: النوع والموعد والمُقابِل والمكان فقط (الحالة تُضبط تلقائياً «مجدولة»)."""
    st.markdown('<div class="ats-section-title">🗓️ جدولة مقابلة</div>', unsafe_allow_html=True)
    st.caption("لم تُجدول مقابلة لهذا المرشح بعد.")

    with get_db_session() as session:
        question_count = len(QuestionBankService(session).list_for_job(job.id))
    if question_count:
        st.caption(f"📋 ستُستخدم أسئلة الوظيفة ({question_count} سؤال) أثناء المقابلة.")
    else:
        st.warning("لا توجد أسئلة في بنك هذه الوظيفة بعد. يمكنك إضافتها من تبويب «🗂️ بنك الأسئلة».")

    key = f"new_{application_id}"
    with st.form(f"new_interview_{application_id}"):
        col1, col2 = st.columns(2)
        with col1:
            itype = st.selectbox("نوع المقابلة", INTERVIEW_TYPES, key=f"{key}_type")
            date_input = st.date_input("التاريخ", value=datetime.now().date(), key=f"{key}_date")
            time_input = st.time_input(
                "الوقت", value=datetime.now().time().replace(second=0, microsecond=0), key=f"{key}_time"
            )
        with col2:
            interviewer = st.text_input("المُقابِل(ون)", key=f"{key}_interviewer")
            location = st.text_input("المكان / رابط الاجتماع", key=f"{key}_location")
        submitted = st.form_submit_button("🗓️ جدولة المقابلة", type="primary")

    if submitted:
        values = {
            "interview_type": itype,
            "status": INTERVIEW_STATUSES[0],
            "scheduled_at": datetime.combine(date_input, time_input).replace(tzinfo=timezone.utc),
            "interviewer": interviewer.strip() or None,
            "location": location.strip() or None,
        }
        try:
            with get_db_session() as session:
                interview = InterviewService(session).schedule(application_id, **values)
                interview_id = interview.id
            st.session_state[_PENDING_SELECT_KEY] = (application_id, interview_id)
            st.toast("تمت جدولة المقابلة ونُقل المرشح إلى مرحلة «المقابلة» ✅")
            st.rerun()
        except SmartATSError as exc:
            st.error(str(exc))

def _render_header(interview, job, candidate) -> None:
    """شريط ترويسة المقابلة: بيانات أساسية + شارة الحالة + أزرار البدء والإنهاء."""
    when = interview.scheduled_at.strftime("%Y-%m-%d %H:%M") if interview.scheduled_at else "-"
    cells = [
        ("المرشح / الوظيفة", f"{candidate.full_name} — {job.title}"),
        ("رقم المقابلة", interview.code or f"#{interview.id}"),
        ("الموعد", when),
        ("النوع", interview.interview_type),
        ("المُقابِل", interview.interviewer or "-"),
    ]
    cells_html = "".join(
        f'<div class="ats-hcell"><div class="ats-hlabel">{label}</div>'
        f'<div class="ats-hvalue">{html.escape(value)}</div></div>'
        for label, value in cells
    )
    badge = _badge(
        _STATUS_LABELS.get(interview.status, interview.status), _STATUS_COLORS.get(interview.status, "#64748b")
    )
    st.markdown(
        f'<div class="ats-header">{cells_html}<div class="ats-hcell"><div class="ats-hlabel">الحالة</div>'
        f'{badge}</div></div>',
        unsafe_allow_html=True,
    )

    can_start = interview.status == "Scheduled"
    can_finish = interview.status in ("Scheduled", "In Progress")
    if can_start or can_finish:
        col_start, col_done, _ = st.columns([1, 1, 4])
        with col_start:
            if can_start and st.button("▶️ بدء المقابلة", key=f"start_{interview.id}", width="stretch"):
                _run(lambda s: InterviewService(s).update(interview.id, status="In Progress"))
        with col_done:
            if can_finish and st.button(
                "✅ إنهاء المقابلة", key=f"complete_{interview.id}", type="primary", width="stretch"
            ):
                _run(lambda s: InterviewService(s).update(interview.id, status="Completed"))


# ------------------------------------------------------------ بطاقة المرشح (العمود الأيسر)

def _render_candidate_panel(interview, candidate, app_status: str, score, history: list[dict]) -> None:
    st.markdown('<div class="ats-section-title">👤 بيانات المرشح</div>', unsafe_allow_html=True)
    photo_path = CandidateService.photo_absolute_path(candidate)
    with st.container(border=True):
        col_photo, col_info, col_score = st.columns([1, 2.2, 1.2])
        with col_photo:
            if photo_path:
                st.image(str(photo_path), width=_PHOTO_WIDTH_PX)
            else:
                st.markdown("## 👤")
        with col_info:
            st.markdown(f"**{candidate.full_name}**")
            st.caption(candidate.current_position or "بدون مسمى")
            if candidate.total_experience_years is not None:
                st.caption(f"⏳ {candidate.total_experience_years:g} سنة خبرة")
        with col_score:
            if score is not None:
                st.markdown(_ring(score, "مطابقة ATS", 68), unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown("**🧭 رحلة المرشح**")
        st.markdown(_journey_html(app_status), unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown("**🕘 المقابلات السابقة**")
        if history:
            st.dataframe(
                [{"التاريخ": h["date"], "النوع": h["type"], "الوظيفة": h["job"],
                  "الدرجة": h["score"] if h["score"] is not None else "-"}
                 for h in history[:_HISTORY_MAX_ROWS]],
                hide_index=True, width="stretch",
            )
        else:
            st.caption("لا توجد مقابلات سابقة لهذا المرشح.")

    with st.expander("📄 عرض السيرة الذاتية الكاملة"):
        candidate_profile.render_profile(candidate.id)


# ------------------------------------------------------------ مساحة السؤال (العمود الأيمن)

def _step(key: str, delta: int, last: int) -> None:
    st.session_state[key] = min(max(st.session_state.get(key, 0) + delta, 0), last)


def _render_navigator(interview_id: int, questions: list, answers: dict) -> int:
    key = f"iv_nav_{interview_id}"
    last = len(questions) - 1
    st.session_state[key] = min(st.session_state.get(key, 0), last)

    answered = sum(
        1 for q in questions if answers.get(q.id) and (answers[q.id].answer or "").strip()
    )
    st.progress(answered / len(questions), text=f"تمت الإجابة على {answered} من {len(questions)} سؤال")

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
    return st.text_area("إجابة المرشح", value=current, key=key, height=150, placeholder="اكتب إجابة المرشح هنا...")


def _render_ai_analysis(answer, interview_id: int, job, question_id: int) -> None:
    if answer is None or answer.ai_score is None:
        return
    with st.container(border=True):
        st.markdown(f"**🤖 تحليل الذكاء الاصطناعي** — الدرجة: **{answer.ai_score * 20}/100**")
        col_dims, col_notes = st.columns(2)
        with col_dims:
            dims = answer.ai_dimensions or {}
            if dims:
                st.markdown(
                    "".join(_bar(_DIMENSION_LABELS.get(n, n), v) for n, v in dims.items()),
                    unsafe_allow_html=True,
                )
        with col_notes:
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
        st.markdown("**🧑 تقييم السؤال**")
        current = (answer.manual_score if answer else None) or 0
        col_ai, col_score, col_notes = st.columns([1, 1, 2])
        with col_ai:
            ai_score = answer.ai_score if answer and answer.ai_score else None
            st.metric("تقييم الذكاء الاصطناعي", f"{ai_score}/5" if ai_score else "—")
        with col_score:
            score = st.selectbox(
                "تقييم المُقابِل", _MANUAL_OPTIONS, index=_MANUAL_OPTIONS.index(current),
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

    with st.container(border=True):
        chips = [QuestionBankService.category_label(question.category), _TYPE_LABELS.get(question.question_type or "text", "")]
        if question.competency:
            chips.append(f"🎯 {question.competency}")
        if question.difficulty:
            chips.append(question.difficulty)
        chips_html = "".join(f'<span class="ats-chip">{html.escape(c)}</span>' for c in chips if c)
        st.markdown(f"**سؤال {index + 1} من {total}**")
        st.markdown(chips_html, unsafe_allow_html=True)
        st.markdown(f"#### {question.question}")
        if question.rationale:
            st.caption(f"💡 {question.rationale}")

    with st.container(border=True):
        answer_text = _answer_input(iid, question, (answer.answer if answer else "") or "")
        col_save, col_ai = st.columns(2)
        with col_save:
            if st.button("💾 حفظ الإجابة", key=f"ans_save_{iid}_{qid}", width="stretch"):
                _run(lambda s: InterviewService(s).save_answer(iid, qid, answer_text), "تم الحفظ ✅")
        with col_ai:
            if st.button("🤖 تحليل بالذكاء الاصطناعي", key=f"ans_ai_{iid}_{qid}", type="primary", width="stretch"):
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

    st.markdown('<div class="ats-section-title">🏁 التقييم النهائي</div>', unsafe_allow_html=True)
    with st.container(border=True):
        col_rings, col_overall = st.columns([3, 1])
        with col_rings:
            if report["scores"]:
                rings = "".join(_ring(v, n) for n, v in report["scores"].items())
                st.markdown(f'<div class="ats-rings">{rings}</div>', unsafe_allow_html=True)
                st.caption("الدرجة الكلية للكفاءات تُحسب على الكفاءات المُقيَّمة فقط، بأوزان الوظيفة إن وُجدت.")
            else:
                st.caption("اربط الأسئلة بكفاءات من بنك الأسئلة لتظهر درجات الكفاءات هنا.")
        with col_overall:
            if interview.overall_score is not None:
                st.markdown(_ring(interview.overall_score, "الدرجة النهائية", 96), unsafe_allow_html=True)
                source = "معدَّلة يدوياً" if interview.overall_method == "manual" else "محسوبة تلقائياً"
                st.caption(f"{source} · أسئلة مقيَّمة: {scored} من {written}")
            else:
                st.caption("لم تُحسب الدرجة النهائية بعد.")
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

    with st.container(border=True):
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
            col_a, col_b = st.columns(2)
            with col_a:
                interviewer_notes = st.text_area(
                    "ملاحظات المُقابِل (شخصية، لا يستنتجها الذكاء الاصطناعي)",
                    value=interview.notes or "", key=f"final_inotes_{interview.id}", height=110,
                )
            with col_b:
                notes = st.text_area(
                    "ملاحظات التقييم النهائي", value=interview.overall_notes or "",
                    key=f"final_notes_{interview.id}", height=110,
                )
            saved = st.form_submit_button("💾 حفظ التقييم النهائي", type="primary")
        if saved:
            def save_final(session) -> None:
                service = InterviewService(session)
                # إن لم تتغير الدرجة نحدّث الملاحظات فقط فلا تُوسَم الدرجة المحسوبة بأنها يدوية
                service.set_overall(interview.id, new_score if new_score != current else None, notes, decision)
                service.update(interview.id, notes=interviewer_notes.strip() or None)
            _run(save_final, "تم حفظ التقييم النهائي ✅")


# ------------------------------------------------------------ تبويب الإدارة: تعديل / تصدير / استيراد / حذف

def _render_edit_interview(interview) -> None:
    with st.container(border=True):
        st.markdown("**✏️ تعديل بيانات المقابلة**")
        with st.form(f"edit_interview_{interview.id}"):
            values = _header_fields(f"edit_{interview.id}", interview)
            saved = st.form_submit_button("💾 حفظ", type="primary")
        if saved:
            _run(lambda s: InterviewService(s).update(interview.id, **values), "تم حفظ التعديلات ✅")
        confirm = st.checkbox("تأكيد حذف هذه المقابلة", key=f"confirm_del_{interview.id}")
        if st.button("🗑️ حذف المقابلة", disabled=not confirm, key=f"del_{interview.id}"):
            _run(lambda s: InterviewService(s).delete(interview.id), "تم حذف المقابلة 🗑️")


def _render_export_questions(job, questions: list) -> None:
    with st.container(border=True):
        st.markdown("**📤 تصدير الأسئلة**")
        if not questions:
            st.caption("لا توجد أسئلة لتصديرها.")
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


def _render_import_answers(interview, job) -> None:
    """يرفع ملف Word المعبّأ، يحفظ الإجابات، يقيّمها بالذكاء الاصطناعي، ثم يحسب الدرجة النهائية."""
    with st.container(border=True):
        st.markdown("**📥 استيراد الإجابات من ملف Word**")
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


def _render_manage_tab(interview, job, questions: list) -> None:
    col_left, col_right = st.columns(2)
    with col_left:
        _render_edit_interview(interview)
    with col_right:
        _render_export_questions(job, questions)
        _render_import_answers(interview, job)


# ------------------------------------------------------------ مساحة العمل الرئيسية

def _render_interview_tab(interview, job, candidate, app_status: str, score, questions, answers, history) -> None:
    _render_header(interview, job, candidate)
    st.write("")

    col_left, col_right = st.columns([1, 2], gap="large")
    with col_left:
        _render_candidate_panel(interview, candidate, app_status, score, history)
    with col_right:
        st.markdown('<div class="ats-section-title">🎙️ مساحة المقابلة</div>', unsafe_allow_html=True)
        if not questions:
            st.info("لا توجد أسئلة في بنك هذه الوظيفة بعد. أضفها من تبويب «🗂️ بنك الأسئلة».")
        else:
            index = _render_navigator(interview.id, questions, answers)
            _render_question_workspace(
                interview, job, questions[index], answers.get(questions[index].id), index, len(questions)
            )

    st.divider()
    _render_evaluation(interview, job)


def _render_workspace(interview, job, candidate, app_status: str, score) -> None:
    with get_db_session() as session:
        questions = QuestionBankService(session).list_for_job(job.id)
        service = InterviewService(session)
        answers = service.answers_map(interview.id)
        history = service.history_for_candidate(candidate.id, exclude_id=interview.id)

    tab_main, tab_bank, tab_manage = st.tabs(["🎙️ المقابلة", "🗂️ بنك الأسئلة", "⚙️ الإدارة"])
    with tab_main:
        _render_interview_tab(interview, job, candidate, app_status, score, questions, answers, history)
    with tab_bank:
        _render_question_bank(job, candidate)
    with tab_manage:
        _render_manage_tab(interview, job, questions)


# ------------------------------------------------------------ الصفحة الرئيسية
def _render_next_step(interview) -> None:
    """الخطوة التالية بعد المقابلة (اقتراح فقط؛ القرار النهائي يسجّله المُقابِل بنفسه)."""
    if interview.status != "Completed":
        return
    with st.container(border=True):
        if interview.decision == "Continue":
            st.markdown("**✅ قرارك: الانتقال للمرحلة التالية**")
            st.button(
                "📨 إنشاء عرض", key=f"iv_offer_{interview.id}", type="primary",
                on_click=go_to, args=("offers",),
                kwargs={OPEN_CREATE_OFFER: True, OFFER_PREFILL_APP: interview.application_id},
            )
        elif interview.decision is None:
            hint = (
                "قيّم الإجابات واحسب الدرجة النهائية، ثم سجّل قرارك في قسم «التقييم النهائي» أسفل الصفحة."
                if interview.overall_score is None
                else "سجّل قرارك في قسم «التقييم النهائي» أسفل الصفحة."
            )
            st.info(f"💡 الخطوة التالية: {hint}")
        else:
            st.caption(f"القرار المسجّل: {_DECISION_LABELS.get(interview.decision, interview.decision)}")

def render() -> None:
    st.header("🗓️ المقابلات")
    _inject_css()
    _show_flash()

    jobs = _cached_jobs()
    if not jobs:
        components.empty_state(
            "💼", "لا توجد وظائف بعد", "أنشئ وظيفة أولاً، ثم اختر مرشحاً وحدّد موعد المقابلة.",
            [("➕ إنشاء وظيفة", "jobs", {OPEN_CREATE_JOB: True})], key="iv_empty_jobs",
        )
        return

    with st.container(border=True):
        col_job, col_candidate, col_interview = st.columns(3)

        with col_job:
            job_labels = {f"{j.title} (#{j.id})": j.id for j in jobs}
            if st.session_state.get("iv_job_select") not in job_labels:
                st.session_state.pop("iv_job_select", None)  # قيمة قادمة من صفحة أخرى لم تعد صالحة
            job_id = job_labels[st.selectbox("💼 الوظيفة", list(job_labels), key="iv_job_select")]

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
            with col_candidate:
                st.caption("لا يوجد مرشحون مطابَقون لهذه الوظيفة بعد.")
        else:
            with col_candidate:
                app_labels = {
                    (f"{c.full_name} · مطابقة {score}% · {status}" if score is not None else f"{c.full_name} · {status}"):
                    (app_id, c, status, score)
                    for app_id, c, status, score in app_rows
                }
                if st.session_state.get("iv_app_select") not in app_labels:
                    st.session_state.pop("iv_app_select", None)
                application_id, candidate, app_status, score = app_labels[
                    st.selectbox("👤 المرشح (مرتب حسب المطابقة)", list(app_labels), key="iv_app_select")
                ]

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
                return f"{iv.code or f'#{iv.id}'} · {iv.interview_type} · {_STATUS_LABELS.get(iv.status, iv.status)} · {when}"

            with col_interview:
                selected = st.selectbox(
                    "🗓️ المقابلة", [None] + list(by_id), index=1 if by_id else 0,
                    format_func=_label, key=select_key,
                )

    if not app_rows:
        components.empty_state(
            "🎯", "لا يوجد مرشحون لهذه الوظيفة بعد",
            "ابحث عن أفضل المرشحين للوظيفة أولاً، ثم اختر أحدهم لجدولة مقابلته. يمكنك تجهيز بنك الأسئلة الآن:",
            [("🎯 البحث عن مرشحين", "jobs", None)], key="iv_empty_apps",
        )
        _render_question_bank(job, None)
        return

    if selected is None:
        tab_new, tab_bank = st.tabs(["🗓️ جدولة مقابلة", "🗂️ بنك الأسئلة"])
        with tab_new:
            _render_new_interview(application_id, job)
        with tab_bank:
            _render_question_bank(job, candidate)
    else:
        _render_next_step(by_id[selected])
        _render_workspace(by_id[selected], job, candidate, app_status, score)