"""
Library Mode — Composition Layer.

Faceted Filter + Discovery Cards + External Compound Analyzer 통합 레이아웃.
데이터 레이어 함수는 import하여 호출만 한다 (구현 X).
"""
from __future__ import annotations

from dash import html, dcc, callback, Input, Output, State, ctx, no_update, ALL

from nsclc_ui.components.library_colors import (
    BG_PRIMARY,
    BG_SECONDARY,
    TEXT_MUTED,
    FONT_SIZE_BODY,
)
from nsclc_ui.components.library_facet_filter import render_facet_filter
from nsclc_ui.components.library_discovery_card import render_discovery_cards
from nsclc_ui.components.library_external_analyzer import (
    render_external_analyzer,
    render_external_result,
)
from nsclc_ui.components.library_ranking_table import render_ranking_table
from nsclc_ui.data.library.cards import (
    load_library_cards,
    filter_cards,
    paginate,
    compute_facet_counts,
)
from nsclc_ui.data.library.external import analyze_external


# ── Constants ─────────────────────────────────────────────────────────────────

PAGE_SIZE = 6

DEFAULT_FILTER_STATE: dict = {
    "source": [],
    "phase": [],
    "nsclc_status": [],
    "cross_source_only": False,
    "target_query": "",
    "scaffold_cluster": None,
    "discovery_types": [],
    "sort_by": "rank_score",
    "view": "cards",
}


# ── Render ────────────────────────────────────────────────────────────────────


def render_library_mode(**_kwargs) -> html.Div:
    """
    Library 모드 전체 레이아웃을 조합하여 반환한다.

    기존 simulator.py 콜백과의 호환을 위해 **kwargs를 받되,
    내부적으로는 자체 dcc.Store 기반 상태 관리를 사용한다.
    """
    # 초기 데이터 로드
    all_cards = load_library_cards()

    if not all_cards:
        return html.Div(
            [
                _stores(),
                render_external_analyzer(),
                html.Div(
                    "데이터 로딩 중...",
                    style={
                        "color": TEXT_MUTED,
                        "textAlign": "center",
                        "padding": "80px 0",
                        "fontSize": f"{FONT_SIZE_BODY}px",
                    },
                ),
            ],
            className="library-mode-v2",
        )

    # 초기 필터 적용
    filtered, filtered_count = filter_cards(all_cards, DEFAULT_FILTER_STATE)
    facet_counts = compute_facet_counts(all_cards, DEFAULT_FILTER_STATE)
    page_cards = paginate(filtered, page=1, page_size=PAGE_SIZE)
    total_count = len(all_cards)

    # 초기 메인 영역 (Discovery Cards)
    main_content = render_discovery_cards(
        cards=page_cards,
        page=1,
        total_count=total_count,
        filtered_count=filtered_count,
        sort_by="rank_score",
        view_mode="cards",
    )

    # 초기 Facet Filter
    facet_panel = render_facet_filter(
        facet_counts=facet_counts,
        filter_state=DEFAULT_FILTER_STATE,
        total_count=total_count,
        filtered_count=filtered_count,
    )

    return html.Div(
        [
            _stores(),
            # External Analyzer (항상 표시)
            render_external_analyzer(),
            # Split layout: Facet (280px) + Main (1052px)
            html.Div(
                [
                    html.Div(
                        facet_panel,
                        id="lib-facet-panel-wrapper",
                    ),
                    html.Div(
                        main_content,
                        id="lib-main-area",
                        style={"flex": "1", "minWidth": "0"},
                    ),
                ],
                style={
                    "display": "flex",
                    "gap": "20px",
                    "alignItems": "flex-start",
                },
            ),
        ],
        className="library-mode-v2",
    )


def _stores() -> html.Div:
    """5개 dcc.Store 선언."""
    return html.Div(
        [
            dcc.Store(id="library-filter-store", data=DEFAULT_FILTER_STATE),
            dcc.Store(id="library-page-store", data=1),
            dcc.Store(id="library-view-store", data="cards"),
            dcc.Store(id="library-external-input-store", data=None),
            dcc.Store(id="library-external-result-store", data=None),
        ],
        style={"display": "none"},
    )


# ── Callbacks ─────────────────────────────────────────────────────────────────


@callback(
    Output("library-filter-store", "data"),
    Output("library-page-store", "data", allow_duplicate=True),
    # Facet filter inputs
    Input({"type": "lib-filter-check", "group": ALL, "value": ALL}, "value"),
    Input("lib-filter-target", "value"),
    Input("lib-filter-scaffold", "value"),
    Input("lib-filter-reset", "n_clicks"),
    Input("lib-sort-dropdown", "value"),
    State("library-filter-store", "data"),
    prevent_initial_call=True,
)
def _on_filter_change(check_values, target_query, scaffold_cluster, _reset_clicks, sort_by, current_state):
    """Callback 1 + 4 + 7: 필터/정렬/초기화 변경 → filter_state 업데이트 + page reset."""
    triggered = ctx.triggered_id

    # 필터 초기화
    if triggered == "lib-filter-reset":
        return DEFAULT_FILTER_STATE, 1

    # 현재 상태 기반으로 업데이트
    new_state = dict(current_state) if current_state else dict(DEFAULT_FILTER_STATE)

    # 정렬 변경
    if triggered == "lib-sort-dropdown" and sort_by:
        new_state["sort_by"] = sort_by
        return new_state, 1

    # Target 검색
    new_state["target_query"] = target_query or ""

    # Scaffold cluster
    new_state["scaffold_cluster"] = scaffold_cluster

    # 체크박스 그룹 파싱
    source_vals = []
    phase_vals = []
    nsclc_vals = []
    cross_source = False
    discovery_vals = []

    if check_values and ctx.inputs_list:
        for input_item_list in ctx.inputs_list:
            if not isinstance(input_item_list, list):
                continue
            for item in input_item_list:
                item_id = item.get("id", {})
                if not isinstance(item_id, dict):
                    continue
                group = item_id.get("group", "")
                value = item_id.get("value", "")
                checked = item.get("value", [])

                if group == "source" and checked:
                    source_vals.append(value)
                elif group == "phase" and checked:
                    phase_vals.append(value)
                elif group == "nsclc_status" and checked:
                    nsclc_vals.append(value)
                elif group == "cross_source" and checked:
                    cross_source = True
                elif group == "discovery_types" and checked:
                    discovery_vals.append(value)

    new_state["source"] = source_vals
    new_state["phase"] = phase_vals
    new_state["nsclc_status"] = nsclc_vals
    new_state["cross_source_only"] = cross_source
    new_state["discovery_types"] = discovery_vals

    return new_state, 1


@callback(
    Output("lib-facet-panel-wrapper", "children"),
    Output("lib-main-area", "children"),
    Input("library-filter-store", "data"),
    Input("library-page-store", "data"),
    Input("library-view-store", "data"),
    Input("library-external-result-store", "data"),
)
def _on_state_change(filter_state, page, view_mode, external_result):
    """메인 렌더 콜백: store 변경 → facet + main area 재렌더."""
    filter_state = filter_state or DEFAULT_FILTER_STATE
    page = page or 1
    view_mode = view_mode or "cards"

    all_cards = load_library_cards()
    if not all_cards:
        empty = html.Div("데이터 로딩 중...", style={"color": TEXT_MUTED, "padding": "40px"})
        return empty, empty

    total_count = len(all_cards)
    filtered, filtered_count = filter_cards(all_cards, filter_state)
    facet_counts = compute_facet_counts(all_cards, filter_state)

    # Facet panel
    facet = render_facet_filter(
        facet_counts=facet_counts,
        filter_state=filter_state,
        total_count=total_count,
        filtered_count=filtered_count,
    )

    # Main area
    if external_result:
        main = render_external_result(external_result)
    else:
        page_cards = paginate(filtered, page=page, page_size=PAGE_SIZE)
        sort_by = filter_state.get("sort_by", "rank_score")

        if view_mode == "table":
            main = render_ranking_table(
                cards=page_cards,
                page=page,
                total_count=total_count,
                filtered_count=filtered_count,
                sort_by=sort_by,
                view_mode=view_mode,
            )
        else:
            main = render_discovery_cards(
                cards=page_cards,
                page=page,
                total_count=total_count,
                filtered_count=filtered_count,
                sort_by=sort_by,
                view_mode=view_mode,
            )

    return facet, main


@callback(
    Output("library-page-store", "data"),
    Input({"type": "lib-page", "page": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def _on_page_change(_clicks):
    """Callback 2: 페이지 변경."""
    triggered = ctx.triggered_id
    if isinstance(triggered, dict) and "page" in triggered:
        return triggered["page"]
    return no_update


@callback(
    Output("library-view-store", "data"),
    Input("lib-view-cards", "n_clicks"),
    Input("lib-view-table", "n_clicks"),
    prevent_initial_call=True,
)
def _on_view_toggle(_cards_clicks, _table_clicks):
    """Callback 3: View toggle."""
    triggered = ctx.triggered_id
    if triggered == "lib-view-cards":
        return "cards"
    if triggered == "lib-view-table":
        return "table"
    return no_update


@callback(
    Output("library-external-input-store", "data"),
    Output("library-external-result-store", "data"),
    Input("lib-external-analyze-btn", "n_clicks"),
    State("lib-external-input", "value"),
    prevent_initial_call=True,
)
def _on_external_analyze(_clicks, input_value):
    """Callback 5: External Analyze."""
    if not input_value or not input_value.strip():
        return no_update, no_update

    try:
        result = analyze_external(input_value.strip())
        return input_value.strip(), result
    except Exception:
        return input_value.strip(), None


@callback(
    Output("library-external-result-store", "data", allow_duplicate=True),
    Input("lib-external-close-btn", "n_clicks"),
    prevent_initial_call=True,
)
def _on_external_close(_clicks):
    """Callback 6: Close External Result."""
    return None
