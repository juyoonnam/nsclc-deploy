"""
nsclc_ui/components/paper_intel_panel.py

논문 기반 분석 패널 — Pathway Map 안에 들어감.

구성
----
1. 상단 입력: PMID/DOI 입력창 + 예시 버튼 + 분석 시작 버튼
2. 결과 영역:
   - 메타 카드 (제목/저널/연도/저자/소스 배지)
   - 추출 카드 4개 (drugs / targets / clinical_phase / response_rates)
   - 패스웨이 매칭 정보 (cytoscape overlay 트리거용 Store)
3. collapsible (Pathway Map 안에서 접고 펼치기)

상태 관리
---------
- `paper-extraction-store`: 추출 결과 dict (cytoscape overlay와 공유)
  → pathway_map.py가 이 Store의 targets를 보고 노드 highlight
- `paper-collapsed-store`: 접힘 상태

설계 결정
---------
- fetch + extract는 1번 callback으로 묶음 (UX: 분석 시작 한번)
- 길이 긴 호출이라 dcc.Loading 필수 (5-30초 가능)
- 시연용 PMID 예시 3개 prefab (FLAURA / AURA / ALEX)
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import dash_mantine_components as dmc
from dash import callback, dcc, html, no_update, ALL, ctx as dash_ctx
from dash.dependencies import Input, Output, State

from nsclc_ui.data.pubmed import FetchError, fetch_paper
from nsclc_ui.data.paper_extractor import (
    PaperExtraction,
    extract_from_paper,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public IDs
# ---------------------------------------------------------------------------
INPUT_ID = "paper-intel-input"
SUBMIT_BTN_ID = "paper-intel-submit-btn"
RESULT_AREA_ID = "paper-intel-result"
EXTRACTION_STORE_ID = "paper-extraction-store"  # cytoscape overlay 공유
COLLAPSE_BTN_ID = "paper-intel-collapse-btn"
COLLAPSE_ID = "paper-intel-collapse"
LOADING_ID = "paper-intel-loading"
PREFAB_BTN_TYPE = "paper-intel-prefab"

# 시연용 PMID 예시 (NSCLC 표준 임상시험)
PREFAB_EXAMPLES = [
    {"label": "FLAURA (Osimertinib 1L)", "pmid": "29151359"},
    {"label": "AURA3 (Osimertinib T790M)", "pmid": "27959700"},
    {"label": "ALEX (Alectinib ALK)", "pmid": "28586279"},
]

# 임상 phase별 색상
_PHASE_COLOR = {
    "Approved": "green",
    "Phase 4": "teal",
    "Phase 3": "cyan",
    "Phase 2": "blue",
    "Phase 1": "indigo",
    "Preclinical": "violet",
    "Unknown": "gray",
}


# ---------------------------------------------------------------------------
# UI: 패널 layout
# ---------------------------------------------------------------------------
def paper_intel_panel() -> dmc.Paper:
    """Pathway Map 안에 들어갈 논문 분석 패널."""
    header = dmc.Group([
        dmc.Group([
            dmc.Text("📄", size="xl"),
            dmc.Stack([
                dmc.Text("논문 기반 분석", size="md", fw=600,
                         style={"color": "#C1C2C5", "lineHeight": 1.1}),
                dmc.Text(
                    "PMID/DOI 입력 → 4항목 자동 추출 + 패스웨이 매칭",
                    size="xs", c="dimmed", style={"lineHeight": 1.1},
                ),
            ], gap=2),
        ], gap="xs", align="center"),
        dmc.Button(
            "▼ 접기",
            id=COLLAPSE_BTN_ID,
            variant="subtle",
            size="xs",
            color="gray",
        ),
    ], justify="space-between", align="center")

    input_section = dmc.Stack([
        # 예시 칩
        dmc.Group([
            dmc.Text("💡 예시:", size="xs", c="dimmed"),
            *[
                dmc.Button(
                    p["label"],
                    id={"type": PREFAB_BTN_TYPE, "index": i},
                    variant="light",
                    color="violet",
                    size="xs",
                    radius="xl",
                )
                for i, p in enumerate(PREFAB_EXAMPLES)
            ],
        ], gap="xs", wrap="wrap"),

        # 입력 + 분석 시작 버튼 (한 줄)
        dmc.Group([
            dcc.Input(
                id=INPUT_ID,
                type="text",
                placeholder="PMID(예: 29151359) 또는 DOI(예: 10.1056/NEJMoa1713137)",
                value="",
                style={
                    "flex": "1",
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
                "분석 시작",
                id=SUBMIT_BTN_ID,
                color="violet",
                variant="filled",
                size="sm",
            ),
        ], gap="xs", style={"width": "100%"}),

        dmc.Text(
            "⚠️ PMC Open Access 논문은 본문, 외 논문은 초록만 분석됩니다. "
            "Bedrock 호출로 5-30초 소요.",
            size="xs", c="dimmed", fs="italic",
        ),
    ], gap=8)

    initial_result = dmc.Paper(
        dmc.Stack([
            dmc.Text("👆 위에서 PMID/DOI를 입력하거나 예시를 눌러주세요.",
                     size="sm", c="dimmed", ta="center"),
        ], gap=4),
        p="md",
        style={
            "backgroundColor": "rgba(190, 75, 219, 0.05)",
            "border": "1px dashed rgba(190, 75, 219, 0.3)",
            "borderRadius": "6px",
        },
    )

    body = dmc.Stack([
        input_section,
        dmc.Divider(variant="dashed"),
        dcc.Loading(
            id=LOADING_ID,
            type="dot",
            color="#BE4BDB",
            children=html.Div(id=RESULT_AREA_ID, children=initial_result),
        ),
    ], gap="md")

    return dmc.Paper(
        dmc.Stack([
            header,
            dmc.Collapse(
                id=COLLAPSE_ID,
                opened=True,
                children=body,
            ),
            # Stores
            dcc.Store(id=EXTRACTION_STORE_ID, data=None),
        ], gap="sm"),
        style={
            "padding": "16px",
            "backgroundColor": "rgba(37, 38, 43, 0.6)",
            "border": "1px solid #373A40",
            "borderRadius": "8px",
        },
    )


# ---------------------------------------------------------------------------
# 결과 렌더링
# ---------------------------------------------------------------------------
def _render_paper_meta(paper, extraction: PaperExtraction) -> dmc.Paper:
    """논문 메타데이터 카드 (제목/저널/연도/소스)."""
    source_badge = (
        dmc.Badge("PMC OA 본문", color="green", variant="filled", size="sm")
        if paper.has_full_text
        else dmc.Badge("초록만", color="orange", variant="light", size="sm")
    )

    authors_text = ", ".join(paper.authors[:3])
    if len(paper.authors) > 3:
        authors_text += f" 외 {len(paper.authors) - 3}명"

    return dmc.Paper(
        dmc.Stack([
            dmc.Group([
                dmc.Badge(f"PMID {paper.pmid}", color="blue", variant="outline", size="sm"),
                source_badge,
                dmc.Badge(
                    extraction.clinical_phase,
                    color=_PHASE_COLOR.get(extraction.clinical_phase, "gray"),
                    variant="filled", size="sm",
                ),
            ], gap="xs"),

            dmc.Text(paper.title, size="md", fw=600,
                     style={"color": "#C1C2C5"}),

            dmc.Group([
                dmc.Text(paper.journal or "?", size="xs", c="dimmed", fs="italic"),
                dmc.Text(f"({paper.year})" if paper.year else "", size="xs", c="dimmed"),
                dmc.Text(authors_text, size="xs", c="dimmed"),
            ], gap="sm"),

            *(
                [dmc.Paper(
                    dmc.Group([
                        dmc.Text("📝", size="sm"),
                        dmc.Text(extraction.raw_summary, size="sm",
                                 style={"color": "#C1C2C5", "fontStyle": "italic"}),
                    ], gap="xs", align="flex-start"),
                    p="sm",
                    style={"backgroundColor": "rgba(77, 171, 247, 0.05)",
                           "borderRadius": "4px"},
                )]
                if extraction.raw_summary else []
            ),
        ], gap=6),
        p="md",
        style={
            "backgroundColor": "rgba(255,255,255,0.02)",
            "border": "1px solid rgba(255,255,255,0.05)",
            "borderRadius": "6px",
        },
    )


def _render_extraction_cards(extraction: PaperExtraction) -> dmc.Grid:
    """추출 4항목 그리드 카드."""
    cards = []

    # 약물
    if extraction.drugs:
        drug_items = [
            dmc.Group([
                dmc.Badge(d.name, color="violet", variant="filled", size="sm"),
                *(
                    [dmc.Badge(d.chembl_id, color="grape", variant="outline", size="xs")]
                    if d.chembl_id else []
                ),
                *(
                    [dmc.Badge(d.role, color="gray", variant="dot", size="xs")]
                    if d.role else []
                ),
            ], gap=4)
            for d in extraction.drugs[:8]
        ]
        cards.append(_card_block("💊 약물", "violet", drug_items, count=len(extraction.drugs)))
    else:
        cards.append(_card_empty("💊 약물", "추출 안 됨"))

    # 타겟
    if extraction.targets:
        target_items = [
            dmc.Group([
                dmc.Badge(t.symbol, color="orange", variant="filled", size="sm"),
                *(
                    [dmc.Text(t.full_name[:40], size="xs", c="dimmed")]
                    if t.full_name else []
                ),
            ], gap=4)
            for t in extraction.targets[:8]
        ]
        cards.append(_card_block("🎯 타겟", "orange", target_items, count=len(extraction.targets)))
    else:
        cards.append(_card_empty("🎯 타겟", "추출 안 됨"))

    # 임상 단계 (단일 값)
    phase_color = _PHASE_COLOR.get(extraction.clinical_phase, "gray")
    cards.append(_card_block(
        "📋 임상 단계", phase_color,
        [dmc.Badge(extraction.clinical_phase, color=phase_color,
                   variant="filled", size="lg")],
    ))

    # 반응률
    if extraction.response_rates:
        rate_items = []
        for r in extraction.response_rates[:5]:
            cohort_text = f" ({r.cohort})" if r.cohort else ""
            rate_items.append(
                dmc.Group([
                    dmc.Badge(r.metric, color="cyan", variant="filled", size="xs"),
                    dmc.Text(r.value, size="sm", fw=600,
                             style={"color": "#C1C2C5"}),
                    *(
                        [dmc.Text(cohort_text, size="xs", c="dimmed")]
                        if cohort_text else []
                    ),
                ], gap=4, align="center")
            )
        cards.append(_card_block(
            "📊 반응률", "cyan", rate_items, count=len(extraction.response_rates),
        ))
    else:
        cards.append(_card_empty("📊 반응률", "추출 안 됨"))

    return dmc.Grid([
        dmc.GridCol(c, span=6) for c in cards
    ], gutter="sm")


def _card_block(title: str, color: str, items: list, count: Optional[int] = None) -> dmc.Paper:
    header_text = f"{title} ({count})" if count is not None and count > 0 else title
    return dmc.Paper(
        dmc.Stack([
            dmc.Text(header_text, size="xs", fw=600,
                     style={"color": "#C1C2C5"}),
            dmc.Stack(items, gap=4),
        ], gap="xs"),
        p="sm",
        style={
            "backgroundColor": "rgba(255,255,255,0.03)",
            "border": "1px solid rgba(255,255,255,0.06)",
            "borderRadius": "6px",
            "minHeight": "120px",
        },
    )


def _card_empty(title: str, msg: str) -> dmc.Paper:
    return dmc.Paper(
        dmc.Stack([
            dmc.Text(title, size="xs", fw=600, c="dimmed"),
            dmc.Text(msg, size="xs", c="dimmed", fs="italic"),
        ], gap="xs"),
        p="sm",
        style={
            "backgroundColor": "rgba(255,255,255,0.01)",
            "border": "1px dashed rgba(255,255,255,0.05)",
            "borderRadius": "6px",
            "minHeight": "120px",
        },
    )


def _render_pathway_match_hint(extraction: PaperExtraction) -> Optional[dmc.Alert]:
    """패스웨이 노드 매칭 안내 — 추출 타겟이 그래프 노드와 매치될 가능성."""
    if not extraction.targets:
        return None
    symbols = [t.symbol for t in extraction.targets]
    return dmc.Alert(
        dmc.Group([
            dmc.Text("✨", size="md"),
            dmc.Text(
                f"위 타겟({', '.join(symbols[:5])})이 패스웨이 그래프에서 하이라이트됩니다.",
                size="sm", style={"color": "#C1C2C5"},
            ),
        ], gap="xs"),
        color="violet", variant="light", radius="sm",
    )


def _render_error(reason: str, detail: Optional[str] = None) -> dmc.Alert:
    return dmc.Alert(
        dmc.Stack([
            dmc.Text(reason, fw=600, size="sm"),
            *([dmc.Text(detail, size="xs", c="dimmed")] if detail else []),
        ], gap=4),
        title="분석 실패",
        color="red", variant="light",
    )


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------
@callback(
    Output(RESULT_AREA_ID, "children"),
    Output(EXTRACTION_STORE_ID, "data"),
    Input(SUBMIT_BTN_ID, "n_clicks"),
    Input(INPUT_ID, "n_submit"),
    State(INPUT_ID, "value"),
    prevent_initial_call=True,
)
def _on_submit(n_clicks, n_submit, identifier: Optional[str]):
    """입력 → fetch → extract → 카드 렌더 + Store에 저장."""
    if not n_clicks and not n_submit:
        return no_update, no_update

    if not identifier or not identifier.strip():
        return _render_error("입력 비어있음", "PMID 또는 DOI를 입력하세요."), None

    identifier = identifier.strip()

    # 1. fetch
    try:
        paper = fetch_paper(identifier, fetch_fulltext=True)
    except FetchError as e:
        return _render_error(e.reason, e.detail), None
    except Exception as e:  # noqa: BLE001
        logger.exception("[paper_intel] unexpected fetch error")
        return _render_error(
            "예상치 못한 오류",
            f"{type(e).__name__}: {str(e)[:200]}",
        ), None

    # 2. extract
    try:
        extraction = extract_from_paper(paper.title, paper.text_for_extraction)
    except Exception as e:  # noqa: BLE001
        logger.exception("[paper_intel] unexpected extract error")
        # paper 메타는 보여주되 추출은 실패 표시
        return dmc.Stack([
            _render_paper_meta(paper, PaperExtraction(
                fallback_reason=f"unexpected: {type(e).__name__}",
                confidence=0.0,
            )),
            _render_error("추출 실패", str(e)[:200]),
        ]), None

    # 3. render
    blocks = [_render_paper_meta(paper, extraction)]

    if extraction.fallback_reason:
        blocks.append(dmc.Alert(
            f"LLM 추출 실패 — {extraction.fallback_reason}",
            color="orange", variant="light", title="Fallback",
        ))
    elif extraction.is_empty():
        blocks.append(dmc.Alert(
            "추출된 항목이 없습니다. NSCLC와 관련성이 낮거나 텍스트가 부족할 수 있습니다.",
            color="yellow", variant="light",
        ))
    else:
        blocks.append(_render_extraction_cards(extraction))
        match_hint = _render_pathway_match_hint(extraction)
        if match_hint is not None:
            blocks.append(match_hint)

    # Store payload — cytoscape overlay에서 쓰일 형식
    store_data = {
        "pmid": paper.pmid,
        "title": paper.title,
        "target_symbols": [t.symbol for t in extraction.targets],
        "drug_names": [d.name for d in extraction.drugs],
        "clinical_phase": extraction.clinical_phase,
    } if not extraction.is_empty() else None

    return dmc.Stack(blocks, gap="sm"), store_data


@callback(
    Output(INPUT_ID, "value"),
    Input({"type": PREFAB_BTN_TYPE, "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def _on_prefab_click(n_clicks_list):
    """예시 칩 클릭 → 입력창 채움 (자동 전송 X — 사용자가 시작 버튼 누름)."""
    if not n_clicks_list or not any(n for n in n_clicks_list if n):
        return no_update

    triggered = dash_ctx.triggered_id
    if triggered is None or not isinstance(triggered, dict):
        return no_update
    idx = triggered.get("index")
    if not isinstance(idx, int) or idx >= len(PREFAB_EXAMPLES):
        return no_update

    return PREFAB_EXAMPLES[idx]["pmid"]


@callback(
    Output(COLLAPSE_ID, "opened"),
    Output(COLLAPSE_BTN_ID, "children"),
    Input(COLLAPSE_BTN_ID, "n_clicks"),
    State(COLLAPSE_ID, "opened"),
    prevent_initial_call=True,
)
def _on_collapse_toggle(n_clicks, currently_opened):
    """접기/펼치기 토글."""
    if not n_clicks:
        return no_update, no_update
    new_opened = not currently_opened
    label = "▼ 접기" if new_opened else "▶ 펼치기"
    return new_opened, label
