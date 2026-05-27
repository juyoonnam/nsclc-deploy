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
from dash import html, clientside_callback, Input, Output

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
                "cursor": "pointer",
                "transition": "background 0.15s ease, color 0.15s ease",
            }
            class_names = ["scenario-btn"]
            if is_demo_path:
                btn_style.update({
                    "color": "var(--mantine-color-violet-3)",
                    "borderLeft": "2px solid var(--mantine-color-violet-5)",
                    "paddingLeft": "8px",
                    "background": "rgba(124, 58, 237, 0.05)",
                })
                class_names.append("scenario-btn-demo-path")

            questions_buttons.append(
                dmc.UnstyledButton(
                    html.Div(
                        className="scenario-btn-content",
                        children=[
                            html.Span(prefix + label_text, className="scenario-btn-label"),
                        ],
                    ),
                    id={"type": "scenario-btn", "index": qid_full},
                    n_clicks=0,
                    className=" ".join(class_names),
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
        radius=0,
        p=0,
        withBorder=False,
        className="scenario-panel-paper",
        style={
            "minHeight": "640px",
            "maxHeight": "780px",
            "overflowY": "auto",
            "background": "transparent",
            "border": "0",
            "padding": "16px",
        },
        children=[
            dmc.Stack(
                gap="xs",
                children=[
                    html.Div(
                        "시나리오",
                        className="scenario-panel-title",
                    ),
                    dmc.TextInput(
                        id="scenario-search",
                        placeholder="추천 질문 검색...",
                        leftSection=html.Span("🔍"),
                        rightSection=html.Span("↑", className="scenario-search-arrow"),
                        size="sm",
                        className="scenario-search",
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
                    # 검색 필터 클라이언트사이드 hook 용 hidden output
                    html.Div(id="scenario-search-sync", style={"display": "none"}),
                ],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Clientside filter — search input → hide non-matching scenarios
# ---------------------------------------------------------------------------
clientside_callback(
    """
    function(query) {
        const q = (query || "").toString().trim().toLowerCase();
        const root = document.getElementById("scenario-accordion-root");
        if (!root) { return ""; }
        const items = root.querySelectorAll(".mantine-Accordion-item");
        let firstMatchOpened = false;
        items.forEach(function(item) {
            const ctrl = item.querySelector(".mantine-Accordion-control");
            const catLabel = (ctrl ? ctrl.textContent : "").toLowerCase();
            const buttons = item.querySelectorAll(".scenario-btn");
            let visibleCount = 0;
            buttons.forEach(function(btn) {
                const txt = (btn.textContent || "").toLowerCase();
                const match = !q || txt.indexOf(q) !== -1 || catLabel.indexOf(q) !== -1;
                btn.style.display = match ? "" : "none";
                if (match) { visibleCount += 1; }
            });
            const anyMatch = !q || visibleCount > 0 || catLabel.indexOf(q) !== -1;
            item.style.display = anyMatch ? "" : "none";

            // 검색 중이고 첫 매치 카테고리는 자동 펼침 (multiple=false 한계 회피)
            if (q && anyMatch && visibleCount > 0 && !firstMatchOpened) {
                if (ctrl && ctrl.getAttribute("aria-expanded") === "false") {
                    ctrl.click();
                }
                firstMatchOpened = true;
            }
        });
        return q;
    }
    """,
    Output("scenario-search-sync", "children"),
    Input("scenario-search", "value"),
)
