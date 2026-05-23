"""
Target Essentiality Overlay — CRISPR DepMap gene effect.
"""

import dash_mantine_components as dmc

from nsclc_ui.layout.theme import COLORS

# Target keywords for matching KEGG MoA
_TARGET_KEYWORDS = {
    "EGFR": ["egfr", "erbb1", "erbb-1"],
    "KRAS": ["kras", "ras"],
    "ALK": ["alk", "anaplastic"],
    "BRAF": ["braf", "b-raf"],
    "MET": ["met", "hepatocyte growth factor"],
    "ROS1": ["ros1"],
    "RET": ["ret"],
    "ERBB2": ["erbb2", "her2", "erbb-2"],
    "NTRK1": ["ntrk", "trk"],
}


def _detect_targets(kegg_entries: list[dict]) -> list[str]:
    """Detect targets from KEGG MoA entries."""
    if not kegg_entries:
        return []
    text = " ".join(
        e.get("mechanism_of_action", "") + " " + e.get("target_name", "")
        for e in kegg_entries
    ).lower()
    found = []
    for target, keywords in _TARGET_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            found.append(target)
    return found


def essentiality_panel(kegg_entries: list[dict], essentiality_data: dict):
    """Render target essentiality overlay."""
    targets = _detect_targets(kegg_entries)

    if not targets:
        return dmc.Paper([
            dmc.Text("Target Essentiality", size="xs", fw=500, mb=4),
            dmc.Text("No target detected from KEGG data", size="xs", c="dimmed"),
        ], style={"background": COLORS["bg_tertiary"], "borderRadius": "8px", "padding": "10px"})

    rows = []
    for t in targets:
        ess = essentiality_data.get(t)
        if not ess:
            rows.append(dmc.Group([
                dmc.Text(t, size="xs", fw=500, style={"width": "60px"}),
                dmc.Badge("No data", color="gray", variant="light", size="xs"),
            ], gap=8))
            continue

        mean = ess["mean"]
        if mean < -0.5:
            color, label = "green", "Essential"
        elif mean < 0:
            color, label = "yellow", "Moderate"
        else:
            color, label = "red", "Not essential"

        rows.append(dmc.Group([
            dmc.Text(t, size="xs", fw=500, style={"width": "60px"}),
            dmc.Badge(f"{label} ({mean:.2f})", color=color, variant="light", size="xs"),
            dmc.Text(f"{ess['essential_pct']}% cell lines", size="xs", c="dimmed", style={"fontSize": "10px"}),
        ], gap=8))

    return dmc.Paper([
        dmc.Group([
            dmc.Text("Target Essentiality", size="xs", fw=500),
            dmc.Badge("CRISPR DepMap", color="cyan", variant="light", size="xs"),
        ], justify="space-between", mb=6),
        dmc.Stack(rows, gap=4),
        dmc.Text("E2 모델의 핵심 데이터소스 (TCGA+CRISPR) · 전체 세포주 평균",
                 size="xs", c="dimmed", style={"fontSize": "9px", "marginTop": "6px"}),
    ], style={"background": COLORS["bg_tertiary"], "borderRadius": "8px", "padding": "10px"})
