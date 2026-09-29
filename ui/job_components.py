"""مولّدات HTML صغيرة لصفحة الوظائف (بطاقات المؤشرات، الشارات، القمع...). لا تصل للقاعدة."""

import html
from datetime import datetime, timezone

import streamlit as st

_STATUS_COLORS = {"Open": "#16a34a", "Draft": "#64748b", "On Hold": "#d97706", "Closed": "#dc2626"}
_SECONDS_PER_MINUTE, _MINUTES_PER_HOUR, _HOURS_PER_DAY = 60, 60, 24
_DAYS_PER_MONTH, _DAYS_PER_YEAR = 30, 365

_CSS = """<style>
.jb{direction:rtl;text-align:right}
.jb-kpi{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:14px 16px;
  border:1px solid rgba(128,128,128,.25);border-radius:12px;background:rgba(128,128,128,.06)}
.jb-kpi-main{display:flex;align-items:center;gap:12px}
.jb-kpi-icon{font-size:1.4rem;width:44px;height:44px;display:grid;place-items:center;border-radius:12px;
  background:rgba(37,99,235,.14)}
.jb-kpi-label{font-size:.8rem;opacity:.75}
.jb-kpi-value{font-size:1.7rem;font-weight:700;line-height:1.2}
.jb-kpi-sub{font-size:.72rem;font-weight:600}
.jb-up{color:#16a34a}.jb-down{color:#dc2626}.jb-muted{opacity:.65}
.jb-badge{display:inline-block;padding:2px 12px;border-radius:999px;font-size:.78rem;font-weight:700;
  color:var(--c);border:1px solid var(--c);background:color-mix(in srgb,var(--c) 14%,transparent)}
.jb-chip{display:inline-block;padding:3px 10px;margin:0 0 6px 6px;border-radius:999px;font-size:.75rem;
  border:1px solid rgba(37,99,235,.35);background:rgba(37,99,235,.1)}
.jb-title{font-size:1.1rem;font-weight:700;margin-bottom:6px}
.jb-section{font-size:.95rem;font-weight:700;margin:14px 0 6px}
.jb-row{display:flex;justify-content:space-between;gap:10px;padding:5px 0;font-size:.85rem;
  border-bottom:1px dashed rgba(128,128,128,.2)}
.jb-row-label{opacity:.65}
.jb-funnel{display:flex;align-items:center;justify-content:space-between;gap:4px}
.jb-fstage{text-align:center}
.jb-fcircle{display:grid;place-items:center;border-radius:50%;font-weight:700;margin:0 auto;color:#2563eb;
  background:rgba(37,99,235,.16);border:2px solid rgba(37,99,235,.35)}
.jb-flabel{font-size:.68rem;opacity:.75;margin-top:4px}
.jb-farrow{opacity:.5}
.jb-dist{display:flex;height:10px;border-radius:999px;overflow:hidden;background:rgba(128,128,128,.22)}
.jb-legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:.75rem;margin-top:6px}
.jb-dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-left:5px}
.jb-card-meta{font-size:.78rem;opacity:.75;margin:2px 0 8px}
.jb-card-nums{display:flex;gap:18px;font-size:.8rem;margin-top:8px}
</style>"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def relative_time(value: datetime | None) -> str:
    """وقت نسبي بالعربية (منذ ساعتين...)."""
    if value is None:
        return "-"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    seconds = int((datetime.now(timezone.utc) - value).total_seconds())
    minutes = seconds // _SECONDS_PER_MINUTE
    hours = minutes // _MINUTES_PER_HOUR
    days = hours // _HOURS_PER_DAY
    if minutes < 1:
        return "الآن"
    if hours < 1:
        return f"منذ {minutes} دقيقة"
    if days < 1:
        return f"منذ {hours} ساعة"
    if days < _DAYS_PER_MONTH:
        return f"منذ {days} يوم"
    if days < _DAYS_PER_YEAR:
        return f"منذ {days // _DAYS_PER_MONTH} شهر"
    return f"منذ {days // _DAYS_PER_YEAR} سنة"


def sparkline(values: list[int], color: str = "#16a34a", width: int = 84, height: int = 32) -> str:
    if len(values) < 2:
        return ""
    peak = max(values) or 1
    step = width / (len(values) - 1)
    points = " ".join(f"{i * step:.1f},{height - 2 - v / peak * (height - 4):.1f}" for i, v in enumerate(values))
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{points}"/></svg>'
    )


def kpi_card(icon: str, label: str, value: int, sub: str = "", tone: str = "muted", trend: list[int] | None = None) -> str:
    spark = sparkline(trend) if trend else ""
    return (
        f'<div class="jb jb-kpi"><div class="jb-kpi-main"><div class="jb-kpi-icon">{icon}</div>'
        f'<div><div class="jb-kpi-label">{html.escape(label)}</div><div class="jb-kpi-value">{value}</div>'
        f'<div class="jb-kpi-sub jb-{tone}">{html.escape(sub)}</div></div></div>{spark}</div>'
    )


def status_badge(status: str, label: str) -> str:
    color = _STATUS_COLORS.get(status, "#64748b")
    return f'<span class="jb-badge" style="--c:{color}">{html.escape(label)}</span>'


def skill_chips(skills: list[str]) -> str:
    if not skills:
        return '<span class="jb-muted">غير محدد</span>'
    return "".join(f'<span class="jb-chip">{html.escape(s)}</span>' for s in skills)


def info_rows(rows: list[tuple[str, str]]) -> str:
    body = "".join(
        f'<div class="jb-row"><span class="jb-row-label">{html.escape(label)}</span>'
        f'<span>{html.escape(value or "-")}</span></div>'
        for label, value in rows
    )
    return f'<div class="jb">{body}</div>'


def funnel_html(stages: list[tuple[str, int]], size: int = 54) -> str:
    parts = []
    for index, (label, value) in enumerate(stages):
        if index:
            parts.append('<span class="jb-farrow">←</span>')
        parts.append(
            f'<div class="jb-fstage"><div class="jb-fcircle" style="width:{size}px;height:{size}px;'
            f'font-size:{size // 3.4:.0f}px">{value}</div><div class="jb-flabel">{html.escape(label)}</div></div>'
        )
    return f'<div class="jb jb-funnel">{"".join(parts)}</div>'


def distribution_html(high: int, medium: int, low: int) -> str:
    total = high + medium + low
    segments = [(high, "#2563eb", "عالية (80–100%)"), (medium, "#60a5fa", "متوسطة (50–79%)"), (low, "#cbd5e1", "منخفضة (0–49%)")]
    bar = "".join(
        f'<div style="width:{count / total * 100:.1f}%;background:{color}"></div>'
        for count, color, _ in segments if total and count
    )
    legend = "".join(
        f'<span><span class="jb-dot" style="background:{color}"></span>{label}: {count}</span>'
        for count, color, label in segments
    )
    return f'<div class="jb"><div class="jb-dist">{bar}</div><div class="jb-legend">{legend}</div></div>'


def job_card_html(title: str, subtitle: str, badge: str, experience: str, applicants: int, qualified: int) -> str:
    return (
        f'<div class="jb"><div class="jb-title">{html.escape(title)}</div>'
        f'<div class="jb-card-meta">{html.escape(subtitle)}</div>{badge}'
        f'<div class="jb-card-nums"><span>⏳ {html.escape(experience)}</span>'
        f'<span>👥 {applicants}</span><span>✅ {qualified}</span></div></div>'
    )