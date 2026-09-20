"""خدمة التصدير: تحويل المرشحين والوظائف إلى ملفات CSV / Excel."""

import io

import pandas as pd

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
    