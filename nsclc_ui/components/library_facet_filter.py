"""
Library Mode — Facet Filter 패널 (좌측 280px).

필터 그룹: SOURCE, PHASE, NSCLC STATUS, CROSS-SOURCE, TARGET, SCAFFOLD CLUSTER, DISCOVERY TYPE.
같은 그룹 내 OR, 그룹 간 AND.
"""
from __future__ import annotations

from dash import html, dcc

from nsclc_ui.components.library_colors import (
    BG_SECONDARY,
    BG_CARD,
    BG_INPUT,
    BORDER_DEFAULT,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
    TEXT_MUTED,
    PHASE_COLORS,
    PHASE_LABELS,
    DISCOVERY_COLORS,
    DISCOVERY_LABELS,
    XS_FG,
    FACET_COUNT_COLOR,
    FACET_DIVIDER,
    FACET_LABEL_DISCOVERY,
    FONT_SIZE_CAPTION,
    FONT_SIZE_BODY,
    FONT_SIZE_HEADER,
    FONT_SIZE_FACET_COUNT,
)


# ── Helper: 섹션 라벨 ─────────────────────────────────────────────────────────


def _section_label(text: str, color: str = TEXT_MUTED) -> html.Div:
    """필터 섹션 라벨 (11px, 500, 회색)."""
    return html.Div(
        text,
        style={
            "fontSize": f"{FONT_SIZE_CAPTION}px",
            "fontWeight": "500",
            "color": color,
            "marginBottom": "8px",
            "marginTop": "16px",
            "letterSpacing": "0.5px",
        },
    )


# ── Helper: 체크박스 행 ────────────────────────────────────────────────────────


def _checkbox_row(
    label: str,
    value: str,
    count: int,
    group: str,
    checked: bool = False,
    chip_color: tuple[str, str] | None = None,
    label_color: str | None = None,
) -> html.Div:
    """단일 체크박스 + 라벨 + 카운트."""
    label_el = html.Span(label, style={"color": label_color or TEXT_PRIMARY})

    # Phase chip 색상 dot
    chip_el = None
    if chip_color:
        chip_el = html.Span(
            style={
                "display": "inline-block",
                "width": "8px",
                "height": "8px",
                "borderRadius": "50%",
                "backgroundColor": chip_color[1],
                "marginRight": "6px",
            }
        )

    count_style = {"color": TEXT_TERTIARY, "fontSize": f"{FONT_SIZE_CAPTION}px"}
    if label_color:
        count_style["color"] = label_color
        count_style["fontWeight"] = "500"

    return html.Div(
        [
            html.Label(
                [
                    dcc.Checklist(
                        id={"type": "lib-filter-check", "group": group, "value": value},
                        options=[{"label": "", "value": value}],
                        value=[value] if checked else [],
                        style={"display": "inline-block", "marginRight": "4px"},
                        inputStyle={"marginRight": "6px"},
                    ),
                    chip_el,
                    label_el,
                ] if chip_el else [
                    dcc.Checklist(
                        id={"type": "lib-filter-check", "group": group, "value": value},
                        options=[{"label": "", "value": value}],
                        value=[value] if checked else [],
                        style={"display": "inline-block", "marginRight": "4px"},
                        inputStyle={"marginRight": "6px"},
                    ),
                    label_el,
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "cursor": "pointer",
                    "flex": "1",
                },
            ),
            html.Span(f"{count:,}", style=count_style),
        ],
        style={
            "display": "flex",
            "justifyContent": "space-between",
            "alignItems": "center",
            "padding": "4px 0",
            "fontSize": f"{FONT_SIZE_BODY}px",
        },
    )


# ── Main render ────────────────────────────────────────────────────────────────


def render_facet_filter(
    facet_counts: dict,
    filter_state: dict,
    total_count: int,
    filtered_count: int,
) -> html.Div:
    """
    좌측 280px 패싯 필터 패널을 렌더링한다.

    Args:
        facet_counts: compute_facet_counts() 반환값
            {
                "source": {"drugbank": int, "drugcentral": int, "chembl": int},
                "phase": {"A": int, "B": int, "C": int, "X": int},
                "nsclc_status": {"D": int, "E": int},
                "cross_source": int,
                "discovery_types": {
                    "surprising": int, "scaffold_novel": int,
                    "target_rare": int, "repurpose_ready": int,
                },
                "scaffold_clusters": [{"id": int, "count": int}, ...],
            }
        filter_state: 현재 Filter_State dict
        total_count: 전체 화합물 수 (33,057)
        filtered_count: 필터 적용 후 결과 수
    """
    source_counts = facet_counts.get("source", {})
    phase_counts = facet_counts.get("phase", {})
    nsclc_counts = facet_counts.get("nsclc_status", {})
    xs_count = facet_counts.get("cross_source", 0)
    discovery_counts = facet_counts.get("discovery_types", {})
    scaffold_clusters = facet_counts.get("scaffold_clusters", [])

    active_sources = filter_state.get("source", [])
    active_phases = filter_state.get("phase", [])
    active_nsclc = filter_state.get("nsclc_status", [])
    xs_only = filter_state.get("cross_source_only", False)
    target_query = filter_state.get("target_query", "")
    active_scaffold = filter_state.get("scaffold_cluster", None)
    active_discovery = filter_state.get("discovery_types", [])

    # ── 결과 카운트 카드 ──
    count_card = html.Div(
        [
            html.Div(
                [
                    html.Span("필터", style={
                        "fontSize": f"{FONT_SIZE_HEADER}px",
                        "fontWeight": "500",
                        "color": TEXT_PRIMARY,
                    }),
                    html.Button(
                        "초기화",
                        id="lib-filter-reset",
                        n_clicks=0,
                        style={
                            "background": "none",
                            "border": "none",
                            "color": TEXT_TERTIARY,
                            "fontSize": f"{FONT_SIZE_CAPTION}px",
                            "cursor": "pointer",
                            "padding": "0",
                        },
                    ),
                ],
                style={
                    "display": "flex",
                    "justifyContent": "space-between",
                    "alignItems": "center",
                    "marginBottom": "12px",
                },
            ),
            html.Div(
                [
                    html.Div("결과", style={
                        "fontSize": f"{FONT_SIZE_CAPTION}px",
                        "color": TEXT_MUTED,
                        "marginBottom": "4px",
                    }),
                    html.Div(
                        [
                            html.Span(f"{filtered_count:,}", style={
                                "fontSize": f"{FONT_SIZE_FACET_COUNT}px",
                                "fontWeight": "500",
                                "color": FACET_COUNT_COLOR,
                            }),
                            html.Span(f" / {total_count:,} 전체", style={
                                "fontSize": f"{FONT_SIZE_BODY}px",
                                "color": TEXT_TERTIARY,
                                "marginLeft": "8px",
                            }),
                        ],
                    ),
                ],
                style={
                    "backgroundColor": BG_CARD,
                    "borderRadius": "8px",
                    "padding": "12px",
                },
            ),
        ],
    )

    # ── SOURCE ──
    source_section = html.Div([
        _section_label("SOURCE"),
        _checkbox_row("DrugBank", "drugbank", source_counts.get("drugbank", 0),
                      "source", "drugbank" in active_sources),
        _checkbox_row("DrugCentral", "drugcentral", source_counts.get("drugcentral", 0),
                      "source", "drugcentral" in active_sources),
        _checkbox_row("ChEMBL", "chembl", source_counts.get("chembl", 0),
                      "source", "chembl" in active_sources),
    ])

    # ── PHASE / 카테고리 ──
    phase_section = html.Div([
        _section_label("PHASE / 카테고리"),
        *[
            _checkbox_row(
                PHASE_LABELS[p], p, phase_counts.get(p, 0),
                "phase", p in active_phases,
                chip_color=PHASE_COLORS[p],
            )
            for p in ("A", "B", "C", "X")
        ],
    ])

    # ── NSCLC STATUS ──
    nsclc_section = html.Div([
        _section_label("NSCLC STATUS"),
        _checkbox_row("NSCLC 미사용 (D)", "D", nsclc_counts.get("D", 0),
                      "nsclc_status", "D" in active_nsclc),
        _checkbox_row("ATC 없음 (E)", "E", nsclc_counts.get("E", 0),
                      "nsclc_status", "E" in active_nsclc),
    ])

    # ── CROSS-SOURCE ──
    xs_section = html.Div([
        _section_label("CROSS-SOURCE"),
        _checkbox_row(
            "X-S 검증만 (PRISM ∩ GDSC2)", "cross_source", xs_count,
            "cross_source", xs_only,
            label_color=XS_FG,
        ),
    ])

    # ── TARGET ──
    target_section = html.Div([
        _section_label("TARGET"),
        dcc.Input(
            id="lib-filter-target",
            type="text",
            placeholder="검색 (EGFR, ALK, MET...)",
            value=target_query,
            debounce=True,
            style={
                "width": "100%",
                "backgroundColor": BG_INPUT,
                "border": f"1px solid {BORDER_DEFAULT}",
                "borderRadius": "6px",
                "padding": "8px 12px",
                "color": TEXT_PRIMARY,
                "fontSize": f"{FONT_SIZE_BODY}px",
            },
        ),
    ])

    # ── SCAFFOLD CLUSTER ──
    scaffold_options = [
        {"label": f"#{c['id']} ({c['count']} 화합물)", "value": c["id"]}
        for c in scaffold_clusters
    ]
    scaffold_section = html.Div([
        _section_label("SCAFFOLD CLUSTER"),
        dcc.Dropdown(
            id="lib-filter-scaffold",
            options=scaffold_options,
            value=active_scaffold,
            placeholder="클러스터 선택...",
            clearable=True,
            style={
                "backgroundColor": BG_INPUT,
                "fontSize": f"{FONT_SIZE_BODY}px",
            },
            className="library-scaffold-dropdown",
        ),
    ])

    # ── Divider ──
    divider = html.Hr(style={
        "border": "none",
        "borderTop": f"1px solid {FACET_DIVIDER}",
        "margin": "16px 0",
    })

    # ── DISCOVERY TYPE ──
    discovery_section = html.Div([
        html.Div(
            "✨ DISCOVERY TYPE",
            style={
                "fontSize": f"{FONT_SIZE_CAPTION}px",
                "fontWeight": "500",
                "color": FACET_LABEL_DISCOVERY,
                "marginBottom": "8px",
                "marginTop": "4px",
            },
        ),
        *[
            _checkbox_row(
                DISCOVERY_LABELS[dt], dt, discovery_counts.get(dt, 0),
                "discovery_types", dt in active_discovery,
                chip_color=DISCOVERY_COLORS[dt],
            )
            for dt in ("surprising", "scaffold_novel", "target_rare", "repurpose_ready")
        ],
    ])

    # ── 조합 ──
    return html.Div(
        [
            count_card,
            source_section,
            phase_section,
            nsclc_section,
            xs_section,
            target_section,
            scaffold_section,
            divider,
            discovery_section,
        ],
        id="lib-facet-filter",
        style={
            "width": "280px",
            "minWidth": "280px",
            "backgroundColor": BG_SECONDARY,
            "borderRadius": "12px",
            "padding": "20px",
            "overflowY": "auto",
        },
    )
