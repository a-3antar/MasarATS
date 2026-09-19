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
    major: str | None = None
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


def _coerce_to_str_list(value: Any) -> Any:
    """يطبّع قوائم النصوص: None → قائمة فارغة، نص مفرد → قائمة، ويحذف الفارغ والمكرر."""
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return value

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item).strip() if item is not None else ""
        if text and text.lower() not in seen:
            seen.add(text.lower())
            cleaned.append(text)
    return cleaned


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

    # المهارات مقسّمة حسب النوع - وحقل skills للمهارات التي لا تنتمي لأي فئة
    technical_skills: list[str] = Field(default_factory=list)
    computer_skills: list[str] = Field(default_factory=list)
    managerial_skills: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)

    industries: list[str] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)
    experience: list[ExperienceItem] = Field(default_factory=list)
    summary: str | None = None

    @field_validator("education", "experience", mode="before")
    @classmethod
    def _normalize_list_fields(cls, value: Any) -> Any:
        return _coerce_to_list(value)

    @field_validator(
        "skills", "technical_skills", "computer_skills",
        "managerial_skills", "soft_skills", "industries",
        mode="before",
    )
    @classmethod
    def _normalize_str_list_fields(cls, value: Any) -> Any:
        return _coerce_to_str_list(value)