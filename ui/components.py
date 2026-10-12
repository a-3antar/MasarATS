
import html
from collections.abc import Iterable

import streamlit as st

from ui.navigation import go_to
from ui.theme import COLORS, score_color

_PCT_MAX = 100.0
_DEFAULT_AVATAR_PX = 44


def _pct(value) -> float:
    return max(0.0, min(_PCT_MAX, float(value or 0)))


def badge(text: str, color: str | None = None) -> str:
    return f'<span class="ui-badge" style="--c:{color or COLORS["neutral"]}">{html.escape(text)}</span>'


def chip(text: str) -> str:
    return f'<span class="ui-chip">{html.escape(text)}</span>'


def chips(items: Iterable[str] | None, empty: str = "") -> str:
    return "".join(chip(i) for i in items or []) or empty


def score_bar(value: float | None) -> str:
    pct = _pct(value)
    color = score_color(pct)
    return (
        f'<div class="ui-score"><div class="ui-track"><div class="ui-fill" '
        f'style="width:{pct}%;background:{color}"></div></div>'
        f'<span class="ui-score-val" style="color:{color}">{pct:g}%</span></div>'
    )


def labeled_bar(label: str, value: float | None) -> str:
    pct = _pct(value)
    return (
        f'<div class="ui-bar-row"><div class="ui-bar-head"><span>{html.escape(label)}</span>'
        f'<span>{pct:g}%</span></div><div class="ui-track"><div class="ui-fill" '
        f'style="width:{pct}%;background:{score_color(pct)}"></div></div></div>'
    )


def score_ring(value: float | None, label: str, size: int = 64) -> str:
    pct = _pct(value)
    return (
        f'<div class="ui-ring-wrap"><div class="ui-ring-box" style="width:{size}px;height:{size}px">'
        f'<div class="ui-ring" style="--p:{pct};--c:{score_color(pct)}"></div>'
        f'<span class="ui-ring-val" style="font-size:{size // 4}px">{pct:g}</span></div>'
        f'<div class="ui-ring-label">{html.escape(label)}</div></div>'
    )


def initials(name: str | None) -> str:
    parts = [p for p in (name or "").split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "؟"


def avatar(name: str | None, photo_uri: str | None = None, size: int = _DEFAULT_AVATAR_PX) -> str:
    inner = f'<img src="{photo_uri}" alt="">' if photo_uri else html.escape(initials(name))
    return f'<div class="ui-avatar" style="--s:{size}px">{inner}</div>'


def empty_state(
    icon: str,
    title: str,
    message: str,
    actions: list[tuple[str, str, dict | None]],
    key: str,
) -> None:
    with st.container(border=True):
        st.markdown(f"### {icon} {title}")
        st.write(message)
        if not actions:
            return
        for index, (column, (label, page, state)) in enumerate(zip(st.columns(len(actions)), actions)):
            column.button(
                label, key=f"{key}_{index}", on_click=go_to, args=(page,), kwargs=state or {},
                type="primary" if index == 0 else "secondary", width="stretch",
            )
