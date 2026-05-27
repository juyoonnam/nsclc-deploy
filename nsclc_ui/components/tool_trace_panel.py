"""Tool Trace Panel — 우측 도구 호출 추적 + 핵심 근거.

LLM이 호출한 MCP tool 시퀀스 + 정량 근거 (SHAP / in-library / Tanimoto / PR-AUC) 박힘.
이 패널이 우리의 핵심 차별점("정량 근거 강제") 시각화.

State 흐름:
  scenario 클릭 또는 chat-submit → supervisor 응답 → tool-trace-store 업데이트
  → 이 패널의 tool-trace-list / tool-trace-findings / 핵심 요약 자동 렌더링

UI polish:
  - 각 도구 행 클릭 → 입력/출력/소요시간 인라인 펼침
  - 하단 "모든 근거 및 로그 보기" 버튼 → 전체 call_log 모달
"""

from __future__ import annotations

import json
from typing import Any

import dash_mantine_components as dmc
from dash import html, callback, Input, Output, State, ALL, no_update, ctx as dash_ctx


# ─────────────────────────────────────────────────────────────────────────────
# Component IDs
# ─────────────────────────────────────────────────────────────────────────────
TRACE_MODAL_ID = "tool-trace-full-modal"
TRACE_MODAL_BODY_ID = "tool-trace-full-modal-body"
TRACE_ROW_BTN_TYPE = "tool-trace-row-btn"


def tool_trace_panel() -> dmc.Paper:
    """우측 Tool Trace 패널 (초기 빈 상태)."""
    return dmc.Paper(
        radius="md",
        p="md",
        withBorder=True,
        className="tool-trace-card",
        style={
            "minHeight": "640px",
            "maxHeight": "780px",
            "overflowY": "auto",
            "background": "rgba(7, 16, 29, 0.96)",
        },
        children=[
            dmc.Stack(
                gap="md",
                children=[
                    # 헤더
                    dmc.Group(
                        gap="xs",
                        align="center",
                        className="panel-header-row",
                        children=[
                            html.Span("✨", style={"fontSize": "18px"}),
                            dmc.Text("추적 근거", fw=700, size="sm",
                                     className="panel-title"),
                            dmc.Text(
                                "(Evidence / Tool Trace)",
                                size="xs",
                                c="dimmed",
                                className="panel-subtitle",
                            ),
                        ],
                    ),
                    # 핵심 요약 (3 stat cards)
                    html.Div(
                        id="tool-trace-stats",
                        children=_initial_stats(),
                    ),
                    # 도구 실행 순서
                    dmc.Text("도구 실행 순서", size="xs", fw=500, c="dimmed"),
                    html.Div(
                        id="tool-trace-list",
                        children=[_empty_state()],
                    ),
                    # 주요 근거
                    dmc.Text("주요 근거 (Top Findings)", size="xs", fw=500, c="dimmed", mt="sm"),
                    html.Div(
                        id="tool-trace-findings",
                        children=[],
                    ),
                    dmc.Button(
                        "모든 근거 및 로그 보기",
                        id="tool-trace-expand-btn",
                        variant="light",
                        color="violet",
                        size="xs",
                        fullWidth=True,
                        mt="sm",
                    ),
                    # 모달 — 전체 call_log
                    dmc.Modal(
                        id=TRACE_MODAL_ID,
                        title="전체 도구 호출 로그",
                        size="lg",
                        opened=False,
                        zIndex=2000,
                        children=html.Div(id=TRACE_MODAL_BODY_ID, children=[]),
                    ),
                ],
            ),
        ],
    )


def _initial_stats() -> dmc.Group:
    """초기 stat cards (빈 상태)."""
    return dmc.Group(
        grow=True,
        gap="xs",
        children=[
            _stat_card("—", "최고 PR-AUC"),
            _stat_card("—", "데이터 소스"),
            _stat_card("—", "모델 신뢰도"),
        ],
    )


def _stat_card(value: str, label: str) -> dmc.Paper:
    return dmc.Paper(
        p="xs",
        radius="sm",
        withBorder=True,
        style={"textAlign": "center", "minHeight": "60px"},
        children=[
            dmc.Text(value, size="lg", fw=600, c="violet"),
            dmc.Text(label, size="xs", c="dimmed"),
        ],
    )


def _empty_state() -> dmc.Text:
    return dmc.Text(
        "시나리오를 선택하거나 질문을 입력하면 호출된 tool 순서가 여기 표시됩니다.",
        size="xs",
        c="dimmed",
        ta="center",
        style={"padding": "32px 8px"},
    )


# ===== Helpers (callback에서 사용) =====

def render_stats(stats: dict[str, Any] | None) -> dmc.Group:
    """tool-trace-store의 stats를 stat cards로 렌더링."""
    if not stats:
        return _initial_stats()
    return dmc.Group(
        grow=True,
        gap="xs",
        children=[
            _stat_card(stats.get("pr_auc", "—"), "최고 PR-AUC"),
            _stat_card(stats.get("n_sources", "—"), "데이터 소스"),
            _stat_card(stats.get("confidence", "—"), "모델 신뢰도"),
        ],
    )


def _status_color(status: str) -> str:
    return {
        "완료": "green",
        "진행 중": "yellow",
        "거부": "red",
        "에러": "red",
    }.get(status, "gray")


def _format_value(value: Any) -> str:
    """input/output dict/list/str → 사람이 읽기 좋은 문자열."""
    if value is None:
        return "—"
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return str(value)


def _render_row(t: dict[str, Any], idx: int) -> dmc.Paper:
    """tool 호출 한 행 — 클릭 시 인라인 collapse로 입력/출력 표시."""
    status = t.get("status", "")
    color = _status_color(status)

    # collapse content (입력 / 출력 / 소요시간 / 에러)
    detail_rows: list = []
    if t.get("input") is not None:
        detail_rows.append(
            dmc.Stack(
                gap=2,
                children=[
                    dmc.Text("입력", size="xs", fw=600, c="dimmed"),
                    html.Pre(
                        _format_value(t.get("input")),
                        className="tool-trace-pre",
                    ),
                ],
            )
        )
    if t.get("output") is not None:
        detail_rows.append(
            dmc.Stack(
                gap=2,
                children=[
                    dmc.Text("출력", size="xs", fw=600, c="dimmed"),
                    html.Pre(
                        _format_value(t.get("output")),
                        className="tool-trace-pre",
                    ),
                ],
            )
        )
    elapsed_sec = t.get("elapsed_sec")
    meta_chips: list = []
    if elapsed_sec is not None:
        meta_chips.append(
            dmc.Badge(f"{float(elapsed_sec):.2f}s", color="gray", size="xs", variant="light")
        )
    if t.get("error"):
        meta_chips.append(
            dmc.Badge(str(t.get("error"))[:60], color="red", size="xs", variant="light")
        )
    if meta_chips:
        detail_rows.append(dmc.Group(meta_chips, gap=4))

    if not detail_rows:
        detail_rows.append(
            dmc.Text("(추가 상세 데이터 없음 — 요약만 수신)", size="xs", c="dimmed", fs="italic")
        )

    row_button = html.Button(
        children=[
            dmc.Group(
                gap="xs",
                align="flex-start",
                style={"width": "100%"},
                children=[
                    dmc.Badge(
                        str(t.get("step", "?")),
                        size="sm",
                        variant="filled",
                        color="violet",
                        radius="xl",
                    ),
                    dmc.Stack(
                        gap=2,
                        style={"flex": "1", "minWidth": 0},
                        children=[
                            dmc.Group(
                                gap="xs",
                                justify="space-between",
                                children=[
                                    dmc.Text(t.get("tool", ""), size="xs", fw=500),
                                    dmc.Badge(
                                        status,
                                        size="xs",
                                        variant="light",
                                        color=color,
                                    ),
                                ],
                            ),
                            dmc.Text(
                                t.get("detail", ""),
                                size="xs",
                                c="dimmed",
                            ) if t.get("detail") else None,
                        ],
                    ),
                    html.Span("▾", className="tool-trace-row-chev"),
                ],
            ),
        ],
        id={"type": TRACE_ROW_BTN_TYPE, "index": idx},
        n_clicks=0,
        type="button",
        className="tool-trace-row-btn",
    )

    return dmc.Paper(
        p=0,
        withBorder=False,
        style={"marginBottom": "6px"},
        children=[
            row_button,
            dmc.Collapse(
                id={"type": "tool-trace-row-collapse", "index": idx},
                opened=False,
                children=dmc.Stack(
                    detail_rows,
                    gap="xs",
                    style={
                        "padding": "8px 10px 10px 36px",
                        "background": "rgba(124, 58, 237, 0.04)",
                        "borderLeft": "2px solid rgba(124, 58, 237, 0.3)",
                        "borderRadius": "0 4px 4px 0",
                        "marginTop": "2px",
                    },
                ),
            ),
        ],
    )


def render_tool_list(tools: list[dict[str, Any]]) -> html.Div:
    """tool 호출 시퀀스 렌더링 — 행 클릭 시 입력/출력 펼침."""
    if not tools:
        return html.Div([_empty_state()])
    return html.Div([_render_row(t, i) for i, t in enumerate(tools)])


def render_findings(findings: list[dict[str, Any]]) -> html.Div:
    """Top Findings 렌더링."""
    if not findings:
        return html.Div()
    items = []
    for f in findings:
        items.append(
            dmc.Group(
                gap="xs",
                align="flex-start",
                children=[
                    dmc.Text(
                        str(f.get("rank", "•")),
                        size="sm",
                        fw=600,
                        c="violet",
                        style={"minWidth": "16px"},
                    ),
                    dmc.Stack(
                        gap=0,
                        style={"flex": "1"},
                        children=[
                            dmc.Text(f.get("title", ""), size="xs", fw=500),
                            dmc.Text(
                                f.get("detail", ""),
                                size="xs",
                                c="dimmed",
                                style={"lineHeight": "1.3"},
                            ),
                        ],
                    ),
                ],
                style={"marginBottom": "8px"},
            )
        )
    return html.Div(items)


# ─────────────────────────────────────────────────────────────────────────────
# Modal — full call log
# ─────────────────────────────────────────────────────────────────────────────

def _render_modal_body(tools: list[dict[str, Any]]) -> dmc.Stack:
    if not tools:
        return dmc.Stack(
            [dmc.Text("호출된 도구가 없습니다.", size="sm", c="dimmed")],
            gap="xs",
        )

    rows: list = []
    for t in tools:
        status = t.get("status", "")
        color = _status_color(status)
        elapsed_sec = t.get("elapsed_sec")
        elapsed_text = (
            f"{float(elapsed_sec):.2f}s" if elapsed_sec is not None else (t.get("detail") or "—")
        )

        body_blocks: list = [
            dmc.Group(
                gap="xs",
                align="center",
                children=[
                    dmc.Badge(str(t.get("step", "?")), color="violet", variant="filled",
                              size="sm", radius="xl"),
                    dmc.Text(t.get("tool", "?"), size="sm", fw=600),
                    dmc.Badge(status, color=color, variant="light", size="xs"),
                    dmc.Badge(elapsed_text, color="gray", variant="light", size="xs"),
                ],
            ),
        ]
        if t.get("input") is not None:
            body_blocks.append(
                dmc.Stack(
                    gap=2,
                    children=[
                        dmc.Text("input", size="xs", c="dimmed", fw=600),
                        html.Pre(_format_value(t.get("input")), className="tool-trace-pre"),
                    ],
                )
            )
        if t.get("output") is not None:
            body_blocks.append(
                dmc.Stack(
                    gap=2,
                    children=[
                        dmc.Text("output", size="xs", c="dimmed", fw=600),
                        html.Pre(_format_value(t.get("output")), className="tool-trace-pre"),
                    ],
                )
            )
        if t.get("error"):
            body_blocks.append(
                dmc.Alert(
                    str(t.get("error"))[:500],
                    color="red",
                    variant="light",
                    title="에러 메시지",
                )
            )

        # 실패 호출은 빨간 보더
        border = "1px solid rgba(248, 113, 113, 0.4)" if color == "red" else "1px solid var(--nsclc-border)"
        rows.append(
            dmc.Paper(
                p="sm",
                radius="sm",
                withBorder=False,
                style={"border": border, "marginBottom": "8px"},
                children=dmc.Stack(body_blocks, gap="xs"),
            )
        )

    return dmc.Stack(rows, gap="xs")


@callback(
    Output(TRACE_MODAL_ID, "opened"),
    Output(TRACE_MODAL_BODY_ID, "children"),
    Input("tool-trace-expand-btn", "n_clicks"),
    State("tool-trace-store", "data"),
    prevent_initial_call=True,
)
def _open_full_log_modal(n_clicks, store_data):
    if not n_clicks:
        return no_update, no_update
    tools = (store_data or {}).get("tools", []) if isinstance(store_data, dict) else []
    return True, _render_modal_body(tools)


@callback(
    Output({"type": "tool-trace-row-collapse", "index": ALL}, "opened"),
    Input({"type": TRACE_ROW_BTN_TYPE, "index": ALL}, "n_clicks"),
    State({"type": "tool-trace-row-collapse", "index": ALL}, "opened"),
    prevent_initial_call=True,
)
def _toggle_row(n_clicks_list, opened_list):
    """행 클릭 → 해당 인덱스 collapse 토글."""
    if not n_clicks_list or not any(n for n in n_clicks_list if n):
        return no_update
    triggered_full = dash_ctx.triggered
    if not triggered_full or not triggered_full[0].get("value"):
        return no_update
    triggered = dash_ctx.triggered_id
    if not isinstance(triggered, dict):
        return no_update
    idx = triggered.get("index")
    new_opened = list(opened_list or [])
    if not isinstance(idx, int) or idx >= len(new_opened):
        return no_update
    new_opened[idx] = not bool(new_opened[idx])
    return new_opened
