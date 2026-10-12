
import streamlit as st

from core.constants import SCORE_GOOD, SCORE_MID

COLORS: dict[str, str] = {
    "primary": "#2563eb",
    "success": "#16a34a",
    "warning": "#d97706",
    "danger": "#dc2626",
    "neutral": "#64748b",
    "info": "#3b82f6",
}

STAGE_COLORS: dict[str, str] = {
    "New": "#64748b", "Screening": "#3b82f6", "Shortlisted": "#d9a21b",
    "Interview": "#f59e0b", "Offer": "#d9487a", "Hired": "#16a34a", "Rejected": "#b91c1c",
}
STAGE_LABELS: dict[str, str] = {
    "New": "جديد", "Screening": "الفرز", "Shortlisted": "القائمة المختصرة",
    "Interview": "المقابلة", "Offer": "العرض", "Hired": "التعيين", "Rejected": "مرفوض",
}


def score_color(value: float) -> str:
    if value >= SCORE_GOOD:
        return COLORS["success"]
    return COLORS["warning"] if value >= SCORE_MID else COLORS["danger"]


_CSS = f"""
<style>
:root {{
  --ats-primary: {COLORS["primary"]};
  --ats-success: {COLORS["success"]};
  --ats-warning: {COLORS["warning"]};
  --ats-danger: {COLORS["danger"]};
  --ats-neutral: {COLORS["neutral"]};
  --ats-border: rgba(128,128,128,.25);
  --ats-surface: rgba(128,128,128,.06);
  --ats-radius: 12px;
}}

/* خط واضح للعربية والإنجليزية */
html, body, [class*="css"], .stApp {{
  font-family: "Segoe UI", "Tahoma", "Cairo", "Noto Sans Arabic", Arial, sans-serif;
}}

/* محاذاة النصوص لليمين (النص فقط، بدون قلب ترتيب الأعمدة) */
.stMarkdown p, .stMarkdown li, .stCaption, label, h1, h2, h3, h4, h5 {{
  text-align: right;
}}

/* مساحة الصفحة */
[data-testid="stMainBlockContainer"] {{
  padding-top: 2rem;
  max-width: 1600px;
}}

/* العناوين */
h1, h2, h3 {{ font-weight: 700; letter-spacing: 0; }}
h2 {{ padding-bottom: .35rem; border-bottom: 2px solid var(--ats-primary); display: inline-block; }}

/* البطاقات (الحاويات ذات الحدود) */
[data-testid="stVerticalBlockBorderWrapper"] {{
  border-radius: var(--ats-radius);
  border-color: var(--ats-border);
  background: var(--ats-surface);
}}

/* مؤشرات st.metric كبطاقات */
[data-testid="stMetric"] {{
  padding: 12px 16px;
  border: 1px solid var(--ats-border);
  border-radius: var(--ats-radius);
  background: var(--ats-surface);
}}
[data-testid="stMetricLabel"] {{ opacity: .75; font-size: .8rem; }}
[data-testid="stMetricValue"] {{ font-weight: 700; font-size: 1.6rem; }}

/* الأزرار */
.stButton > button, .stDownloadButton > button, .stLinkButton > a {{
  border-radius: 8px;
  font-weight: 600;
  min-height: 2.25rem;
  transition: transform .08s ease, box-shadow .15s ease;
}}
.stButton > button:hover, .stDownloadButton > button:hover {{
  box-shadow: 0 2px 8px rgba(0,0,0,.18);
  transform: translateY(-1px);
}}

/* الحقول */
.stTextInput input, .stTextArea textarea, .stNumberInput input,
[data-baseweb="select"] > div {{
  border-radius: 8px;
}}

/* التبويبات */
.stTabs [data-baseweb="tab-list"] {{ gap: 4px; border-bottom: 1px solid var(--ats-border); }}
.stTabs [data-baseweb="tab"] {{ padding: 8px 16px; border-radius: 8px 8px 0 0; font-weight: 600; }}
.stTabs [aria-selected="true"] {{ color: var(--ats-primary); }}

/* الجداول */
[data-testid="stDataFrame"] {{
  border: 1px solid var(--ats-border);
  border-radius: var(--ats-radius);
  overflow: hidden;
}}

/* expander */
[data-testid="stExpander"] {{
  border-radius: var(--ats-radius);
  border-color: var(--ats-border);
}}

/* الشريط الجانبي */
[data-testid="stSidebar"] {{ border-inline-end: 1px solid var(--ats-border); }}
[data-testid="stSidebar"] [role="radiogroup"] label {{
  padding: 6px 10px;
  border-radius: 8px;
  margin-bottom: 2px;
}}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {{ background: var(--ats-surface); }}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {{
  background: color-mix(in srgb, var(--ats-primary) 14%, transparent);
  font-weight: 700;
}}

/* التنبيهات */
[data-testid="stAlert"] {{ border-radius: var(--ats-radius); }}

/* ===== مكوّنات مشتركة (المرحلة B): تقابل ui/components.py ===== */

/* شارة حالة */
.ui-badge {{
  display: inline-block; padding: 2px 12px; border-radius: 999px;
  font-size: .78rem; font-weight: 700; white-space: nowrap;
  color: var(--c); border: 1px solid var(--c);
  background: color-mix(in srgb, var(--c) 14%, transparent);
}}

/* شريحة (مهارة / فلتر) */
.ui-chip {{
  display: inline-block; padding: 3px 10px; margin: 0 0 6px 6px; border-radius: 999px;
  font-size: .75rem; border: 1px solid rgba(37,99,235,.35); background: rgba(37,99,235,.1);
}}

/* شريط الدرجة */
.ui-track {{ height: 7px; border-radius: 999px; background: rgba(128,128,128,.22); overflow: hidden; }}
.ui-fill {{ height: 100%; border-radius: 999px; }}
.ui-score {{ display: flex; align-items: center; gap: 8px; margin: 10px 0 4px; }}
.ui-score .ui-track {{ flex: 1; }}
.ui-score-val {{ font-size: .8rem; font-weight: 700; min-width: 44px; text-align: end; }}

/* شريط بعنوان (تفصيل معيار) */
.ui-bar-row {{ margin-bottom: 8px; }}
.ui-bar-head {{ display: flex; justify-content: space-between; font-size: .76rem; margin-bottom: 3px; }}

/* حلقة الدرجة */
.ui-ring-wrap {{ display: flex; flex-direction: column; align-items: center; gap: 6px; min-width: 84px; }}
.ui-ring-box {{ position: relative; display: grid; place-items: center; }}
.ui-ring {{
  position: absolute; inset: 0; border-radius: 50%;
  background: conic-gradient(var(--c) calc(var(--p) * 1%), rgba(128,128,128,.22) 0);
  -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 7px), #000 calc(100% - 6px));
  mask: radial-gradient(farthest-side, transparent calc(100% - 7px), #000 calc(100% - 6px));
}}
.ui-ring-val {{ position: relative; font-weight: 700; }}
.ui-ring-label {{ font-size: .75rem; opacity: .8; text-align: center; }}

/* الصورة الرمزية (المقاس عبر --s) */
.ui-avatar {{
  width: var(--s); height: var(--s); flex: 0 0 var(--s); border-radius: 50%; overflow: hidden;
  display: grid; place-items: center; font-weight: 700; font-size: calc(var(--s) * .36); color: #fff;
  background: linear-gradient(135deg, #14b8a6, #3b82f6); border: 2px solid rgba(255,255,255,.25);
}}
.ui-avatar img {{ width: 100%; height: 100%; object-fit: cover; }}
</style>
"""

def inject_theme() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
