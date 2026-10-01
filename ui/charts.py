"""بناء رسوم Plotly للوحة المعلومات. الدوال هنا لا تصل للقاعدة، تستقبل بيانات جاهزة فقط."""

import plotly.graph_objects as go

_HEIGHT = 320
_MARGIN = dict(l=10, r=10, t=40, b=10)


def _base(fig: go.Figure, title: str) -> go.Figure:
    fig.update_layout(title=title, height=_HEIGHT, margin=_MARGIN, showlegend=False)
    return fig


def funnel_chart(stages: list[tuple[str, int]], title: str = "قمع التوظيف") -> go.Figure:
    return _base(go.Figure(go.Funnel(y=[s for s, _ in stages], x=[n for _, n in stages], textinfo="value+percent initial")), title)


def bar_chart(data: dict[str, int] | list[tuple[str, int]], title: str, horizontal: bool = False) -> go.Figure:
    items = list(data.items()) if isinstance(data, dict) else list(data)
    labels, values = [k for k, _ in items], [v for _, v in items]
    if horizontal:
        fig = go.Figure(go.Bar(x=values[::-1], y=labels[::-1], orientation="h", text=values[::-1]))
    else:
        fig = go.Figure(go.Bar(x=labels, y=values, text=values))
    return _base(fig, title)


def pie_chart(data: dict[str, int], title: str) -> go.Figure:
    return _base(go.Figure(go.Pie(labels=list(data), values=list(data.values()), hole=0.45)), title)


def availability_chart(rows: list[dict], title: str = "توفر المهارات المطلوبة (الأقل توفراً)") -> go.Figure:
    skills = [r["skill"] for r in rows][::-1]
    fig = go.Figure(go.Bar(x=[r["candidates_with_skill"] for r in rows][::-1], y=skills, orientation="h"))
    return _base(fig, title)

def donut_chart(items: list[tuple[str, int, str]], center_text: str, title: str = "") -> go.Figure:
    """دونات بنص في المنتصف. items = [(التسمية، القيمة، اللون)]."""
    fig = go.Figure(go.Pie(
        labels=[label for label, _, _ in items],
        values=[value for _, value, _ in items],
        marker=dict(colors=[color for _, _, color in items]),
        hole=0.68, sort=False, textinfo="none",
    ))
    fig.update_layout(
        title=title, height=220, showlegend=False,
        margin=dict(l=0, r=0, t=30 if title else 0, b=0),
        annotations=[dict(text=center_text, x=0.5, y=0.5, font_size=22, showarrow=False)],
    )
    return fig