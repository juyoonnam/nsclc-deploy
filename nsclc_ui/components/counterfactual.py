"""
Counterfactual Explanation — What-if analysis for Top-10 entry.
"""

import dash_mantine_components as dmc

from nsclc_ui.layout.theme import COLORS


def counterfactual_panel(cf: dict):
    """Render counterfactual explanation accordion."""
    if not cf:
        return dmc.Text("Counterfactual data not available", size="xs", c="dimmed")

    current = cf["current_rank_score"]
    threshold = cf["top10_threshold"]
    gap = cf["gap"]
    in_top10 = cf["in_top10"]

    if in_top10:
        status = dmc.Badge("✓ Already in Top-10", color="green", variant="light", size="sm")
    else:
        status = dmc.Badge(f"Gap: {gap:+.4f}", color="yellow", variant="light", size="sm")

    suggestion_rows = []
    for s in cf.get("suggestions", []):
        suggestion_rows.append(
            dmc.Text(
                f"  {s['feature']}: {s['direction']} → impact: {s['impact']}",
                size="xs", ff="monospace", style={"fontSize": "10px", "color": COLORS["text_secondary"]},
            )
        )

    return dmc.Accordion(
        children=[dmc.AccordionItem(
            value="counterfactual",
            children=[
                dmc.AccordionControl(dmc.Text("What-if (Counterfactual)", size="xs", fw=500)),
                dmc.AccordionPanel(dmc.Stack([
                    dmc.Group([
                        dmc.Text(f"Current: {current:.4f}", size="xs",
                                 style={"fontVariantNumeric": "tabular-nums"}),
                        dmc.Text(f"Top-10 threshold: {threshold:.4f}", size="xs",
                                 style={"fontVariantNumeric": "tabular-nums"}),
                        status,
                    ], gap=8),
                    dmc.Text("Top-10 진입 조건 (추정):", size="xs", fw=500, mt=4,
                             style={"fontSize": "11px"}) if not in_top10 else None,
                    *suggestion_rows,
                    dmc.Text(
                        "⚠ 추정값이며, 실제 변화는 비선형 효과로 다를 수 있음",
                        size="xs", c="dimmed", fs="italic", style={"fontSize": "10px", "marginTop": "4px"},
                    ),
                ], gap=4)),
            ],
        )],
        variant="separated", radius="md",
    )
