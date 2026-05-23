"""Home page — NSCLC Insight Engine 메인 채팅 (v2.6).

v2.6 변경 (D-6 D-7):
- 시나리오 클릭 + chat-submit을 단일 callback으로 통합
  → dmc.Textarea State stale 문제 우회. 시나리오 클릭은 input 안 거치고 직접 streaming 시작.
- on_interval_poll button disabled 출력을 no_update로 (race condition 회피)

v2.5 기능 유지:
- ConverseStream UI (체감 latency 1분 → 5초)
- threading + dcc.Interval (500ms) 폴링
- 진행 중 assistant 버블 점진 표시
- tool-trace 실시간 업데이트
"""

from __future__ import annotations

from pathlib import Path
import yaml

import dash
import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update

from nsclc_ui.components.scenario_accordion import scenario_accordion
from nsclc_ui.components.tool_trace_panel import (
    render_findings,
    render_stats,
    render_tool_list,
    tool_trace_panel,
)

dash.register_page(
    __name__,
    path="/",
    name="홈",
    title="NSCLC Insight Engine",
)


# ════════════════════════════════════════════════════════════
# Scenario YAML lookup
# ════════════════════════════════════════════════════════════

_SCENARIOS_YAML = (
    Path(__file__).resolve().parent.parent.parent / "agentcore" / "scenarios.yaml"
)
_SCENARIO_TEXT_MAP: dict[str, str] = {}


def _load_scenario_text_map() -> dict[str, str]:
    global _SCENARIO_TEXT_MAP
    if _SCENARIO_TEXT_MAP:
        return _SCENARIO_TEXT_MAP
    try:
        with open(_SCENARIOS_YAML, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        result = {}
        for cat in data.get("categories", []):
            cat_id = cat["id"]
            for q in cat.get("questions", []):
                result[f"{cat_id}.{q['id']}"] = q["text"]
        _SCENARIO_TEXT_MAP = result
    except Exception:
        _SCENARIO_TEXT_MAP = {}
    return _SCENARIO_TEXT_MAP


# ════════════════════════════════════════════════════════════
# Layout
# ════════════════════════════════════════════════════════════

def layout(**kwargs):
    return dmc.Stack(
        gap="sm",
        children=[
            _hero(),
            dmc.Grid(
                gutter="md",
                children=[
                    dmc.GridCol(
                        span={"base": 12, "md": 3},
                        children=scenario_accordion(),
                    ),
                    dmc.GridCol(
                        span={"base": 12, "md": 6},
                        children=_chat_area(),
                    ),
                    dmc.GridCol(
                        span={"base": 12, "md": 3},
                        children=tool_trace_panel(),
                    ),
                ],
            ),
            dmc.Text(
                "AI 답변은 참고용이며 임상적 판단은 전문가의 책임입니다. "
                "모든 응답은 21개 MCP tool 정량 근거에 박혀있습니다.",
                size="xs",
                c="dimmed",
                ta="center",
                mt="md",
            ),
            # Stores
            dcc.Store(id="chat-history-store", data=[]),
            dcc.Store(id="current-scenario-store", data=None),
            dcc.Store(id="tool-trace-store",
                      data={"tools": [], "findings": [], "stats": None}),
            dcc.Store(id="streaming-job-store",
                      data={"job_id": "", "active": False,
                            "text": "", "tools": []}),
            # Polling interval (500ms when active)
            dcc.Interval(
                id="streaming-poller",
                interval=500,
                disabled=True,
                n_intervals=0,
            ),
        ],
    )


def _hero() -> dmc.Group:
    return dmc.Group(
        justify="space-between",
        align="center",
        mb="xs",
        children=[
            dmc.Stack(
                gap=0,
                children=[
                    dmc.Title(
                        "NSCLC Insight Engine",
                        order=3,
                        style={
                            "background": "linear-gradient(90deg, #c084fc, #60a5fa)",
                            "WebkitBackgroundClip": "text",
                            "WebkitTextFillColor": "transparent",
                            "backgroundClip": "text",
                        },
                    ),
                    dmc.Text(
                        "답을 주는 AI가 아니라 사용자의 판단을 강화하는 플랫폼",
                        size="xs",
                        c="dimmed",
                    ),
                ],
            ),
            dmc.Group(
                gap="xs",
                children=[
                    dmc.Badge("Champion E6", color="violet", variant="light", size="sm"),
                    dmc.Badge("PR-AUC 0.1383", color="blue", variant="light", size="sm"),
                    dmc.Badge("21 MCP Tools", color="teal", variant="light", size="sm"),
                    dmc.Badge("Model B ✓", color="green", variant="light", size="sm"),
                    dmc.Badge("Streaming ✓", color="grape", variant="light", size="sm"),
                ],
            ),
        ],
    )


def _chat_area() -> dmc.Paper:
    return dmc.Paper(
        radius="md",
        p="md",
        withBorder=True,
        style={"minHeight": "640px", "display": "flex", "flexDirection": "column"},
        children=[
            html.Div(
                id="chat-thread",
                style={
                    "flex": "1",
                    "overflowY": "auto",
                    "minHeight": "500px",
                    "maxHeight": "640px",
                    "marginBottom": "12px",
                    "padding": "4px",
                },
                children=[_initial_welcome()],
            ),
            dmc.Stack(
                gap="xs",
                children=[
                    dmc.Textarea(
                        id="chat-input",
                        placeholder="NSCLC 인사이트를 위해 무엇이든 물어보세요...",
                        autosize=True,
                        minRows=2,
                        maxRows=6,
                    ),
                    dmc.Group(
                        justify="space-between",
                        children=[
                            dmc.Group(
                                gap="xs",
                                children=[
                                    dmc.ActionIcon(
                                        html.Span("+", style={"fontSize": "16px"}),
                                        variant="subtle", color="gray", size="md",
                                    ),
                                    dmc.ActionIcon(
                                        html.Span("🌐"),
                                        variant="subtle", color="gray", size="md",
                                    ),
                                ],
                            ),
                            dmc.Group(
                                gap="xs",
                                children=[
                                    dmc.Text("⏎ Enter로 전송", size="xs", c="dimmed"),
                                    dmc.Button(
                                        "전송",
                                        id="chat-submit-btn",
                                        rightSection=html.Span("➤"),
                                        variant="gradient",
                                        gradient={"from": "violet", "to": "blue"},
                                        size="sm",
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


# ════════════════════════════════════════════════════════════
# Bubble helpers
# ════════════════════════════════════════════════════════════

def _initial_welcome() -> html.Div:
    return _assistant_bubble_text(children=[
        dmc.Text("안녕하세요! NSCLC Insight Engine 입니다.", fw=500, size="sm"),
        dmc.Text(
            "좌측 카테고리에서 ⭐ 표시된 시나리오를 선택하거나 자유롭게 질문해보세요.",
            size="sm",
        ),
        dmc.Text(
            "모든 응답에는 호출된 MCP tool의 정량 근거 (SHAP, in-library, Tanimoto, "
            "PR-AUC, provenance)가 우측 패널에 박힙니다.",
            size="xs",
            c="dimmed",
        ),
    ])


def _assistant_bubble_text(children: list) -> html.Div:
    return html.Div(
        style={"display": "flex", "gap": "12px", "marginBottom": "16px"},
        children=[
            dmc.Avatar("AI", color="violet", radius="xl", size="md"),
            dmc.Paper(
                p="sm", radius="md", withBorder=True,
                style={
                    "flex": "1",
                    "background": "rgba(124, 58, 237, 0.06)",
                    "borderColor": "rgba(124, 58, 237, 0.2)",
                },
                children=dmc.Stack(gap="xs", children=children),
            ),
        ],
    )


def _assistant_bubble_markdown(text: str, meta: dict | None = None,
                                streaming: bool = False) -> html.Div:
    """LLM 응답 Markdown 렌더 + meta badges + streaming indicator."""
    badges = []
    if streaming:
        badges.append(
            dmc.Badge("⚡ STREAMING", color="violet", size="xs", variant="filled")
        )
    if meta:
        backend = meta.get("backend", "")
        latency = meta.get("latency_sec", 0)
        n_tools = meta.get("n_tools", 0)
        violations = meta.get("violations", [])
        if backend == "error":
            badges.append(dmc.Badge("ERROR", color="red", size="xs"))
        elif backend == "mock":
            badges.append(dmc.Badge("MOCK", color="yellow", size="xs"))
        elif backend and backend != "streaming":
            model = meta.get("model_used", "") or ""
            complexity = meta.get("complexity", "")
            if "haiku" in model.lower():
                badges.append(dmc.Badge("⚡ Haiku 4.5", color="cyan", size="xs", variant="filled"))
            elif "sonnet" in model.lower():
                badges.append(dmc.Badge("Sonnet 4.6", color="violet", size="xs", variant="filled"))
            else:
                badges.append(dmc.Badge(backend, color="violet", size="xs", variant="light"))
            if complexity and complexity not in ("default", "forced_sonnet", "forced_haiku"):
                badges.append(dmc.Badge(complexity, color="gray", size="xs", variant="outline"))
        if latency:
            badges.append(dmc.Badge(f"{latency:.1f}s", color="gray", size="xs", variant="light"))
        if n_tools:
            badges.append(dmc.Badge(f"tools: {n_tools}", color="teal", size="xs", variant="light"))
        if violations:
            badges.append(dmc.Badge(f"⚠ {len(violations)}", color="orange", size="xs"))

    children = []
    if badges:
        children.append(dmc.Group(gap="xs", children=badges, mb=4))

    if not text and streaming:
        children.append(dmc.Loader(color="violet", size="sm", type="dots"))
    else:
        display_text = text + (" ▌" if streaming else "")
        children.append(
            dcc.Markdown(
                display_text,
                style={"fontSize": "13px", "lineHeight": "1.6"},
                dangerously_allow_html=False,
            )
        )
    return _assistant_bubble_text(children=children)


def _user_bubble(text: str) -> html.Div:
    return html.Div(
        style={"display": "flex", "gap": "12px",
               "marginBottom": "16px", "justifyContent": "flex-end"},
        children=[
            dmc.Paper(
                p="sm", radius="md", withBorder=True,
                style={
                    "maxWidth": "70%",
                    "background": "rgba(96, 165, 250, 0.08)",
                    "borderColor": "rgba(96, 165, 250, 0.25)",
                },
                children=dmc.Text(text, size="sm"),
            ),
            dmc.Avatar("나", color="blue", radius="xl", size="md"),
        ],
    )


def _render_thread(history: list, streaming: dict | None) -> list:
    items = [_initial_welcome()]
    for msg in (history or []):
        role = msg.get("role")
        if role == "user":
            items.append(_user_bubble(msg.get("content", "")))
        elif role == "assistant":
            items.append(
                _assistant_bubble_markdown(
                    msg.get("content", ""),
                    meta=msg.get("meta"),
                    streaming=False,
                )
            )
    if streaming and streaming.get("active"):
        items.append(
            _assistant_bubble_markdown(
                streaming.get("text", ""),
                meta={"backend": "streaming",
                      "n_tools": len(streaming.get("tools", []))},
                streaming=True,
            )
        )
    return items


# ════════════════════════════════════════════════════════════
# Callbacks
# ════════════════════════════════════════════════════════════

@callback(
    Output("chat-history-store", "data", allow_duplicate=True),
    Output("streaming-job-store", "data", allow_duplicate=True),
    Output("chat-input", "value", allow_duplicate=True),
    Output("current-scenario-store", "data", allow_duplicate=True),
    Output("streaming-poller", "disabled", allow_duplicate=True),
    Output("streaming-poller", "n_intervals", allow_duplicate=True),
    Output("chat-submit-btn", "disabled", allow_duplicate=True),
    Input("chat-submit-btn", "n_clicks"),
    Input({"type": "scenario-btn", "index": ALL}, "n_clicks"),
    State("chat-input", "value"),
    State("chat-history-store", "data"),
    State("streaming-job-store", "data"),
    prevent_initial_call=True,
)
def on_submit_or_scenario(submit_clicks, scenario_clicks, input_value,
                           history, current_streaming):
    """통합 callback: chat-submit + 시나리오 클릭 → streaming 시작.

    v2.6: 두 trigger를 합쳐 dmc.Textarea State sync 문제 우회.
    시나리오 클릭은 input value 안 거치고 직접 query 전달.
    """
    trig = ctx.triggered_id
    if not trig:
        return (no_update, no_update, no_update, no_update,
                no_update, no_update, no_update)

    # 이미 streaming 중이면 새 query 무시 (race 방지)
    if current_streaming and current_streaming.get("active"):
        return (no_update, no_update, no_update, no_update,
                no_update, no_update, no_update)

    query = None
    qid_full = no_update

    # chat-submit 버튼 클릭
    if trig == "chat-submit-btn":
        if not submit_clicks:
            return (no_update, no_update, no_update, no_update,
                    no_update, no_update, no_update)
        if not input_value or not input_value.strip():
            return (no_update, no_update, no_update, no_update,
                    no_update, no_update, no_update)
        query = input_value.strip()

    # 시나리오 버튼 클릭
    elif isinstance(trig, dict) and trig.get("type") == "scenario-btn":
        qid_full = trig.get("index")
        if not qid_full or not any(scenario_clicks or []):
            return (no_update, no_update, no_update, no_update,
                    no_update, no_update, no_update)
        text_map = _load_scenario_text_map()
        question_text = text_map.get(qid_full)
        if not question_text:
            return (no_update, no_update, no_update, qid_full,
                    no_update, no_update, no_update)
        query = question_text

    if not query:
        return (no_update, no_update, no_update, no_update,
                no_update, no_update, no_update)

    from nsclc_ui.llm.supervisor_client import start_streaming_invoke

    history = list(history or [])
    history.append({"role": "user", "content": query})

    start_info = start_streaming_invoke(query)
    job_id = start_info.get("job_id", "")

    streaming = {
        "job_id": job_id,
        "active": True if job_id else False,
        "text": "",
        "tools": [],
        "mock": start_info.get("mock", False),
        "cached": start_info.get("cached", False),
    }

    return (
        history,        # chat-history-store
        streaming,      # streaming-job-store
        "",             # chat-input value (clear)
        qid_full,       # current-scenario-store
        False,          # streaming-poller disabled = False (enabled)
        0,              # n_intervals reset
        True,           # chat-submit-btn disabled while streaming
    )


@callback(
    Output("chat-history-store", "data", allow_duplicate=True),
    Output("streaming-job-store", "data", allow_duplicate=True),
    Output("tool-trace-store", "data"),
    Output("streaming-poller", "disabled", allow_duplicate=True),
    Output("chat-submit-btn", "disabled", allow_duplicate=True),
    Input("streaming-poller", "n_intervals"),
    State("streaming-job-store", "data"),
    State("chat-history-store", "data"),
    prevent_initial_call=True,
)
def on_interval_poll(n, streaming, history):
    """Interval tick — chunk 폴링 + store 업데이트.

    v2.6: streaming 비활성 시 button disabled는 건드리지 않음 (no_update).
    """
    if not streaming or not streaming.get("active"):
        # poller만 disable, button 상태는 건드리지 않음
        return no_update, no_update, no_update, True, no_update

    job_id = streaming.get("job_id", "")
    if not job_id:
        return no_update, no_update, no_update, True, False

    from nsclc_ui.llm.supervisor_client import (
        poll_streaming_chunks,
        chunks_to_store_updates,
        build_findings_from_text,
        build_stats_from_tools,
        cleanup_job,
    )

    chunks = poll_streaming_chunks(job_id)
    if not chunks:
        return no_update, no_update, no_update, no_update, no_update

    updates = chunks_to_store_updates(
        chunks,
        current_text=streaming.get("text", ""),
        current_tools=streaming.get("tools", []),
    )

    new_streaming = {
        **streaming,
        "text": updates["text"],
        "tools": updates["tools"],
    }

    tool_trace = {
        "tools": updates["tools"],
        "findings": build_findings_from_text(updates["text"]),
        "stats": build_stats_from_tools(updates["tools"], has_violations=False),
    }

    # done 처리
    if updates["done"]:
        new_streaming["active"] = False
        final_result = updates.get("final_result")
        if final_result:
            final_text = final_result.get("text", updates["text"])
            n_turns = final_result.get("n_turns", 0)
            n_dedup = final_result.get("n_dedup_hits", 0)
            violations = final_result.get("policy_violations", [])
            latency = final_result.get("latency_sec", 0)
            backend = final_result.get("backend", "bedrock_converse_stream")

            history = list(history or [])
            history.append({
                "role": "assistant",
                "content": final_text,
                "meta": {
                    "backend": backend,
                    "latency_sec": latency,
                    "n_tools": len(updates["tools"]),
                    "violations": violations,
                    "n_turns": n_turns,
                    "n_dedup_hits": n_dedup,
                },
            })

            tool_trace["findings"] = build_findings_from_text(final_text)
            tool_trace["stats"] = build_stats_from_tools(
                updates["tools"], has_violations=bool(violations)
            )
        elif updates.get("error"):
            history = list(history or [])
            history.append({
                "role": "assistant",
                "content": f"❌ {updates['error']}",
                "meta": {"backend": "error", "latency_sec": 0,
                         "n_tools": 0, "violations": []},
            })
        else:
            history = list(history or [])
            history.append({
                "role": "assistant",
                "content": updates["text"] or "(응답 없음)",
                "meta": {"backend": "streaming",
                         "n_tools": len(updates["tools"])},
            })

        cleanup_job(job_id)
        return history, new_streaming, tool_trace, True, False

    # 진행 중 — Interval 유지, button disable 계속
    return no_update, new_streaming, tool_trace, False, True


@callback(
    Output("chat-thread", "children"),
    Input("chat-history-store", "data"),
    Input("streaming-job-store", "data"),
)
def render_chat_thread(history, streaming):
    return _render_thread(history or [], streaming)


@callback(
    Output("tool-trace-stats", "children"),
    Output("tool-trace-list", "children"),
    Output("tool-trace-findings", "children"),
    Input("tool-trace-store", "data"),
)
def render_tool_trace(data):
    data = data or {}
    return (
        render_stats(data.get("stats")),
        render_tool_list(data.get("tools", [])),
        render_findings(data.get("findings", [])),
    )
