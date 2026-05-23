"""
Library Mode — Ranking Table 컴포넌트.

기존 simulator_library.py 테이블 디자인 기반 + Discovery flag / Cross-source 컬럼 추가.
View toggle "Ranking Table" 클릭 시 Cards 영역 통째로 교체.
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
)
from nsclc_ui.components.library_discovery_card import (
    _view_toggle,
    _sort_dropdown,
    _render_pagination,
)


# ── Helper: 테이블 셀 렌더 ────────────────────────────────────────────────────


def _phase_badge(category: str) -> html.Span:
    """Phase 배지 (테이블 셀용)."""
    bg, fg = PHASE_COLORS.get(category, PHASE_COLORS["X"])
    label = PHASE_LABELS.get(category, "X 전임상")
    return html.Span(
        label,
        style={
            "backgroundColor": bg,
            "color": fg,
            "padding": "2px 6px",
            "borderRadius": "4px",
            "fontSize": f"{FONT_SIZE_CAPTION}px",
            "fontWeight": "500",
        },
    )


def _discovery_badge(discovery_type: str | None) -> html.Span:
    """Discovery type 배지 (테이블 셀용)."""
    if not discovery_type or discovery_type not in DISCOVERY_COLORS:
        return html.Span("—", style={"color": TEXT_MUTED})
    bg, fg = DISCOVERY_COLORS[discovery_type]
    label = DISCOVERY_LABELS.get(discovery_type, discovery_type)
    return html.Span(
        label,
        style={
            "backgroundColor": bg,
            "color": fg,
            "padding": "2px 6px",
            "borderRadius": "4px",
            "fontSize": "10px",
            "fontWeight": "500",
        },
    )


def _xs_cell(verified: bool) -> html.Span:
    """Cross-source 셀."""
    if verified:
        return html.Span("X-S ✓", style={"color": XS_FG, "fontWeight": "500"})
    return html.Span("—", style={"color": TEXT_MUTED})


def _confidence_dots(dots: int) -> html.Span:
    """신뢰도 dots (테이블 셀용)."""
    max_dots = 3
    filled = min(max(dots, 0), max_dots)
    return html.Span(
        "●" * filled + "○" * (max_dots - filled),
        style={"color": TEXT_TERTIARY, "fontSize": "10px", "letterSpacing": "2px"},
    )


# ── Main: render_ranking_table ────────────────────────────────────────────────


def render_ranking_table(
    cards: list[dict],
    page: int,
    total_count: int,
    filtered_count: int,
    sort_by: str = "rank_score",
    view_mode: str = "table",
) -> html.Div:
    """
    Ranking Table 뷰.

    Args:
        cards: 현재 페이지의 카드 목록 (filter + paginate 결과)
        page: 현재 페이지 번호
        total_count: 전체 화합물 수
        filtered_count: 필터 적용 후 결과 수
        sort_by: 정렬 기준
        view_mode: 현재 뷰 모드
    """
    # 상단 컨트롤 (View toggle + Sort)
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

    # 테이블 헤더
    th_style = {
        "padding": "10px 12px",
        "fontSize": f"{FONT_SIZE_CAPTION}px",
        "fontWeight": "500",
        "color": TEXT_MUTED,
        "textAlign": "left",
        "borderBottom": f"1px solid {BORDER_DEFAULT}",
    }

    header = html.Thead(
        html.Tr([
            html.Th("순위", style=th_style),
            html.Th("약물", style=th_style),
            html.Th("Target", style=th_style),
            html.Th("rank_score", style=th_style),
            html.Th("신뢰도", style=th_style),
            html.Th("Phase", style=th_style),
            html.Th("Discovery", style=th_style),
            html.Th("X-S", style=th_style),
        ])
    )

    # 테이블 행
    td_style = {
        "padding": "10px 12px",
        "fontSize": f"{FONT_SIZE_BODY}px",
        "color": TEXT_PRIMARY,
        "borderBottom": f"1px solid {BORDER_DEFAULT}20",
    }

    page_size = 6
    start_rank = (page - 1) * page_size + 1

    rows = []
    for idx, card in enumerate(cards):
        phase = card.get("phase_chip", {})
        phase_cat = phase.get("category", "X") if isinstance(phase, dict) else phase
        targets = card.get("targets", [])
        target_text = " / ".join(targets[:3]) if targets else "—"

        rows.append(
            html.Tr(
                [
                    html.Td(str(start_rank + idx), style={**td_style, "color": TEXT_MUTED, "width": "50px"}),
                    html.Td(
                        html.Span(card.get("name", "—"), style={"fontWeight": "500"}),
                        style=td_style,
                    ),
                    html.Td(target_text, style={**td_style, "color": TEXT_TERTIARY, "maxWidth": "180px"}),
                    html.Td(
                        f"{card.get('rank_score', 0):.2f}",
                        style={**td_style, "fontWeight": "500"},
                    ),
                    html.Td(_confidence_dots(card.get("confidence_dots", 0)), style=td_style),
                    html.Td(_phase_badge(phase_cat), style=td_style),
                    html.Td(_discovery_badge(card.get("discovery_type")), style=td_style),
                    html.Td(_xs_cell(card.get("x_s_verified", False)), style=td_style),
                ],
                style={"cursor": "pointer"},
            )
        )

    body = html.Tbody(rows)

    table = html.Table(
        [header, body],
        style={
            "width": "100%",
            "borderCollapse": "collapse",
            "backgroundColor": BG_CARD,
            "borderRadius": "12px",
        },
    )

    # 페이지네이션
    pagination = _render_pagination(page, total_count, filtered_count, page_size)

    return html.Div(
        [
            controls,
            html.Div(
                table,
                style={
                    "backgroundColor": BG_CARD,
                    "borderRadius": "12px",
                    "overflow": "hidden",
                },
            ),
            pagination,
        ],
        id="lib-table-area",
    )
