"""تصدير أسئلة وإجابات مقابلة مرشح واحد (بنك الوظيفة + الأسئلة الخاصة به) إلى Word أو PDF للطباعة."""

import io

from models.candidate import Candidate
from models.interview import Interview
from models.job import Job
from models.job_question import JobQuestion
from services.question_bank_service import QuestionBankService


def _merged_lines(interview: Interview, bank_questions: list[JobQuestion], answers_map: dict) -> list[dict]:
    """يجمع أسئلة بنك الوظيفة والأسئلة الخاصة بالمرشح في شكل موحّد واحد للتصدير."""
    lines: list[dict] = []
    for q in bank_questions:
        answer = answers_map.get(q.id)
        lines.append({
            "question": q.question,
            "category": QuestionBankService.category_label(q.category),
            "answer": answer.answer if answer else None,
            "score": answer.eval_score if answer else None,
        })
    for item in interview.custom_questions or []:
        lines.append({
            "question": item["question"],
            "category": QuestionBankService.category_label(item.get("category")),
            "answer": item.get("answer"),
            "score": item.get("eval_score"),
        })
    return lines


def build_docx(
    candidate: Candidate, job: Job, interview: Interview,
    bank_questions: list[JobQuestion], answers_map: dict,
) -> bytes:
    """يبني ملف Word بكل أسئلة وإجابات المقابلة، جاهزاً للطباعة أو المشاركة."""
    import docx

    document = docx.Document()
    document.add_heading(f"أسئلة مقابلة: {candidate.full_name}", level=1)
    document.add_paragraph(f"الوظيفة: {job.title}")
    if interview.scheduled_at:
        document.add_paragraph(f"موعد المقابلة: {interview.scheduled_at.strftime('%Y-%m-%d %H:%M')}")
    document.add_paragraph(f"نوع المقابلة: {interview.interview_type}")
    document.add_paragraph("")

    lines = _merged_lines(interview, bank_questions, answers_map)
    if not lines:
        document.add_paragraph("لا توجد أسئلة مضافة لهذه المقابلة بعد.")
    for idx, line in enumerate(lines, start=1):
        heading = f"{idx}. {line['question']}"
        if line["category"]:
            heading += f"  ({line['category']})"
        document.add_paragraph(heading)
        document.add_paragraph(f"الإجابة: {line['answer'] or '—'}")
        if line["score"] is not None:
            document.add_paragraph(f"التقييم: {line['score']}/5")
        document.add_paragraph("")

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def build_pdf(
    candidate: Candidate, job: Job, interview: Interview,
    bank_questions: list[JobQuestion], answers_map: dict,
) -> bytes:
    """يبني PDF بنفس المحتوى عبر PyMuPDF (يدعم العربية عبر insert_htmlbox)."""
    import pymupdf as fitz

    lines = _merged_lines(interview, bank_questions, answers_map)
    parts = [
        "<div style='direction:rtl; font-family:Arial; font-size:11pt;'>",
        f"<h2>أسئلة مقابلة: {candidate.full_name}</h2>",
        f"<p>الوظيفة: {job.title}</p>",
    ]
    if interview.scheduled_at:
        parts.append(f"<p>موعد المقابلة: {interview.scheduled_at.strftime('%Y-%m-%d %H:%M')}</p>")
    parts.append(f"<p>نوع المقابلة: {interview.interview_type}</p><hr/>")

    if not lines:
        parts.append("<p>لا توجد أسئلة مضافة لهذه المقابلة بعد.</p>")
    for idx, line in enumerate(lines, start=1):
        category = f" <i>({line['category']})</i>" if line["category"] else ""
        parts.append(f"<p><b>{idx}. {line['question']}</b>{category}</p>")
        parts.append(f"<p>الإجابة: {line['answer'] or '—'}</p>")
        if line["score"] is not None:
            parts.append(f"<p>التقييم: {line['score']}/5</p>")
    parts.append("</div>")

    document = fitz.open()
    page = document.new_page()
    rect = fitz.Rect(36, 36, page.rect.width - 36, page.rect.height - 36)
    page.insert_htmlbox(rect, "".join(parts))
    return document.tobytes()