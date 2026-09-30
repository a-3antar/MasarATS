"""مولّدات HTML لصفحة الهيكل التنظيمي بنفس لغة تصميم صفحة الوظائف (ui/job_components.py). لا تصل للقاعدة."""

import html

import streamlit as st

from ui import job_components

_COLOR_OK, _COLOR_WARN, _COLOR_BAD = "#16a34a", "#d97706", "#dc2626"
_GOOD_PCT, _MID_PCT = 75.0, 50.0
_FULL_PCT = 100.0

_CSS = """<style>
.og-bar{height:8px;border-radius:999px;background:rgba(128,128,128,.22);overflow:hidden}
.og-bar-fill{height:100%;border-radius:999px}
.og-bar-meta{display:flex;justify-content:space-between;font-size:.74rem;margin-top:4px;opacity:.8}
.og-node{display:flex;align-items:center;gap:8px;padding:6px 10px;margin:3px 0;border-radius:10px;
  border:1px solid rgba(128,128,128,.22);background:rgba(128,128,128,.05);font-size:.85rem}
.og-dept{font-weight:700;background:rgba(37,99,235,.10);border-color:rgba(37,99,235,.35)}
.og-count{margin-inline-start:auto;font-size:.72rem;opacity:.75}
.og-children{margin-inline-start:22px;padding-inline-start:10px;border-inline-start:2px solid rgba(128,128,128,.25)}
.og-score{margin-bottom:10px}
</style>"""


def inject_css() -> None:
    job_components.inject_css()
    st.markdown(_CSS, unsafe_allow_html=True)


def _esc(value: str | None) -> str:
    return html.escape(value or "")


def gap_badge(gap: int) -> str:
    """شارة الفجوة: فجوة (أحمر)، مكتمل (أخضر)، زيادة عن المطلوب (برتقالي)."""
    if gap > 0:
        color, label = _COLOR_BAD, f"فجوة {gap}"
    elif gap < 0:
        color, label = _COLOR_WARN, f"زيادة {-gap}"
    else:
        color, label = _COLOR_OK, "مكتمل"
    return f'<span class="jb-badge" style="--c:{color}">{html.escape(label)}</span>'


def headcount_bar(current: int, required: int) -> str:
    pct = min(current / required * 100, _FULL_PCT) if required else _FULL_PCT
    color = _COLOR_OK if pct >= _FULL_PCT else _COLOR_WARN if pct >= _MID_PCT else _COLOR_BAD
    return (
        f'<div class="jb"><div class="og-bar"><div class="og-bar-fill" style="width:{pct:.0f}%;background:{color}"></div></div>'
        f'<div class="og-bar-meta"><span>الحالي {current} / المطلوب {required}</span><span>{pct:.0f}%</span></div></div>'
    )


def score_row(name: str, subtitle: str, score: float) -> str:
    pct = max(0.0, min(_FULL_PCT, float(score)))
    color = _COLOR_OK if pct >= _GOOD_PCT else _COLOR_WARN if pct >= _MID_PCT else _COLOR_BAD
    return (
        f'<div class="jb og-score"><div class="jb-row"><span><b>{_esc(name)}</b> '
        f'<span class="jb-muted">{_esc(subtitle)}</span></span>'
        f'<span style="color:{color};font-weight:700">{pct:g}%</span></div>'
        f'<div class="og-bar"><div class="og-bar-fill" style="width:{pct}%;background:{color}"></div></div></div>'
    )


def _position_node(pos: dict, by_boss: dict, seen: frozenset) -> str:
    seen = seen | {pos["id"]}
    children = "".join(
        _position_node(child, by_boss, seen) for child in by_boss.get(pos["id"], []) if child["id"] not in seen
    )
    jobs_note = f" · 💼 {pos['active_jobs']}" if pos["active_jobs"] else ""
    node = (
        f'<div class="og-node"><span>👤 {_esc(pos["title"])}</span>{gap_badge(pos["gap"])}'
        f'<span class="og-count">{pos["current"]}/{pos["required"]}{jobs_note}</span></div>'
    )
    return node + (f'<div class="og-children">{children}</div>' if children else "")


def tree_html(departments: list[dict], positions: list[dict]) -> str:
    """شجرة الأقسام والمسميات: المسميات الجذرية تحت قسمها، والتابعون تحت مسمى مديرهم."""
    dept_children: dict = {}
    for dept in departments:
        dept_children.setdefault(dept["parent_id"], []).append(dept)
    by_dept: dict = {}
    by_boss: dict = {}
    for pos in positions:
        by_dept.setdefault(pos["department_id"], []).append(pos)
        by_boss.setdefault(pos["reports_to_id"], []).append(pos)

    def department_node(dept: dict) -> str:
        roots = "".join(
            _position_node(p, by_boss, frozenset()) for p in by_dept.get(dept["id"], []) if p["reports_to_id"] is None
        )
        subs = "".join(department_node(child) for child in dept_children.get(dept["id"], []))
        head = (
            f'<div class="og-node og-dept"><span>🏢 {_esc(dept["name"])}</span>'
            f'<span class="og-count">🧑‍💼 {dept["positions"]} · 💼 {dept["jobs"]}</span></div>'
        )
        body = roots + subs
        return head + (f'<div class="og-children">{body}</div>' if body else "")

    parts = [department_node(d) for d in dept_children.get(None, [])]
    orphans = [p for p in positions if p["department_id"] is None and p["reports_to_id"] is None]
    if orphans:
        parts.append('<div class="og-node og-dept"><span>🧑‍💼 مسميات بدون قسم</span></div>')
        parts.append(f'<div class="og-children">{"".join(_position_node(p, by_boss, frozenset()) for p in orphans)}</div>')
    return f'<div class="jb">{"".join(parts)}</div>'