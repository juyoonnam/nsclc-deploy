"""
Mode 1 Library view for the Simulator tab.
"""

from __future__ import annotations

import math

from dash import dcc, html

from nsclc_ui.data.simulator_demo import LIBRARY_PAGE_SIZE


_STATUS_LABELS = {
    "approved": "승인",
    "approved_other": "승인*",
    "phase_2": "Phase 2",
    "preclinical": "전임상",
}


def _filters(filters: dict | None) -> dict:
    defaults = {
        "drugbank": True,
        "drugcentral": True,
        "nsclc_unused_only": True,
        "query": "",
        "sort_desc": True,
    }
    defaults.update(filters or {})
    return defaults


def _status_label(status: str) -> str:
    return _STATUS_LABELS.get(status, status or "-")


def _status_badge(status: str) -> html.Span:
    return html.Span(
        _status_label(status),
        className=f"simulator-status-badge simulator-status-{status}",
    )


def _confidence_dots(confidence: int) -> html.Div:
    confidence = max(0, min(3, int(confidence or 0)))
    return html.Div(
        [
            html.Span(
                "●",
                className="simulator-confidence-dot is-filled"
                if idx < confidence
                else "simulator-confidence-dot",
            )
            for idx in range(3)
        ],
        className="simulator-confidence",
        title=f"confidence {confidence}/3",
    )


def _source_chip(label: str, key: str, active: bool) -> html.Button:
    return html.Button(
        [
            html.Span("▤", className="simulator-chip-icon"),
            html.Span(label),
            html.Span("✓", className="simulator-chip-check"),
        ],
        id=f"sim-filter-{key}",
        n_clicks=0,
        className="simulator-source-chip is-active" if active else "simulator-source-chip",
    )


def _toggle_switch(active: bool) -> html.Button:
    return html.Button(
        [
            html.Span(className="simulator-switch-track"),
            html.Span("NSCLC 미사용약만", className="simulator-switch-label"),
            html.Span("ⓘ", className="simulator-info", title="NSCLC 라벨이 없는 재창출 후보를 우선 표시합니다."),
        ],
        id="sim-filter-unused",
        n_clicks=0,
        className="simulator-switch is-on" if active else "simulator-switch",
    )


def _controls(filters: dict, total_count: int) -> html.Div:
    query = filters.get("query", "")
    return html.Div(
        [
            html.Div(
                [
                    _source_chip("DrugBank", "drugbank", bool(filters.get("drugbank"))),
                    _source_chip("DrugCentral", "drugcentral", bool(filters.get("drugcentral"))),
                    _toggle_switch(bool(filters.get("nsclc_unused_only"))),
                ],
                className="simulator-filter-group",
            ),
            html.Div(
                [
                    html.Span("⌕", className="simulator-search-icon"),
                    dcc.Input(
                        id="sim-library-search",
                        type="text",
                        value=query,
                        placeholder="약물명 검색 (예: Crizotinib)",
                        debounce=False,
                        className="simulator-search-input",
                    ),
                ],
                className="simulator-search",
            ),
            html.Button(
                [
                    html.Span("▥", className="simulator-candidate-icon"),
                    html.Span(f"재창출 후보 {total_count}개"),
                ],
                className="simulator-candidate-button",
                title="현재 필터 기준 재창출 후보 수",
            ),
        ],
        className="simulator-controls",
    )


def _metric_card(icon: str, tone: str, label: str, value: str) -> html.Div:
    return html.Div(
        [
            html.Div(icon, className=f"simulator-metric-icon simulator-metric-{tone}"),
            html.Div(
                [
                    html.Div(label, className="simulator-metric-label"),
                    html.Div(value, className="simulator-metric-value"),
                ],
                className="simulator-metric-copy",
            ),
        ],
        className="simulator-metric-card",
    )


def _metric_cards() -> html.Div:
    return html.Div(
        [
            _metric_card("⚗", "purple", "스크리닝 약물", "14,000+"),
            _metric_card("◈", "green", "Top confidence 후보", "23"),
            _metric_card("◎", "blue", "재창출 후보 중심", "NSCLC 미사용약 우선"),
        ],
        className="simulator-metrics",
    )


def _pagination_items(page: int, page_count: int) -> list[int | str]:
    if page_count <= 7:
        return list(range(1, page_count + 1))
    if page <= 5:
        return [1, 2, 3, 4, 5, "...", page_count]
    if page >= page_count - 3:
        return [1, "...", page_count - 4, page_count - 3, page_count - 2, page_count - 1, page_count]
    return [1, "...", page - 1, page, page + 1, "...", page_count]


def _pagination(page: int, total_count: int) -> html.Div:
    page_count = max(1, math.ceil(max(total_count, 1) / LIBRARY_PAGE_SIZE))
    page = min(max(1, page), page_count)
    controls = [
        html.Button(
            "‹",
            id="sim-page-prev",
            n_clicks=0,
            disabled=page <= 1,
            className="simulator-page-button",
            title="이전 페이지",
        )
    ]
    for item in _pagination_items(page, page_count):
        if item == "...":
            controls.append(html.Span("...", className="simulator-page-ellipsis"))
        else:
            controls.append(
                html.Button(
                    str(item),
                    id={"type": "sim-library-page", "page": item},
                    n_clicks=0,
                    className=(
                        "simulator-page-button is-active"
                        if item == page
                        else "simulator-page-button"
                    ),
                    title=f"{item} 페이지",
                )
            )
    controls.append(
        html.Button(
            "›",
            id="sim-page-next",
            n_clicks=0,
            disabled=page >= page_count,
            className="simulator-page-button",
            title="다음 페이지",
        )
    )
    return html.Div(controls, className="simulator-pagination")


def _table(rows: list[dict], selected_drug: dict | None, page: int, total_count: int) -> html.Div:
    selected_id = (selected_drug or {}).get("drugbank_id")
    return html.Div(
        [
            html.Div(
                html.Table(
                    [
                        html.Thead(
                            html.Tr(
                                [
                                    html.Th("순위"),
                                    html.Th("약물"),
                                    html.Th(
                                        html.Button(
                                            "rank_score ↓",
                                            id="sim-sort-score",
                                            n_clicks=0,
                                            className="simulator-sort-button",
                                            title="rank_score 정렬 전환",
                                        )
                                    ),
                                    html.Th("신뢰도"),
                                    html.Th("임상상태"),
                                ]
                            )
                        ),
                        html.Tbody(
                            [
                                html.Tr(
                                    [
                                        html.Td(row["rank"]),
                                        html.Td(row["name"], className="simulator-drug-name"),
                                        html.Td(f"{row['rank_score']:.2f}", className="simulator-score-cell"),
                                        html.Td(_confidence_dots(row.get("confidence", 0))),
                                        html.Td(_status_badge(row.get("clinical_status", ""))),
                                    ],
                                    id={"type": "sim-library-row", "drugbank_id": row["drugbank_id"]},
                                    n_clicks=0,
                                    className=(
                                        "simulator-table-row is-selected"
                                        if row["drugbank_id"] == selected_id
                                        else "simulator-table-row"
                                    ),
                                    title=f"{row['name']} 상세 보기",
                                )
                                for row in rows
                            ]
                        ),
                    ],
                    className="simulator-table",
                ),
                className="simulator-table-scroll",
            ),
            _pagination(page, total_count),
            html.Div(
                "* = 다른 암종 승인, NSCLC 미사용 → 재창출 후보",
                className="simulator-table-footnote",
            ),
        ],
        className="simulator-table-card",
    )


def _structure_sketch() -> html.Div:
    bonds = [
        ("b1", 68, 162, 58, -28),
        ("b2", 113, 137, 65, 29),
        ("b3", 171, 166, 66, -16),
        ("b4", 226, 151, 56, 26),
        ("b5", 273, 175, 57, -35),
        ("b6", 318, 141, 48, 32),
        ("b7", 169, 166, 44, 38),
        ("b8", 211, 203, 42, 34),
    ]
    atoms = [
        ("N", 60, 138),
        ("N", 132, 132),
        ("N", 246, 158),
        ("NH", 347, 172),
        ("NH₂", 398, 218),
        ("CH₃", 334, 265),
        ("Cl", 399, 42),
        ("F", 399, 93),
    ]
    return html.Div(
        [
            html.Div("화학 구조", className="simulator-structure-label"),
            html.Div(className="simulator-highlight-red"),
            html.Div(className="simulator-highlight-amber"),
            *[
                html.Div(
                    className=f"simulator-bond simulator-bond-{name}",
                    style={
                        "left": f"{left}px",
                        "top": f"{top}px",
                        "width": f"{width}px",
                        "transform": f"rotate({angle}deg)",
                    },
                )
                for name, left, top, width, angle in bonds
            ],
            *[
                html.Span(atom, className="simulator-atom", style={"left": f"{left}px", "top": f"{top}px"})
                for atom, left, top in atoms
            ],
            html.Div("구조 단순화 표시", className="simulator-structure-caption"),
            html.Button("↗", className="simulator-structure-expand", title="확대"),
        ],
        className="simulator-structure",
    )


def _recommend_section(selected_drug: dict) -> html.Div:
    return html.Div(
        [
            html.Div("💡 왜 추천?", className="simulator-detail-section-title"),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("rank_score"),
                            html.Span(f"{selected_drug.get('rank_score', 0):.2f}", className="simulator-green-text"),
                        ],
                        className="simulator-detail-kv",
                    ),
                    html.Div(
                        [
                            html.Span("Scaffold cluster"),
                            html.Span(f"#{selected_drug.get('scaffold_cluster', '-')}", className="simulator-green-text"),
                        ],
                        className="simulator-detail-kv",
                    ),
                    html.Div(selected_drug.get("why_recommend", "-"), className="simulator-detail-line"),
                ],
                className="simulator-detail-list",
            ),
        ],
        className="simulator-detail-section",
    )


def _model_note_section(selected_drug: dict) -> html.Div:
    return html.Div(
        [
            html.Div("📝 모델 메모", className="simulator-detail-section-title"),
            html.Div(selected_drug.get("model_note", "-"), className="simulator-note-text"),
        ],
        className="simulator-detail-section",
    )


def _next_steps() -> html.Div:
    return html.Div(
        [
            html.Div("🚀 다음 단계", className="simulator-detail-section-title"),
            html.Div(
                [
                    html.A("🔗 Pathway Map에서 보기", href="/pathway", className="simulator-cta simulator-cta-outline"),
                    html.A("🧪 Cell-line 검증", href="/simulator", className="simulator-cta simulator-cta-filled"),
                ],
                className="simulator-cta-row",
            ),
        ],
        className="simulator-detail-section simulator-next-section",
    )


def _detail_card(selected_drug: dict | None) -> html.Div:
    if not selected_drug:
        return html.Div(
            "표에서 약물을 선택하면 상세 카드가 표시됩니다.",
            className="simulator-detail-card simulator-detail-empty",
        )
    favorite = bool(selected_drug.get("favorite"))
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H2(selected_drug["name"], className="simulator-detail-title"),
                                    _status_badge(selected_drug.get("clinical_status", "")),
                                ],
                                className="simulator-detail-title-row",
                            ),
                            html.Div(
                                [
                                    html.Span(f"DrugBank ID: {selected_drug.get('drugbank_id', '-')}"),
                                    html.A(
                                        "외부 링크 ↗",
                                        href=selected_drug.get("external_url", "#"),
                                        target="_blank",
                                        rel="noopener noreferrer",
                                        className="simulator-external-link",
                                    ),
                                ],
                                className="simulator-detail-meta",
                            ),
                        ],
                        className="simulator-detail-heading",
                    ),
                    html.Button(
                        "★" if favorite else "☆",
                        id="sim-favorite-toggle",
                        n_clicks=0,
                        className="simulator-favorite is-active" if favorite else "simulator-favorite",
                        title="즐겨찾기",
                    ),
                ],
                className="simulator-detail-header",
            ),
            _structure_sketch(),
            _recommend_section(selected_drug),
            _model_note_section(selected_drug),
            _next_steps(),
        ],
        className="simulator-detail-card",
    )


def render_library_mode(
    rows: list[dict],
    total_count: int,
    selected_drug: dict | None,
    page: int = 1,
    filters: dict | None = None,
):
    filters = _filters(filters)
    return html.Div(
        [
            _controls(filters, total_count),
            _metric_cards(),
            html.Div(
                [
                    _table(rows, selected_drug, page, total_count),
                    _detail_card(selected_drug),
                ],
                className="simulator-library-main",
            ),
        ],
        className="simulator-library",
    )
