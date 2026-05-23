"""
NSCLC Insight Engine — Label status badge component.
"""

import dash_mantine_components as dmc

from nsclc_ui.layout.theme import COLORS

# status → (background, text color)
_STATUS_COLORS = {
    "Positive":  (COLORS["success_bg"],  COLORS["success_text"]),
    "Promoted":  (COLORS["warning_bg"],  COLORS["warning_text"]),
    "Unlabeled": (COLORS["bg_tertiary"], COLORS["text_secondary"]),
    "Blocked":   (COLORS["danger_bg"],   COLORS["danger_text"]),
}


def label_badge(status: str):
    """Render a small colored badge for a compound label status.

    Parameters
    ----------
    status : str
        One of "Positive", "Promoted", "Unlabeled", "Blocked".
    """

    bg, color = _STATUS_COLORS.get(status, _STATUS_COLORS["Unlabeled"])

    return dmc.Badge(
        status,
        variant="light",
        size="sm",
        radius="sm",
        style={
            "background": bg,
            "color": color,
            "border": "none",
            "textTransform": "none",
            "fontWeight": "500",
            "fontSize": "11px",
        },
    )
