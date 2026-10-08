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
.og-manager{border-color:rgba(217,119,6,.55);background:rgba(217,119,6,.08)}
.og-warn{border-color:rgba(220,38,38,.55)}
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

def _position_node(pos: dict, by_boss: dict, seen: frozenset,
                   same_dept_only: bool = True, show_dept: bool = False) -> str:
    seen = seen | {pos["id"]}
    kids = [
        c for c in by_boss.get(pos["id"], [])
        if c["id"] not in seen and (not same_dept_only or c["department_id"] == pos["department_id"])
    ]
    children = "".join(_position_node(c, by_boss, seen, same_dept_only, show_dept) for c in kids)
    jobs_note = f" · 💼 {pos['active_jobs']}" if pos["active_jobs"] else ""
    crown = "👑 " if pos.get("is_manager") else ""
    warn = " ⚠️" if pos.get("warnings") else ""
    dept_note = f' <span class="jb-muted">· 🏢 {_esc(pos["department"])}</span>' if show_dept and pos["department"] else ""
    # مسمى جذر في قسمه لكن رئيسه في قسم آخر: نعرض اسم رئيسه
    ext_note = f' <span class="jb-muted">↗ يتبع: {_esc(pos["reports_to"])}</span>' if pos.get("_ext") else ""
    classes = "og-node" + (" og-manager" if pos.get("is_manager") else "") + (" og-warn" if pos.get("warnings") else "")
    tooltip = html.escape(" | ".join(pos.get("warnings") or []), quote=True)
    node = (
        f'<div class="{classes}" title="{tooltip}"><span>{crown}👤 {_esc(pos["title"])}{warn}{dept_note}{ext_note}</span>'
        f'{gap_badge(pos["gap"])}'
        f'<span class="og-count">{pos["current"]}/{pos["required"]}{jobs_note}</span></div>'
    )
    return node + (f'<div class="og-children">{children}</div>' if children else "")


def tree_html(departments: list[dict], positions: list[dict], mode: str = "departments") -> str:
    """mode='departments': قسم ← مسمياته (الأبناء من نفس القسم فقط). mode='reporting': خطوط التبعية عبر الأقسام."""
    by_boss: dict = {}
    for pos in positions:
        by_boss.setdefault(pos["reports_to_id"], []).append(pos)

    if mode == "reporting":
        roots = by_boss.get(None, [])
        body = "".join(_position_node(p, by_boss, frozenset(), same_dept_only=False, show_dept=True) for p in roots)
        return f'<div class="jb">{body}</div>'

    dept_children: dict = {}
    for dept in departments:
        dept_children.setdefault(dept["parent_id"], []).append(dept)
    by_dept: dict = {}
    dept_of = {p["id"]: p["department_id"] for p in positions}
    for pos in positions:
        by_dept.setdefault(pos["department_id"], []).append(pos)

    def department_node(dept: dict) -> str:
        roots = []
        for p in by_dept.get(dept["id"], []):
            boss = p["reports_to_id"]
            if boss is None:
                roots.append(p)
            elif dept_of.get(boss) != dept["id"]:
                roots.append({**p, "_ext": True})  # رئيسه في قسم آخر
        body_roots = "".join(_position_node(p, by_boss, frozenset()) for p in roots)
        subs = "".join(department_node(child) for child in dept_children.get(dept["id"], []))
        manager = f' · 👑 {_esc(dept["manager"])}' if dept.get("manager") else ""
        head = (
            f'<div class="og-node og-dept"><span>🏢 {_esc(dept["name"])}{manager}</span>'
            f'<span class="og-count">🧑‍💼 {dept["positions"]} · 💼 {dept["jobs"]}</span></div>'
        )
        body = body_roots + subs
        return head + (f'<div class="og-children">{body}</div>' if body else "")

    parts = [department_node(d) for d in dept_children.get(None, [])]
    orphans = [p for p in positions if p["department_id"] is None]
    if orphans:
        parts.append('<div class="og-node og-dept"><span>🧑‍💼 مسميات بدون قسم</span></div>')
        parts.append(
            f'<div class="og-children">'
            f'{"".join(_position_node(p, by_boss, frozenset(), same_dept_only=False) for p in orphans if p["reports_to_id"] is None)}</div>'
        )
    return f'<div class="jb">{"".join(parts)}</div>'