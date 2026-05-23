"""
Simulator — Triple-Mode Validation Engine.
"""

from __future__ import annotations

import copy
import importlib
import math

import dash
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update

from nsclc_ui.components.simulator_tabs import render_simulator_tabs
from nsclc_ui.tabs.library_mode import render_library_mode
from nsclc_ui.data.simulator_demo import (
    LIBRARY_PAGE_SIZE,
    LIBRARY_ROWS,
    LIBRARY_TOTAL_COUNT,
    SELECTED_DRUG,
)


dash.register_page(
    __name__,
    path="/simulator",
    name="AI Simulator",
    title="NSCLC Insight Engine",
    order=6,
)


def _render_cell_line_mode():
    for page in dash.page_registry.values():
        if page.get("path") == "/cell-line-mode":
            layout = page.get("layout")
            return layout() if callable(layout) else layout
    return importlib.import_module("nsclc_ui.tabs.cell_line_mode").layout()


def _render_patient_mode():
    for page in dash.page_registry.values():
        if page.get("path") == "/patient-mode":
            layout = page.get("layout")
            return layout() if callable(layout) else layout
    return importlib.import_module("nsclc_ui.tabs.patient_mode").layout()


def layout():
    filters = _default_filters()
    selected = _selected_drug(SELECTED_DRUG["drugbank_id"], favorite=False)
    rows, total_count, page = _library_page(filters, page=1, sort_desc=True, query="")
    return html.Div(
        [
            dcc.Store(id="simulator-mode-store", data="library"),
            dcc.Store(id="simulator-filters-store", data=filters),
            dcc.Store(id="simulator-page-store", data=1),
            dcc.Store(id="simulator-sort-store", data=True),
            dcc.Store(id="simulator-query-store", data=""),
            dcc.Store(id="simulator-selected-store", data=SELECTED_DRUG["drugbank_id"]),
            dcc.Store(id="simulator-favorite-store", data=False),
            html.Div(id="simulator-mode-tabs", children=render_simulator_tabs("library")),
            html.Div(
                id="simulator-mode-content",
                children=render_library_mode(
                    rows=rows,
                    total_count=total_count,
                    selected_drug=selected,
                    page=page,
                    filters={**filters, "query": ""},
                ),
            ),
            html.Div(
                "면책: 본 화면은 시뮬레이션 예시이며 실제 치료 추천이 아닙니다.",
                className="simulator-disclaimer",
            ),
        ],
        className="simulator-shell",
    )


def _default_filters() -> dict:
    return {
        "drugbank": True,
        "drugcentral": True,
        "nsclc_unused_only": True,
    }


def _catalog() -> list[dict]:
    rows = [copy.deepcopy(row) for row in LIBRARY_ROWS]
    statuses = ["approved_other", "phase_2", "preclinical", "preclinical"]
    source_patterns = [
        ["drugbank", "drugcentral"],
        ["drugbank"],
        ["drugcentral"],
    ]
    while len(rows) < LIBRARY_TOTAL_COUNT:
        base = LIBRARY_ROWS[len(rows) % len(LIBRARY_ROWS)]
        rank = len(rows) + 1
        score = max(0.11, round(0.38 - 0.002 * (rank - len(LIBRARY_ROWS)), 2))
        rows.append(
            {
                **copy.deepcopy(base),
                "rank": rank,
                "name": f"{base['name']} 후보 {rank:03d}",
                "drugbank_id": f"DBSIM{rank:05d}",
                "rank_score": score,
                "confidence": max(1, min(3, int(math.ceil(score * 3)))),
                "clinical_status": statuses[rank % len(statuses)],
                "sources": source_patterns[rank % len(source_patterns)],
                "nsclc_unused": True,
            }
        )
    return rows


_LIBRARY_CATALOG = _catalog()


def _filtered_rows(filters: dict | None, query: str, sort_desc: bool) -> list[dict]:
    filters = {**_default_filters(), **(filters or {})}
    active_sources = {
        source
        for source, enabled in {
            "drugbank": filters.get("drugbank"),
            "drugcentral": filters.get("drugcentral"),
        }.items()
        if enabled
    }
    query = (query or "").strip().lower()

    rows = []
    for row in _LIBRARY_CATALOG:
        if active_sources and not (set(row.get("sources", [])) & active_sources):
            continue
        if not active_sources:
            continue
        if filters.get("nsclc_unused_only") and not row.get("nsclc_unused", False):
            continue
        if query and query not in row["name"].lower() and query not in row["drugbank_id"].lower():
            continue
        rows.append(row)
    return sorted(rows, key=lambda item: item["rank_score"], reverse=bool(sort_desc))


def _library_page(
    filters: dict | None,
    page: int,
    sort_desc: bool,
    query: str,
) -> tuple[list[dict], int, int]:
    rows = _filtered_rows(filters, query, sort_desc)
    total_count = len(rows)
    page_count = max(1, math.ceil(max(total_count, 1) / LIBRARY_PAGE_SIZE))
    page = min(max(int(page or 1), 1), page_count)
    start = (page - 1) * LIBRARY_PAGE_SIZE
    return rows[start:start + LIBRARY_PAGE_SIZE], total_count, page


def _selected_drug(drugbank_id: str | None, favorite: bool) -> dict | None:
    if not drugbank_id:
        return None
    if drugbank_id == SELECTED_DRUG["drugbank_id"]:
        selected = copy.deepcopy(SELECTED_DRUG)
    else:
        row = next((item for item in _LIBRARY_CATALOG if item["drugbank_id"] == drugbank_id), None)
        if not row:
            return copy.deepcopy(SELECTED_DRUG)
        selected = {
            "name": row["name"],
            "drugbank_id": row["drugbank_id"],
            "external_url": f"https://go.drugbank.com/drugs/{row['drugbank_id']}",
            "smiles": "",
            "structure_svg_highlights": [],
            "rank_score": row["rank_score"],
            "scaffold_cluster": (row["rank"] % 12) + 1,
            "why_recommend": "kinase scaffold 기반 재창출 후보",
            "model_note": "더미 데이터 기반 후보이며 백엔드 연결 후 근거가 갱신됩니다.",
            "clinical_status": row["clinical_status"],
        }
    selected["favorite"] = bool(favorite)
    return selected


def _placeholder_mode(mode: str) -> html.Div:
    title = "Patient 모드" if mode == "patient" else "준비 중"
    return html.Div(
        [
            html.Div("준비 중", className="simulator-placeholder-kicker"),
            html.H2(title, className="simulator-placeholder-title"),
            html.P(
                "Patient 모드는 후속 Part에서 구현됩니다.",
                className="simulator-placeholder-copy",
            ),
        ],
        className="simulator-placeholder",
    )


@callback(
    Output("simulator-mode-store", "data"),
    Input({"type": "simulator-mode-tab", "mode": ALL}, "n_clicks"),
    State("simulator-mode-store", "data"),
    prevent_initial_call=True,
)
def _set_mode(_clicks, current_mode):
    triggered = ctx.triggered_id
    if isinstance(triggered, dict) and triggered.get("mode"):
        return triggered["mode"]
    return current_mode or "library"


@callback(
    Output("simulator-filters-store", "data"),
    Output("simulator-page-store", "data"),
    Output("simulator-sort-store", "data"),
    Output("simulator-query-store", "data"),
    Input("sim-filter-drugbank", "n_clicks"),
    Input("sim-filter-drugcentral", "n_clicks"),
    Input("sim-filter-unused", "n_clicks"),
    Input("sim-sort-score", "n_clicks"),
    Input("sim-page-prev", "n_clicks"),
    Input("sim-page-next", "n_clicks"),
    Input({"type": "sim-library-page", "page": ALL}, "n_clicks"),
    Input("sim-library-search", "value"),
    State("simulator-filters-store", "data"),
    State("simulator-page-store", "data"),
    State("simulator-sort-store", "data"),
    State("simulator-query-store", "data"),
    prevent_initial_call=True,
)
def _library_controls(
    _drugbank,
    _drugcentral,
    _unused,
    _sort,
    _prev,
    _next,
    _pages,
    search_value,
    filters,
    page,
    sort_desc,
    query,
):
    triggered = ctx.triggered_id
    filters = {**_default_filters(), **(filters or {})}
    page = int(page or 1)
    sort_desc = bool(sort_desc)
    query = query or ""

    if triggered == "sim-filter-drugbank":
        filters["drugbank"] = not filters.get("drugbank")
        page = 1
    elif triggered == "sim-filter-drugcentral":
        filters["drugcentral"] = not filters.get("drugcentral")
        page = 1
    elif triggered == "sim-filter-unused":
        filters["nsclc_unused_only"] = not filters.get("nsclc_unused_only")
        page = 1
    elif triggered == "sim-sort-score":
        sort_desc = not sort_desc
        page = 1
    elif triggered == "sim-page-prev":
        page = max(1, page - 1)
    elif triggered == "sim-page-next":
        total_count = len(_filtered_rows(filters, query, sort_desc))
        page_count = max(1, math.ceil(max(total_count, 1) / LIBRARY_PAGE_SIZE))
        page = min(page_count, page + 1)
    elif isinstance(triggered, dict) and triggered.get("type") == "sim-library-page":
        page = int(triggered.get("page") or 1)
    elif triggered == "sim-library-search":
        next_query = search_value or ""
        if next_query == query:
            return no_update, no_update, no_update, no_update
        query = next_query
        page = 1
    else:
        return no_update, no_update, no_update, no_update

    return filters, page, sort_desc, query


@callback(
    Output("simulator-selected-store", "data"),
    Input({"type": "sim-library-row", "drugbank_id": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def _select_library_row(_clicks):
    triggered = ctx.triggered_id
    if isinstance(triggered, dict) and triggered.get("drugbank_id"):
        return triggered["drugbank_id"]
    return no_update


@callback(
    Output("simulator-favorite-store", "data"),
    Input("sim-favorite-toggle", "n_clicks"),
    State("simulator-favorite-store", "data"),
    prevent_initial_call=True,
)
def _toggle_favorite(_clicks, favorite):
    if not ctx.triggered_id:
        return no_update
    return not bool(favorite)


@callback(
    Output("simulator-mode-tabs", "children"),
    Output("simulator-mode-content", "children"),
    Input("simulator-mode-store", "data"),
    Input("simulator-filters-store", "data"),
    Input("simulator-page-store", "data"),
    Input("simulator-sort-store", "data"),
    Input("simulator-query-store", "data"),
    Input("simulator-selected-store", "data"),
    Input("simulator-favorite-store", "data"),
)
def _render_simulator(
    mode,
    filters,
    page,
    sort_desc,
    query,
    selected_id,
    favorite,
):
    mode = mode or "library"
    tabs = render_simulator_tabs(mode)
    if mode == "cell_line":
        return tabs, _render_cell_line_mode()
    if mode == "patient":
        return tabs, _render_patient_mode()

    rows, total_count, bounded_page = _library_page(filters, page, sort_desc, query)
    selected = _selected_drug(selected_id, favorite)
    return tabs, render_library_mode(
        rows=rows,
        total_count=total_count,
        selected_drug=selected,
        page=bounded_page,
        filters={**_default_filters(), **(filters or {}), "query": query or "", "sort_desc": sort_desc},
    )
