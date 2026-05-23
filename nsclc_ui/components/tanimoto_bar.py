"""
NSCLC Insight Engine — Inline Tanimoto similarity bar for table cells.
"""

from dash import html
import dash_mantine_components as dmc

from nsclc_ui.layout.theme import COLORS


def tanimoto_bar(value: float):
    """Compact inline bar showing a 0–1 similarity score.

    Parameters
    ----------
    value : float
        Tanimoto coefficient in [0, 1].
    """
    pct = max(0.0, min(1.0, value)) * 100

    track = html.Div(
        html.Div(
            style={
                "width": f"{pct}%",
                "height": "100%",
                "background": COLORS["warning_text"],
                "borderRadius": "2px",
            },
        ),
        style={
            "width": "50px",
            "height": "6px",
            "background": COLORS["bg_tertiary"],
            "borderRadius": "2px",
            "overflow": "hidden",
        },
    )

    label = dmc.Text(
        f"{value:.2f}",
        size="xs",
        style={
            "fontSize": "11px",
            "fontVariantNumeric": "tabular-nums",
            "color": COLORS["text_primary"],
            "minWidth": "28px",
        },
    )

    return dmc.Group([track, label], gap=6, wrap="nowrap")
