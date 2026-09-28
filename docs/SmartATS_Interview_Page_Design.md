# SmartATS — Interview Management & Evaluation Page

## 1. Core Concept

The interview should be an independent entity in SmartATS:

```text
Interview
│
├── Job / الوظيفة
├── Candidate / المرشح
├── Interviewer(s) / المقابلون
├── Date & Time / الموعد
├── Interview Type / نوع المقابلة
├── Questions / الأسئلة
│   ├── Question
│   ├── Candidate Answer
│   ├── AI Analysis
│   ├── Score
│   └── Interviewer Notes
├── Competencies / الكفاءات
└── Final Evaluation / التقييم النهائي
```

The page should be designed as an **Interview Workspace**, not as a long single form.

---

## 2. Proposed Page Layout

The page is divided into three main areas:

1. Interview Header
2. Candidate + Question Workspace
3. Final Evaluation

Conceptually:

```text
┌──────────────────────────────────────────────────────────────┐
│  New Interview                         [Save] [Complete]      │
├──────────────────────────────────────────────────────────────┤
│  Interview Information                                        │
│  Job | Candidate | Date & Time | Type | Interviewer | Status │
├──────────────────────────────────────────────────────────────┤
│  Candidate Information       │  Interview Workspace            │
│                              │                               │
│  Candidate Card              │  Question 01                  │
│  CV / Experience             │  Candidate Answer             │
│  ATS Match                   │  AI Analysis                  │
│                              │  Score                         │
├──────────────────────────────────────────────────────────────┤
│  Final Evaluation                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Interview Header

Required fields:

| Field | Purpose |
|---|---|
| Interview ID | Unique interview identifier |
| Job | Select the target job |
| Candidate | Select the candidate |
| Date | Interview date |
| Time | Interview time |
| Interview Type | HR / Technical / Managerial / Final |
| Interviewer | Person conducting the interview |
| Status | Scheduled / In Progress / Completed / Cancelled |

Example:

```text
INT-2026-0045
Production Manager
Ahmed Ali
28 Sep 2026 — 10:00 AM
Technical Interview
Interviewer: HR + Operations Manager
Status: In Progress
```

---

## 4. Job and Candidate Selection

After selecting a job, SmartATS can show suitable candidates:

```text
Recommended Candidates

Ahmed Ali        Match 92%
Mohamed Hassan   Match 87%
Mahmoud Ahmed    Match 81%
```

The user selects the candidate.

This connects the interview directly to the ATS matching system.

---

## 5. Candidate Card

The candidate should be visible during the interview without repeatedly opening the CV.

Example:

```text
┌───────────────────────────┐
│       Ahmed Ali            │
│                           │
│ Production Engineer       │
│ 9 Years Experience        │
│                           │
│ Current: Production Eng.  │
│ ATS Match       92%       │
│                           │
│ [View CV] [Candidate]     │
└───────────────────────────┘
```

---

## 6. Question Management

Do not display all questions as one long form.

Use a question navigator:

```text
Questions

01 ●
02 ●
03 ●
04 ○
05 ○
06 ○
07 ○
08 ○
```

Display:

```text
Question 03 of 10
```

Navigation:

```text
[Previous]    [Next]
```

---

## 7. Question Types

The system should support multiple question types.

### A. Text Question

```text
What is your experience in production team management?
```

### B. Multiple Choice

```text
How would you handle a decrease in productivity?

○ Root Cause Analysis
○ Increase manpower
○ Increase working hours
○ Other
```

### C. Rating Question

```text
How would you rate your Power BI skills?

1  2  3  4  5
```

### D. Competency-Based Question

Example competency:

```text
Leadership
```

Question:

> Describe a situation where you had to deal with an underperforming employee.

---

## 8. Candidate Answer

The answer area should be large and easy to use:

```text
Candidate Answer

┌─────────────────────────────────────────┐
│                                         │
│ Candidate's answer...                   │
│                                         │
└─────────────────────────────────────────┘

[Record Answer]   [Analyze with AI]
```

Future support can include:

- Voice recording
- Speech-to-text
- Automatic transcription

---

## 9. AI Answer Analysis

AI analysis should be a core feature.

Example:

```text
AI Analysis

Technical Knowledge       82%
Problem Solving           90%
Communication             72%
Practical Experience      88%

Overall Answer Score      83/100
```

### Strengths

```text
✓ Clear practical experience
✓ Uses real examples
✓ Demonstrates a structured problem-solving approach
```

### Points to Verify

```text
! Did not explain how results were measured
! Management answer was relatively general
```

### AI Suggested Follow-up

```text
" You mentioned that productivity increased by 15%.
   How did you measure this improvement? "

[Ask Question]
```

The purpose is to assist the interviewer rather than replace the interviewer.

---

## 10. Question-Level Evaluation

Each question should support structured scoring.

Example:

| Criterion | Score |
|---|---:|
| Technical Accuracy | 8/10 |
| Depth | 7/10 |
| Practical Experience | 9/10 |
| Communication | 8/10 |
| **Question Score** | **8.0/10** |

Recommended evaluation flow:

```text
AI Score
   ↓
Interviewer Score
   ↓
Final Score
```

Human evaluation should remain available and should not simply be replaced by AI.

---

## 11. Competency Evaluation

Do not rely only on question scores.

Questions should be mapped to competencies.

Example for Production Manager:

| Competency | Weight |
|---|---:|
| Production Management | 25% |
| Technical Knowledge | 20% |
| Leadership | 20% |
| Problem Solving | 15% |
| Planning | 10% |
| Communication | 10% |

Question mapping:

```text
Question 1 → Production Management
Question 2 → Problem Solving
Question 3 → Leadership
Question 4 → Technical Knowledge
```

The system calculates competency scores.

Example:

```text
Production Management    88
Technical Knowledge      91
Leadership               76
Problem Solving          84
Planning                 80
Communication            82
────────────────────────────
Overall                  84
```

---

## 12. Final Evaluation

The bottom section should provide a clear summary:

```text
FINAL EVALUATION

Overall Score
84 / 100

Technical       91
Experience      88
Leadership      76
Problem Solving 84
Communication   82
Cultural Fit    80
```

Possible workflow decisions:

```text
○ Continue to next stage
○ Additional interview
○ Hold
○ Not selected
```

The final decision remains with the user.

---

## 13. Interviewer Notes

A dedicated notes area should be available:

```text
Interviewer Notes

┌─────────────────────────────────────────┐
│                                         │
│                                         │
└─────────────────────────────────────────┘
```

This allows interviewers to record observations that should not be inferred by AI.

---

## 14. Candidate Interview Timeline

The interview page should connect to the candidate's ATS journey:

```text
Candidate Journey

✓ CV Received
✓ Screening
✓ Shortlisted
✓ Interview 1
● Interview 2
○ Final Decision
○ Offer
```

This gives the interviewer the candidate's current recruitment stage.

---

## 15. Previous Interviews

Show previous interviews for the same candidate:

| Date | Type | Interviewer | Score |
|---|---|---|---:|
| 20 Sep | HR | Ahmed | 82 |
| 24 Sep | Technical | Mohamed | 87 |
| 28 Sep | Managerial | Ahmed | 84 |

This avoids repeating questions and helps the interviewer understand the recruitment history.

---

## 16. Interview Templates

Interviewers should not manually create all questions every time.

Create reusable templates.

Example:

```text
Production Manager Interview
```

Template sections:

```text
Technical Questions
Leadership Questions
Planning Questions
Problem-Solving Questions
Behavioral Questions
```

When creating an interview:

```text
Select Template

[Production Manager Interview ▼]
```

Questions are loaded automatically.

The interviewer can then add, remove, or reorder questions.

---

## 17. Question Bank

Create a reusable question library.

Example:

| Question | Category | Competency | Difficulty |
|---|---|---|---|
| How do you handle low OEE? | Technical | Production | High |
| How do you handle an underperforming employee? | Behavioral | Leadership | Medium |
| How do you plan production? | Technical | Planning | High |

This allows questions to be reused across jobs and interviews.

---

## 18. AI Question Generator

For a selected job, SmartATS can generate an interview structure based on:

- Job Description
- Required Skills
- Candidate CV
- Candidate Experience
- Interview Stage

Example:

```text
Production Manager

10 Technical Questions
5 Leadership Questions
3 Behavioral Questions
2 Problem-Solving Questions
```

This can make SmartATS an AI Interview Assistant rather than only an interview record system.

---

## 19. Candidate Comparison

Candidate comparison should be a separate page, not part of the main interview workspace.

Example:

| Competency | Ahmed | Mohamed | Mahmoud |
|---|---:|---:|---:|
| Technical | 91 | 84 | 79 |
| Leadership | 76 | 90 | 81 |
| Experience | 88 | 82 | 86 |
| Problem Solving | 84 | 78 | 89 |
| Interview | 84 | 83 | 82 |

This provides factual comparison data for the user's decision.

---

## 20. Recommended Development Phases

### Phase 1 — Core Interview

```text
Job
 ↓
Candidate
 ↓
Date / Time
 ↓
Interview
 ↓
Questions
 ↓
Answers
 ↓
Manual Score
 ↓
Final Evaluation
```

### Phase 2 — AI

```text
Answer
 ↓
AI Analysis
 ↓
Strengths
Weaknesses
Suggested Follow-up
AI Score
```

### Phase 3 — Advanced ATS

```text
CV
 ↓
Job Matching
 ↓
Interview
 ↓
Competency Analysis
 ↓
Candidate Comparison
 ↓
Hiring Decision
```

---

## 21. Recommended SmartATS Architecture

```text
                    SMART ATS
                        │
        ┌───────────────┼────────────────┐
        ↓               ↓                ↓
    Candidates         Jobs          Interviews
        │               │                │
        └──────────── Matching ──────────┘
                        │
                        ↓
                   Interview
                        │
              ┌─────────┴─────────┐
              ↓                   ↓
          Questions             Answers
                                  │
                                  ↓
                              AI Analysis
                                  │
                                  ↓
                            Competencies
                                  │
                                  ↓
                              Evaluation
                                  │
                                  ↓
                         Candidate Decision
```

---

# 22. Design Decisions to Finalize Before Coding

The following points should be decided before implementing the interface:

1. **Interview stages**
   - Can one candidate have HR → Technical → Managerial → Final interviews?

2. **Question source**
   - Manual questions
   - Question Bank
   - AI-generated questions
   - Combination of all three

3. **AI analysis trigger**
   - Automatic after every answer
   - Manual `Analyze` button
   - Both

4. **Scoring scale**
   - 5 points
   - 10 points
   - 100 points

5. **Competency model**
   - Use competencies and weights for every job
   - Or use a simpler general scoring model

6. **Audio**
   - Text answers only
   - Voice recording + Speech-to-Text

7. **AI follow-up**
   - Allow AI to generate follow-up questions based on the candidate's answer

8. **Final decision**
   - Human decision only
   - AI provides supporting analysis but does not make the hiring decision

---

# 23. Recommended Data Model

The interview should not be stored as one large record.

Use separate entities:

```text
Interview
    │
    ├── InterviewQuestion
    │       │
    │       └── InterviewAnswer
    │                │
    │                └── AIAnalysis
    │
    └── CompetencyEvaluation
```

This architecture makes the system easier to:

- Analyze
- Compare candidates
- Generate reports
- Track interview history
- Change interview templates
- Add AI features
- Build Power BI dashboards later

---

# Final Recommendation

The main page should be designed as an **Interview Workspace**, with:

**Header → Candidate Context → Question → Answer → AI Analysis → Human Score → Competency Score → Final Evaluation**

The most important architectural decision is to keep **Interview, Questions, Answers, AI Analysis, and Competency Evaluations as separate entities** rather than storing the interview as one record.
