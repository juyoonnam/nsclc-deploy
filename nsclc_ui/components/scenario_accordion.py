"""Scenario Accordion — 좌측 7 카테고리 × 30 시나리오 패널.

scenarios.yaml (final/agentcore/scenarios.yaml) 직접 로드.
- stable_demo: 별 마크 (⭐)
- demo_path: 보라색 강조 + 좌측 보더
- 시나리오 클릭 → chat-input 자동 채움 (callback은 다음 답변)
"""

from __future__ import annotations

from pathlib import Path
import yaml

import dash_mantine_components as dmc
from dash import html

# scenarios.yaml 경로:
# __file__ = .../final/nsclc_ui/components/scenario_accordion.py
# .parent.parent.parent = .../final/
SCENARIOS_YAML = (
    Path(__file__).resolve().parent.parent.parent / "agentcore" / "scenarios.yaml"
)


def _load_scenarios() -> dict:
    try:
        with open(SCENARIOS_YAML, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return {"categories": [], "demo_path": []}
    except Exception:
        return {"categories": [], "demo_path": []}


def scenario_accordion() -> dmc.Paper:
    """좌측 시나리오 카테고리 패널."""
    data = _load_scenarios()
    cats = data.get("categories", [])
    demo_path = set(data.get("demo_path", []))

    accordion_items = []
    for cat in cats:
        cat_id = cat["id"]
        questions_buttons = []

        for q in cat.get("questions", []):
            qid_full = f"{cat_id}.{q['id']}"
            is_stable = q.get("stable_demo", False)
            is_demo_path = qid_full in demo_path

            label_text = q["text"]
            prefix = "⭐ " if is_stable else "• "

            btn_style = {
                "padding": "6px 10px",
                "fontSize": "12.5px",
                "borderRadius": "6px",
                "width": "100%",
                "textAlign": "left",
                "lineHeight": "1.4",
                "transition": "background 0.15s",
            }
            if is_demo_path:
                btn_style.update({
                    "color": "var(--mantine-color-violet-3)",
                    "borderLeft": "2px solid var(--mantine-color-violet-5)",
                    "paddingLeft": "8px",
                    "background": "rgba(124, 58, 237, 0.05)",
                })

            questions_buttons.append(
                dmc.UnstyledButton(
                    prefix + label_text,
                    id={"type": "scenario-btn", "index": qid_full},
                    style=btn_style,
                )
            )

        accordion_items.append(
            dmc.AccordionItem(
                value=cat_id,
                children=[
                    dmc.AccordionControl(
                        dmc.Group(
                            gap="xs",
                            children=[
                                dmc.Text(cat.get("icon", "📌"), size="md"),
                                dmc.Text(cat["title"], fw=500, size="sm"),
                                dmc.Badge(
                                    str(len(cat.get("questions", []))),
                                    size="xs",
                                    variant="light",
                                    color="gray",
                                    ml="auto",
                                ),
                            ],
                        ),
                    ),
                    dmc.AccordionPanel(
                        dmc.Stack(gap=4, children=questions_buttons),
                    ),
                ],
            )
        )

    return dmc.Paper(
        radius="md",
        p="sm",
        withBorder=True,
        style={"minHeight": "640px", "maxHeight": "780px", "overflowY": "auto"},
        children=[
            dmc.Stack(
                gap="xs",
                children=[
                    dmc.TextInput(
                        id="scenario-search",
                        placeholder="추천 질문 검색...",
                        leftSection=html.Span("🔍"),
                        rightSection=dmc.Kbd("⌘K"),
                        size="sm",
                    ),
                    dmc.Group(
                        justify="space-between",
                        align="center",
                        children=[
                            dmc.Text("추천 질문 카테고리", size="xs", c="dimmed", fw=500),
                            dmc.Text(
                                f"{len(cats)} 카테고리 · {sum(len(c.get('questions', [])) for c in cats)} 질문",
                                size="xs",
                                c="dimmed",
                            ),
                        ],
                    ),
                    dmc.Accordion(
                        id="scenario-accordion-root",
                        children=accordion_items,
                        chevronPosition="right",
                        multiple=False,
                        value="patient_drug_matching" if cats else None,
                        variant="separated",
                        styles={
                            "control": {"padding": "8px 10px"},
                            "panel": {"padding": "4px 8px 8px"},
                        },
                    ),
                ],
            ),
        ],
    )
