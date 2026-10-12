
from typing import Any
import re
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
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    return value


def _coerce_to_str_list(value: Any) -> Any:
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

    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    location: str | None = None
    birth_date: str | None = None
    age: int | None = None
    
    current_position: str | None = None
    total_experience_years: float | None = None
   
    marital_status: str | None = None
    military_status: str | None = None
    languages: list[str] = Field(default_factory=list)

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
        "managerial_skills", "soft_skills", "industries", "languages",
        mode="before",
    )
    @classmethod
    def _normalize_str_list_fields(cls, value: Any) -> Any:
        return _coerce_to_str_list(value)

    @field_validator("age", mode="before")
    @classmethod
    def _normalize_age(cls, value: Any) -> Any:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            age = int(value)
        else:
            match = re.search(r"\d{1,3}", str(value))
            age = int(match.group(0)) if match else None
        return age if age is not None and 15 <= age <= 80 else None

class CandidateSearchFilters(BaseModel):

    role: str | None = None
    experience_min: float | None = None
    experience_max: float | None = None
    skills: list[str] = Field(default_factory=list)
    industry: str | None = None
    location: str | None = None

    @field_validator("skills", mode="before")
    @classmethod
    def _normalize_skills(cls, value: Any) -> Any:
        return _coerce_to_str_list(value)

_VALID_DIFFICULTIES = {"low": "Low", "medium": "Medium", "high": "High"}


class InterviewQuestion(BaseModel):
    question: str
    rationale: str | None = None
    competency: str | None = None
    difficulty: str | None = None

    @field_validator("competency", mode="before")
    @classmethod
    def _clean_competency(cls, value: Any) -> Any:
        text = str(value).strip() if value is not None else ""
        return text[:100] or None

    @field_validator("difficulty", mode="before")
    @classmethod
    def _normalize_difficulty(cls, value: Any) -> Any:
        return _VALID_DIFFICULTIES.get(str(value or "").strip().lower())

class InterviewQuestions(BaseModel):

    technical: list[InterviewQuestion] = Field(default_factory=list)
    behavioral: list[InterviewQuestion] = Field(default_factory=list)
    leadership: list[InterviewQuestion] = Field(default_factory=list)
    cv_specific: list[InterviewQuestion] = Field(default_factory=list)
    risk_areas: list[str] = Field(default_factory=list)

class CandidateAnalysis(BaseModel):

    career_level: str | None = None
    strengths: list[str] = Field(default_factory=list)
    potential_gaps: list[str] = Field(default_factory=list)
    suitable_functions: list[str] = Field(default_factory=list)

    @field_validator("strengths", "potential_gaps", "suitable_functions", mode="before")
    @classmethod
    def _normalize_analysis_lists(cls, value: Any) -> Any:
        return _coerce_to_str_list(value)

class JobRequirements(BaseModel):

    title: str | None = None
    department: str | None = None
    location: str | None = None
    required_experience_years: float | None = None

    required_technical_skills: list[str] = Field(default_factory=list)
    required_computer_skills: list[str] = Field(default_factory=list)
    required_managerial_skills: list[str] = Field(default_factory=list)
    required_soft_skills: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    preferred_industries: list[str] = Field(default_factory=list)

    description: str | None = None

    @field_validator(
        "required_technical_skills", "required_computer_skills", "required_managerial_skills",
        "required_soft_skills", "required_skills", "preferred_industries",
        mode="before",
    )
    @classmethod
    def _normalize_job_lists(cls, value: Any) -> Any:
        return _coerce_to_str_list(value)

class AnswerEvaluation(BaseModel):

    score: int = Field(ge=1, le=5)
    technical_knowledge: int | None = None
    problem_solving: int | None = None
    communication: int | None = None
    practical_experience: int | None = None
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    feedback: str | None = None
    follow_up_question: str | None = None

    @field_validator("strengths", "concerns", mode="before")
    @classmethod
    def _normalize_lists(cls, value: Any) -> Any:
        return _coerce_to_str_list(value)

    @field_validator("score", mode="before")
    @classmethod
    def _clamp_score(cls, value: Any) -> Any:
        try:
            score = int(value)
        except (TypeError, ValueError):
            return 3
        return min(max(score, 1), 5)

    @field_validator(
        "technical_knowledge", "problem_solving", "communication", "practical_experience",
        mode="before",
    )
    @classmethod
    def _clamp_dimension(cls, value: Any) -> Any:
        if value is None or isinstance(value, bool):
            return None
        try:
            return min(max(int(value), 0), 100)
        except (TypeError, ValueError):
            return None
