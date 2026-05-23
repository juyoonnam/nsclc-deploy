"""
Library Mode — Discovery Card 컴포넌트.

render_single_card(): 개별 카드 (340×280px)
render_discovery_cards(): 3-col 그리드 + View toggle + 정렬 + 페이지네이션
"""
from __future__ import annotations

import math

from dash import html, dcc

from nsclc_ui.components.library_colors import (
    BG_CARD,
    BG_PRIMARY,
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
    ACCENT_CYAN,
    FONT_SIZE_CAPTION,
    FONT_SIZE_BODY,
    FONT_SIZE_HEADER,
    FONT_SIZE_DRUG_NAME,
    FONT_SIZE_CARD_SCORE,
)


# ── Helper: Phase chip badge ──────────────────────────────────────────────────


def _phase_chip(category: str) -> html.Span:
    """Phase chip 배지 렌더."""
    bg, fg = PHASE_COLORS.get(category, PHASE_COLORS["X"])
    label = PHASE_LABELS.get(category, "X 전임상")
    return html.Span(
        label,
        style={
            "backgroundColor": bg,
            "color": fg,
            "padding": "2px 8px",
            "borderRadius": "4px",
            "fontSize": f"{FONT_SIZE_CAPTION}px",
            "fontWeight": "500",
            "marginLeft": "8px",
        },
    )


# ── Helper: Discovery type chip ───────────────────────────────────────────────


def _discovery_chip(discovery_type: str | None) -> html.Span:
    """Discovery type chip 또는 None → 회색 '—'."""
    if not discovery_type or discovery_type not in DISCOVERY_COLORS:
        return html.Span(
            "—",
            style={
                "color": TEXT_MUTED,
                "fontSize": f"{FONT_SIZE_BODY}px",
            },
        )
    bg, fg = DISCOVERY_COLORS[discovery_type]
    label = DISCOVERY_LABELS.get(discovery_type, discovery_type)
    return html.Span(
        label,
        style={
            "backgroundColor": bg,
            "color": fg,
            "padding": "4px 12px",
            "borderRadius": "6px",
            "fontSize": f"{FONT_SIZE_BODY}px",
            "fontWeight": "500",
            "height": "22px",
            "display": "inline-flex",
            "alignItems": "center",
        },
    )


# ── Helper: Confidence dots ───────────────────────────────────────────────────


def _confidence_dots(dots: int) -> html.Span:
    """신뢰도 dots (1-3). ● 채움, ○ 빈 것."""
    max_dots = 3
    filled = min(max(dots, 0), max_dots)
    labels = {1: "낮음", 2: "중간", 3: "높음"}
    dot_str = "●" * filled + "○" * (max_dots - filled)
    return html.Span(
        f"신뢰도 {dot_str} {labels.get(filled, '')}",
        style={
            "fontSize": "10px",
            "color": TEXT_TERTIARY,
        },
    )


# ── Helper: Cross-source badge ────────────────────────────────────────────────


def _xs_badge(verified: bool) -> html.Span:
    """X-S ✓ (cyan) 또는 — (회색)."""
    if verified:
        return html.Span(
            "X-S ✓",
            style={"color": XS_FG, "fontSize": f"{FONT_SIZE_BODY}px", "fontWeight": "500"},
        )
    return html.Span(
        "—",
        style={"color": TEXT_MUTED, "fontSize": f"{FONT_SIZE_BODY}px"},
    )


# ── Main: render_single_card ──────────────────────────────────────────────────


def render_single_card(card: dict) -> html.Div:
    """
    개별 Discovery Card (340×280px).

    Args:
        card: LibraryCardDict
    """
    discovery_type = card.get("discovery_type")
    compound_id = card.get("compound_id", "")
    name = card.get("name", "Unknown")
    phase = card.get("phase_chip", {})
    phase_cat = phase.get("category", "X") if isinstance(phase, dict) else phase
    rank_score = card.get("rank_score", 0.0)
    confidence = card.get("confidence_dots", 1)
    targets = card.get("targets", [])
    smiles = card.get("smiles", "")
    x_s_verified = card.get("x_s_verified", False)
    reason = card.get("reason", "")
    actions = card.get("actions", {})

    # 카드 테두리 색상 (discovery type 기반, 50% opacity)
    border_style = f"1px solid {BORDER_DEFAULT}"
    if discovery_type and discovery_type in DISCOVERY_COLORS:
        _, fg = DISCOVERY_COLORS[discovery_type]
        border_style = f"1px solid {fg}80"  # 50% opacity via hex alpha

    # rank_score 색상 (discovery type 기반)
    score_color = TEXT_PRIMARY
    if discovery_type and discovery_type in DISCOVERY_COLORS:
        _, score_color = DISCOVERY_COLORS[discovery_type]

    # Target 줄
    target_text = " / ".join(targets[:3]) if targets else "—"
    if compound_id:
        target_text += f" — {compound_id}"

    # 화학구조 placeholder
    structure_placeholder = html.Div(
        "[화학 구조]" if smiles else "구조 없음",
        style={
            "width": "180px",
            "height": "80px",
            "backgroundColor": "#1F2937",
            "borderRadius": "6px",
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "center",
            "color": TEXT_MUTED,
            "fontSize": f"{FONT_SIZE_CAPTION}px",
        },
    )

    # 액션 버튼
    detail_href = actions.get("detail_href", "#") if isinstance(actions, dict) else "#"
    pathway_href = actions.get("pathway_href", "#") if isinstance(actions, dict) else "#"
    cell_line_href = actions.get("cell_line_href", "#") if isinstance(actions, dict) else "#"

    action_btn_base = {
        "padding": "4px 12px",
        "borderRadius": "6px",
        "fontSize": f"{FONT_SIZE_CAPTION}px",
        "cursor": "pointer",
        "textDecoration": "none",
    }
    action_buttons = html.Div(
        [
            html.A("상세 →", href=detail_href, style={
                **action_btn_base,
                "border": f"1px solid {BORDER_DEFAULT}",
                "color": TEXT_SECONDARY,
                "backgroundColor": "transparent",
            }),
            html.A("패스웨이", href=pathway_href, style={
                **action_btn_base,
                "border": f"1px solid {BORDER_DEFAULT}",
                "color": TEXT_SECONDARY,
                "backgroundColor": "transparent",
            }),
            html.A("Cell-line", href=cell_line_href, style={
                **action_btn_base,
                "border": f"1px solid {ACCENT_CYAN}",
                "color": ACCENT_CYAN,
                "backgroundColor": "transparent",
                "fontWeight": "500",
            }),
        ],
        style={"display": "flex", "gap": "8px", "marginTop": "auto"},
    )

    return html.Div(
        [
            # 상단: Discovery chip + X-S badge
            html.Div(
                [_discovery_chip(discovery_type), _xs_badge(x_s_verified)],
                style={"display": "flex", "justifyContent": "space-between", "alignItems": "center"},
            ),
            # 약물명 + Phase chip
            html.Div(
                [
                    html.Span(name, style={
                        "fontSize": f"{FONT_SIZE_DRUG_NAME}px",
                        "fontWeight": "500",
                        "color": TEXT_PRIMARY,
                    }),
                    _phase_chip(phase_cat),
                ],
                style={"marginTop": "8px", "display": "flex", "alignItems": "center"},
            ),
            # Target 줄
            html.Div(target_text, style={
                "fontSize": f"{FONT_SIZE_CAPTION}px",
                "color": TEXT_TERTIARY,
                "marginTop": "4px",
            }),
            # 중간: 구조 + score
            html.Div(
                [
                    structure_placeholder,
                    html.Div(
                        [
                            html.Div("rank_score", style={
                                "fontSize": f"{FONT_SIZE_CAPTION}px",
                                "color": TEXT_MUTED,
                            }),
                            html.Div(f"{rank_score:.2f}", style={
                                "fontSize": f"{FONT_SIZE_CARD_SCORE}px",
                                "fontWeight": "500",
                                "color": score_color,
                            }),
                            _confidence_dots(confidence),
                        ],
                        style={"textAlign": "right"},
                    ),
                ],
                style={
                    "display": "flex",
                    "justifyContent": "space-between",
                    "alignItems": "center",
                    "marginTop": "8px",
                },
            ),
            # Reason
            html.Div(
                f"💡 {reason}" if reason else "",
                style={
                    "fontSize": f"{FONT_SIZE_CAPTION}px",
                    "color": TEXT_TERTIARY,
                    "marginTop": "8px",
                    "whiteSpace": "nowrap",
                    "overflow": "hidden",
                    "textOverflow": "ellipsis",
                },
            ),
            # 액션 버튼
            action_buttons,
        ],
        style={
            "width": "340px",
            "height": "280px",
            "backgroundColor": BG_CARD,
            "border": border_style,
            "borderRadius": "12px",
            "padding": "16px",
            "display": "flex",
            "flexDirection": "column",
            "gap": "0",
        },
    )


# ── Helper: Pagination ────────────────────────────────────────────────────────


def _pagination_items(page: int, page_count: int) -> list[int | str]:
    """페이지네이션 번호 목록 생성. 1 2 3 ... N 형태."""
    if page_count <= 7:
        return list(range(1, page_count + 1))

    items: list[int | str] = []
    if page <= 4:
        items = [1, 2, 3, 4, "...", page_count]
    elif page >= page_count - 3:
        items = [1, "...", page_count - 3, page_count - 2, page_count - 1, page_count]
    else:
        items = [1, "...", page - 1, page, page + 1, "...", page_count]
    return items


def _render_pagination(page: int, total_count: int, filtered_count: int, page_size: int = 6) -> html.Div:
    """페이지네이션 바 렌더."""
    page_count = max(1, math.ceil(filtered_count / page_size))
    items = _pagination_items(page, page_count)

    start_idx = (page - 1) * page_size + 1
    end_idx = min(page * page_size, filtered_count)

    pagination_buttons = []

    # 이전 버튼
    pagination_buttons.append(
        html.Button(
            "‹",
            id={"type": "lib-page", "page": max(1, page - 1)},
            n_clicks=0,
            disabled=(page <= 1),
            style={
                "background": "none",
                "border": "none",
                "color": TEXT_SECONDARY if page > 1 else TEXT_MUTED,
                "fontSize": "16px",
                "cursor": "pointer" if page > 1 else "default",
                "padding": "4px 8px",
            },
        )
    )

    # 페이지 번호
    for item in items:
        if item == "...":
            pagination_buttons.append(
                html.Span("...", style={"color": TEXT_MUTED, "padding": "4px 8px"})
            )
        else:
            is_active = item == page
            pagination_buttons.append(
                html.Button(
                    str(item),
                    id={"type": "lib-page", "page": item},
                    n_clicks=0,
                    style={
                        "background": ACCENT_CYAN if is_active else "none",
                        "border": "none",
                        "color": BG_PRIMARY if is_active else TEXT_SECONDARY,
                        "fontSize": f"{FONT_SIZE_BODY}px",
                        "fontWeight": "500" if is_active else "400",
                        "cursor": "pointer",
                        "padding": "4px 10px",
                        "borderRadius": "4px",
                    },
                )
            )

    # 다음 버튼
    pagination_buttons.append(
        html.Button(
            "›",
            id={"type": "lib-page", "page": min(page_count, page + 1)},
            n_clicks=0,
            disabled=(page >= page_count),
            style={
                "background": "none",
                "border": "none",
                "color": TEXT_SECONDARY if page < page_count else TEXT_MUTED,
                "fontSize": "16px",
                "cursor": "pointer" if page < page_count else "default",
                "padding": "4px 8px",
            },
        )
    )

    # 결과 요약
    summary_text = f"{start_idx}-{end_idx} / {filtered_count:,}"
    if filtered_count < 33057:
        summary_text += " (필터 적용)"

    return html.Div(
        [
            html.Div(pagination_buttons, style={"display": "flex", "alignItems": "center", "gap": "2px"}),
            html.Span(summary_text, style={
                "color": TEXT_TERTIARY,
                "fontSize": f"{FONT_SIZE_CAPTION}px",
            }),
        ],
        style={
            "display": "flex",
            "justifyContent": "space-between",
            "alignItems": "center",
            "marginTop": "20px",
            "padding": "0 4px",
        },
    )


# ── Helper: View toggle ──────────────────────────────────────────────────────


def _view_toggle(active_view: str) -> html.Div:
    """View toggle 버튼 2개 (Discovery Cards / Ranking Table)."""
    btn_base = {
        "padding": "8px 16px",
        "borderRadius": "8px",
        "fontSize": f"{FONT_SIZE_BODY}px",
        "fontWeight": "500",
        "cursor": "pointer",
        "border": "none",
    }
    return html.Div(
        [
            html.Button(
                "✨ Discovery Cards",
                id="lib-view-cards",
                n_clicks=0,
                style={
                    **btn_base,
                    "backgroundColor": ACCENT_CYAN if active_view == "cards" else "transparent",
                    "color": BG_PRIMARY if active_view == "cards" else TEXT_SECONDARY,
                    "border": f"1px solid {ACCENT_CYAN}" if active_view == "cards" else f"1px solid {BORDER_DEFAULT}",
                },
            ),
            html.Button(
                "📊 Ranking Table",
                id="lib-view-table",
                n_clicks=0,
                style={
                    **btn_base,
                    "backgroundColor": ACCENT_CYAN if active_view == "table" else "transparent",
                    "color": BG_PRIMARY if active_view == "table" else TEXT_SECONDARY,
                    "border": f"1px solid {ACCENT_CYAN}" if active_view == "table" else f"1px solid {BORDER_DEFAULT}",
                },
            ),
        ],
        style={"display": "flex", "gap": "8px"},
    )


# ── Helper: Sort dropdown ─────────────────────────────────────────────────────


def _sort_dropdown(sort_by: str) -> dcc.Dropdown:
    """정렬 드롭다운."""
    return dcc.Dropdown(
        id="lib-sort-dropdown",
        options=[
            {"label": "정렬: rank_score ↓", "value": "rank_score"},
            {"label": "정렬: Confidence ↓", "value": "confidence"},
            {"label": "정렬: Novelty ↓", "value": "novelty"},
        ],
        value=sort_by,
        clearable=False,
        style={
            "width": "180px",
            "fontSize": f"{FONT_SIZE_BODY}px",
        },
        className="library-sort-dropdown",
    )


# ── Main: render_discovery_cards ──────────────────────────────────────────────


def render_discovery_cards(
    cards: list[dict],
    page: int,
    total_count: int,
    filtered_count: int,
    sort_by: str = "rank_score",
    view_mode: str = "cards",
) -> html.Div:
    """
    Discovery Cards 그리드 뷰.

    Args:
        cards: paginate() 반환값 (현재 페이지 카드, max 6)
        page: 현재 페이지 번호
        total_count: 전체 화합물 수
        filtered_count: 필터 적용 후 결과 수
        sort_by: 정렬 기준
        view_mode: 현재 뷰 모드
    """
    # 상단 컨트롤
    controls = html.Div(
        [
            _view_toggle(view_mode),
            _sort_dropdown(sort_by),
        ],
        style={
            "display": "flex",
            "justifyContent": "space-between",
            "alignItems": "center",
            "marginBottom": "16px",
        },
    )

    # 3-col 그리드
    card_grid = html.Div(
        [render_single_card(c) for c in cards],
        style={
            "display": "grid",
            "gridTemplateColumns": "repeat(3, 340px)",
            "gap": "16px",
        },
    )

    # 페이지네이션
    pagination = _render_pagination(page, total_count, filtered_count)

    return html.Div(
        [controls, card_grid, pagination],
        id="lib-cards-area",
    )
