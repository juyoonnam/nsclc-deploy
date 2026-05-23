"""Tool Trace Panel — 우측 도구 호출 추적 + 핵심 근거.

LLM이 호출한 MCP tool 시퀀스 + 정량 근거 (SHAP / in-library / Tanimoto / PR-AUC) 박힘.
이 패널이 우리의 핵심 차별점("정량 근거 강제") 시각화.

State 흐름:
  scenario 클릭 또는 chat-submit → supervisor 응답 → tool-trace-store 업데이트
  → 이 패널의 tool-trace-list / tool-trace-findings / 핵심 요약 자동 렌더링
"""

from __future__ import annotations

from typing import Any
import dash_mantine_components as dmc
from dash import html


def tool_trace_panel() -> dmc.Paper:
    """우측 Tool Trace 패널 (초기 빈 상태)."""
    return dmc.Paper(
        radius="md",
        p="md",
        withBorder=True,
        style={"minHeight": "640px", "maxHeight": "780px", "overflowY": "auto"},
        children=[
            dmc.Stack(
                gap="md",
                children=[
                    # 헤더
                    dmc.Group(
                        gap="xs",
                        align="center",
                        children=[
                            html.Span("✨", style={"fontSize": "18px"}),
                            dmc.Text("추적 근거", fw=500, size="sm"),
                            dmc.Text(
                                "(Evidence / Tool Trace)",
                                size="xs",
                                c="dimmed",
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
    """tool-trace-store의 stats를 stat cards로 렌더링.

    stats 예시:
      {"pr_auc": "0.1383", "n_sources": "5/14", "confidence": "high"}
    """
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


def render_tool_list(tools: list[dict[str, Any]]) -> html.Div:
    """tool 호출 시퀀스 렌더링.

    tools 예시:
      [
        {"step": 1, "tool": "check_in_library", "status": "완료", "detail": "Olaparib not in lib"},
        {"step": 2, "tool": "compute_tanimoto", "status": "완료", "detail": "Niraparib T=0.494"},
        ...
      ]
    """
    if not tools:
        return html.Div([_empty_state()])
    items = []
    for t in tools:
        status = t.get("status", "")
        status_color = {
            "완료": "green",
            "진행 중": "yellow",
            "거부": "red",
            "에러": "red",
        }.get(status, "gray")
        items.append(
            dmc.Group(
                gap="xs",
                align="flex-start",
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
                        style={"flex": "1"},
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
                                        color=status_color,
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
                ],
                style={"marginBottom": "8px"},
            )
        )
    return html.Div(items)


def render_findings(findings: list[dict[str, Any]]) -> html.Div:
    """Top Findings 렌더링.

    findings 예시:
      [
        {"rank": 1, "title": "Olaparib", "detail": "in_library=False → POLICY_REJECT_EXTERNAL"},
        {"rank": 2, "title": "Niraparib", "detail": "Tanimoto=0.494, analog evidence"},
        ...
      ]
    """
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
