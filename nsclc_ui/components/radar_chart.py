"""
5-Modality Radar Chart component.
"""

import plotly.graph_objects as go
from dash import dcc

from nsclc_ui.layout.theme import COLORS

_MODALITIES = ["Drug", "ADC", "PROTAC", "Glue", "RLT"]
_KEYS = ["drug_score", "adc_score", "protac_score", "glue_score", "rlt_score"]


def radar_chart(compound: dict, height: int = 280):
    """Render a 5-axis radar chart for modality scores."""
    values = [compound.get(k, 0) for k in _KEYS]
    values_closed = values + [values[0]]  # close the polygon
    labels_closed = _MODALITIES + [_MODALITIES[0]]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values_closed,
        theta=labels_closed,
        fill="toself",
        fillcolor="rgba(77, 171, 247, 0.15)",
        line=dict(color=COLORS["accent"], width=2),
        marker=dict(size=6, color=COLORS["accent"]),
        text=[f"{v:.3f}" for v in values_closed],
        textposition="top center",
        textfont=dict(size=9, color=COLORS["text_primary"]),
        mode="lines+markers+text",
    ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True, range=[0, 1],
                tickfont=dict(size=8, color=COLORS["text_tertiary"]),
                gridcolor=COLORS["border"],
            ),
            angularaxis=dict(
                tickfont=dict(size=10, color=COLORS["text_secondary"]),
                gridcolor=COLORS["border"],
            ),
            bgcolor="rgba(0,0,0,0)",
        ),
        showlegend=False,
        height=height,
        margin=dict(l=40, r=40, t=20, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        font_color=COLORS["text_primary"],
    )

    return dcc.Graph(figure=fig, config={"displayModeBar": False}, style={"height": f"{height}px"})
