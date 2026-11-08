import io
import re

import pandas as pd
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from models.candidate import Candidate
from models.job import Job
from services.candidate_service import analysis_for_language, localized_value


def _join(items: list | None) -> str:
    return ", ".join(str(i) for i in items or [])


def _education_text(items: list[dict] | None) -> str:
    lines = []
    for e in items or []:
        line = " — ".join(p for p in (e.get("degree"), e.get("major"), e.get("institution")) if p)
        if line:
            lines.append(line)
    return "; ".join(lines)


def _date_text(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else ""


_ORG_COLOR_HEADER_BG = "1F4E78"
_ORG_COLOR_SECTION_BG = "5B9BD5"
_ORG_COLOR_SUBTITLE_BG = "EAF2F8"
_ORG_COLOR_FIELD_BG = "F3F6F9"
_ORG_COLOR_TOTAL_BG = "EAF2F8"
_ORG_COLOR_LINK = "0563C1"
_ORG_COLOR_FIELD_TEXT = "1F1F1F"
_ORG_COLOR_WHITE = "FFFFFF"
_ORG_COLOR_TOTAL_TEXT = "1F4E78"

_ORG_INDEX_SHEET_NAME = {"ar": "الفهرس", "en": "Index"}
_ORG_FLAT_SHEET_NAME = "Candidates"
_ORG_EMPTY_DISPLAY = "—"
_ORG_MAX_SHEET_NAME_LEN = 31
_ORG_INVALID_SHEET_CHARS_RE = re.compile(r"[\[\]:*?/\\]")

_ORG_PHOTO_PX = 160
_ORG_PHOTO_FIRST_ROW = 5      # أول صف تغطيه الصورة (الصف 4 عنوان القسم الأول)
_ORG_PHOTO_LAST_ROW = 12      # آخر صف تغطيه الصورة؛ من بعده يُدمج B:C
_ORG_PHOTO_ROW_HEIGHT = 20    # بالنقاط
_ORG_COL_WIDTHS = {"A": 30, "B": 60, "C": 30}

_STATUS_AR = {
    "New": "جديد", "Screening": "الفرز", "Shortlisted": "القائمة المختصرة", "Interview": "المقابلة",
    "Offer": "العرض", "Hired": "التعيين", "Rejected": "مرفوض",
}
_DECISION_AR = {
    "Continue": "الانتقال للمرحلة التالية", "Additional": "مقابلة إضافية",
    "Hold": "تعليق", "Not Selected": "غير مختار",
}
_IV_STATUS_AR = {"Scheduled": "مجدولة", "In Progress": "جارية", "Completed": "مكتملة", "Cancelled": "ملغاة"}

_T = {
    "ar": {
        "index_title": "فهرس المرشحين", "index_sub": "اضغط على اسم المرشح للانتقال إلى صفحة بياناته",
        "total": "إجمالي المرشحين: {n}", "code": "الكود", "name": "اسم المرشح", "position": "الوظيفة الحالية",
        "back": "← العودة إلى الفهرس", "profile": "ملف المرشح — {name}", "none": "لا توجد مقابلات",
        "interviews": "المقابلات والتقييم", "q": "س{n}", "overall_ai": "تقييم الذكاء الاصطناعي",
        "manual": "تقييم المُقابِل", "effective": "الدرجة الفعلية", "feedback": "ملاحظات التحليل",
        "inotes": "ملاحظات المُقابِل", "answer": "الإجابة",
    },
    "en": {
        "index_title": "Candidates Index", "index_sub": "Click a candidate name to open the profile page",
        "total": "Total candidates: {n}", "code": "Code", "name": "Candidate", "position": "Current position",
        "back": "← Back to index", "profile": "Candidate profile — {name}", "none": "No interviews",
        "interviews": "Interviews & evaluation", "q": "Q{n}", "overall_ai": "AI score",
        "manual": "Interviewer score", "effective": "Effective score", "feedback": "Analysis feedback",
        "inotes": "Interviewer notes", "answer": "Answer",
    },
}

_IV_FIELDS = [  # (مفتاح، عربي، إنجليزي)
    ("interviewer", "المُقابِل", "Interviewer"), ("status", "الحالة", "Status"),
    ("overall", "الدرجة النهائية (من 100)", "Overall score (/100)"), ("decision", "القرار", "Decision"),
    ("overall_notes", "ملاحظات التقييم النهائي", "Final evaluation notes"),
    ("notes", "ملاحظات المُقابِل", "Interviewer notes"),
]

_FLAT_AR_HEADERS = [
    "الكود", "الاسم الكامل", "البريد", "الهاتف", "العمر", "لينكدإن", "الموقع", "الوظيفة الحالية",
    "الوظيفة المتقدم لها", "الحالة", "التقييم", "الخبرة (سنوات)", "الراتب المتوقع", "فترة الإخطار (أيام)",
    "الحالة الاجتماعية", "موقف التجنيد", "اللغات", "التعليم", "المهارات الفنية", "مهارات الحاسب",
    "المهارات الإدارية", "المهارات الشخصية", "مهارات أخرى", "الوظائف السابقة", "القطاعات",
    "الشركات السابقة", "الملخص", "ملاحظات المسؤول", "ملف المصدر", "تاريخ الإضافة",
]


def _v(c: Candidate, attr: str, lang: str | None):
    return localized_value(c, attr, lang) if lang else getattr(c, attr)


def _bullets(items) -> str:
    return "\n".join(f"• {i}" for i in items or [])


def _analysis(c: Candidate, lang: str) -> dict:
    return analysis_for_language(c, lang)


_ORG_PROFILE_SECTIONS = [
    (("البيانات الأساسية", "Basic information"), [
        ("الكود", "Code", lambda c, l: c.candidate_code),
        ("الاسم الكامل", "Full name", lambda c, l: _v(c, "full_name", l)),
        ("البريد الإلكتروني", "Email", lambda c, l: c.email),
        ("الهاتف", "Phone", lambda c, l: c.phone),
        ("العمر", "Age", lambda c, l: c.age),
        ("لينكدإن", "LinkedIn", lambda c, l: c.linkedin_url),
        ("محل الإقامة", "Location", lambda c, l: _v(c, "location", l)),
        ("الوظيفة الحالية", "Current position", lambda c, l: _v(c, "current_position", l)),
        ("الوظيفة المتقدم لها", "Applied job", lambda c, l: c.applied_job),
        ("الحالة", "Status", lambda c, l: _STATUS_AR.get(c.status, c.status) if l == "ar" else c.status),
        ("التقييم", "Rating", lambda c, l: c.rating),
        ("سنوات الخبرة", "Experience (years)", lambda c, l: c.total_experience_years),
        ("الراتب المتوقع", "Expected salary", lambda c, l: c.expected_salary),
        ("فترة الإخطار (بالأيام)", "Notice period (days)", lambda c, l: c.notice_period_days),
        ("الحالة الاجتماعية", "Marital status", lambda c, l: _v(c, "marital_status", l)),
        ("الموقف من التجنيد", "Military status", lambda c, l: _v(c, "military_status", l)),
    ]),
    (("التعليم والمهارات", "Education & skills"), [
        ("اللغات", "Languages", lambda c, l: _join(_v(c, "languages", l))),
        ("المؤهل العلمي", "Education", lambda c, l: _education_text(_v(c, "education", l))),
        ("المهارات الفنية", "Technical skills", lambda c, l: _join(_v(c, "technical_skills", l))),
        ("مهارات الحاسب", "Computer skills", lambda c, l: _join(_v(c, "computer_skills", l))),
        ("المهارات الإدارية", "Managerial skills", lambda c, l: _join(_v(c, "managerial_skills", l))),
        ("المهارات الشخصية", "Soft skills", lambda c, l: _join(_v(c, "soft_skills", l))),
        ("مهارات أخرى", "Other skills", lambda c, l: _join(_v(c, "skills", l))),
    ]),
    (("الخبرات السابقة", "Experience"), [
        ("الوظائف السابقة", "Previous positions", lambda c, l: _join(_v(c, "previous_positions", l))),
        ("القطاعات / الصناعات", "Industries", lambda c, l: _join(_v(c, "industries", l))),
        ("الشركات السابقة", "Previous companies", lambda c, l: _join(c.previous_companies)),
        ("الملخص المهني", "Summary", lambda c, l: _v(c, "summary", l)),
    ]),
    (("تحليل الذكاء الاصطناعي", "AI analysis"), [
        ("المستوى الوظيفي", "Career level", lambda c, l: _analysis(c, l).get("career_level")),
        ("نقاط القوة", "Strengths", lambda c, l: _bullets(_analysis(c, l).get("strengths"))),
        ("فجوات محتملة", "Potential gaps", lambda c, l: _bullets(_analysis(c, l).get("potential_gaps"))),
        ("الوظائف المناسبة", "Suitable functions", lambda c, l: _join(_analysis(c, l).get("suitable_functions"))),
    ]),
    (("التوظيف والملاحظات", "Recruitment & notes"), [
        ("ملاحظات مسؤول التوظيف", "Recruiter notes", lambda c, l: c.recruiter_notes),
        ("ملف المصدر", "Source file", lambda c, l: c.source_filename),
        ("تاريخ الإضافة", "Added on", lambda c, l: _date_text(c.created_at)),
    ]),
]


def _org_display_value(value):
    if isinstance(value, bool):
        return _ORG_EMPTY_DISPLAY
    if isinstance(value, (int, float)):
        return value
    text = value.strip() if isinstance(value, str) else value
    return text if text else _ORG_EMPTY_DISPLAY


def _org_is_formula_injection_risk(value) -> bool:
    return isinstance(value, str) and value.startswith(("=", "+", "-", "@"))


def _org_safe_text_cell(cell, value) -> None:
    cell.value = value
    if _org_is_formula_injection_risk(value):
        cell.data_type = "s"  # نص صريح: لا يُفسَّر كمعادلة


def _org_sanitize_sheet_name(raw_name: str, used_names: set[str], reserved: set[str]) -> str:
    cleaned = _ORG_INVALID_SHEET_CHARS_RE.sub("-", raw_name or "").strip() or "Candidate"
    cleaned = cleaned[:_ORG_MAX_SHEET_NAME_LEN]
    name, suffix = cleaned, 2
    while name in used_names or name in reserved:
        tail = f"_{suffix}"
        name = cleaned[: _ORG_MAX_SHEET_NAME_LEN - len(tail)] + tail
        suffix += 1
    used_names.add(name)
    return name


def _org_escape_sheet_name_for_formula(sheet_name: str) -> str:
    return sheet_name.replace("'", "''")


def _org_escape_display_text_for_formula(text: str) -> str:
    return (text or "").replace('"', '""')


def _org_set_column_widths(sheet, widths: dict[str, int]) -> None:
    for column_letter, width in widths.items():
        sheet.column_dimensions[column_letter].width = width


def _org_value_last_col(row: int) -> int:
    """آخر عمود تمتد عليه القيمة: B فقط جوار الصورة، ثم B:C بعدها."""
    return 2 if row <= _ORG_PHOTO_LAST_ROW else 3


def _org_draw_section_header(sheet, row: int, title: str, rtl: bool) -> None:
    sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
    cell = sheet.cell(row=row, column=1, value=title)
    cell.font = Font(name="Calibri", bold=True, color=_ORG_COLOR_WHITE)
    cell.fill = PatternFill("solid", fgColor=_ORG_COLOR_SECTION_BG)
    cell.alignment = Alignment(horizontal="right" if rtl else "left", vertical="center", wrap_text=True)


def _org_draw_field_row(sheet, row: int, label: str, value) -> None:
    label_cell = sheet.cell(row=row, column=1, value=label)
    label_cell.font = Font(name="Calibri", bold=True, color=_ORG_COLOR_FIELD_TEXT)
    label_cell.fill = PatternFill("solid", fgColor=_ORG_COLOR_FIELD_BG)
    label_cell.alignment = Alignment(vertical="top", wrap_text=True)

    value_cell = sheet.cell(row=row, column=2)
    _org_safe_text_cell(value_cell, _org_display_value(value))
    value_cell.alignment = Alignment(vertical="top", wrap_text=True)
    if _org_value_last_col(row) == 3:
        sheet.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)


def _org_add_photo(sheet, photo_path) -> None:
    if not photo_path:
        return
    try:
        from PIL import Image

        with Image.open(photo_path) as source:
            image = source.convert("RGB")
        image.thumbnail((_ORG_PHOTO_PX, _ORG_PHOTO_PX))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        sheet.add_image(XLImage(buffer), f"C{_ORG_PHOTO_FIRST_ROW}")
    except Exception:  # noqa: BLE001 - صورة تالفة لا توقف التصدير
        pass


def _score_text(value, scale: str = "/5") -> str:
    return f"{value}{scale}" if value else "-"


def _answer_text(a: dict, t: dict) -> str:
    lines = [a["answer"] or "-"]
    lines.append(
        f"{t['overall_ai']}: {_score_text(a['ai_score'])} | {t['manual']}: {_score_text(a['manual_score'])} | "
        f"{t['effective']}: {_score_text(a['eval_score'])}"
    )
    if a["feedback"]:
        lines.append(f"{t['feedback']}: {a['feedback']}")
    if a["notes"]:
        lines.append(f"{t['inotes']}: {a['notes']}")
    return "\n".join(lines)


def _org_draw_interviews(sheet, row: int, interviews: list[dict], lang: str) -> int:
    i, t, rtl = (0 if lang == "ar" else 1), _T[lang], lang == "ar"
    _org_draw_section_header(sheet, row, t["interviews"], rtl)
    row += 1
    if not interviews:
        _org_draw_field_row(sheet, row, "—", t["none"])
        return row + 1
    for iv in interviews:
        head = f"{iv['code']} · {iv['type']} · {iv['job']} · {iv['when']}"
        _org_draw_section_header(sheet, row, head, rtl)
        row += 1
        values = {
            **iv,
            "status": _IV_STATUS_AR.get(iv["status"], iv["status"]) if rtl else iv["status"],
            "decision": _DECISION_AR.get(iv["decision"], iv["decision"]) if rtl else iv["decision"],
        }
        for key, ar, en in _IV_FIELDS:
            _org_draw_field_row(sheet, row, (ar, en)[i], values.get(key))
            row += 1
        for n, a in enumerate(iv["answers"], start=1):
            _org_draw_field_row(sheet, row, f"{t['q'].format(n=n)}: {a['question']}", _answer_text(a, t))
            row += 1
    return row


def _org_build_candidate_sheet(
    workbook: Workbook, candidate: Candidate, sheet_name: str, lang: str, photo, interviews: list[dict],
) -> None:
    i, t, rtl = (0 if lang == "ar" else 1), _T[lang], lang == "ar"
    sheet = workbook.create_sheet(sheet_name)
    _org_set_column_widths(sheet, _ORG_COL_WIDTHS)
    sheet.sheet_view.rightToLeft = rtl

    # الصف 1: العنوان (A:C)
    sheet.merge_cells("A1:C1")
    name = _v(candidate, "full_name", lang) or candidate.full_name
    title = sheet.cell(row=1, column=1, value=t["profile"].format(name=name))
    title.font = Font(name="Calibri", size=16, bold=True, color=_ORG_COLOR_WHITE)
    title.fill = PatternFill("solid", fgColor=_ORG_COLOR_HEADER_BG)
    title.alignment = Alignment(horizontal="center", vertical="center")
    sheet.row_dimensions[1].height = 26

    # الصف 2: رابط العودة (A:C)
    sheet.merge_cells("A2:C2")
    index_ref = _org_escape_sheet_name_for_formula(_ORG_INDEX_SHEET_NAME[lang])
    back = sheet.cell(row=2, column=1, value=f"=HYPERLINK(\"#'{index_ref}'!A1\",\"{t['back']}\")")
    back.font = Font(name="Calibri", bold=True, color=_ORG_COLOR_LINK)
    back.fill = PatternFill("solid", fgColor=_ORG_COLOR_SUBTITLE_BG)
    back.alignment = Alignment(horizontal="center", vertical="center")

    # الصف 3 فارغ، والمحتوى يبدأ من الصف 4
    row = 4
    for titles, fields in _ORG_PROFILE_SECTIONS:
        _org_draw_section_header(sheet, row, titles[i], rtl)
        row += 1
        for ar, en, getter in fields:
            _org_draw_field_row(sheet, row, (ar, en)[i], getter(candidate, lang))
            row += 1

    _org_draw_interviews(sheet, row, interviews, lang)

    if photo:
        for r in range(_ORG_PHOTO_FIRST_ROW, _ORG_PHOTO_LAST_ROW + 1):
            sheet.row_dimensions[r].height = _ORG_PHOTO_ROW_HEIGHT
        _org_add_photo(sheet, photo)


def _org_build_index_sheet(workbook: Workbook, entries: list[tuple[str, Candidate]], lang: str) -> None:
    t, rtl = _T[lang], lang == "ar"
    sheet = workbook.create_sheet(_ORG_INDEX_SHEET_NAME[lang], 0)
    sheet.sheet_view.rightToLeft = rtl
    _org_set_column_widths(sheet, {"A": 20, "B": 34, "C": 42})

    banner = [
        (t["index_title"], 18, True, _ORG_COLOR_HEADER_BG, _ORG_COLOR_WHITE),
        (t["index_sub"], 11, False, _ORG_COLOR_SUBTITLE_BG, _ORG_COLOR_FIELD_TEXT),
        (t["total"].format(n=len(entries)), 11, True, _ORG_COLOR_TOTAL_BG, _ORG_COLOR_TOTAL_TEXT),
    ]
    for row, (text, size, bold, fill, color) in enumerate(banner, start=1):
        sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
        cell = sheet.cell(row=row, column=1, value=text)
        cell.font = Font(name="Calibri", size=size, bold=bold, color=color)
        cell.fill = PatternFill("solid", fgColor=fill)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for col_index, header in enumerate([t["code"], t["name"], t["position"]], start=1):
        cell = sheet.cell(row=4, column=col_index, value=header)
        cell.font = Font(name="Calibri", bold=True, color=_ORG_COLOR_WHITE)
        cell.fill = PatternFill("solid", fgColor=_ORG_COLOR_SECTION_BG)
        cell.alignment = Alignment(horizontal="center", vertical="center")

    row = 5
    for sheet_name, candidate in entries:
        code = sheet.cell(row=row, column=1, value=candidate.candidate_code or _ORG_EMPTY_DISPLAY)
        code.alignment = Alignment(horizontal="center", vertical="center")
        ref = _org_escape_sheet_name_for_formula(sheet_name)
        display = _org_escape_display_text_for_formula(_v(candidate, "full_name", lang) or candidate.full_name)
        name_cell = sheet.cell(row=row, column=2, value=f"=HYPERLINK(\"#'{ref}'!A1\",\"{display}\")")
        name_cell.font = Font(name="Calibri", bold=True, color=_ORG_COLOR_LINK)
        name_cell.alignment = Alignment(vertical="center", wrap_text=True)
        position = sheet.cell(
            row=row, column=3, value=_v(candidate, "current_position", lang) or _ORG_EMPTY_DISPLAY
        )
        position.alignment = Alignment(vertical="center", wrap_text=True)
        row += 1
    sheet.freeze_panes = "A5"


def _org_write_flat_sheet(sheet, candidates: list[Candidate], lang: str = "ar") -> None:
    df = ExportService.candidates_to_dataframe(candidates, lang)
    sheet.sheet_view.rightToLeft = lang == "ar"
    sheet.append(list(df.columns))
    for _, row_values in df.iterrows():
        row_index = sheet.max_row + 1
        for col_index, value in enumerate(row_values, start=1):
            _org_safe_text_cell(sheet.cell(row=row_index, column=col_index), value)
    for cell in sheet[1]:
        cell.font = Font(name="Calibri", bold=True, color=_ORG_COLOR_WHITE)
        cell.fill = PatternFill("solid", fgColor=_ORG_COLOR_SECTION_BG)
    sheet.freeze_panes = "A2"
    for column_cells in sheet.columns:
        longest = max((len(str(cell.value or "")) for cell in column_cells), default=10)
        sheet.column_dimensions[get_column_letter(column_cells[0].column)].width = min(max(longest + 2, 10), 50)


class ExportService:

    @staticmethod
    def candidates_to_dataframe(candidates: list[Candidate], lang: str | None = None) -> pd.DataFrame:
        rows = [
            {
                "Code": c.candidate_code,
                "Full Name": _v(c, "full_name", lang),
                "Email": c.email,
                "Phone": c.phone,
                "Age": c.age,
                "LinkedIn": c.linkedin_url,
                "Location": _v(c, "location", lang),
                "Current Position": _v(c, "current_position", lang),
                "Applied Job": c.applied_job,
                "Status": (_STATUS_AR.get(c.status, c.status) if lang == "ar" else c.status),
                "Rating": c.rating,
                "Experience (Years)": c.total_experience_years,
                "Expected Salary": c.expected_salary,
                "Notice Period (Days)": c.notice_period_days,
                "Marital Status": _v(c, "marital_status", lang),
                "Military Status": _v(c, "military_status", lang),
                "Languages": _join(_v(c, "languages", lang)),
                "Education": _education_text(_v(c, "education", lang)),
                "Technical Skills": _join(_v(c, "technical_skills", lang)),
                "Computer Skills": _join(_v(c, "computer_skills", lang)),
                "Managerial Skills": _join(_v(c, "managerial_skills", lang)),
                "Soft Skills": _join(_v(c, "soft_skills", lang)),
                "Other Skills": _join(_v(c, "skills", lang)),
                "Previous Positions": _join(_v(c, "previous_positions", lang)),
                "Industries": _join(_v(c, "industries", lang)),
                "Previous Companies": _join(c.previous_companies),
                "Summary": _v(c, "summary", lang),
                "Recruiter Notes": c.recruiter_notes,
                "Source File": c.source_filename,
                "Created At": _date_text(c.created_at),
            }
            for c in candidates
        ]
        df = pd.DataFrame(rows)
        if lang == "ar" and len(df.columns) == len(_FLAT_AR_HEADERS):
            df.columns = _FLAT_AR_HEADERS
        return df

    @staticmethod
    def jobs_to_dataframe(jobs: list[Job]) -> pd.DataFrame:
        rows = [
            {
                "ID": j.id,
                "Title": j.title,
                "Department": j.department,
                "Location": j.location,
                "Employment Type": j.employment_type,
                "Career Level": j.career_level,
                "Reports To": j.reports_to,
                "Education": j.education,
                "Required Experience (Years)": j.required_experience_years,
                "Salary Min": j.salary_min,
                "Salary Max": j.salary_max,
                "Vacancies": j.vacancies,
                "Status": j.status,
                "Technical Skills": _join(j.required_technical_skills),
                "Computer Skills": _join(j.required_computer_skills),
                "Managerial Skills": _join(j.required_managerial_skills),
                "Soft Skills": _join(j.required_soft_skills),
                "Other Skills": _join(j.required_skills),
                "Preferred Industries": _join(j.preferred_industries),
                "Description": j.description,
                "Created At": _date_text(j.created_at),
                "Updated At": _date_text(j.updated_at),
            }
            for j in jobs
        ]
        return pd.DataFrame(rows)

    @staticmethod
    def to_csv_bytes(df: pd.DataFrame) -> bytes:
        return df.to_csv(index=False).encode("utf-8-sig")

    @staticmethod
    def to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Data") -> bytes:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name)
            sheet = writer.sheets[sheet_name]
            sheet.freeze_panes = "A2"
            for column_cells in sheet.columns:
                longest = max((len(str(cell.value or "")) for cell in column_cells), default=10)
                sheet.column_dimensions[column_cells[0].column_letter].width = min(max(longest + 2, 10), 50)
        return buffer.getvalue()

    @staticmethod
    def candidates_to_organized_workbook_bytes(
        candidates: list[Candidate],
        include_flat_sheet: bool = True,
        lang: str = "ar",
        photos: dict | None = None,
        interviews: dict[int, list[dict]] | None = None,
    ) -> bytes:
        lang = lang if lang in _T else "ar"
        photos, interviews = photos or {}, interviews or {}
        reserved = {_ORG_INDEX_SHEET_NAME[lang], _ORG_FLAT_SHEET_NAME}

        workbook = Workbook()
        workbook.remove(workbook.active)
        if include_flat_sheet:
            _org_write_flat_sheet(workbook.create_sheet(_ORG_FLAT_SHEET_NAME), candidates, lang)

        used: set[str] = set()
        entries: list[tuple[str, Candidate]] = []
        for candidate in candidates:
            base = candidate.candidate_code or f"ID-{candidate.id}"
            entries.append((_org_sanitize_sheet_name(base, used, reserved), candidate))

        _org_build_index_sheet(workbook, entries, lang)
        for sheet_name, candidate in entries:
            _org_build_candidate_sheet(
                workbook, candidate, sheet_name, lang,
                photos.get(candidate.id), interviews.get(candidate.id, []),
            )

        order = ([_ORG_FLAT_SHEET_NAME] if include_flat_sheet else []) + [_ORG_INDEX_SHEET_NAME[lang]] + [
            name for name, _ in entries
        ]
        workbook._sheets = [workbook[name] for name in order]  # noqa: SLF001 - إعادة ترتيب مقصودة

        buffer = io.BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()