# SmartATS AI — Master Development Prompt

## 1. Project Role

You are a senior Python software architect, UI/UX designer, AI engineer, and clean-code developer.

Your task is to design and implement a **production-ready AI-powered Applicant Tracking System (ATS)** called **SmartATS AI** using:

- Python 3.12+
- Streamlit
- SQLAlchemy
- Pydantic
- Google Gemini API
- Gemini Flash-Lite as the default AI model
- Pandas
- Plotly
- PyMuPDF
- python-docx
- python-pptx
- OCR support
- SQLite for the first version
- PostgreSQL/SQL Server compatibility for future scaling

The application must be modular, maintainable, secure, extensible, and professionally designed.

Do not build the application as one large Python file.

---

# 2. Main Objective

Build an AI-powered recruitment management system similar in concept to modern ATS platforms.

The system must allow users to:

1. Upload CVs for multiple candidates.
2. Support multiple file formats.
3. Extract structured candidate information automatically.
4. Store all candidate information in a database.
5. Analyze CVs using Gemini AI.
6. Create and manage job vacancies.
7. Define job requirements and skills.
8. Match candidates to jobs.
9. Recommend suitable jobs for candidates.
10. Calculate explainable matching scores.
11. Identify strengths and potential skill gaps.
12. Detect duplicate candidates.
13. Manage recruitment pipelines.
14. Manage interviews.
15. Generate AI-assisted interview questions.
16. Build an organizational structure.
17. Identify workforce gaps.
18. Search candidates using natural language.
19. Export candidates, jobs, applications, and CV data.
20. Provide dashboards and recruitment analytics.
21. Maintain AI analysis history and audit information.
22. Support role-based access control.
23. Keep AI provider abstraction so other AI providers can be added later.
24. Provide a complete Candidate 360° profile and talent history.
25. Support Talent Pools, Talent Rediscovery, and candidate relationship management.
26. Support structured hiring through job-specific scorecards and evaluation criteria.
27. Provide evidence-based matching with confidence and source traceability.
28. Support Skill Graph, Skill Gap, career path, and internal mobility analysis.
29. Support workforce planning and staffing-gap-driven candidate search.
30. Provide AI-assisted recruitment, analytics, and interview assistants under human approval.
31. Record recruiter feedback and human decisions for analysis without silently changing scoring rules.

---

# 3. Core Design Principle

Do NOT allow Gemini to make all recruitment decisions.

Separate the system into:

```text
Deterministic Business Logic
        +
AI Semantic Understanding
        +
Human Review
```

Use deterministic code for:

- Experience calculations
- Required skills
- Matching weights
- Education requirements
- Location filters
- Salary filters
- Status
- Recruitment pipeline
- Database queries
- Sorting
- Filtering

Use AI for:

- CV understanding
- Information extraction
- Semantic interpretation
- CV summaries
- Strength analysis
- Potential gaps
- Job description analysis
- Semantic matching
- Interview question generation
- Natural language query interpretation

AI must provide recommendations and explanations, not autonomous hiring decisions.

---

# 4. High-Level Architecture

Use a layered architecture:

```text
                    Streamlit UI
                         │
                         ▼
                  Application Layer
                         │
                         ▼
                   Service Layer
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
     Repository       AI Engine     Document Engine
          │              │              │
          ▼              ▼              ▼
      Database         Gemini       PDF/DOCX/PPTX/OCR
```

The Streamlit UI must not contain database queries, Gemini implementation, or document parsing logic.

---

# 5. Project Structure

Use this structure as the baseline:

```text
smartats/
│
├── app.py
│
├── config/
│   ├── settings.py
│   └── config.yaml
│
├── core/
│   ├── constants.py
│   ├── exceptions.py
│   ├── logging.py
│   ├── security.py
│   └── enums.py
│
├── models/
│   ├── candidate.py
│   ├── experience.py
│   ├── education.py
│   ├── skill.py
│   ├── certification.py
│   ├── language.py
│   ├── project.py
│   ├── candidate_evidence.py
│   ├── candidate_skill.py
│   ├── talent_pool.py
│   ├── candidate_activity.py
│   ├── job.py
│   ├── job_requirement.py
│   ├── job_scorecard.py
│   ├── application.py
│   ├── match_result.py
│   ├── interview.py
│   ├── interview_feedback.py
│   ├── department.py
│   ├── position.py
│   ├── organization.py
│   ├── workforce_plan.py
│   ├── skill_gap.py
│   └── recruiter_feedback.py
│
├── schemas/
│   ├── candidate_schema.py
│   ├── job_schema.py
│   ├── interview_schema.py
│   ├── organization_schema.py
│   └── ai_schema.py
│
├── repositories/
│   ├── base.py
│   ├── candidate_repository.py
│   ├── job_repository.py
│   ├── application_repository.py
│   ├── interview_repository.py
│   └── organization_repository.py
│
├── services/
│   ├── candidate_service.py
│   ├── job_service.py
│   ├── matching_service.py
│   ├── interview_service.py
│   ├── organization_service.py
│   ├── talent_service.py
│   ├── scorecard_service.py
│   ├── skill_service.py
│   ├── workforce_service.py
│   ├── recruiter_feedback_service.py
│   ├── analytics_service.py
│   ├── report_service.py
│   └── export_service.py
│
├── ai/
│   ├── base.py
│   ├── gemini_service.py
│   ├── analyzer.py
│   ├── matcher.py
│   ├── interview_generator.py
│   ├── recruitment_assistant.py
│   ├── analytics_assistant.py
│   ├── query_parser.py
│   ├── evidence_analyzer.py
│   ├── prompts.py
│   └── schemas.py
│
├── document_processing/
│   ├── base.py
│   ├── factory.py
│   ├── pdf_parser.py
│   ├── word_parser.py
│   ├── powerpoint_parser.py
│   ├── text_parser.py
│   ├── image_parser.py
│   └── ocr_parser.py
│
├── matching/
│   ├── base.py
│   ├── rule_engine.py
│   ├── semantic_engine.py
│   └── hybrid_engine.py
│
├── database/
│   ├── database.py
│   ├── base.py
│   └── migrations/
│
├── pages/
│   ├── dashboard.py
│   ├── candidates.py
│   ├── candidate_profile.py
│   ├── upload_cv.py
│   ├── talent_pools.py
│   ├── jobs.py
│   ├── job_details.py
│   ├── matching.py
│   ├── scorecards.py
│   ├── interviews.py
│   ├── organization.py
│   ├── workforce_planning.py
│   ├── skills.py
│   ├── ai_assistant.py
│   ├── analytics.py
│   ├── reports.py
│   └── settings.py
│
├── ui/
│   ├── components.py
│   ├── cards.py
│   ├── tables.py
│   ├── charts.py
│   ├── forms.py
│   └── styles.py
│
├── utils/
│   ├── files.py
│   ├── dates.py
│   ├── validators.py
│   ├── text.py
│   └── hashing.py
│
├── tests/
│   ├── test_candidates.py
│   ├── test_jobs.py
│   ├── test_matching.py
│   ├── test_documents.py
│   ├── test_duplicates.py
│   └── test_ai.py
│
├── data/
├── uploads/
├── exports/
├── .env.example
├── requirements.txt
├── README.md
└── .gitignore
```

---

# 6. OOP Requirements

Use OOP professionally.

Do not use inheritance simply for the sake of inheritance.

Use inheritance where there is a genuine `is-a` relationship.

Use:

- Abstract Base Classes
- Interfaces through ABC
- Polymorphism
- Composition
- Dependency Injection
- Factory Pattern
- Strategy Pattern
- Repository Pattern
- Service Layer

Example:

```python
class DocumentParser(ABC):

    @abstractmethod
    def extract_text(self, file_path: str) -> str:
        raise NotImplementedError
```

Implement:

```python
class PDFParser(DocumentParser):
    ...

class WordParser(DocumentParser):
    ...

class PowerPointParser(DocumentParser):
    ...

class OCRParser(DocumentParser):
    ...
```

Create:

```python
class DocumentParserFactory:
    ...
```

Similarly, AI providers must use an abstraction:

```python
class AIProvider(ABC):

    @abstractmethod
    def analyze(self, prompt: str, schema):
        raise NotImplementedError
```

Then:

```python
class GeminiService(AIProvider):
    ...
```

Design the system so future providers such as OpenAI or Groq can be added without changing business logic.

---

# 7. Candidate Management

Create a complete candidate management module.

Candidate data should include, where available:

## Personal Information

- Candidate ID
- Full name
- Email
- Phone
- Location
- LinkedIn
- Portfolio
- Date of birth if explicitly provided
- Other contact information

## Professional Information

- Current position
- Current company
- Career level
- Total experience
- Industries
- Functional areas
- Skills
- Technical skills
- Soft skills
- Certifications
- Languages
- Salary expectation
- Notice period
- Availability

## Experience

For every job:

- Company
- Position
- Start date
- End date
- Duration
- Responsibilities
- Achievements
- Technologies
- Industry

## Education

- Degree
- Institution
- Major
- Graduation year
- Academic level

## Projects

- Project name
- Description
- Role
- Technologies
- Achievements

## Documents

- Original CV
- File type
- File hash
- Upload date
- Extracted text
- AI analysis
- AI model
- Prompt version
- Analysis timestamp

Never invent missing information.

If a field is not present, return `null` or an empty collection.

---

# 8. Supported CV Formats

The system should support:

- PDF
- DOCX
- DOC where technically possible
- PPTX
- TXT
- RTF
- Images
- Scanned PDFs

Use specialized parsers.

Suggested libraries:

```text
PDF       → PyMuPDF
DOCX      → python-docx
PPTX      → python-pptx
XLSX      → openpyxl
Images    → OCR
Scanned   → OCR
```

Create a common document abstraction so the rest of the application does not care about the file format.

---

# 9. CV Upload Workflow

The workflow should be:

```text
Upload
  ↓
File Validation
  ↓
File Hash
  ↓
Duplicate Detection
  ↓
Document Parsing
  ↓
Text Extraction
  ↓
AI Structured Extraction
  ↓
Pydantic Validation
  ↓
Candidate Creation/Update
  ↓
AI Analysis
  ↓
Database Storage
  ↓
Job Matching
```

For multiple files, show progress:

```text
Processing 73 / 100

████████████████░░░░

Completed: 68
Processing: 5
Errors: 0
```

Do not make the application appear frozen during batch processing.

---

# 10. Gemini AI Integration

Use Gemini Flash-Lite as the default model.

Keep model configuration outside the code:

```yaml
ai:
  provider: gemini
  model: gemini-3.5-flash-lite
  temperature: 0.2
```

Also allow the model name to be changed from configuration.

Do not hard-code the API key.

Use:

```env
GEMINI_API_KEY=
```

Use structured output with Pydantic schemas.

AI must return validated structured data.

---

# 11. AI CV Extraction

Create a structured schema such as:

```python
class Experience(BaseModel):
    company: str | None
    position: str | None
    start_date: str | None
    end_date: str | None
    responsibilities: list[str]
    achievements: list[str]
```

And:

```python
class CandidateProfile(BaseModel):
    full_name: str | None
    email: str | None
    phone: str | None
    location: str | None
    current_position: str | None
    total_experience_years: float | None
    skills: list[str]
    languages: list[str]
    education: list[Education]
    experience: list[Experience]
    certifications: list[str]
    industries: list[str]
    projects: list[Project]
    summary: str | None
```

AI prompt requirements:

- Do not hallucinate.
- Do not infer facts without evidence.
- Preserve dates when available.
- Normalize skill names.
- Separate technical skills from soft skills.
- Distinguish responsibilities from achievements.
- Return null when information is missing.
- Return structured JSON according to schema.

---

# 12. AI Candidate Analysis

For each candidate generate:

## Summary

A concise professional summary.

## Strengths

Evidence-based strengths.

## Potential Gaps

Potential missing or insufficiently documented requirements.

Do not claim that a candidate lacks a skill simply because it is absent from the CV.

Use wording such as:

```text
"Not explicitly documented in the CV."
```

instead of:

```text
"Candidate does not have this skill."
```

## Career Level

Examples:

- Intern
- Junior
- Mid-Level
- Senior
- Manager
- Director
- Executive

Base classification on evidence.

## Suitable Functions

Examples:

- Production
- Engineering
- Quality
- Maintenance
- Supply Chain
- Sales
- Finance
- HR
- IT

---

# 13. Job Management

Allow users to create jobs with:

- Job title
- Department
- Location
- Reports to
- Employment type
- Salary range
- Required experience
- Education
- Required skills
- Preferred skills
- Certifications
- Languages
- Responsibilities
- KPIs
- Number of vacancies
- Job status

Statuses:

```text
Draft
Open
On Hold
Closed
```

---

# 14. AI Job Description Analysis

Allow users to paste an unstructured job description.

Example:

```text
I need a production manager for a plastic factory
with injection and extrusion experience...
```

AI should convert it into structured requirements.

Example:

```json
{
  "title": "Plastic Factory Production Manager",
  "experience_min": 8,
  "skills": [
    "Injection Molding",
    "Extrusion",
    "PVC",
    "PPR",
    "Production Planning"
  ]
}
```

The user must be able to review and edit the generated requirements before saving.

---

# 15. Candidate Matching

Create a professional matching engine.

Do not rely only on keyword matching.

Use three levels:

```text
Rule Matching
+
Semantic Matching
+
Hybrid Matching
```

Example configurable weights:

```text
Experience             25%
Technical Skills       25%
Education              10%
Industry               15%
Management             10%
Location                5%
Language                5%
Certification           5%
                         ----
                        100%
```

Weights must be configurable per job.

---

# 16. Explainable Match Score

The final score must be explainable.

Example:

```text
Match Score: 87%

Experience              90%
Technical Skills        85%
Education              100%
Industry                90%
Management              80%
Location               100%
Language                80%
Certification           60%
```

Show:

## Strong Matches

```text
✓ 11 years of relevant experience
✓ Injection molding
✓ PVC / PPR
✓ Production planning
✓ Team management
```

## Potential Gaps

```text
⚠ ERP experience is not explicitly documented
⚠ English proficiency is not specified
```

Never show only a mysterious score.

---

# 17. Job → Candidates

For every open job provide:

```text
Find Candidates
```

Display candidates with:

- Candidate name
- Current position
- Experience
- Match score
- Key matching skills
- Potential gaps
- Application status

Allow filtering by:

- Minimum score
- Experience
- Skills
- Location
- Career level
- Availability

---

# 18. Candidate → Jobs

For every candidate provide:

```text
Find Suitable Jobs
```

Example:

```text
Production Manager       94%
Plant Manager             89%
Operations Manager        84%
Production Engineer       67%
```

Provide the explanation for every match.

---

# 19. Duplicate Detection

Create:

```python
class DuplicateDetector:
    ...
```

Use multiple signals:

- Email
- Phone
- LinkedIn
- File hash
- Name similarity
- Employment history
- Semantic similarity

When a probable duplicate is found:

```text
Possible Duplicate

Ahmed Hassan

Existing Candidate:
C-00124

Similarity:
96%

[Merge]
[Create New]
[Review]
```

Do not silently overwrite existing candidate records.

---

# 20. Recruitment Pipeline

Implement ATS pipeline:

```text
New
  ↓
Screening
  ↓
Shortlisted
  ↓
Interview 1
  ↓
Interview 2
  ↓
Technical Assessment
  ↓
Offer
  ↓
Hired
```

Additional statuses:

```text
Rejected
On Hold
Withdrawn
```

Provide a Kanban-style interface where practical.

---

# 21. Interview Management

For each candidate/job application:

- Interview date
- Interview type
- Interviewer
- Location/meeting link
- Questions
- Notes
- Feedback
- Evaluation
- Next action

Interview types:

- HR
- Technical
- Management
- Behavioral
- Final

---

# 22. AI Interview Assistant

Given a job and candidate CV, generate:

- Technical questions
- Behavioral questions
- Leadership questions
- Industry questions
- CV-specific questions
- Clarification questions
- Potential risk areas to clarify
- Expected good-answer indicators
- Evaluation criteria

Example:

If CV states:

```text
Improved OEE by 18%
```

Generate questions such as:

```text
What was the OEE baseline?
Which OEE components improved?
How did you measure the improvement?
What actions produced the improvement?
```

Do not fabricate achievements.

---

# 23. Organization Management

Create:

```text
Department
Position
Employee
Reporting Relationship
```

Example:

```text
General Manager
│
├── Production
│   ├── Production Manager
│   ├── Injection Supervisor
│   ├── Extrusion Supervisor
│   └── Assembly Supervisor
│
├── Quality
│
├── Finance
│
└── HR
```

Use a graph/tree visualization.

Possible libraries:

- NetworkX
- Plotly
- Streamlit-compatible graph components

---

# 24. Workforce Gap Analysis

Allow the user to define required manpower:

```text
Production Manager      Required: 1   Current: 1
Production Engineer     Required: 3   Current: 2
Supervisor              Required: 6   Current: 4
Operator                Required: 24  Current: 21
```

Calculate:

```text
Gap =
Required - Current
```

Then allow:

```text
Find Candidates
```

to search the candidate database for suitable people.

---

# 25. Natural Language Search

Allow users to type requests such as:

```text
Find production managers with more than 10 years
of plastic manufacturing experience and injection
and extrusion knowledge near 10th Ramadan.
```

AI should convert the request into structured filters:

```json
{
  "role": "Production Manager",
  "experience_min": 10,
  "industry": "Plastic Manufacturing",
  "skills": [
    "Injection Molding",
    "Extrusion"
  ],
  "location": "10th Ramadan"
}
```

Then the database should execute the search.

Do not send the entire candidate database to Gemini.

---

# 26. Semantic Search

Design the system so semantic search can be added.

Architecture:

```text
Candidate CV
    ↓
Embedding
    ↓
Vector Store

Job Description
    ↓
Embedding
    ↓
Vector Store

Semantic Similarity
    ↓
Matching Engine
```

Possible technologies:

- Gemini Embeddings
- pgvector
- FAISS
- Chroma

Keep this as an extensible module.

---

# 27. AI Chat Assistant

Add contextual AI chat.

For a candidate:

```text
What are this candidate's strongest technical skills?

Is this candidate suitable for Production Manager?

What should I verify during the interview?
```

For a job:

```text
Show candidates above 80% match.

Why does Candidate A match better than Candidate B?

Which required skills are difficult to find?
```

The assistant must use only authorized and relevant database information.

---

# 28. AI Cost Optimization

Never call Gemini unnecessarily.

Store AI results.

Each analysis should include:

```text
candidate_id
model_name
prompt_version
analysis_version
input_hash
output
created_at
processing_time
```

If the same CV has already been analyzed and has not changed, reuse the existing analysis.

Re-analyze only when:

- CV changes
- Prompt version changes
- Model changes
- User explicitly requests re-analysis

---

# 29. Prompt Versioning

Store prompts centrally.

Examples:

```text
CV_EXTRACTION_PROMPT_V1
CV_ANALYSIS_PROMPT_V1
JOB_ANALYSIS_PROMPT_V1
MATCHING_PROMPT_V1
INTERVIEW_PROMPT_V1
NATURAL_LANGUAGE_QUERY_PROMPT_V1
```

Never scatter large prompts throughout Streamlit pages.

---

# 30. AI Audit Trail

Store:

```text
Candidate ID
Model
Prompt Version
Timestamp
Input Hash
Output
Processing Time
```

This allows traceability and debugging.

---

# 31. Database Design

Start with SQLite.

Use SQLAlchemy ORM.

Prepare the architecture for PostgreSQL or SQL Server later.

Recommended entities:

```text
candidates
candidate_contacts
candidate_experiences
candidate_education
candidate_skills
candidate_certifications
candidate_languages
candidate_projects
candidate_documents

jobs
job_requirements
job_skills
job_responsibilities

applications
candidate_job_matches

departments
positions
organization_structure

interviews
interview_questions
interview_feedback

ai_analysis
activity_log
users
roles
settings

# Talent Intelligence
talent_pools
candidate_talent_pools
candidate_evidence
candidate_activities
candidate_skill_profiles
skills
skill_relationships

# Structured Hiring
job_scorecards
job_scorecard_criteria
candidate_scorecards
candidate_scorecard_scores
match_evidence
match_explanations

# Workforce Planning
workforce_plans
workforce_requirements
workforce_gaps
career_paths
internal_mobility_recommendations
skill_gaps

# Human Feedback / Audit
recruiter_feedback
human_decisions
ai_action_proposals
ai_action_approvals
```

Use foreign keys and indexes appropriately.

Avoid storing everything in one giant candidates table.

---

# 32. Repository Pattern

Use:

```python
class CandidateRepository:
    def create(...)
    def get_by_id(...)
    def search(...)
    def update(...)
    def delete(...)
```

Similar repositories should exist for:

- Jobs
- Applications
- Interviews
- Organization
- AI analysis

UI must call services, not repositories directly whenever business logic is required.

---

# 33. Service Layer

Examples:

```python
class CandidateService:
    ...

class JobService:
    ...

class MatchingService:
    ...

class InterviewService:
    ...

class OrganizationService:
    ...

class ReportService:
    ...
```

Example workflow:

```text
CandidateService
      ↓
Document Processor
      ↓
AI Service
      ↓
Duplicate Detector
      ↓
Repository
      ↓
Database
```

---

# 34. Professional UI

Use Streamlit with a professional desktop-first design.

Use:

```python
st.navigation()
```

for multipage navigation.

Main navigation:

```text
Dashboard

Candidates
    ├── All Candidates
    ├── Add Candidate
    ├── Upload CVs
    └── Search

Jobs
    ├── All Jobs
    ├── Create Job
    └── Job Pipeline

AI Matching
    ├── Find Candidates
    ├── Find Jobs
    ├── Skill Gap
    └── AI Analysis

Recruitment
    ├── Applications
    ├── Interviews
    ├── Offers
    └── Hiring

Organization
    ├── Departments
    ├── Positions
    ├── Org Chart
    └── Workforce Gap

Talent Intelligence
    ├── Talent Pools
    ├── Talent Rediscovery
    ├── Skill Graph
    ├── Skill Gaps
    └── Internal Mobility

Workforce Planning
    ├── Workforce Plan
    ├── Staffing Gaps
    └── Career Paths

AI Assistant
    ├── Recruitment Assistant
    ├── Candidate Assistant
    └── Analytics Assistant

Reports

Settings
```

---

# 35. Dashboard

Show:

```text
Total Candidates
Open Jobs
Interviews
New CVs
Shortlisted Candidates
Offers
Hired
```

Charts:

- Candidates by department
- Candidates by career level
- Top skills
- Recruitment funnel
- Applications by status
- Time to hire
- Candidates by source
- Jobs with insufficient candidates
- Skill availability

Use Plotly for interactive charts.

---

# 36. Candidate Profile UI

Design a professional candidate profile:

```text
Candidate
Ahmed Mohamed

Contact
────────────────────────
Phone
Email
LinkedIn
Location

Current Position
────────────────────────
Production Manager

Experience
────────────────────────
2019–Present
Production Manager
ABC Manufacturing

2014–2019
Production Engineer
XYZ Manufacturing

Skills
────────────────────────
Production Planning
Lean Manufacturing
Power BI
Excel
ERP
OEE
```

AI panel:

```text
AI Candidate Analysis

Summary
Strengths
Potential Gaps
Career Level
Suitable Jobs
Interview Questions
```

---

# 37. Job Profile UI

Show:

```text
Job Title
Department
Reports To
Location
Status
Salary Range

Requirements
Skills
Experience
Education
Certifications
Languages

Responsibilities

Matching Candidates
```

---

# 38. Reusable UI Components

Create reusable components:

```python
render_metric_card()
render_candidate_card()
render_match_score()
render_skill_badges()
render_status_badge()
render_ai_analysis()
render_candidate_table()
render_job_card()
render_progress()
render_empty_state()
render_error_state()
```

Do not duplicate UI code across pages.

---

# 39. Configuration

Use:

```yaml
ai:
  provider: gemini
  model: gemini-3.5-flash-lite
  temperature: 0.2

matching:
  experience_weight: 0.25
  skills_weight: 0.25
  education_weight: 0.10
  industry_weight: 0.15
  management_weight: 0.10
  location_weight: 0.05
  language_weight: 0.05
  certification_weight: 0.05

storage:
  upload_dir: uploads
  export_dir: exports

database:
  url: sqlite:///data/smartats.db
```

Do not hard-code business configuration.

---

# 40. Security

Implement:

- Login
- Roles
- Permissions
- Environment variables
- File validation
- Secure file storage
- Audit logs
- Database constraints
- Input validation

Never expose API keys.

Never place secrets directly in source code.

CVs contain personal information. Treat candidate files and data as private.

Provide controlled deletion of candidate records and documents.

---

# 41. Roles

Example:

| Role | Candidates | Jobs | Settings |
|---|---|---|---|
| Admin | Full | Full | Full |
| HR Manager | Full | Full | Limited |
| Recruiter | Full | Assigned | No |
| Interviewer | Assigned | View | No |
| Viewer | View | View | No |

Implement permissions in the service/application layer, not only in the UI.

---

# 42. Export System

Allow exporting:

## Candidates

- Excel
- CSV
- PDF where useful

## Jobs

- Excel
- CSV

## Recruitment Pipeline

- Excel

## AI Analysis

- PDF
- DOCX

## CV Database

- Excel

Allow the user to choose fields before exporting.

Example:

```text
Export Candidates

☑ Contact Information
☑ Experience
☑ Skills
☑ Education
☑ Certifications
☑ AI Score
☑ Suitable Jobs

[Export Excel]
```

---

# 43. Reports

Create reports such as:

## Recruitment Report

```text
Position: Production Manager

Total CVs       143
Qualified        37
Shortlisted       9
Interviewed       5
Offers            2
Hired             1
```

## Candidate Source

```text
LinkedIn
Facebook
Referral
Website
Other
```

## Recruitment Funnel

```text
CVs
 ↓
Qualified
 ↓
Shortlisted
 ↓
Interview
 ↓
Offer
 ↓
Hired
```

## Time to Hire

Calculate average and median where enough data exists.

---

# 44. Data Validation

Use Pydantic.

Example:

```python
class CandidateCreate(BaseModel):

    full_name: str = Field(min_length=2)

    email: EmailStr | None = None

    phone: str | None = None

    total_experience_years: float = Field(
        default=0,
        ge=0,
        le=60
    )
```

Validate all important external inputs.

---

# 45. Enums

Use enums instead of magic strings.

Example:

```python
class CandidateStatus(str, Enum):
    NEW = "new"
    SCREENING = "screening"
    SHORTLISTED = "shortlisted"
    INTERVIEW = "interview"
    OFFER = "offer"
    HIRED = "hired"
    REJECTED = "rejected"
```

---

# 46. Error Handling

Create custom exceptions:

```text
UnsupportedFileTypeError
DocumentParsingError
AIServiceError
DatabaseError
ValidationError
DuplicateCandidateError
ConfigurationError
```

Do not expose technical stack traces to normal users.

Log technical details while displaying useful messages.

---

# 47. Logging

Implement structured application logging.

Log:

- Upload operations
- Parsing errors
- AI calls
- Database errors
- Authentication events
- Candidate modifications
- Job modifications
- Export operations

Never log API keys or unnecessary sensitive information.

---

# 48. Performance

Optimize for large candidate databases.

Requirements:

- Database indexes
- Pagination
- Cached configuration
- Cached AI results
- Batch processing
- Lazy loading where appropriate
- Avoid sending complete CV databases to Gemini
- Avoid unnecessary AI calls
- Use background processing architecture when scaling requires it

The UI must remain responsive.

---

# 49. Testing

Create unit tests for:

```text
CandidateService
JobService
MatchingEngine
DocumentParser
DuplicateDetector
AI schemas
Natural language query parser
Repositories
```

Examples:

```python
def test_experience_score():
    ...

def test_duplicate_candidate():
    ...

def test_pdf_parser():
    ...

def test_invalid_candidate_data():
    ...
```

Add integration tests for critical workflows.

---

# 50. Clean Code Requirements

Follow:

- SOLID principles
- DRY
- Single Responsibility Principle
- Dependency Injection
- Small focused functions
- Meaningful names
- Type hints
- Pydantic models
- Dataclasses where appropriate
- Enums
- Custom exceptions
- Docstrings for public classes and methods
- English code comments
- No magic numbers
- No duplicated business logic

Keep functions short and focused.

Do not create unnecessary abstractions.

---

# 51. Important Architectural Rule

Do not create this:

```text
app.py
  ├── Streamlit UI
  ├── SQL
  ├── Gemini
  ├── PDF parsing
  ├── matching
  ├── exports
  └── business logic
```

Instead:

```text
Streamlit
   ↓
Services
   ↓
Repositories / AI / Documents
   ↓
Database / External APIs
```

---

# 52. AI Ethics and Human Oversight

The system must not make autonomous employment decisions.

It should provide:

- Evidence
- Matching analysis
- Explainable scores
- Missing information
- Interview questions
- Search results
- Recommendations

The final hiring decision remains with authorized human users.

Avoid using protected or sensitive characteristics for ranking unless there is a specific lawful business requirement and appropriate safeguards.

Do not infer sensitive personal attributes from CV text.

---

# 53. Development Phases

Implement the system in phases.

## Phase 1 — Core ATS

Implement:

- Database
- Candidate management
- Job management
- CV upload
- PDF/DOCX/PPTX/TXT
- AI extraction
- Candidate search
- Job search
- Excel/CSV export
- Professional Streamlit UI

## Phase 2 — AI Matching

Implement:

- Job → Candidates
- Candidate → Jobs
- Weighted scoring
- Explainable matching
- Skill gaps
- AI candidate analysis
- Duplicate detection
- Natural language search

## Phase 3 — Recruitment Management

Implement:

- Applications
- Recruitment pipeline
- Interviews
- AI interview questions
- Interview feedback
- Offers
- Recruitment analytics

## Phase 4 — Organization

Implement:

- Departments
- Positions
- Reporting relationships
- Org chart
- Workforce planning
- Staffing gap
- Candidate search from workforce gaps

## Phase 5 — Advanced AI

Implement:

- Embeddings
- Semantic search
- AI recruitment assistant
- AI interview assistant
- Automated reports
- Advanced analytics
- Evidence-aware semantic matching

## Phase 6 — Talent Intelligence

Implement:

- Candidate 360° profile
- Talent Pools
- Talent Rediscovery
- Candidate relationship history
- Candidate evidence and confidence
- Structured job scorecards
- Skill Graph
- Skill Gap analysis
- Career paths
- Internal mobility
- Recruiter feedback
- Human decision tracking

## Phase 7 — Workforce Intelligence

Implement:

- Workforce planning
- Required vs current headcount
- Staffing gap analysis
- Gap-to-candidate search
- Position succession planning
- Critical skill availability
- Organization capability analysis

## Phase 8 — AI Assistants and Controlled Agents

Implement:

- Candidate AI Assistant
- Recruiter AI Assistant
- Job AI Assistant
- Analytics AI Assistant
- Interview AI Assistant
- Action proposals
- Human approval workflow
- AI action audit trail

AI agents must never independently make final employment decisions.

---


# 53A. Candidate 360° Profile

Every candidate must have a unified profile rather than being represented only by the original CV.

The Candidate 360° view should combine:

```text
Candidate
│
├── Contact Information
├── Current Position
├── Career History
├── Education
├── Skills
├── Certifications
├── Languages
├── Projects
├── Documents
├── Applications
├── Match History
├── Interviews
├── Interview Feedback
├── Talent Pools
├── Recruiter Notes
├── Candidate Activities
├── AI Analysis History
├── Evidence
├── Skill Gaps
└── Suitable Jobs
```

The original CV must remain available as the source document.

AI-derived information must be distinguishable from user-entered or source-derived information.

---

# 53B. Evidence-Based Candidate Data

Do not treat AI extraction as unquestionable truth.

For important candidate attributes, maintain:

```text
Attribute
Value
Source
Evidence
Confidence
Last Verified
Verification Status
```

Example:

```text
Skill: Injection Molding
Value: Experienced
Source: CV
Evidence: "Managed 24 injection molding machines"
Confidence: High
Verification: Not Interview Verified
```

Important distinction:

```text
Not documented
    !=
Does not have the skill
```

The system must use statuses such as:

```text
Confirmed
Evidence Found
Not Explicitly Documented
Needs Verification
User Verified
Contradictory Evidence
```

Never fabricate evidence.

---

# 53C. Talent Pools and Candidate Relationship Management

Implement Talent Pools to organize candidates independently from specific applications.

Examples:

```text
Plant Managers
Production Managers
Production Engineers
Maintenance Managers
Future Leaders
High Potential
Silver Medalists
Interviewed but Not Hired
Future Opportunities
Passive Candidates
```

A candidate may belong to multiple Talent Pools.

Track:

```text
Pool
Date Added
Added By
Reason
Last Contact
Next Follow-up
Interest Level
Availability
Notes
```

Talent Pools must be searchable and usable by the matching engine.

---

# 53D. Talent Rediscovery

When a new job is created, SmartATS should automatically search existing candidates before assuming that new sourcing is required.

Workflow:

```text
New Job
   ↓
Structured Requirements
   ↓
Existing Candidate Search
   ↓
Rule Matching
   +
Semantic Matching
   ↓
Top Existing Candidates
   ↓
Recruiter Review
```

Show:

```text
Existing candidates found: 17

Strong matches: 5
Potential matches: 8
Needs verification: 4
```

The system must include previous candidates even if they never applied to the current job.

---

# 53E. Structured Hiring and Scorecards

Every important job should support a configurable Scorecard.

A Scorecard defines what the organization will evaluate.

Example:

```text
Production Manager

Technical Skills          25%
Relevant Experience       20%
Leadership                15%
Production Planning       15%
Industry Experience      10%
Problem Solving            5%
Education                  5%
Communication              5%
```

Each criterion must support:

```text
Name
Description
Weight
Required / Preferred
Evidence Requirement
Interview Method
Evaluation Scale
```

Do not silently change weights.

Allow job-specific weights.

Candidate evaluation should show:

```text
Criterion
Expected
Evidence
Score
Confidence
Reviewer Comment
```

---

# 53F. Hybrid Matching Engine

The matching engine must combine:

```text
Hard Filters
      +
Rule-Based Scoring
      +
Semantic Similarity
      +
Evidence Quality
      +
Human Review
```

Hard requirements may include:

```text
Minimum experience
Required certification
Required location
Employment eligibility
Required language
Required technical skill
```

Soft requirements may include:

```text
Preferred skill
Industry similarity
Leadership experience
Related technologies
Career progression
```

A candidate must not receive a high score merely because the CV contains many matching keywords.

---

# 53G. Match Explanation and Evidence

Every match result must contain:

```text
Overall Match
Hard Requirement Status
Score Breakdown
Strong Matches
Potential Gaps
Unknown / Unverified Items
Evidence
Confidence
Recommended Verification Questions
```

Example:

```text
Match: 88%

Strong Matches
✓ 12 years relevant experience
✓ Injection molding
✓ Production planning
✓ Team leadership

Needs Verification
⚠ Extrusion experience not clearly documented
⚠ ERP system not specified

Recommended interview questions
1. Which extrusion processes have you managed?
2. Which ERP system did you use?
```

Never display only a numeric score.

---

# 53H. Skill Graph

Create a normalized skill system.

Instead of storing only free text:

```text
Injection
```

maintain relationships such as:

```text
Plastic Manufacturing
    ├── Injection Molding
    │      ├── Thermoplastics
    │      ├── Cycle Time
    │      └── Mold Changeover
    │
    └── Extrusion
           ├── PVC
           ├── PPR
           └── Profile Extrusion
```

Skills may have:

```text
Skill ID
Canonical Name
Aliases
Category
Parent Skill
Related Skills
Industry
Level
```

Example aliases:

```text
Injection Molding
Injection
Plastic Injection
Injection Moulding
```

The system should normalize these to one canonical skill.

---

# 53I. Skill Gap Analysis

For every candidate/job combination, calculate:

```text
Required Skills
Candidate Skills
Verified Skills
Unknown Skills
Potential Gaps
```

Example:

```text
Job requires:

Injection       ✓
Extrusion       ?
OEE              ✓
ERP              ?
Leadership       ✓
```

The system must distinguish:

```text
Missing
Unknown
Weak
Verified
Strong
```

A gap should lead to an actionable recommendation:

```text
Interview Question
Training Recommendation
Further Evidence Request
```

---

# 53J. Candidate-to-Job and Job-to-Candidate Matching

Support both directions.

### Job → Candidates

```text
Production Manager
        ↓
Candidate A 94%
Candidate B 90%
Candidate C 86%
```

### Candidate → Jobs

```text
Ahmed
        ↓
Production Manager 94%
Plant Manager       89%
Operations Manager  84%
```

Both results must use the same matching engine and evidence model.

---

# 53K. Interview Intelligence

Interview planning should be based on:

```text
Job Requirements
+
Candidate Evidence
+
Skill Gaps
+
Unverified Claims
```

Generate:

- Technical questions
- Behavioral questions
- Leadership questions
- Industry questions
- CV-specific questions
- Gap verification questions
- Achievement verification questions

For each question optionally provide:

```text
Why ask this?
What evidence to look for?
Good-answer indicators
Evaluation criterion
```

Never invent candidate achievements.

---

# 53L. Recruitment and Candidate Activity Timeline

Maintain a timeline:

```text
2026-09-01  CV Uploaded
2026-09-01  AI Analysis
2026-09-02  Added to Talent Pool
2026-09-05  Applied to Production Manager
2026-09-07  Shortlisted
2026-09-10  Technical Interview
2026-09-12  Interview Feedback
2026-09-15  Offer
```

This timeline should be visible from the Candidate 360° profile.

---

# 53M. Workforce Planning Intelligence

Workforce planning must connect organization structure with recruitment.

For each position:

```text
Position
Required Headcount
Current Headcount
Open Vacancies
Expected Attrition
Future Requirement
Gap
```

Example:

```text
Production Manager
Required: 2
Current: 1
Open: 1
Future Requirement: 2
Gap: 1
```

Provide:

```text
Find Candidates
```

which searches the candidate database for the missing capability.

Support planning by:

```text
Department
Position
Location
Shift
Career Level
Required Skills
Headcount
Time Horizon
```

---

# 53N. Career Path and Internal Mobility

Where employee data is available, support:

```text
Current Position
        ↓
Possible Next Positions
        ↓
Skill Gap
        ↓
Development Recommendation
```

Example:

```text
Production Engineer
        ↓
Production Supervisor
        ↓
Production Manager
```

The system should explain:

```text
Current Fit
Missing Skills
Required Experience
Recommended Development
```

Internal mobility must be treated as a recommendation, not an automatic promotion decision.

---

# 53O. Recruiter Feedback Loop

Capture human actions without automatically changing the scoring model.

When a recruiter selects a candidate that differs from the AI ordering, record:

```text
Job
AI Ranking
Candidate Selected
Human Decision
Reason
User
Timestamp
```

Possible reasons:

```text
Better interview performance
Unlisted experience
Location preference
Salary fit
Cultural / team considerations
Reference information
Incorrect AI interpretation
Other
```

Use this data for analytics and future model/rule review.

Do not automatically modify production weights based on one human decision.

---

# 53P. AI Assistants

Provide specialized assistants.

## Candidate Assistant

Examples:

```text
What are this candidate's strongest skills?
What information is missing?
Which jobs fit this candidate?
What should I verify?
Summarize the career history.
```

## Recruiter Assistant

Examples:

```text
Find suitable candidates for this job.
Why are there few qualified candidates?
Which candidates should I review first?
Find previous candidates who may fit.
```

## Job Assistant

Examples:

```text
Which requirements are difficult to satisfy?
Which skills are rare in our database?
How many candidates meet the hard requirements?
```

## Analytics Assistant

Examples:

```text
Which jobs have the largest staffing gaps?
Where is the recruitment pipeline slowing down?
What are the most common missing skills?
Which sources produce the most qualified candidates?
```

AI assistants must query authorized application services rather than receiving the entire database blindly.

---

# 53Q. Controlled AI Actions and Human Approval

AI may propose actions, but actions affecting recruitment records must use an approval workflow when appropriate.

Architecture:

```text
User Request
     ↓
AI Interpretation
     ↓
Action Proposal
     ↓
Validation
     ↓
Human Approval
     ↓
Execution
     ↓
Audit Log
```

Examples:

```text
AI proposes:
"Add Candidate A to Plant Managers Talent Pool"

[Approve] [Reject]
```

Do not allow autonomous hiring, rejection, promotion, or employment decisions.

---

# 53R. Recruitment Analytics

Extend reporting with:

```text
Candidate Quality
Source Conversion
CV → Screening
Screening → Interview
Interview → Offer
Offer → Hire
Time to Screen
Time to Hire
Job Aging
Qualified Candidate Availability
Skill Availability
Workforce Gap
Talent Pool Size
Rediscovery Rate
```

Use both counts and percentages.

Where statistically meaningful, provide:

```text
Average
Median
Trend
Period Comparison
```

Do not present unstable metrics when sample size is too small.

---

# 53S. AI and Matching Configuration

Extend configuration:

```yaml
matching:
  experience_weight: 0.25
  skills_weight: 0.25
  education_weight: 0.10
  industry_weight: 0.15
  management_weight: 0.10
  location_weight: 0.05
  language_weight: 0.05
  certification_weight: 0.05

  hard_requirement_penalty: true
  unknown_skill_penalty: false
  evidence_weight: 0.10
  semantic_weight: 0.20

talent:
  enable_rediscovery: true
  enable_talent_pools: true

ai:
  enable_candidate_assistant: true
  enable_recruiter_assistant: true
  enable_analytics_assistant: true
  require_human_approval_for_actions: true
```

Important:

`unknown_skill_penalty: false` means absence from a CV must not automatically be treated as lack of skill.

---

# 53T. Data Model Rules for AI Evidence

Never overwrite source data with AI interpretations.

Maintain separate layers:

```text
SOURCE DATA
    ↓
EXTRACTED DATA
    ↓
NORMALIZED DATA
    ↓
AI INTERPRETATION
    ↓
MATCHING RESULT
    ↓
HUMAN VERIFICATION
```

Example:

```text
CV says:
"Managed production team of 40."

Source Fact:
team_size = 40

AI Interpretation:
management_scope = large

Human Verification:
verified = true
```

The original source must remain recoverable.

---

# 53U. Privacy and Sensitive Data

Candidate information is personal data.

Do not use sensitive or protected characteristics for ranking or matching unless there is a specific lawful business requirement and appropriate safeguards.

Do not infer:

- Race
- Religion
- Political affiliation
- Sexual orientation
- Health conditions
- Disability status
- Other sensitive characteristics

from CV text.

Avoid unnecessary storage of sensitive information.

Support:

```text
Data Access Control
Data Deletion
Audit Trail
Export Control
Document Retention
```

---

# 53V. Performance Requirements for Talent Intelligence

Do not send the entire candidate database to the AI model.

Use:

```text
Database Filters
      ↓
Candidate Retrieval
      ↓
Relevant Candidate Set
      ↓
Semantic Search
      ↓
Top-K Candidates
      ↓
AI Explanation
```

Cache:

- Embeddings
- AI analyses
- Match results where inputs have not changed
- Prompt results where appropriate

Recalculate only when relevant source data changes.

---

# 53W. New Testing Requirements

Add unit and integration tests for:

```text
Candidate 360
Evidence tracking
Skill normalization
Talent Pool membership
Talent Rediscovery
Scorecard calculation
Match explanation
Unknown vs missing skill
Skill Gap calculation
Workforce Gap
Candidate → Job matching
Job → Candidate matching
Recruiter feedback
AI action approval
AI audit trail
Analytics calculations
```

Test critical cases such as:

```text
A CV does not mention a required skill.
→ Result must be Unknown, not automatically Missing.

Two CVs belong to the same person.
→ Duplicate detection must request review.

AI proposes changing a recruitment status.
→ Human approval must be required when configured.

A recruiter chooses a lower-ranked candidate.
→ Record feedback without silently changing weights.
```

---

# 54. Development Instructions

When generating the code:

1. Start with the architecture.
2. Build the database layer.
3. Build Pydantic schemas.
4. Build document processing.
5. Build AI abstraction.
6. Implement Gemini integration.
7. Implement candidate services.
8. Implement job services.
9. Implement matching engine.
10. Implement Streamlit UI.
11. Implement reports and exports.
12. Implement tests.
13. Add advanced features incrementally.

Do not skip foundational layers.

Do not create fake implementations for core functionality unless explicitly marked as placeholders.

If an external dependency is required, add it to `requirements.txt`.

---

# 55. Code Quality Standard

Every generated Python file must:

- Be syntactically valid.
- Have proper imports.
- Use type hints.
- Follow PEP 8.
- Avoid circular dependencies.
- Avoid global mutable state.
- Avoid duplicated logic.
- Have clear class responsibilities.
- Be independently testable.

Use dependency injection instead of constructing complex dependencies deep inside classes.

---

# 56. Documentation

Create a professional `README.md` containing:

- Project overview
- Features
- Architecture
- Installation
- Environment variables
- Gemini configuration
- Database configuration
- Running the application
- Project structure
- Testing
- Deployment
- Troubleshooting

Also document major classes and services.

---

# 57. Environment

Create:

```env
GEMINI_API_KEY=
DATABASE_URL=sqlite:///data/smartats.db
APP_ENV=development
LOG_LEVEL=INFO
```

Create:

```text
.env.example
```

Never commit `.env`.

---

# 58. Final Product Experience

The final user experience should feel like a modern professional ATS:

```text
┌─────────────────────────────────────────────────────────────┐
│ SMARTATS AI                                      User ▾     │
├─────────────┬───────────────────────────────────────────────┤
│ Dashboard   │ Dashboard                                     │
│             │                                               │
│ Candidates  │ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ │
│             │ │ 1,248  │ │  37    │ │  18    │ │  94    │ │
│ Jobs        │ │ CVs    │ │ Jobs   │ │Interv. │ │ New    │ │
│             │ └────────┘ └────────┘ └────────┘ └────────┘ │
│ Matching    │                                               │
│             │ Recruitment Funnel                             │
│ Interviews  │ New → Screening → Interview → Offer → Hired  │
│             │                                               │
│ Organization│ Top Candidates                                │
│             │ Ahmed        Production Manager       94%    │
│ Reports     │ Mohamed      Plant Manager             91%    │
│             │ Khaled       Operations Manager        88%    │
│ Settings    │                                               │
└─────────────┴───────────────────────────────────────────────┘
```

Use a clean professional visual language:

- Clear hierarchy
- Consistent spacing
- Professional cards
- Interactive tables
- Search and filters
- Status badges
- Progress indicators
- Interactive charts
- Responsive layout
- Clear error and empty states

Avoid excessive decoration.

---

# 59. Final Technical Objective

The completed system should behave as:

```text
                  SMARTATS AI
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
   CV Management    Job Management   Organization
        │              │              │
        ▼              ▼              ▼
   AI Extraction   Requirements    Org Structure
        │              │              │
        └──────────────┼──────────────┘
                       ▼
                Hybrid Matching
                       │
             ┌─────────┴─────────┐
             ▼                   ▼
       Candidate → Job       Job → Candidate
             │                   │
             └─────────┬─────────┘
                       ▼
                 AI Analysis
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
     Strengths      Skill Gaps     Interview
        │              │              │
        └──────────────┼──────────────┘
                       ▼
                Human Decision
```

Build the system as a real extensible software product, not as a simple Streamlit demo.

Prioritize correctness, maintainability, explainability, performance, security, and professional UX.
