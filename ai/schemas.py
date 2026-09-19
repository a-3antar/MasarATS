"""مخططات Pydantic لمخرجات استخلاص السيرة الذاتية. تُستخدم للتحقق من استجابة Gemini قبل حفظها."""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class ExperienceItem(BaseModel):
    company: str | None = None
    position: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    responsibilities: list[str] = Field(default_factory=list)


class EducationItem(BaseModel):
    degree: str | None = None
    institution: str | None = None
    graduation_year: str | None = None


def _coerce_to_list(value: Any) -> Any:
    """
    Gemini يُرجع أحياناً كائناً مفرداً (dict) بدل قائمة عندما يكون هناك عنصر واحد فقط
    (مثلاً تعليم واحد أو خبرة واحدة)، رغم طلب schema بقائمة صراحة. نطبّع القيمة هنا
    بدل رفض الاستجابة بالكامل وفقدان كل البيانات الأخرى الصحيحة.
    """
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    return value


class CandidateProfile(BaseModel):
    """الشكل المهيكل الذي نطلبه من الذكاء الاصطناعي بعد قراءة نص السيرة الذاتية.

    قاعدة أساسية: لا تخمين. أي حقل غير موجود بوضوح في النص يجب أن يكون null
    أو قائمة فارغة، وليس قيمة مُستنتَجة.
    """

    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    current_position: str | None = None
    total_experience_years: float | None = None
    skills: list[str] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)
    experience: list[ExperienceItem] = Field(default_factory=list)
    summary: str | None = None

    @field_validator("education", "experience", mode="before")
    @classmethod
    def _normalize_list_fields(cls, value: Any) -> Any:
        return _coerce_to_list(value)
