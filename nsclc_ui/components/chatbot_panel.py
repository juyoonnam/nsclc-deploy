"""
nsclc_ui/components/chatbot_panel.py

Pathway Map 우측에 통합되는 챗봇 패널.

구성
----
1. UI: 입력창 + 전송 버튼 + 답변 영역 + spinner + 컨텍스트 배지
2. 어댑터: pathway_map.py의 데이터 구조 → ChatbotContext (키명 차이 흡수)
3. Callback: 전송 → answer_question → 답변 렌더 (history 1개만 유지)

설계 결정
---------
- 챗봇 history 보존: 노드 클릭으로 컨텍스트만 갱신, 답변은 유지
- 컨텍스트 Store(`chatbot-context-store`)에 노드 클릭 시점 데이터 보관
  → 사용자가 입력 후 Send 누른 시점에 Store에서 컨텍스트 읽음
- pathway_map.py 통합 시 `_compound_detail_panel`이 (panel, context_payload)
  tuple 반환하도록 변경 (ChEMBL/OT 중복 호출 방지)
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from functools import lru_cache
from pathlib import Path
import time
from typing import Any, Optional

import dash_mantine_components as dmc
import pandas as pd
from dash import callback, clientside_callback, dcc, html, no_update, ALL, ctx as dash_ctx
from dash.dependencies import Input, Output, State

from nsclc_ui.data.chatbot import (
    ChatbotContext,
    ChatbotResponse,
    answer_question,
)
from nsclc_ui.llm.bedrock_client import LLMResponse, query_entity, query_freeform, query_entity_haiku
from nsclc_ui.llm.mock_lib import known_entities

# ---------------------------------------------------------------------------
# Public IDs (pathway_map.py에서 참조)
# ---------------------------------------------------------------------------
CONTEXT_STORE_ID = "chatbot-context-store"
ANSWER_AREA_ID = "chatbot-answer-area"
INPUT_ID = "chatbot-input"
SUBMIT_BTN_ID = "chatbot-submit-btn"
CONTEXT_BADGE_ID = "chatbot-context-badge"
LOADING_ID = "chatbot-loading"
SUGGESTIONS_ID = "chatbot-suggestions"
SUGGEST_BTN_TYPE = "chatbot-suggest-btn"
COLLAPSE_BTN_ID = "chatbot-collapse-btn"
COLLAPSE_ID = "chatbot-collapse"
AUTO_SCROLL_ID = "chatbot-autoscroll-anchor"
RWR_NODE_BTN_TYPE = "signor-top-influenced-node-v1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RWR_PATH = PROJECT_ROOT / "data" / "derived" / "rwr_nsclc_targets.parquet"
CHAT_QUERY_TIMEOUT_SECONDS = 10

# 답변 type별 색상
_TYPE_COLOR = {
    "answer": "teal",
    "no_info": "gray",
    "off_topic": "yellow",
    "fallback_rule": "orange",
}
_TYPE_LABEL = {
    "answer": "LLM 응답",
    "no_info": "정보 없음",
    "off_topic": "범위 밖",
    "fallback_rule": "규칙 기반",
}

# 추천 질문 — 컨텍스트 기반 동적 생성.
# 데이터 있는 카테고리만 노출 (외부 0개면 외부 버튼 안 보임).
def _build_suggested_questions(payload: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    # 컨텍스트 없을 때 — 사용 시작 안내용 일반 질문
    if not payload:
        return [
            {
                "color": "gray",
                "question": "champion 모델이 뭐야?",
            },
            {
                "color": "gray",
                "question": "어떤 노드부터 클릭해야 좋아?",
            },
            {
                "color": "gray",
                "question": "NSCLC 약물 재창출이 뭐야?",
            },
        ]

    gene = payload.get("gene_symbol", "이 타겟")
    return [
        {
            "color": "indigo",
            "question": f"{gene}이(가) NSCLC에서 어떤 역할을 해?",
        },
        {
            "color": "teal",
            "question": "이 결과 다음에 어떤 노드·탭을 보면 좋아?",
        },
    ]


def _render_suggestions(payload: Optional[dict[str, Any]]):
    """컨텍스트 → 추천 질문 칩 렌더링. 컨텍스트 없을 때도 안내 질문 표시."""
    qs = _build_suggested_questions(payload)

    label_text = "💡 추천 질문 (클릭 즉시 전송)" if payload else "💡 시작 가이드"
    chip_label_style = (
        {"whiteSpace": "normal", "lineHeight": 1.25}
        if payload else {"whiteSpace": "nowrap", "lineHeight": 1.2}
    )
    return dmc.Stack([
        html.Div(
            [
                html.Span("💡 후보 Top 3 / SHAP 분석 → "),
                html.Strong("'후보 상세'"),
                html.Span(" 또는 "),
                html.Strong("'순위'"),
                html.Span(" 탭에서 확인"),
            ],
            className="chatbot-capability-note",
        ),
        dmc.Text(label_text, size="xs", c="dimmed", fw=600),
        html.Div(
            [
                dmc.Button(
                    q["question"],
                    id={"type": SUGGEST_BTN_TYPE, "index": i},
                    n_clicks=0,
                    variant="light",
                    color=q["color"],
                    size="xs",
                    radius="xl",
                    styles={"label": chip_label_style},
                )
                for i, q in enumerate(qs)
            ],
            style={"display": "flex", "flexWrap": "wrap", "gap": "6px"},
        ),
    ], gap=6)


# ---------------------------------------------------------------------------
# 어댑터: pathway_map.py 데이터 구조 → chatbot 컨텍스트 payload
# ---------------------------------------------------------------------------
def build_context_payload(
    *,
    genes: list[str],
    internal_compounds: list[dict],
    external_chembl_compounds: list[dict],
    ot_drugs: list[dict],
    chembl_coverage: float,
) -> dict[str, Any]:
    """pathway_map.py 변수명 → chatbot.py 키명 변환.

    실제 데이터 차이:
    - 외부 ChEMBL: `compound_id`/`max_pchembl` → chatbot은 `chembl_id`/`pchembl`
    - OT 약물: `drug_name` → chatbot은 `name`

    Args:
        chembl_coverage: 0.0~1.0 ratio (예: 0.991 = 99.1%).
            pathway_map.py의 `ext_overlap / ext_dedup`가 직접 들어옴.
            ※ % 단위(99.1) 아님. silent 단위 변환 안 함 — 호출자 책임.

    이 함수는 pathway_map의 _compound_detail_panel 안에서 호출되어
    Store에 dict로 저장됨 (Dash Store는 JSON serializable만 허용).
    """
    # gene_symbol: 단일 gene이면 그대로, 복합체면 첫 번째 + 라벨
    gene_symbol = genes[0] if genes else "Unknown"
    gene_name = ", ".join(genes) if len(genes) > 1 else None

    internal = [
        {
            "compound_id": c.get("compound_id", "?"),
            "rank_score": c.get("rank_score"),
            "modality": c.get("modality"),
        }
        for c in (internal_compounds or [])[:5]
    ]

    external = [
        {
            "chembl_id": c.get("compound_id", "?"),  # 키명 변환
            "pchembl": c.get("max_pchembl"),
        }
        for c in (external_chembl_compounds or [])[:5]
    ]

    clinical = [
        {
            "name": d.get("drug_name", "unnamed"),  # 키명 변환
            "max_phase": d.get("max_phase"),
            "nsclc": bool(d.get("nsclc", False)),
        }
        for d in (ot_drugs or [])[:5]
    ]

    return {
        "gene_symbol": gene_symbol,
        "gene_name": gene_name,
        "pathway_id": "hsa05223",
        "pathway_name": "NSCLC",
        "internal_compounds": internal,
        "external_chembl": external,
        "clinical_drugs": clinical,
        "chembl_coverage_pct": (
            chembl_coverage * 100.0 if chembl_coverage is not None else None
        ),
    }


def _payload_to_context(payload: dict[str, Any]) -> ChatbotContext:
    return ChatbotContext(
        gene_symbol=payload.get("gene_symbol", "Unknown"),
        gene_name=payload.get("gene_name"),
        pathway_id=payload.get("pathway_id", "hsa05223"),
        pathway_name=payload.get("pathway_name", "NSCLC"),
        internal_compounds=payload.get("internal_compounds", []),
        external_chembl=payload.get("external_chembl", []),
        clinical_drugs=payload.get("clinical_drugs", []),
        chembl_coverage_pct=payload.get("chembl_coverage_pct"),
    )


# ---------------------------------------------------------------------------
# UI: 패널 layout
# ---------------------------------------------------------------------------
def chatbot_panel() -> dmc.Paper:
    """Pathway Map 우측에 들어갈 챗봇 패널.

    노드 클릭 전 초기 상태 안내 → Store 갱신되면 컨텍스트 배지 활성화.
    """
    initial_placeholder = dmc.Paper(
        dmc.Stack([
            dmc.Group([
                dmc.Text("👋", size="xl"),
                dmc.Text("안녕하세요!", size="md", fw=600,
                         style={"color": "#C1C2C5"}),
            ], gap="xs", align="center"),
            dmc.Text(
                "왼쪽 그래프에서 유전자 노드를 클릭하면 그 타겟에 대해 자세히 알려드릴게요.",
                size="sm", c="dimmed",
            ),
            dmc.Text(
                "💡 아래 추천 질문을 눌러보거나 직접 입력해보세요.",
                size="xs", c="dimmed", fs="italic",
            ),
        ], gap=6),
        p="md",
        style={
            "backgroundColor": "rgba(190, 75, 219, 0.05)",
            "border": "1px dashed rgba(190, 75, 219, 0.3)",
            "borderRadius": "6px",
        },
    )

    return dmc.Paper(
        dmc.Stack([
            # 헤더 — 귀여운 아이콘 + 친근한 이름 + 접기 버튼
            dmc.Group([
                dmc.Group([
                    dmc.Text("🧬", size="xl"),
                    dmc.Stack([
                        dmc.Text("Pathway 도우미", size="md", fw=600,
                                 style={"color": "#C1C2C5", "lineHeight": 1.1}),
                        dmc.Text("어떤 도움이 필요하신가요?", size="xs", c="dimmed",
                                 style={"lineHeight": 1.1}),
                    ], gap=2),
                ], gap="xs", align="center"),
                dmc.Group([
                    html.Div(id=CONTEXT_BADGE_ID, children=dmc.Badge(
                        "노드 미선택", color="gray", variant="light", size="sm",
                    )),
                    dmc.Button(
                        "▼ 접기",
                        id=COLLAPSE_BTN_ID,
                        variant="subtle",
                        size="xs",
                        color="gray",
                    ),
                ], gap="xs"),
            ], justify="space-between", align="flex-start"),

            dmc.Collapse(
                id=COLLAPSE_ID,
                className="atlas-chat-collapse",
                opened=True,
                children=html.Div(
                    [
                        # 좌측 사이드바 — 추천 질문 영구 세로 리스트
                        html.Div(
                            [
                                html.Div("추천 질문", className="atlas-chat-sidebar-title"),
                                html.Div(id=SUGGESTIONS_ID, children=_render_suggestions(None)),
                            ],
                            className="atlas-chat-sidebar",
                        ),
                        # 우측 메인 — 채팅창 (하단 정렬) + 입력창 하단 고정
                        html.Div(
                            [
                                html.Div(
                                    html.Div(
                                        id=ANSWER_AREA_ID,
                                        children=initial_placeholder,
                                        className="atlas-chat-thread",
                                    ),
                                    className="atlas-chat-thread-wrap",
                                ),
                                html.Div(
                                    [
                                        dcc.Input(
                                            id=INPUT_ID,
                                            type="text",
                                            placeholder="질문을 입력하세요...",
                                            debounce=False,
                                            value="",
                                            style={
                                                "width": "100%",
                                                "minWidth": 0,
                                                "boxSizing": "border-box",
                                                "padding": "10px 12px",
                                                "borderRadius": "6px",
                                                "border": "1px solid #444",
                                                "backgroundColor": "#2A2B2F",
                                                "color": "#C1C2C5",
                                                "fontSize": "14px",
                                                "outline": "none",
                                            },
                                        ),
                                        dmc.Button(
                                            "Send",
                                            id=SUBMIT_BTN_ID,
                                            color="blue",
                                            variant="filled",
                                            size="sm",
                                            style={"width": "72px", "minWidth": "72px"},
                                        ),
                                    ],
                                    className="atlas-chat-input-row",
                                    style={
                                        "display": "grid",
                                        "gridTemplateColumns": "minmax(0, 1fr) 72px",
                                        "gap": "8px",
                                        "width": "100%",
                                        "paddingRight": "0",
                                        "boxSizing": "border-box",
                                    },
                                ),
                            ],
                            className="atlas-chat-main",
                        ),
                    ],
                    className="atlas-chat-grid",
                ),
            ),

            # 컨텍스트 Store (노드 클릭으로 갱신, Collapse 밖 — 항상 active)
            dcc.Store(id=CONTEXT_STORE_ID, data=None),
            html.Div(id=AUTO_SCROLL_ID, style={"display": "none"}),
        ], gap="sm", className="atlas-chat-shell"),
        style={
            "padding": "16px",
            "backgroundColor": "rgba(37, 38, 43, 0.6)",
            "border": "1px solid #373A40",
            "borderRadius": "8px",
            "height": "100%",
        },
    )


# ---------------------------------------------------------------------------
# 답변 렌더링
# ---------------------------------------------------------------------------
def _render_answer(resp: ChatbotResponse, question: str) -> dmc.Stack:
    """ChatbotResponse → Dash 컴포넌트 트리."""
    type_color = _TYPE_COLOR.get(resp.type, "gray")
    type_label = _TYPE_LABEL.get(resp.type, resp.type)

    # 헤더 배지: type + confidence
    header_items = [
        dmc.Badge(type_label, color=type_color, variant="filled", size="sm"),
        dmc.Badge(
            f"신뢰도 {resp.confidence:.1f}",
            color="gray", variant="outline", size="sm",
        ),
    ]
    if resp.fallback_reason:
        header_items.append(
            dmc.Tooltip(
                dmc.Badge("fallback 사유", color="orange",
                          variant="dot", size="sm"),
                label=resp.fallback_reason[:200],
                position="bottom",
                withArrow=True,
            )
        )

    blocks = [
        # 사용자 질문 echo
        dmc.Paper(
            dmc.Group([
                dmc.Badge("Q", color="blue", variant="filled", size="xs"),
                dmc.Text(question, size="sm",
                         style={"color": "#C1C2C5"}),
            ], gap="xs", align="flex-start"),
            p="xs",
            style={
                "backgroundColor": "rgba(77, 171, 247, 0.08)",
                "borderRadius": "4px",
            },
        ),

        # 응답 헤더
        dmc.Group(header_items, gap="xs"),

        # 응답 본문 — fallback_rule은 \n 줄바꿈 유지 위해 white-space pre-wrap
        dmc.Paper(
            dmc.Text(
                resp.text,
                size="sm",
                style={
                    "color": "#C1C2C5",
                    "whiteSpace": "pre-wrap",
                    "lineHeight": 1.6,
                },
            ),
            p="sm",
            style={
                "backgroundColor": "rgba(255,255,255,0.02)",
                "border": "1px solid rgba(255,255,255,0.05)",
                "borderRadius": "4px",
            },
        ),
    ]

    # evidence_refs (있으면 collapse로)
    if resp.evidence_refs:
        ev_items = []
        for r in resp.evidence_refs[:6]:
            src = r.get("source", "?")
            label_parts = [src]
            if "id" in r:
                label_parts.append(str(r["id"]))
            elif "name" in r:
                label_parts.append(str(r["name"]))
            ev_items.append(
                dmc.Badge(
                    " · ".join(label_parts),
                    color="grape", variant="outline", size="xs",
                )
            )
        blocks.append(
            dmc.Group([
                dmc.Text(f"근거 ({len(resp.evidence_refs)})",
                         size="xs", c="dimmed"),
                *ev_items,
            ], gap=4)
        )

    # Grounding source 카드 (LLM 출력 정책 v1.1 §2.1)
    grounding_block = _render_grounding(resp)
    if grounding_block is not None:
        blocks.append(grounding_block)

    return dmc.Stack(blocks, gap="xs")


def _render_grounding(resp: ChatbotResponse) -> Optional[dmc.Paper]:
    """답변 카드 하단에 grounding source 표시.
    LLM 출력 정책 v1.1 §2.1: 모든 답변은 source 명시. fallback도 정형 데이터 source 명시.
    """
    if resp.type == "answer":
        # Bedrock 성공 — champion + KEGG + 컨텍스트 데이터
        badges = [
            dmc.Text("📎 grounding:", size="xs", c="dimmed", fw=600),
            dmc.Badge("champion E2_tcga_crispr", color="cyan",
                      variant="dot", size="xs"),
            dmc.Badge("KEGG hsa05223", color="indigo",
                      variant="dot", size="xs"),
            dmc.Badge("compound_target_map", color="grape",
                      variant="dot", size="xs"),
        ]
        bg = "rgba(34, 211, 238, 0.05)"
    elif resp.type == "fallback_rule":
        # 규칙 기반 fallback — 정형 데이터 source
        badges = [
            dmc.Text("📎 grounding:", size="xs", c="dimmed", fw=600),
            dmc.Badge("정형 데이터 (LLM 미사용)", color="orange",
                      variant="dot", size="xs"),
            dmc.Badge("compound_target_map", color="grape",
                      variant="dot", size="xs"),
        ]
        bg = "rgba(251, 191, 36, 0.05)"
    elif resp.type == "no_info":
        badges = [
            dmc.Text("📎 grounding:", size="xs", c="dimmed", fw=600),
            dmc.Badge("source 부족", color="red",
                      variant="dot", size="xs"),
        ]
        bg = "rgba(248, 113, 113, 0.05)"
    else:
        return None

    return dmc.Paper(
        dmc.Group(badges, gap=3, wrap="wrap", className="chatbot-grounding-row"),
        p=4,
        className="chatbot-grounding",
        style={"backgroundColor": bg, "borderRadius": "4px"},
    )


def _render_no_context_warning() -> dmc.Alert:
    return dmc.Alert(
        "먼저 그래프에서 유전자 노드를 클릭해 컨텍스트를 선택하세요.",
        title="컨텍스트 없음",
        color="yellow",
        variant="light",
    )


def _render_empty_input_warning() -> dmc.Alert:
    return dmc.Alert(
        "질문을 입력하세요.",
        color="gray",
        variant="light",
    )


def _known_entity_choices() -> list[tuple[str, str]]:
    entities = known_entities()
    choices = [(name, "gene") for name in entities.get("proteins", [])]
    choices.extend((name, "drug") for name in entities.get("drugs", []))
    choices.extend([
        ("HER2", "gene"),
        ("ERBB2", "gene"),
    ])
    return sorted(choices, key=lambda item: len(item[0]), reverse=True)


_ENTITY_CHOICES = _known_entity_choices()
_ENTITY_CANONICAL = {name.casefold(): name for name, _ in _ENTITY_CHOICES}
_ENTITY_TYPES = {name.casefold(): typ for name, typ in _ENTITY_CHOICES}
_ENTITY_ALIASES = {"her2": ("ERBB2", "gene")}
_CHAMPION_TARGETS = set(known_entities().get("proteins", []))


def _extract_llm_entity(question: str, payload: Optional[dict]) -> tuple[str, str] | None:
    text = (question or "").casefold()
    for alias, mapped in _ENTITY_ALIASES.items():
        if alias in text:
            return mapped
    for name, typ in _ENTITY_CHOICES:
        if name.casefold() in text:
            canonical = "ERBB2" if name.upper() == "HER2" else name
            return canonical, typ
    return None


def _is_next_node_question(question: str) -> bool:
    text = question or ""
    return "다음" in text and ("노드" in text or "탭" in text)


def _resolve_rwr_seed(payload: Optional[dict]) -> str:
    candidate = str((payload or {}).get("gene_symbol") or (payload or {}).get("display_label") or "EGFR")
    return candidate.strip() or "EGFR"


@lru_cache(maxsize=16)
def _rwr_top5_for_seed(seed: str) -> dict[str, Any]:
    df = pd.read_parquet(RWR_PATH)
    seed_col = "seed_gene" if "seed_gene" in df.columns else "seed"
    available = set(df[seed_col].dropna().astype(str).unique())
    resolved_seed = seed if seed in available else "EGFR"
    subset = df[df[seed_col].astype(str) == resolved_seed].copy()
    if "is_seed" in subset.columns:
        subset = subset[~subset["is_seed"].fillna(False).astype(bool)]
    if "rank" in subset.columns:
        subset = subset.sort_values("rank", ascending=True)
    elif "influence" in subset.columns:
        subset = subset.sort_values("influence", ascending=False)

    rows = []
    for _, row in subset.head(5).iterrows():
        gene = str(row.get("gene") or "")
        if not gene:
            continue
        rows.append({
            "gene": gene,
            "score": float(row.get("influence") or 0.0),
            "is_champion": gene in _CHAMPION_TARGETS,
        })
    return {"seed": resolved_seed, "rows": rows}


def _render_rwr_next_nodes(question: str, payload: Optional[dict]) -> dmc.Stack:
    rwr = _rwr_top5_for_seed(_resolve_rwr_seed(payload))
    seed = rwr["seed"]
    rows = rwr["rows"]
    row_nodes = []
    for idx, row in enumerate(rows, start=1):
        gene = row["gene"]
        row_nodes.append(
            html.Div(
                [
                    html.Span(f"{idx}.", className="chatbot-rwr-rank"),
                    html.Button(
                        gene,
                        id={"type": RWR_NODE_BTN_TYPE, "gene": gene},
                        n_clicks=0,
                        type="button",
                        className="chatbot-rwr-node-button",
                        title=f"{gene} 노드로 이동",
                    ),
                    html.Span(f"({row['score']:.4f})", className="chatbot-rwr-score"),
                    html.Span("★ champion target", className="chatbot-rwr-star") if row["is_champion"] else None,
                ],
                className="chatbot-rwr-row",
            )
        )

    body = [
        html.Div(f"현재 seed [{seed}] 기준 RWR Top-5 영향 노드:", className="chatbot-rwr-title"),
        html.Div(row_nodes or [html.Div("표시할 RWR 노드가 없습니다.", className="chatbot-rwr-empty")], className="chatbot-rwr-list"),
        html.Div("각 노드 클릭 시 cytoscape navigate.", className="chatbot-rwr-hint"),
    ]

    return dmc.Stack(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("data", className="chatbot-status-chip"),
                            html.Span("rwr", className="chatbot-status-chip"),
                            html.Span("0ms", className="chatbot-status-chip"),
                        ],
                        className="chatbot-status-row",
                    ),
                    html.Div(body, className="chatbot-response-body chatbot-rwr-response"),
                ],
                className="chatbot-response chatbot-message-assistant",
            ),
        ],
        gap="xs",
    )


def _format_llm_latency(ms: float | int | None) -> str:
    try:
        value = float(ms or 0)
    except (TypeError, ValueError):
        value = 0.0
    if value >= 1000:
        return f"{value / 1000:.1f}s"
    return f"{value:.0f}ms"


def _render_chatbot_pmid_links(pmids: list[str] | tuple[str, ...]):
    clean: list[str] = []
    for pmid in pmids or []:
        text = str(pmid).strip()
        if text.isdigit() and text not in clean:
            clean.append(text)
    if not clean:
        return [html.Span("—", className="chatbot-pmid-empty")]

    parts = []
    for idx, pmid in enumerate(clean[:5]):
        if idx:
            parts.append(html.Span(" · ", className="chatbot-pmid-separator"))
        parts.append(
            html.A(
                pmid,
                href=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                target="_blank",
                rel="noopener noreferrer",
                className="chatbot-pmid-link",
            )
        )
    return parts


# 인사·환영 키워드 — 매칭 시 LLM 호출 없이 코드 직접 응답 (Guardrail 우회 + 비용 0)
_GREETING_KEYWORDS = {
    "안녕", "ㅎㅇ", "하이", "hi", "hello", "hey",
    "처음", "시작", "도움", "help",
}

_GREETING_CATEGORY_CHIPS = [
    {"id": "drug", "label": "💊 약물이 궁금해요"},
    {"id": "target", "label": "🧬 타겟이 궁금해요"},
    {"id": "model", "label": "📊 모델 결과가 궁금해요"},
    {"id": "usage", "label": "❓ 사용법이 궁금해요"},
]

_GREETING_CATEGORY_RESPONSES = {
    "drug": {
        "user": "[💊 약물 선택]",
        "assistant": (
            "champion model이 추천한 NSCLC 약물 후보를 알려드릴게요. "
            "패스웨이 맵에서 보라색 노드(약물 노드)를 클릭하면 자세한 정보가 나옵니다. "
            "대표 약물은 Osimertinib(3세대 EGFR-TKI), Erlotinib(1세대 EGFR-TKI), "
            "Pembrolizumab(면역항암제)입니다."
        ),
    },
    "target": {
        "user": "[🧬 타겟 선택]",
        "assistant": (
            "champion target은 EGFR, ERBB2, KRAS입니다. "
            "좌측 그래프에서 빨간 노드(seed) 또는 주황 노드(RWR top 10%)를 클릭하면 "
            "mechanism hypothesis를 볼 수 있어요."
        ),
    },
    "model": {
        "user": "[📊 모델 결과 선택]",
        "assistant": (
            "champion model은 E2_tcga_crispr이며 scaffold PR-AUC는 0.1253입니다. "
            "SHAP 기반 근거 분석은 후보 상세 탭에서 확인하세요."
        ),
    },
    "usage": {
        "user": "[❓ 사용법 선택]",
        "assistant": (
            "1) 좌측 그래프에서 노드를 클릭하세요. "
            "2) 추천 질문을 누르거나 직접 질문을 입력하세요. "
            "3) 후보 순위/시뮬레이터 탭에서 자세한 분석을 확인하세요. "
            "더 궁금한 게 있으면 직접 질문해주세요."
        ),
    },
}

_ABUSE_KEYWORDS = {
    "바보", "멍청", "꺼져", "닥쳐", "병신", "새끼", "fuck", "idiot", "stupid",
}
_MEDICAL_ADVICE_KEYWORDS = {
    "처방", "복용", "먹어도", "먹어도 돼", "써도 돼", "치료해줘", "진단", "용량",
    "dose", "dosage", "prescribe", "diagnose",
}


def _is_greeting(question: str) -> bool:
    """순수 인사 여부 — entity 매칭 차단 (Haiku freeform보다 우선 분기)."""
    text = (question or "").strip().casefold()
    if not text or len(text) > 20:
        return False
    return any(kw in text for kw in _GREETING_KEYWORDS)


def _guardrail_refusal(question: str) -> Optional[str]:
    text = (question or "").strip().casefold()
    if any(keyword in text for keyword in _ABUSE_KEYWORDS):
        return "그런 질문에는 답변하지 않습니다. NSCLC 약물 재창출 관련 질문을 해주세요."
    if any(keyword in text for keyword in _MEDICAL_ADVICE_KEYWORDS):
        return (
            "환자 개별 치료 결정은 임상의의 권한입니다. "
            "본 시스템은 약물 재창출 후보 탐색 도구이며, 진단·처방·복용 지침을 제공하지 않습니다."
        )
    return None


def _render_static_assistant(text: str, *, label: str = "instant") -> dmc.Stack:
    return dmc.Stack(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(label, className="chatbot-status-chip"),
                            html.Span("0ms", className="chatbot-status-chip"),
                        ],
                        className="chatbot-status-row",
                    ),
                    html.Div(text, className="chatbot-response-body"),
                ],
                className="chatbot-response chatbot-message-assistant",
            ),
        ],
        gap="xs",
    )


def _render_greeting_with_chips(question: str) -> dmc.Stack:
    """인사 응답 + 4개 카테고리 chip. LLM 호출 X (즉시 응답, 비용 0)."""
    chips = []
    for cat in _GREETING_CATEGORY_CHIPS:
        chips.append(
            html.Button(
                cat["label"],
                id={"type": "greeting-cat-chip", "index": cat["id"]},
                className="chatbot-suggest-btn",
                n_clicks=0,
            )
        )

    return dmc.Stack(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("instant", className="chatbot-status-chip"),
                            html.Span("0ms", className="chatbot-status-chip"),
                        ],
                        className="chatbot-status-row",
                    ),
                    html.Div(
                        "안녕하세요! NSCLC Insight Engine입니다 😊\n무엇이 궁금하신가요? 아래에서 골라주시거나, 직접 질문을 입력해주세요.",
                        className="chatbot-response-body",
                        style={"whiteSpace": "pre-line"},
                    ),
                    html.Div(chips, className="chatbot-suggest-row", style={"marginTop": "12px"}),
                ],
                className="chatbot-response chatbot-message-assistant",
            ),
        ],
        gap="xs",
    )


def _render_user_bubble(question: str) -> html.Div:
    """채팅창 누적용 user message 버블."""
    return html.Div(
        [
            html.Div(question, className="chatbot-bubble-user-text"),
            html.Span(time.strftime("%H:%M"), className="chatbot-bubble-ts"),
        ],
        className="chatbot-bubble-user",
    )


def _append_to_thread(existing_children, *new_messages):
    """기존 ANSWER_AREA children + 새 메시지들 누적.

    existing_children:
    - None/falsy → 첫 메시지, placeholder 제거하고 thread 시작
    - dict (단일 컴포넌트=placeholder) → 동일하게 thread 시작
    - list → 기존 thread에 append

    메시지 30쌍(=60개) 이상 시 오래된 거 자름.
    """
    if not existing_children or isinstance(existing_children, dict):
        return list(new_messages)
    if isinstance(existing_children, list):
        return (existing_children + list(new_messages))[-60:]
    return list(new_messages)


def _render_freeform_answer(question: str, resp: LLMResponse) -> dmc.Stack:
    """entity 매칭 실패 시 Haiku 자연어 응답 렌더."""
    chips = [
        html.Span(resp.mode or "haiku", className="chatbot-status-chip"),
        html.Span(_format_llm_latency(resp.latency_ms), className="chatbot-status-chip"),
    ]
    return dmc.Stack(
        [
            html.Div(
                [
                    html.Div(chips, className="chatbot-status-row"),
                    html.Div(resp.text, className="chatbot-response-body"),
                ],
                className="chatbot-response chatbot-message-assistant",
            ),
        ],
        gap="xs",
    )


def _render_entity_guide(question: str) -> dmc.Stack:
    return dmc.Stack(
        [
            dmc.Alert(
                "구체적인 단백질/약물 이름(EGFR, KRAS, Osimertinib 등)을 포함해 주세요.",
                title="엔티티를 찾지 못했습니다",
                color="yellow",
                variant="light",
                className="chatbot-guide",
            ),
        ],
        gap="xs",
    )


def _query_llm_for_chat(question: str, payload: Optional[dict], fast_mode: bool = False) -> dmc.Stack:
    """챗봇 응답 라우팅.

    1. 인사 매칭 → chip 4개 즉시 응답 (LLM X)
    2. RWR next-node → 전용 핸들러
    3. entity 매칭 시 Sonnet 또는 Haiku (fast_mode)
    4. entity 없음 → Haiku freeform
    """
    refusal = _guardrail_refusal(question)
    if refusal:
        return _render_static_assistant(refusal, label="guardrail")

    if _is_greeting(question):
        return _render_greeting_with_chips(question)

    if _is_next_node_question(question):
        return _render_rwr_next_nodes(question, payload)

    entity = _extract_llm_entity(question, payload)
    if not entity:
        # entity 없음 → Haiku freeform 라우팅 (인사·사용법·잡담)
        try:
            resp = query_freeform(question)
        except Exception as exc:
            resp = LLMResponse(
                text="응답 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
                pmids=[],
                grounded=False,
                cached=False,
                mode="error",
                latency_ms=0,
                error=f"freeform_exc:{type(exc).__name__}",
            )
        return _render_freeform_answer(question, resp)

    name, name_type = entity
    role_parts = ["chatbot popup"]
    if payload and payload.get("pathway_name"):
        role_parts.append(str(payload.get("pathway_name")))
    if payload and payload.get("node_type"):
        role_parts.append(str(payload.get("node_type")))

    query_fn = query_entity_haiku if fast_mode else query_entity
    try:
        resp = query_fn(
            name,
            name_type,
            k=3,
            role=" · ".join(role_parts),
            user_question=question,
        )
    except Exception as exc:
        resp = LLMResponse(
            text="Insufficient evidence: 근거 문헌을 안정적으로 불러오지 못했습니다.",
            pmids=[],
            grounded=False,
            cached=False,
            mode="error",
            latency_ms=0,
            error=f"ui_exception:{type(exc).__name__}",
        )

    chips = [
        html.Span("cached" if resp.cached else "fresh", className="chatbot-status-chip"),
        html.Span(resp.mode or "unknown", className="chatbot-status-chip"),
        html.Span(_format_llm_latency(resp.latency_ms), className="chatbot-status-chip"),
    ]
    if not resp.grounded:
        chips.append(html.Span("insufficient", className="chatbot-status-chip is-muted"))

    return dmc.Stack(
        [
            html.Div(
                [
                    html.Div(chips, className="chatbot-status-row"),
                    html.Div(resp.text, className="chatbot-response-body"),
                    html.Div(
                        [
                            html.Span("참고: ", className="chatbot-pmid-label"),
                            *_render_chatbot_pmid_links(resp.pmids),
                        ],
                        className="chatbot-pmids",
                    ),
                ],
                className="chatbot-response chatbot-message-assistant",
            ),
        ],
        gap="xs",
    )


def _query_llm_for_chat_with_timeout(
    question: str,
    payload: Optional[dict],
    *,
    fast_mode: bool = False,
) -> dmc.Stack:
    """Bound Bedrock latency so the chat thread always receives an assistant turn."""
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(_query_llm_for_chat, question, payload, fast_mode)
    try:
        return future.result(timeout=CHAT_QUERY_TIMEOUT_SECONDS)
    except FuturesTimeoutError:
        future.cancel()
        return _render_static_assistant(
            "응답 생성 실패, 다시 시도해주세요.",
            label="timeout",
        )
    except Exception:
        return _render_static_assistant(
            "응답 생성 실패, 다시 시도해주세요.",
            label="error",
        )
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------
@callback(
    Output(ANSWER_AREA_ID, "children", allow_duplicate=True),
    Output(INPUT_ID, "value", allow_duplicate=True),
    Input(SUBMIT_BTN_ID, "n_clicks"),
    Input(INPUT_ID, "n_submit"),
    State(INPUT_ID, "value"),
    State(CONTEXT_STORE_ID, "data"),
    State(ANSWER_AREA_ID, "children"),
    prevent_initial_call=True,
)
def _on_submit(
    n_clicks: Optional[int],
    n_submit: Optional[int],
    question: Optional[str],
    context_payload: Optional[dict],
    existing_thread,
):
    """전송 버튼 클릭 또는 입력창 Enter 키. 채팅창 누적."""
    if not n_clicks and not n_submit:
        return no_update, no_update
    if not question or not question.strip():
        return _render_empty_input_warning(), no_update
    q = question.strip()
    user_bubble = _render_user_bubble(q)
    assistant_resp = _query_llm_for_chat_with_timeout(q, context_payload)
    thread = _append_to_thread(existing_thread, user_bubble, assistant_resp)
    return thread, ""


@callback(
    Output(SUGGESTIONS_ID, "children"),
    Input(CONTEXT_STORE_ID, "data"),
)
def _update_suggestions(payload: Optional[dict]):
    """컨텍스트 Store 갱신 → 추천 질문 재생성."""
    return _render_suggestions(payload)


clientside_callback(
    """
    function(children) {
        const scrollToBottom = function() {
            const thread = document.getElementById("chatbot-answer-area");
            if (thread) {
                thread.scrollTop = thread.scrollHeight;
            }
        };
        window.requestAnimationFrame(function() {
            scrollToBottom();
            window.setTimeout(scrollToBottom, 60);
        });
        return String(Date.now());
    }
    """,
    Output(AUTO_SCROLL_ID, "children"),
    Input(ANSWER_AREA_ID, "children"),
    prevent_initial_call=True,
)



@callback(
    Output(ANSWER_AREA_ID, "children", allow_duplicate=True),
    Input({"type": SUGGEST_BTN_TYPE, "index": ALL}, "n_clicks"),
    State({"type": SUGGEST_BTN_TYPE, "index": ALL}, "children"),
    State(CONTEXT_STORE_ID, "data"),
    State(ANSWER_AREA_ID, "children"),
    prevent_initial_call=True,
)
def _on_suggest_click(n_clicks_list, questions, context_payload: Optional[dict], existing_thread):
    """추천 질문 칩 클릭 → 즉시 전송. 채팅창 누적."""
    if not n_clicks_list or not any(n for n in n_clicks_list if n):
        return no_update
    # fix v15.1: stale fire 차단
    triggered_full = dash_ctx.triggered
    if not triggered_full or not triggered_full[0].get("value"):
        return no_update
    triggered = dash_ctx.triggered_id
    if triggered is None or not isinstance(triggered, dict):
        return no_update
    idx = triggered.get("index")
    if not isinstance(idx, int) or idx >= len(questions):
        return no_update
    question = questions[idx]
    if not question or not isinstance(question, str):
        return no_update
    user_bubble = _render_user_bubble(question)
    assistant_resp = _query_llm_for_chat_with_timeout(question, context_payload, fast_mode=True)
    return _append_to_thread(existing_thread, user_bubble, assistant_resp)


@callback(
    Output(ANSWER_AREA_ID, "children", allow_duplicate=True),
    Input({"type": "greeting-cat-chip", "index": ALL}, "n_clicks"),
    State(CONTEXT_STORE_ID, "data"),
    State(ANSWER_AREA_ID, "children"),
    prevent_initial_call=True,
)
def _on_greeting_chip_click(n_clicks_list, context_payload, existing_thread):
    """인사 응답 카테고리 chip 클릭 → 카테고리별 안내를 기존 thread에 누적."""
    if not n_clicks_list or not any(n for n in n_clicks_list if n):
        return no_update

    # fix v15.1: stale fire 차단 — 실제 클릭 트리거 검증
    triggered_full = dash_ctx.triggered
    if not triggered_full or not triggered_full[0].get("value"):
        return no_update
    
    triggered = dash_ctx.triggered_id
    if not isinstance(triggered, dict):
        return no_update

    category = triggered.get("index")
    payload = _GREETING_CATEGORY_RESPONSES.get(category)
    if not payload:
        return no_update

    user_bubble = _render_user_bubble(payload["user"])
    assistant_resp = _render_static_assistant(payload["assistant"])
    return _append_to_thread(existing_thread, user_bubble, assistant_resp)


@callback(
    Output(COLLAPSE_ID, "opened"),
    Output(COLLAPSE_BTN_ID, "children"),
    Input(COLLAPSE_BTN_ID, "n_clicks"),
    State(COLLAPSE_ID, "opened"),
    prevent_initial_call=True,
)
def _on_chatbot_collapse_toggle(n_clicks, currently_opened):
    """챗봇 패널 접기/펼치기 토글."""
    if not n_clicks:
        return no_update, no_update
    new_opened = not currently_opened
    label = "▼ 접기" if new_opened else "▶ 펼치기"
    return new_opened, label


@callback(
    Output(CONTEXT_BADGE_ID, "children"),
    Input(CONTEXT_STORE_ID, "data"),
)
def _update_context_badge(payload: Optional[dict]):
    """컨텍스트 Store 갱신 → 헤더 배지 업데이트 (현재 선택 gene 표시)."""
    if not payload:
        return dmc.Badge("노드 미선택", color="gray", variant="light", size="sm")

    gene = payload.get("gene_symbol", "?")
    n_int = len(payload.get("internal_compounds", []))
    n_ext = len(payload.get("external_chembl", []))
    n_ot = len(payload.get("clinical_drugs", []))
    return dmc.Group([
        dmc.Badge(gene, color="orange", variant="filled", size="sm"),
        dmc.Badge(f"내부 {n_int}", color="blue", variant="outline", size="xs"),
        dmc.Badge(f"외부 {n_ext}", color="grape", variant="outline", size="xs"),
        dmc.Badge(f"OT {n_ot}", color="cyan", variant="outline", size="xs"),
    ], gap=4)

# fix v14-B: Send 버튼 즉시 비활성화 + "전송 중..." 표시 (중복 클릭 방지)
clientside_callback(
    """
    function(n_clicks, n_submit, current_value) {
        // 입력값이 비어있으면 비활성화 X
        if (!current_value || !current_value.trim()) {
            return [false, "Send"];
        }
        // 클릭 또는 엔터가 트리거된 경우 즉시 비활성화
        if ((n_clicks && n_clicks > 0) || (n_submit && n_submit > 0)) {
            return [true, "ooO"];
        }
        return [false, "Send"];
    }
    """,
    Output(SUBMIT_BTN_ID, "disabled", allow_duplicate=True),
    Output(SUBMIT_BTN_ID, "children", allow_duplicate=True),
    Input(SUBMIT_BTN_ID, "n_clicks"),
    Input(INPUT_ID, "n_submit"),
    State(INPUT_ID, "value"),
    prevent_initial_call=True,
)


# 응답 완료 후 Send 버튼 복구 (ANSWER_AREA 변경 감지 → 버튼 원복)
clientside_callback(
    """
    function(answer_children) {
        return [false, "Send"];
    }
    """,
    Output(SUBMIT_BTN_ID, "disabled", allow_duplicate=True),
    Output(SUBMIT_BTN_ID, "children", allow_duplicate=True),
    Input(ANSWER_AREA_ID, "children"),
    prevent_initial_call=True,
)
