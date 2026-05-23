"""
Experiment Planner — Cell line recommendations based on target.
"""

from dash import html
import dash_mantine_components as dmc

from nsclc_ui.layout.theme import COLORS

CELL_LINE_MAP = {
    "EGFR": [
        {"line": "PC9", "mutation": "EGFR del19", "notes": "1st-gen TKI sensitive"},
        {"line": "H1975", "mutation": "EGFR T790M+L858R", "notes": "3rd-gen TKI target"},
        {"line": "HCC827", "mutation": "EGFR del19 amp", "notes": "High EGFR expression"},
    ],
    "KRAS": [
        {"line": "A549", "mutation": "KRAS G12S", "notes": "Common NSCLC model"},
        {"line": "H460", "mutation": "KRAS Q61H", "notes": "Large cell"},
        {"line": "H358", "mutation": "KRAS G12C", "notes": "Sotorasib target"},
    ],
    "ALK": [
        {"line": "H3122", "mutation": "EML4-ALK v1", "notes": "ALK fusion standard"},
        {"line": "H2228", "mutation": "EML4-ALK v3/a/b", "notes": "Crizotinib sensitive"},
    ],
    "BRAF": [{"line": "HCC364", "mutation": "BRAF V600E", "notes": "Vemurafenib sensitive"}],
    "MET": [{"line": "H1993", "mutation": "MET amp", "notes": "MET amplification"}],
    "ROS1": [{"line": "HCC78", "mutation": "SLC34A2-ROS1", "notes": "ROS1 fusion"}],
    "RET": [{"line": "LC-2/ad", "mutation": "CCDC6-RET", "notes": "RET fusion"}],
}

DEFAULT_READOUT = "Cell viability (CellTiter-Glo, 72h)"
DEFAULT_DOSE = "0.001 ~ 10 µM, 8-point serial dilution"

# Target keywords to match from KEGG MoA text
_TARGET_KEYWORDS = {
    "EGFR": ["egfr", "erbb1", "erbb-1"],
    "KRAS": ["kras", "ras"],
    "ALK": ["alk", "anaplastic"],
    "BRAF": ["braf", "b-raf"],
    "MET": ["met", "hepatocyte growth factor"],
    "ROS1": ["ros1"],
    "RET": ["ret"],
}


def _detect_target(kegg_entries: list[dict]) -> str | None:
    """Detect primary target from KEGG MoA entries."""
    if not kegg_entries:
        return None
    text = " ".join(e.get("mechanism_of_action", "") + " " + e.get("target_name", "") for e in kegg_entries).lower()
    for target, keywords in _TARGET_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return target
    return None


def experiment_planner(kegg_entries: list[dict], compound_id: str = ""):
    """Build experiment planner accordion section."""
    target = _detect_target(kegg_entries)
    cell_lines = CELL_LINE_MAP.get(target, []) if target else []

    if not cell_lines:
        target_text = target or "Unknown"
        # Show all available targets with their cell lines as sub-accordions
        all_target_items = []
        for tgt, lines in CELL_LINE_MAP.items():
            tgt_rows = [
                dmc.TableTr([
                    dmc.TableTd(dmc.Text(cl["line"], fw=500, size="xs")),
                    dmc.TableTd(dmc.Text(cl["mutation"], size="xs", ff="monospace")),
                    dmc.TableTd(dmc.Text(cl["notes"], size="xs", c="dimmed")),
                ])
                for cl in lines
            ]
            all_target_items.append(
                dmc.AccordionItem(
                    value=f"target-{tgt}",
                    children=[
                        dmc.AccordionControl(dmc.Text(f"{tgt} ({len(lines)} lines)", size="xs", fw=500)),
                        dmc.AccordionPanel(
                            dmc.Table([
                                dmc.TableThead(dmc.TableTr([
                                    dmc.TableTh("Cell Line"), dmc.TableTh("Mutation"), dmc.TableTh("Notes"),
                                ])),
                                dmc.TableTbody(tgt_rows),
                            ], withTableBorder=True, style={"fontSize": "11px"}),
                        ),
                    ],
                )
            )
        content = dmc.Stack([
            dmc.Text(
                f"Detected target: {target_text} — select a target below for cell line recommendations.",
                size="xs", c="dimmed", style={"fontSize": "11px"},
            ),
            dmc.Accordion(children=all_target_items, variant="separated", radius="sm",
                         multiple=True, value=["target-EGFR"]),
            dmc.Text(f"Readout: {DEFAULT_READOUT}", size="xs", c="dimmed", style={"fontSize": "10px"}),
            dmc.Text(f"Dose: {DEFAULT_DOSE}", size="xs", c="dimmed", style={"fontSize": "10px"}),
        ], gap=6)
    else:
        rows = [
            dmc.TableTr([
                dmc.TableTd(dmc.Text(cl["line"], fw=500, size="xs")),
                dmc.TableTd(dmc.Text(cl["mutation"], size="xs", ff="monospace")),
                dmc.TableTd(dmc.Text(cl["notes"], size="xs", c="dimmed")),
            ])
            for cl in cell_lines
        ]
        content = dmc.Stack([
            dmc.Text(f"Target: {target}", size="xs", fw=500, style={"color": COLORS["accent"]}),
            dmc.Table([
                dmc.TableThead(dmc.TableTr([
                    dmc.TableTh("Cell Line"), dmc.TableTh("Mutation"), dmc.TableTh("Notes"),
                ])),
                dmc.TableTbody(rows),
            ], withTableBorder=True, style={"fontSize": "11px"}),
            dmc.Text(f"Readout: {DEFAULT_READOUT}", size="xs", c="dimmed", style={"fontSize": "10px"}),
            dmc.Text(f"Dose: {DEFAULT_DOSE}", size="xs", c="dimmed", style={"fontSize": "10px"}),
            dmc.Text(
                f"Controls: Positive = known {target} inhibitor, Negative = DMSO vehicle",
                size="xs", c="dimmed", style={"fontSize": "10px"},
            ),
        ], gap=6)

    return dmc.Accordion(
        children=[dmc.AccordionItem(
            value="exp-plan",
            children=[
                dmc.AccordionControl(dmc.Text("Experiment Planner", size="xs", fw=500)),
                dmc.AccordionPanel(content),
            ],
        )],
        variant="separated", radius="md",
    )
