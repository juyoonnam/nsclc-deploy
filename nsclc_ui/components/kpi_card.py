"""
NSCLC Insight Engine — KPI metric card component.
"""

import dash_mantine_components as dmc

from nsclc_ui.layout.theme import COLORS


def kpi_card(label: str, value: str, sublabel: str | None = None, sublabel_color: str | None = None):
    """Compact KPI card for the overview row.

    Parameters
    ----------
    label : str
        Metric title (e.g. "Champion Model").
    value : str
        Primary display value.
    sublabel : str, optional
        Secondary description line.
    sublabel_color : str, optional
        One of "success", "warning", "danger", "tertiary" — maps to
        theme COLORS. Defaults to tertiary.
    """

    _color_map = {
        "success":  COLORS["success_text"],
        "warning":  COLORS["warning_text"],
        "danger":   COLORS["danger_text"],
        "tertiary": COLORS["text_tertiary"],
    }

    children = [
        dmc.Text(label, size="xs", style={"fontSize": "11px", "color": COLORS["text_secondary"]}),
        dmc.Text(str(value), fw=500, style={"fontSize": "18px", "lineHeight": "1.3"}),
    ]

    if sublabel is not None:
        children.append(
            dmc.Text(
                sublabel,
                size="xs",
                style={
                    "fontSize": "11px",
                    "color": _color_map.get(sublabel_color, COLORS["text_tertiary"]),
                },
            )
        )

    return dmc.Paper(
        children=children,
        style={
            "background": COLORS["bg_tertiary"],
            "border": f"1px solid {COLORS['border']}",
            "borderRadius": "8px",
            "padding": "10px 12px",
        },
    )
