"""
NSCLC Insight Engine — Page-aware sidebar (filter panel).
"""

import dash_mantine_components as dmc

from nsclc_ui.layout.theme import COLORS

# Pages that show a sidebar
_SIDEBAR_PAGES = {"drug_ranking", "candidate_explorer", "predict"}

_SIDEBAR_STYLE = {
    "width": "220px",
    "minWidth": "220px",
    "borderRight": f"0.5px solid {COLORS['border']}",
    "padding": "16px 12px",
    "background": COLORS["bg_primary"],
}


def sidebar(page_name: str):
    """Return a sidebar for *page_name*, or ``None`` if the page has no filters.

    Actual filter components will be added per-page later;
    for now each page gets a placeholder.
    """
    if page_name not in _SIDEBAR_PAGES:
        return None

    # ── Placeholder filters (to be replaced) ──────────────────────────────
    _placeholders = {
        "drug_ranking": [
            dmc.Text("Filters", size="xs", fw=600, mb=8),
            dmc.Text("Phase, label, score range …", size="xs", c="dimmed"),
        ],
        "candidate_explorer": [
            dmc.Text("Filters", size="xs", fw=600, mb=8),
            dmc.Text("Target, MoA, scaffold …", size="xs", c="dimmed"),
        ],
        "predict": [
            dmc.Text("Input", size="xs", fw=600, mb=8),
            dmc.Text("Compound selector, SMILES …", size="xs", c="dimmed"),
        ],
    }

    return dmc.Stack(
        _placeholders.get(page_name, []),
        gap="xs",
        style=_SIDEBAR_STYLE,
    )
