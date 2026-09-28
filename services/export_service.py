"""خدمة التصدير: تحويل المرشحين والوظائف إلى ملفات CSV / Excel (مسطح) / Excel منظّم (فهرس + صفحة لكل مرشح)."""

import io
import re

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from models.candidate import Candidate
from models.job import Job


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
    # نحوّل التاريخ لنص لأن openpyxl لا يقبل datetime يحمل timezone
    return value.strftime("%Y-%m-%d %H:%M") if value else ""


# ==================================================================================
# تصدير Excel منظّم (فهرس + صفحة مستقلة لكل مرشح) - ثوابت التصميم (بلا أرقام سحرية)
# ==================================================================================

_ORG_COLOR_HEADER_BG = "1F4E78"     # خلفية عناوين الصفحات الرئيسية (فهرس / ترويسة صفحة المرشح)
_ORG_COLOR_SECTION_BG = "5B9BD5"    # خلفية رأس القسم ورأس جدول الفهرس
_ORG_COLOR_SUBTITLE_BG = "EAF2F8"   # خلفية السطر التوضيحي وسطر «العودة إلى الفهرس»
_ORG_COLOR_FIELD_BG = "F3F6F9"      # خلفية خلية اسم الحقل
_ORG_COLOR_TOTAL_BG = "EAF2F8"      # خلفية سطر «إجمالي المرشحين»
_ORG_COLOR_LINK = "0563C1"          # لون روابط HYPERLINK
_ORG_COLOR_FIELD_TEXT = "1F1F1F"    # لون نص اسم الحقل والسطر التوضيحي
_ORG_COLOR_WHITE = "FFFFFF"
_ORG_COLOR_TOTAL_TEXT = "1F4E78"

_ORG_INDEX_SHEET_NAME = "الفهرس"
_ORG_FLAT_SHEET_NAME = "Candidates"
_ORG_RESERVED_SHEET_NAMES = {_ORG_INDEX_SHEET_NAME, _ORG_FLAT_SHEET_NAME}
_ORG_EMPTY_DISPLAY = "—"
_ORG_MAX_SHEET_NAME_LEN = 31
_ORG_INVALID_SHEET_CHARS_RE = re.compile(r"[\[\]:*?/\\]")

_ORG_INDEX_COL_WIDTHS = {"A": 20, "B": 34, "C": 42}
_ORG_PROFILE_COL_WIDTHS = {"A": 28, "B": 78}
_ORG_PROFILE_TITLE_ROW_HEIGHT = 26

# تعريف الأقسام والحقول مرة واحدة: (عنوان القسم، [(التسمية العربية، دالة استخراج القيمة من Candidate)]).
# إضافة حقل جديد لصفحة المرشح المنظّمة = سطر واحد هنا فقط.
_ORG_PROFILE_SECTIONS: list[tuple[str, list[tuple[str, "callable"]]]] = [
    (
        "البيانات الأساسية",
        [
            ("الكود", lambda c: c.candidate_code),
            ("الاسم الكامل", lambda c: c.full_name),
            ("البريد الإلكتروني", lambda c: c.email),
            ("الهاتف", lambda c: c.phone),
            ("العمر", lambda c: c.age),
            ("لينكدإن", lambda c: c.linkedin_url),
            ("محل الإقامة", lambda c: c.location),
            ("الوظيفة الحالية", lambda c: c.current_position),
            ("الوظيفة المتقدم لها", lambda c: c.applied_job),
            ("الحالة", lambda c: c.status),
            ("التقييم", lambda c: c.rating),
            ("سنوات الخبرة", lambda c: c.total_experience_years),
            ("الراتب المتوقع", lambda c: c.expected_salary),
            ("فترة الإخطار (بالأيام)", lambda c: c.notice_period_days),
            ("الحالة الاجتماعية", lambda c: c.marital_status),
            ("الموقف من التجنيد", lambda c: c.military_status),
        ],
    ),
    (
        "التعليم والمهارات",
        [
            ("اللغات", lambda c: _join(c.languages)),
            ("المؤهل العلمي", lambda c: _education_text(c.education)),
            ("المهارات الفنية", lambda c: _join(c.technical_skills)),
            ("مهارات الحاسب", lambda c: _join(c.computer_skills)),
            ("المهارات الإدارية", lambda c: _join(c.managerial_skills)),
            ("المهارات الشخصية", lambda c: _join(c.soft_skills)),
            ("مهارات أخرى", lambda c: _join(c.skills)),
        ],
    ),
    (
        "الخبرات السابقة",
        [
            ("الوظائف السابقة", lambda c: _join(c.previous_positions)),
            ("القطاعات / الصناعات", lambda c: _join(c.industries)),
            ("الشركات السابقة", lambda c: _join(c.previous_companies)),
            ("الملخص المهني", lambda c: c.summary),
        ],
    ),
    (
        "التوظيف والملاحظات",
        [
            ("ملاحظات مسؤول التوظيف", lambda c: c.recruiter_notes),
            ("ملف المصدر", lambda c: c.source_filename),
            ("تاريخ الإضافة", lambda c: _date_text(c.created_at)),
        ],
    ),
]


def _org_display_value(value):
    """يحوّل قيمة الحقل إلى ما يُكتب في الخلية: الأرقام تبقى أرقاماً، والباقي نص أو "—" إن كان فارغاً."""
    if isinstance(value, bool):
        return _ORG_EMPTY_DISPLAY
    if isinstance(value, (int, float)):
        return value
    text = value.strip() if isinstance(value, str) else value
    return text if text else _ORG_EMPTY_DISPLAY


def _org_is_formula_injection_risk(value) -> bool:
    """نص قد يُفسَّر كصيغة في Excel إن فُتح مباشرة (يبدأ بـ = أو + أو - أو @)."""
    return isinstance(value, str) and value.startswith(("=", "+", "-", "@"))


def _org_safe_text_cell(cell, value) -> None:
    """يكتب قيمة في خلية مع تحييد أي حقن صيغ (اسم/مسمى/ملخص... قادم من السيرة الذاتية)."""
    if _org_is_formula_injection_risk(value):
        cell.value = "'" + value
        cell.data_type = "s"
    else:
        cell.value = value


def _org_sanitize_sheet_name(raw_name: str, used_names: set[str]) -> str:
    """يبني اسم صفحة صالحاً (≤31 حرفاً، بلا رموز محظورة)، ويضيف لاحقة رقمية عند التكرار."""
    cleaned = _ORG_INVALID_SHEET_CHARS_RE.sub("-", raw_name or "").strip() or "Candidate"
    cleaned = cleaned[:_ORG_MAX_SHEET_NAME_LEN]

    name = cleaned
    suffix = 2
    while name in used_names or name in _ORG_RESERVED_SHEET_NAMES:
        tail = f"_{suffix}"
        name = cleaned[: _ORG_MAX_SHEET_NAME_LEN - len(tail)] + tail
        suffix += 1
    used_names.add(name)
    return name


def _org_escape_sheet_name_for_formula(sheet_name: str) -> str:
    """يضاعف علامة ' داخل اسم الصفحة قبل استخدامه داخل صيغة HYPERLINK."""
    return sheet_name.replace("'", "''")


def _org_escape_display_text_for_formula(text: str) -> str:
    """يضاعف علامة \" داخل النص المعروض قبل وضعه داخل وسيطة نصية لصيغة HYPERLINK."""
    return (text or "").replace('"', '""')


def _org_set_column_widths(sheet, widths: dict[str, int]) -> None:
    for column_letter, width in widths.items():
        sheet.column_dimensions[column_letter].width = width


def _org_draw_section_header(sheet, row: int, title: str) -> None:
    """رأس قسم: خلية مدمجة A:B، خط أبيض عريض، خلفية زرقاء، محاذاة يمين مع wrap."""
    sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
    cell = sheet.cell(row=row, column=1, value=title)
    cell.font = Font(name="Calibri", bold=True, color=_ORG_COLOR_WHITE)
    cell.fill = PatternFill("solid", fgColor=_ORG_COLOR_SECTION_BG)
    cell.alignment = Alignment(horizontal="right", vertical="center", wrap_text=True)


def _org_draw_field_row(sheet, row: int, label: str, value) -> None:
    """صف (الحقل | القيمة): خلية الحقل بخلفية فاتحة وخط عريض، وخلية القيمة بمحاذاة أعلى مع wrap."""
    label_cell = sheet.cell(row=row, column=1, value=label)
    label_cell.font = Font(name="Calibri", bold=True, color=_ORG_COLOR_FIELD_TEXT)
    label_cell.fill = PatternFill("solid", fgColor=_ORG_COLOR_FIELD_BG)
    label_cell.alignment = Alignment(vertical="top", wrap_text=True)

    value_cell = sheet.cell(row=row, column=2)
    _org_safe_text_cell(value_cell, _org_display_value(value))
    value_cell.alignment = Alignment(vertical="top", wrap_text=True)


def _org_build_candidate_sheet(workbook: Workbook, candidate: Candidate, sheet_name: str) -> None:
    sheet = workbook.create_sheet(sheet_name)
    _org_set_column_widths(sheet, _ORG_PROFILE_COL_WIDTHS)
    sheet.sheet_view.showGridLines = True

    sheet.merge_cells("A1:B1")
    title_cell = sheet.cell(row=1, column=1, value=f"ملف المرشح — {candidate.full_name}")
    title_cell.font = Font(name="Calibri", size=16, bold=True, color=_ORG_COLOR_WHITE)
    title_cell.fill = PatternFill("solid", fgColor=_ORG_COLOR_HEADER_BG)
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    sheet.row_dimensions[1].height = _ORG_PROFILE_TITLE_ROW_HEIGHT

    sheet.merge_cells("A2:B2")
    index_ref = _org_escape_sheet_name_for_formula(_ORG_INDEX_SHEET_NAME)
    back_cell = sheet.cell(row=2, column=1, value=f"=HYPERLINK(\"#'{index_ref}'!A1\",\"← العودة إلى الفهرس\")")
    back_cell.font = Font(name="Calibri", bold=True, color=_ORG_COLOR_LINK)
    back_cell.fill = PatternFill("solid", fgColor=_ORG_COLOR_SUBTITLE_BG)
    back_cell.alignment = Alignment(horizontal="center", vertical="center")

    row = 4
    for section_title, fields in _ORG_PROFILE_SECTIONS:
        _org_draw_section_header(sheet, row, section_title)
        row += 1
        for label, getter in fields:
            _org_draw_field_row(sheet, row, label, getter(candidate))
            row += 1


def _org_build_index_sheet(workbook: Workbook, entries: list[tuple[str, Candidate]]) -> None:
    """entries: [(اسم صفحة المرشح، Candidate)] بنفس ترتيب إنشاء صفحات المرشحين."""
    sheet = workbook.create_sheet(_ORG_INDEX_SHEET_NAME, 0)  # في المقدمة مؤقتاً؛ يُعاد الترتيب النهائي لاحقاً
    _org_set_column_widths(sheet, _ORG_INDEX_COL_WIDTHS)

    sheet.merge_cells("A1:C1")
    title_cell = sheet.cell(row=1, column=1, value="فهرس المرشحين")
    title_cell.font = Font(name="Calibri", size=18, bold=True, color=_ORG_COLOR_WHITE)
    title_cell.fill = PatternFill("solid", fgColor=_ORG_COLOR_HEADER_BG)
    title_cell.alignment = Alignment(horizontal="center", vertical="center")

    sheet.merge_cells("A2:C2")
    subtitle_cell = sheet.cell(row=2, column=1, value="اضغط على اسم المرشح للانتقال مباشرة إلى صفحة بياناته المنظمة")
    subtitle_cell.font = Font(name="Calibri", color=_ORG_COLOR_FIELD_TEXT)
    subtitle_cell.fill = PatternFill("solid", fgColor=_ORG_COLOR_SUBTITLE_BG)
    subtitle_cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    sheet.merge_cells("A3:C3")
    total_cell = sheet.cell(row=3, column=1, value=f"إجمالي المرشحين: {len(entries)}")
    total_cell.font = Font(name="Calibri", bold=True, color=_ORG_COLOR_TOTAL_TEXT)
    total_cell.fill = PatternFill("solid", fgColor=_ORG_COLOR_TOTAL_BG)
    total_cell.alignment = Alignment(horizontal="center")

    headers = ["الكود", "اسم المرشح", "الوظيفة الحالية"]
    for col_index, header in enumerate(headers, start=1):
        cell = sheet.cell(row=4, column=col_index, value=header)
        cell.font = Font(name="Calibri", bold=True, color=_ORG_COLOR_WHITE)
        cell.fill = PatternFill("solid", fgColor=_ORG_COLOR_SECTION_BG)
        cell.alignment = Alignment(horizontal="center", vertical="center")

    row = 5
    for sheet_name, candidate in entries:
        code_cell = sheet.cell(row=row, column=1, value=candidate.candidate_code or _ORG_EMPTY_DISPLAY)
        code_cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        sheet_ref = _org_escape_sheet_name_for_formula(sheet_name)
        display_name = _org_escape_display_text_for_formula(candidate.full_name)
        name_cell = sheet.cell(row=row, column=2, value=f"=HYPERLINK(\"#'{sheet_ref}'!A1\",\"{display_name}\")")
        name_cell.font = Font(name="Calibri", bold=True, color=_ORG_COLOR_LINK)
        name_cell.alignment = Alignment(vertical="center", wrap_text=True)

        position_cell = sheet.cell(row=row, column=3, value=candidate.current_position or _ORG_EMPTY_DISPLAY)
        position_cell.alignment = Alignment(horizontal="right", vertical="center", wrap_text=True)

        row += 1

    sheet.freeze_panes = "A5"


def _org_write_flat_sheet(sheet, candidates: list[Candidate]) -> None:
    """يعيد استخدام نفس أعمدة candidates_to_dataframe، لكن يكتبها مباشرة عبر openpyxl
    مع تحييد أي نص قد يُفسَّر كصيغة (بيانات قادمة من سيرة ذاتية حرة النص)."""
    df = ExportService.candidates_to_dataframe(candidates)
    sheet.append(list(df.columns))
    for _, row_values in df.iterrows():
        row_index = sheet.max_row + 1
        for col_index, value in enumerate(row_values, start=1):
            _org_safe_text_cell(sheet.cell(row=row_index, column=col_index), value)

    header_font = Font(name="Calibri", bold=True, color=_ORG_COLOR_WHITE)
    header_fill = PatternFill("solid", fgColor=_ORG_COLOR_SECTION_BG)
    for cell in sheet[1]:
        cell.font = header_font
        cell.fill = header_fill

    sheet.freeze_panes = "A2"
    for column_cells in sheet.columns:
        longest = max((len(str(cell.value or "")) for cell in column_cells), default=10)
        sheet.column_dimensions[get_column_letter(column_cells[0].column)].width = min(max(longest + 2, 10), 50)


class ExportService:
    """يبني DataFrame من الكائنات ثم يحوّله إلى bytes جاهزة لزر التنزيل."""

    @staticmethod
    def candidates_to_dataframe(candidates: list[Candidate]) -> pd.DataFrame:
        rows = [
            {
                "Code": c.candidate_code,
                "Full Name": c.full_name,
                "Email": c.email,
                "Phone": c.phone,
                "Age": c.age,
                "LinkedIn": c.linkedin_url,
                "Location": c.location,
                "Current Position": c.current_position,
                "Applied Job": c.applied_job,
                "Status": c.status,
                "Rating": c.rating,
                "Experience (Years)": c.total_experience_years,
                "Expected Salary": c.expected_salary,
                "Notice Period (Days)": c.notice_period_days,
                "Marital Status": c.marital_status,
                "Military Status": c.military_status,
                "Languages": _join(c.languages),
                "Education": _education_text(c.education),
                "Technical Skills": _join(c.technical_skills),
                "Computer Skills": _join(c.computer_skills),
                "Managerial Skills": _join(c.managerial_skills),
                "Soft Skills": _join(c.soft_skills),
                "Other Skills": _join(c.skills),
                "Previous Positions": _join(c.previous_positions),
                "Industries": _join(c.industries),
                "Previous Companies": _join(c.previous_companies),
                "Summary": c.summary,
                "Recruiter Notes": c.recruiter_notes,
                "Source File": c.source_filename,
                "Created At": _date_text(c.created_at),
            }
            for c in candidates
        ]
        return pd.DataFrame(rows)

    @staticmethod
    def jobs_to_dataframe(jobs: list[Job]) -> pd.DataFrame:
        rows = [
            {
                "ID": j.id,
                "Title": j.title,
                "Department": j.department,
                "Location": j.location,
                "Required Experience (Years)": j.required_experience_years,
                "Status": j.status,
                "Technical Skills": _join(j.required_technical_skills),
                "Computer Skills": _join(j.required_computer_skills),
                "Managerial Skills": _join(j.required_managerial_skills),
                "Soft Skills": _join(j.required_soft_skills),
                "Other Skills": _join(j.required_skills),
                "Preferred Industries": _join(j.preferred_industries),
                "Description": j.description,
                "Created At": _date_text(j.created_at),
            }
            for j in jobs
        ]
        return pd.DataFrame(rows)

    @staticmethod
    def to_csv_bytes(df: pd.DataFrame) -> bytes:
        # utf-8-sig (BOM) ليفتح Excel النص العربي بشكل صحيح
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
        candidates: list[Candidate], include_flat_sheet: bool = True
    ) -> bytes:
        """
        يبني ملف Excel منظَّم: صفحة "Candidates" مسطحة (اختيارية) + "الفهرس" + صفحة مستقلة لكل مرشح
        (اسمها كود المرشح)، مطابق في التصميم لملف candidates_organized.xlsx النموذجي.
        لا تصل هذه الدالة لقاعدة البيانات ولا تستدعي Streamlit - تستقبل كائنات Candidate جاهزة فقط.
        """
        workbook = Workbook()
        workbook.remove(workbook.active)  # الصفحة الافتراضية الفارغة

        if include_flat_sheet:
            flat_sheet = workbook.create_sheet(_ORG_FLAT_SHEET_NAME)
            _org_write_flat_sheet(flat_sheet, candidates)

        used_sheet_names: set[str] = set()
        entries: list[tuple[str, Candidate]] = []
        for candidate in candidates:
            base_name = candidate.candidate_code or f"ID-{candidate.id}"
            sheet_name = _org_sanitize_sheet_name(base_name, used_sheet_names)
            entries.append((sheet_name, candidate))

        _org_build_index_sheet(workbook, entries)  # يُنشأ مؤقتاً في المقدمة (index=0)

        for sheet_name, candidate in entries:
            _org_build_candidate_sheet(workbook, candidate, sheet_name)

        # إعادة ترتيب الصفحات النهائي: Candidates (إن وُجدت) ثم الفهرس ثم صفحة لكل مرشح بالترتيب
        desired_order = ([_ORG_FLAT_SHEET_NAME] if include_flat_sheet else []) + [_ORG_INDEX_SHEET_NAME] + [
            name for name, _ in entries
        ]
        workbook._sheets = [workbook[name] for name in desired_order]  # noqa: SLF001 - إعادة ترتيب مقصودة

        buffer = io.BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()
