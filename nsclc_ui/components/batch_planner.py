"""
Batch Planner — 4-compound experimental batch design.
"""

import dash_mantine_components as dmc

from nsclc_ui.layout.theme import COLORS


def _batch_card(label: str, compound: dict | None, border_color: str, description: str):
    if compound is None:
        return dmc.Paper(
            dmc.Text(f"{label}: No candidate", size="xs", c="dimmed"),
            style={"background": COLORS["bg_tertiary"], "borderRadius": "8px",
                   "padding": "10px", "borderLeft": f"4px solid {COLORS['text_tertiary']}",
                   "flex": 1},
        )
    return dmc.Paper(
        children=[
            dmc.Text(label, size="xs", fw=600, style={"color": border_color}),
            dmc.Text(compound["compound_id"], size="xs", ff="monospace", mt=2),
            dmc.Text(f"rank_score: {compound['rank_score']:.4f}", size="xs",
                     style={"fontVariantNumeric": "tabular-nums", "fontSize": "11px"}),
            dmc.Text(description, size="xs", c="dimmed", style={"fontSize": "10px", "marginTop": "4px"}),
        ],
        style={
            "background": COLORS["bg_tertiary"],
            "borderLeft": f"4px solid {border_color}",
            "borderRadius": "8px",
            "padding": "10px",
            "flex": 1,
        },
    )


def batch_planner_panel(batch: dict):
    """Render 4-compound batch as horizontal cards."""
    if not batch:
        return dmc.Text("Batch data not available", size="xs", c="dimmed")

    cards = dmc.Group([
        _batch_card("Anchor", batch.get("anchor"), COLORS["success_text"], "확실한 후보"),
        _batch_card("Explorer", batch.get("explorer"), COLORS["accent"], "신규 scaffold 탐색"),
        _batch_card("Boundary", batch.get("boundary"), COLORS["warning_text"], "모델 불확실 → 학습 기여 최대"),
        _batch_card("Negative", batch.get("negative"), COLORS["danger_text"], "대조군"),
    ], grow=True, gap="xs")

    return dmc.Accordion(
        children=[dmc.AccordionItem(
            value="batch-plan",
            children=[
                dmc.AccordionControl(dmc.Text("Batch Planner (4-compound design)", size="xs", fw=500)),
                dmc.AccordionPanel(dmc.Stack([
                    cards,
                    dmc.Text(
                        "이 배치로 실험하면 모델 불확실성 영역 커버 가능. "
                        "Boundary 화합물의 실험 결과가 다음 학습 사이클에 최대 기여.",
                        size="xs", c="dimmed", style={"fontSize": "10px"},
                    ),
                ], gap=8)),
            ],
        )],
        variant="separated", radius="md",
    )
