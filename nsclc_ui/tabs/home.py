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

import logging
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

log = logging.getLogger(__name__)

PATHWAY_POPUP_MODAL_ID = "home-pathway-popup-modal"
PATHWAY_POPUP_FRAME_ID = "home-pathway-popup-frame"
PATHWAY_POPUP_TITLE_ID = "home-pathway-popup-title"
PATHWAY_POPUP_CHIP_TYPE = "home-pathway-popup-chip"

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
            html.Div(
                className="nsclc-home-shell",
                children=[
                    # Col 1 — scenario sidebar
                    html.Div(
                        className="scenario-shell",
                        children=scenario_accordion(),
                    ),
                    # Col 2 — chat assistant
                    html.Div(
                        className="chat-shell",
                        children=_chat_area(),
                    ),
                    # Col 3 — evidence (tool trace + top findings)
                    html.Div(
                        className="evidence-shell",
                        children=tool_trace_panel(),
                    ),
                ],
            ),
            html.Div(
                "본 응답은 연구 참고용이며, 임상적 판단 및 처방 결정의 책임은 전문 의료인에게 있습니다. "
                "모든 응답은 22개 MCP 도구가 산출한 정량 근거에 기반합니다.",
                className="nsclc-disclaimer",
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
            html.Div(id="chat-scroll-sync", style={"display": "none"}),
            _pathway_popup_modal(),
        ],
    )


def _pathway_popup_modal() -> dmc.Modal:
    return dmc.Modal(
        id=PATHWAY_POPUP_MODAL_ID,
        title=html.Span("Pathway Map", id=PATHWAY_POPUP_TITLE_ID),
        opened=False,
        size="95%",
        zIndex=2500,
        centered=True,
        children=html.Iframe(
            id=PATHWAY_POPUP_FRAME_ID,
            src="",
            title="NSCLC Pathway Map",
            style={
                "width": "100%",
                "height": "78vh",
                "border": "1px solid var(--nsclc-border, #2a3140)",
                "borderRadius": "8px",
                "background": "#050914",
            },
        ),
    )


def _hero() -> dmc.Group:
    """v3.0: 더 이상 layout에서 호출되지 않음. status 배지는 header.py로 이전.
    함수 본체는 backwards-compat을 위해 보존 (외부 import 가능성 차단용 dead code).
    """
    return dmc.Group(
        justify="space-between",
        align="center",
        mb="xs",
        children=[
            dmc.Stack(
                gap=0,
                children=[
                    dmc.Text(
                        "답을 주는 AI가 아니라 사용자의 판단을 강화하는 플랫폼",
                        size="sm",
                        c="dimmed",
                        fw=500,
                    ),
                ],
            ),
            dmc.Group(
                gap="xs",
                children=[
                    dmc.Badge("Champion E6", color="violet", variant="light", size="sm"),
                    dmc.Badge("PR-AUC 0.1383", color="blue", variant="light", size="sm"),
                    dmc.Badge("22 MCP Tools", color="teal", variant="light", size="sm"),
                    dmc.Badge("Model B ✓", color="green", variant="light", size="sm"),
                    dmc.Badge("Streaming ✓", color="grape", variant="light", size="sm"),
                ],
            ),
        ],
    )


def _chat_area() -> dmc.Paper:
    return dmc.Paper(
        radius=0,
        p=0,
        withBorder=False,
        style={
            "minHeight": "0",
            "height": "100%",
            "display": "flex",
            "flexDirection": "column",
            "background": "transparent",
            "border": "0",
        },
        children=[
            html.Div(
                className="chat-title-row",
                children=[
                    html.Span("NSCLC Insight Assistant", className="chat-title"),
                    html.Span("AI · Evidence-grounded", className="chat-ai-badge"),
                ],
            ),
            html.Div(
                "답을 주는 AI가 아니라 사용자의 판단을 강화하는 플랫폼",
                className="chat-subtitle",
            ),
            html.Div(
                className="chat-thread-wrap",
                children=html.Div(
                    id="chat-thread",
                    style={
                        "flex": "1",
                        "overflowY": "auto",
                        "minHeight": "500px",
                        "maxHeight": "640px",
                        "marginBottom": "0",
                        "padding": "4px 4px 12px 4px",
                    },
                    children=[_initial_welcome()],
                ),
            ),
            html.Div(
                className="chat-input-wrap",
                children=dmc.Stack(
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
                            justify="flex-end",
                            children=[
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
            ),
        ],
    )


# ════════════════════════════════════════════════════════════
# Bubble helpers
# ════════════════════════════════════════════════════════════

def _initial_welcome() -> html.Div:
    return _assistant_bubble_text(children=[
        dmc.Text("안녕하세요! NSCLC Insight Assistant 입니다.", fw=500, size="sm"),
        dmc.Text(
            "좌측 카테고리에서 시나리오를 선택하거나 자유롭게 질문해보세요.",
            size="sm",
        ),
        dmc.Text(
            "모든 응답에는 호출된 MCP tool의 정량 근거 (SHAP, in-library, Tanimoto, "
            "PR-AUC, provenance)가 우측 패널에 체계적으로 정리됩니다.",
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


# ─────────────────────────────────────────────────────────────────────────────
# Pathway link helper — 응답에서 약물/타겟 언급 감지 → 경로 보기 버튼
# ─────────────────────────────────────────────────────────────────────────────

# NSCLC champion targets + 자주 언급되는 단백질
_PATHWAY_GENES = {
    "EGFR", "ERBB2", "HER2", "KRAS", "ALK", "ROS1", "BRAF", "MET",
    "RET", "NTRK1", "NTRK2", "NTRK3", "PIK3CA", "AKT1", "MTOR",
    "TP53", "STK11", "KEAP1", "NFE2L2", "CDKN2A", "RB1", "MYC",
    "JAK2", "STAT3", "PTEN", "MAP2K1", "BRCA1", "BRCA2", "PARP1",
}

# 약물 → 주 타겟 매핑 (응답에 약물 이름만 있을 때 타겟으로 변환)
_DRUG_TO_TARGET = {
    "OSIMERTINIB": "EGFR", "ERLOTINIB": "EGFR", "GEFITINIB": "EGFR",
    "AFATINIB": "EGFR", "DACOMITINIB": "EGFR",
    "CRIZOTINIB": "ALK", "ALECTINIB": "ALK", "BRIGATINIB": "ALK",
    "LORLATINIB": "ALK", "CERITINIB": "ALK",
    "SOTORASIB": "KRAS", "ADAGRASIB": "KRAS",
    "DABRAFENIB": "BRAF", "TRAMETINIB": "MAP2K1",
    "OLAPARIB": "PARP1", "NIRAPARIB": "PARP1", "RUCAPARIB": "PARP1",
    "PEMBROLIZUMAB": "EGFR",  # 대표적으로 EGFR pathway 시작점 사용
    "TRASTUZUMAB": "ERBB2", "PERTUZUMAB": "ERBB2",
}


def _detect_pathway_genes(text: str) -> list[str]:
    """응답 텍스트에서 NSCLC pathway 관련 유전자/약물 추출 (대문자 단어 매칭)."""
    if not text:
        return []
    import re
    # 대문자/숫자로 된 토큰만 추출 (단순 word boundary)
    tokens = set(re.findall(r"\b[A-Z][A-Z0-9]{1,9}\b", text.upper()))
    detected: list[str] = []
    seen: set = set()
    for t in tokens:
        if t in _PATHWAY_GENES and t not in seen:
            detected.append(t)
            seen.add(t)
        elif t in _DRUG_TO_TARGET and _DRUG_TO_TARGET[t] not in seen:
            mapped = _DRUG_TO_TARGET[t]
            detected.append(mapped)
            seen.add(mapped)
    return detected[:5]


def _pathway_link_block(text: str) -> html.Div | None:
    genes = _detect_pathway_genes(text)
    if not genes:
        return None
    chips = [
        html.Button(
            children=[html.Span("🧬", style={"marginRight": "4px"}), gene],
            id={"type": PATHWAY_POPUP_CHIP_TYPE, "gene": gene},
            n_clicks=0,
            type="button",
            className="chat-pathway-chip",
            title=f"Pathway Map 팝업에서 {gene} 보기",
        )
        for gene in genes
    ]
    return html.Div(
        className="chat-pathway-link-row",
        children=[
            html.Span("🧬", style={"fontSize": "13px"}),
            html.Span("경로에서 보기:", style={"fontSize": "12px", "color": "var(--nsclc-text-secondary, #a0a8b8)"}),
            *chips,
        ],
    )


@callback(
    Output(PATHWAY_POPUP_MODAL_ID, "opened"),
    Output(PATHWAY_POPUP_FRAME_ID, "src"),
    Output(PATHWAY_POPUP_TITLE_ID, "children"),
    Input({"type": PATHWAY_POPUP_CHIP_TYPE, "gene": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def open_pathway_popup(n_clicks_list):
    if not n_clicks_list or not any((n or 0) for n in n_clicks_list):
        return no_update, no_update, no_update
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict):
        return no_update, no_update, no_update
    gene = str(triggered.get("gene") or "").upper()
    if gene not in _PATHWAY_GENES:
        return no_update, no_update, no_update
    nonce = sum(int(n or 0) for n in (n_clicks_list or []))
    return True, f"/pathway?focus={gene}&popup=1&open={nonce}", f"경로에서 보기: {gene}"


def _normalize_top_level_numbering(text: str) -> str:
    """Display-only normalization: make top-level numbered sections start at 1."""
    if not text:
        return text
    import re
    counter = 0
    pattern = re.compile(r"^(\s{0,3})(#{1,3}\s+)(\d{1,2})\.\s+(.+)$", re.MULTILINE)

    def repl(match):
        nonlocal counter
        prefix, hashes, _num, title = match.groups()
        counter += 1
        return f"{prefix}{hashes or ''}{counter}. {title}"

    return pattern.sub(repl, text)


def _tool_progress_label(tool_name: str, status: str) -> tuple[str, str]:
    """tool name + status → 사용자 친화적 진행 메시지."""
    name = (tool_name or "").lower()
    status_norm = status or ""
    icon_map = {
        "search_pubmed": ("📚", "PubMed 문헌 검색"),
        "search_drugs": ("💊", "약물 검색"),
        "list_actionable_genes": ("🧬", "actionable 유전자 조회"),
        "match_patient_drugs": ("🎯", "환자-약물 매칭"),
        "get_ensemble_probability": ("📊", "ensemble 확률 계산"),
        "get_shap_explanation": ("🔍", "SHAP 근거 추출"),
        "compute_tanimoto": ("⚗️", "Tanimoto 유사도 계산"),
        "check_in_library": ("📦", "라이브러리 매칭 확인"),
        "get_cell_line_meta": ("🧪", "세포주 메타 조회"),
        "get_drug_response": ("💉", "약물 반응 조회"),
    }
    icon, label = icon_map.get(name, ("🔧", name or "도구"))
    if status_norm == "진행 중":
        return icon, f"{label} 호출 중…"
    if status_norm == "완료":
        return icon, f"{label} 완료"
    if status_norm == "에러":
        return icon, f"{label} 실패"
    if status_norm == "거부":
        return icon, f"{label} 정책 거부"
    return icon, f"{label} ({status_norm})"


def _streaming_progress_line(tools: list, has_text: bool) -> html.Div | None:
    """현재 진행 단계 한 줄 — 도구 호출 또는 응답 생성 단계."""
    # 가장 최근 in-progress 도구가 있으면 그것 우선
    latest = None
    for t in reversed(tools or []):
        if t.get("status") == "진행 중":
            latest = t
            break
    if latest is None and tools:
        latest = tools[-1]

    if latest is not None:
        icon, label = _tool_progress_label(latest.get("tool", ""), latest.get("status", ""))
    elif has_text:
        icon, label = "✍️", "응답 생성 중…"
    else:
        icon, label = "🤔", "분석 준비 중…"

    return html.Div(
        className="chat-streaming-progress",
        children=[
            dmc.Loader(color="violet", size="xs", type="dots"),
            html.Span(icon, style={"fontSize": "13px"}),
            html.Span(label, style={"fontSize": "12px", "color": "var(--nsclc-text-secondary, #a0a8b8)"}),
        ],
    )


def _assistant_bubble_markdown(text: str, meta: dict | None = None,
                                streaming: bool = False,
                                streaming_tools: list | None = None) -> html.Div:
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

    # 스트리밍 중 — 진행 단계 한 줄 표시 (응답 위)
    if streaming:
        progress = _streaming_progress_line(streaming_tools or [], bool(text))
        if progress is not None:
            children.append(progress)

    if not text and streaming:
        children.append(
            html.Div(
                className="chat-streaming-answer",
                children=[
                    dmc.Loader(color="violet", size="sm", type="dots"),
                    html.Span("▌", className="chat-streaming-cursor"),
                ],
            )
        )
    else:
        display_text = _normalize_top_level_numbering(text)
        children.append(
            html.Div(
                className="chat-streaming-answer" if streaming else None,
                children=[
                    dcc.Markdown(
                        display_text,
                        style={"fontSize": "13px", "lineHeight": "1.6"},
                        dangerously_allow_html=False,
                    ),
                    html.Span("▌", className="chat-streaming-cursor") if streaming else None,
                ],
            )
        )

    # 응답 완료(non-streaming)에만 경로 링크 행 노출
    if not streaming and text:
        path_block = _pathway_link_block(text)
        if path_block is not None:
            children.append(path_block)

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
                meta={
                    "backend": streaming.get("backend") or "streaming",
                    "model_used": streaming.get("model_used", ""),
                    "complexity": streaming.get("complexity", ""),
                    "n_tools": len(streaming.get("tools", [])),
                },
                streaming=True,
                streaming_tools=streaming.get("tools", []),
            )
        )
    return items


# ════════════════════════════════════════════════════════════
# Callbacks
# ════════════════════════════════════════════════════════════

def _single_turn_user_history(history: list | None) -> list:
    """Keep only the most recent user message for demo-stable single-turn chat."""
    users = [m for m in list(history or []) if m.get("role") == "user"]
    return users[-1:] if users else []


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

    from nsclc_ui.llm.supervisor_client import (
        cleanup_job,
        start_streaming_invoke,
    )

    previous_job_id = (current_streaming or {}).get("job_id", "")
    if previous_job_id:
        log.info("single-turn reset cleanup previous_job=%s trigger=%s", previous_job_id, trig)
        cleanup_job(previous_job_id)

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
        if not qid_full:
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

    history = [{"role": "user", "content": query}]

    start_info = start_streaming_invoke(query)
    job_id = start_info.get("job_id", "")
    log.info(
        "stream submit started trigger=%s job_id=%s mock=%s cached=%s query_len=%d",
        trig,
        job_id,
        start_info.get("mock", False),
        start_info.get("cached", False),
        len(query),
    )

    streaming = {
        "job_id": job_id,
        "active": True if job_id else False,
        "text": "",
        "tools": [],
        "backend": "streaming",
        "model_used": "",
        "complexity": "",
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
        log.warning("stream poll missing job_id")
        return no_update, no_update, no_update, True, False

    from nsclc_ui.llm.supervisor_client import (
        poll_streaming_chunks,
        chunks_to_store_updates,
        build_findings_from_text,
        build_stats_from_tools,
        get_job_result,
        is_job_done,
    )

    chunks = poll_streaming_chunks(job_id)
    if not chunks:
        if is_job_done(job_id):
            final_result = get_job_result(job_id) or {}
            if not final_result and streaming.get("active"):
                log.info("stream poll stale/missing job ignored job_id=%s", job_id)
                return no_update, no_update, no_update, True, no_update
            final_text = final_result.get("text") or streaming.get("text") or "(응답 완료)"
            tools = streaming.get("tools", [])
            violations = final_result.get("violations", [])
            new_streaming = {
                **streaming,
                "active": False,
                "text": final_text,
                "tools": tools,
            }
            tool_trace = {
                "tools": tools,
                "findings": build_findings_from_text(final_text),
                "stats": build_stats_from_tools(tools, has_violations=bool(violations)),
            }
            history = _single_turn_user_history(history)
            history.append({
                "role": "assistant",
                "content": final_text,
                "meta": {
                    "backend": final_result.get("backend", "bedrock_converse_stream"),
                    "model_used": final_result.get("model_used", streaming.get("model_used", "")),
                    "complexity": final_result.get("complexity", streaming.get("complexity", "")),
                    "latency_sec": final_result.get("latency_sec", 0),
                    "n_tools": len(tools),
                    "violations": violations,
                },
            })
            log.info(
                "stream poll terminal fallback job_id=%s text_len=%d tools=%d",
                job_id,
                len(final_text),
                len(tools),
            )
            return history, new_streaming, tool_trace, True, False
        return no_update, no_update, no_update, no_update, no_update
    log.info(
        "stream poll job_id=%s chunks=%d types=%s",
        job_id,
        len(chunks),
        ",".join(str(ch.get("type", "?")) for ch in chunks),
    )

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
    routing = updates.get("routing") or {}
    if routing:
        new_streaming.update(routing)

    tool_trace = {
        "tools": updates["tools"],
        "findings": build_findings_from_text(updates["text"]),
        "stats": build_stats_from_tools(updates["tools"], has_violations=False),
    }

    # done 처리
    if updates["done"]:
        log.info(
            "stream poll done job_id=%s error=%s text_len=%d tools=%d",
            job_id,
            updates.get("error") or "",
            len(updates.get("text", "")),
            len(updates.get("tools", [])),
        )
        new_streaming["active"] = False
        final_result = updates.get("final_result")
        if final_result:
            final_text = final_result.get("text", updates["text"])
            n_turns = final_result.get("n_turns", 0)
            n_dedup = final_result.get("n_dedup_hits", 0)
            violations = final_result.get("policy_violations", [])
            latency = final_result.get("latency_sec", 0)
            backend = final_result.get("backend", "bedrock_converse_stream")
            model_used = final_result.get("model_used", new_streaming.get("model_used", ""))
            complexity = final_result.get("complexity", new_streaming.get("complexity", ""))

            history = _single_turn_user_history(history)
            history.append({
                "role": "assistant",
                "content": final_text,
                "meta": {
                    "backend": backend,
                    "model_used": model_used,
                    "complexity": complexity,
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
            history = _single_turn_user_history(history)
            history.append({
                "role": "assistant",
                "content": f"❌ {updates['error']}",
                "meta": {"backend": "error", "latency_sec": 0,
                         "n_tools": 0, "violations": []},
            })
        else:
            history = _single_turn_user_history(history)
            history.append({
                "role": "assistant",
                "content": updates["text"] or "(응답 없음)",
                "meta": {"backend": "streaming",
                         "n_tools": len(updates["tools"])},
            })

        # Keep the completed job in memory briefly. Dash interval callbacks can
        # overlap; deleting immediately lets a stale callback overwrite the
        # completed response with a false "missing job" state.
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


dash.clientside_callback(
    """
    function(streaming) {
      const el = document.getElementById("chat-thread");
      if (!el || !streaming) {
        return "";
      }
      const jobId = streaming.job_id || "";
      if (jobId && jobId !== window.__nsclcHomeLastJobId) {
        window.__nsclcHomeLastJobId = jobId;
        window.setTimeout(function() {
          const target = document.getElementById("chat-thread");
          if (target) {
            target.scrollTop = 0;
          }
        }, 0);
      }
      return jobId;
    }
    """,
    Output("chat-scroll-sync", "children"),
    Input("streaming-job-store", "data"),
)


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
