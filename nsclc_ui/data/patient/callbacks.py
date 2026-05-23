"""
nsclc_ui.data.patient.callbacks

가상투약 탭 callbacks.

patient.py에서 한 줄 import:
    from nsclc_ui.data.patient.callbacks import *  # noqa: F401

Callbacks:
1. _update_real_mode_response   : 실제 환자 모드 — patient_selector → 모든 출력
2. _update_compose_mode_response: 조립 모드 — mutation chips + cancer → 모든 출력
3. _toggle_mutation_chip        : chip 클릭 → mutation set 업데이트
4. _render_mutation_chips       : mutation set 변경 → chip UI re-render

Component IDs (patient.py와 sync):
- 입력: pt-mode-store, pt-patient-selector, pt-cancer-input, pt-drug-input,
        pt-mutations-store, pt-mutation-chips, pt-chip-{type,gene}
- 출력: pt-metric-score, pt-metric-score-hint, pt-metric-similar, pt-metric-cells,
        pt-sankey, pt-treatment-table, pt-concordance
"""

import dash
from dash import callback, Input, Output, State, html, dcc, ALL, MATCH, ctx, no_update

from .loader import (
    get_patient_options,
    get_patient_response,
    get_mutation_chip_genes,
    ACTIONABLE_GENES,
)
from .compose_inference import compose_inference
from .sankey import get_sankey_figure


# ── Callback 1: 페이지 로드 시 환자 dropdown 채우기 ─────────────────────────────

@callback(
    Output("pt-patient-selector", "options"),
    Output("pt-patient-selector", "value", allow_duplicate=True),
    Input("pt-patient-selector", "id"),
    prevent_initial_call="initial_duplicate",
)
def _populate_patient_options(_):
    """페이지 로드 시 942 환자 옵션 채우기.
    시연 default = TCGA-05-4402-01 (EGFR+TP53)."""
    options = get_patient_options()
    # EGFR+TP53 환자 우선 선택
    default = next(
        (o["value"] for o in options if "EGFR" in o["label"] and "TP53" in o["label"]),
        options[0]["value"] if options else None,
    )
    return options, default


# ── Callback 2: 통합 출력 업데이트 (mode 분기) ─────────────────────────────────

@callback(
    Output("pt-metric-score", "children"),
    Output("pt-metric-score-hint", "children"),
    Output("pt-metric-similar", "children"),
    Output("pt-metric-cells", "children"),
    Output("pt-sankey", "children"),
    Output("pt-treatment-table", "children"),
    Output("pt-concordance", "children"),
    Output("pt-concordance", "className"),
    Input("pt-mode-store", "data"),
    Input("pt-patient-selector", "value"),
    Input("pt-mutations-store", "data"),
    Input("pt-drug-input", "value"),
)
def _update_response(mode, sample_id, mutations, selected_drug):
    """Mode 따라 실제/조립 분기. 둘 다 같은 출력 컴포넌트 사용."""
    empty_sankey = dcc.Graph(
        figure=get_sankey_figure([], []),
        config={"displayModeBar": False, "responsive": True},
        style={"height": "240px"},
    )

    if mode == "real":
        if not sample_id:
            return ("—", "환자 선택", "—", "—", empty_sankey, [],
                    "환자 선택 대기", "concordance-badge concordance-partial")
        return _build_real_outputs(sample_id, selected_drug)

    else:  # compose
        if not mutations:
            return ("—", "변이 조립 대기", "—", "—", empty_sankey, [],
                    "변이 1개 이상 추가", "concordance-badge concordance-partial")
        return _build_compose_outputs(mutations, selected_drug)


def _build_real_outputs(sample_id, selected_drug):
    """실제 모드 출력 빌드."""
    resp = get_patient_response(sample_id)
    if resp.get("error"):
        empty_sankey = dcc.Graph(figure=get_sankey_figure([], []),
                                  config={"displayModeBar": False})
        return ("—", resp["error"], "—", "—", empty_sankey, [],
                resp["error"], "concordance-badge concordance-partial")

    mutations = resp["mutations"]
    top_drugs = resp["top_drugs"]
    top_cells = resp["top_cells"]
    mean_sim = resp["mean_top_sim"]

    # Drug 표시 ranking (selected_drug 우선, 없으면 top-1)
    target_drug = None
    if selected_drug:
        for d in top_drugs:
            name = (d.get("drug_name") or "").lower()
            if name == selected_drug.lower():
                target_drug = d
                break
    if target_drug is None and top_drugs:
        target_drug = top_drugs[0]

    if target_drug:
        rank = target_drug.get("rank_hybrid", "?")
        z = target_drug.get("pred_zscore_weighted")
        tier = target_drug.get("hybrid_tier", "?")
        score_str = f"#{rank}"
        score_hint = f"Tier {tier} · z {z:+.2f}" if z is not None else f"Tier {tier}"
    else:
        score_str = "—"
        score_hint = "추천 없음"

    # 유사 cell line
    top1_name = top_cells[0]["ccle_name"].replace("_LUNG", "") if top_cells else "—"
    cell_metric = f"top-1: {top1_name}"

    # Mean similarity
    sim_str = f"{mean_sim:.2f}" if mean_sim else "—"

    # Sankey
    sankey_fig = get_sankey_figure(mutations, top_drugs[:5])
    sankey_graph = dcc.Graph(
        figure=sankey_fig,
        config={"displayModeBar": False, "responsive": True},
        style={"height": "240px"},
    )

    # Treatment table — top-5 drugs
    table = _build_treatment_table(top_drugs[:5])

    # Concordance badge — tier 1 drug 비율 기반
    n_tier1 = sum(1 for d in top_drugs[:5] if d.get("hybrid_tier") == 1)
    if n_tier1 >= 3:
        badge_text = f"✓ 강한 매칭 — top-5 중 {n_tier1}개 actionable target"
        badge_class = "concordance-badge concordance-concordant"
    elif n_tier1 >= 1:
        badge_text = f"◐ 부분 매칭 — top-5 중 {n_tier1}개 actionable"
        badge_class = "concordance-badge concordance-partial"
    else:
        badge_text = "⚠ Actionable target 없음 — ML 예측 only"
        badge_class = "concordance-badge concordance-discordant"

    return (score_str, score_hint, sim_str, cell_metric, sankey_graph,
            table, badge_text, badge_class)


def _build_compose_outputs(mutations, selected_drug):
    """조립 모드 출력 빌드."""
    result = compose_inference(mutations, top_k=5, top_n_drugs=10)
    if result.get("error"):
        empty_sankey = dcc.Graph(figure=get_sankey_figure([], []),
                                  config={"displayModeBar": False})
        return ("—", result["error"], "—", "—", empty_sankey, [],
                result["error"], "concordance-badge concordance-partial")

    top_drugs = result["top_drugs"]
    top_cells = result["top_cells"]
    mean_sim = result["mean_top_sim"]

    target_drug = None
    if selected_drug:
        for d in top_drugs:
            name = (d.get("drug_name") or "").lower()
            if name == selected_drug.lower():
                target_drug = d
                break
    if target_drug is None and top_drugs:
        target_drug = top_drugs[0]

    if target_drug:
        rank = target_drug.get("rank_hybrid", "?")
        z = target_drug.get("pred_zscore_weighted")
        tier = target_drug.get("hybrid_tier", "?")
        score_str = f"#{rank}"
        score_hint = f"Tier {tier} · z {z:+.2f}" if z is not None else f"Tier {tier}"
    else:
        score_str = "—"
        score_hint = "추천 없음"

    top1_name = top_cells[0]["ccle_name"].replace("_LUNG", "") if top_cells else "—"
    cell_metric = f"top-1: {top1_name}"
    sim_str = f"{mean_sim:.2f}" if mean_sim else "—"

    sankey_fig = get_sankey_figure(mutations, top_drugs[:5])
    sankey_graph = dcc.Graph(
        figure=sankey_fig,
        config={"displayModeBar": False, "responsive": True},
        style={"height": "240px"},
    )

    table = _build_treatment_table(top_drugs[:5])

    n_tier1 = result.get("n_tier1", 0)
    if n_tier1 >= 5:
        badge_text = f"✓ 강한 매칭 — {n_tier1}개 actionable target drug"
        badge_class = "concordance-badge concordance-concordant"
    elif n_tier1 >= 1:
        badge_text = f"◐ 부분 매칭 — {n_tier1}개 actionable drug"
        badge_class = "concordance-badge concordance-partial"
    else:
        badge_text = "⚠ Actionable target 없음 — ML 예측 only"
        badge_class = "concordance-badge concordance-discordant"

    return (score_str, score_hint, sim_str, cell_metric, sankey_graph,
            table, badge_text, badge_class)


def _build_treatment_table(top_drugs):
    """Top drugs treatment table."""
    rows = [
        html.Tr([
            html.Td("Rank", style={"padding": "5px 0", "color": "var(--nsclc-text-secondary)", "fontSize": "10px"}),
            html.Td("Drug", style={"padding": "5px 0", "color": "var(--nsclc-text-secondary)", "fontSize": "10px"}),
            html.Td("Target", style={"padding": "5px 0", "color": "var(--nsclc-text-secondary)", "fontSize": "10px"}),
            html.Td("Tier", style={"textAlign": "center", "padding": "5px 0",
                                    "color": "var(--nsclc-text-secondary)", "fontSize": "10px"}),
        ], style={"borderBottom": "0.5px solid var(--nsclc-border)"}),
    ]
    for d in top_drugs:
        rank = d.get("rank_hybrid", "?")
        name = d.get("drug_name") or "?"
        target = d.get("drug_targets_actionable") or d.get("target") or "—"
        if isinstance(target, str) and len(target) > 30:
            target = target[:28] + "…"
        tier = d.get("hybrid_tier", 2)
        tier_color = "var(--accent-cyan)" if tier == 1 else "var(--nsclc-text-tertiary)"

        rows.append(
            html.Tr([
                html.Td(f"#{rank}", style={"padding": "5px 0", "color": "var(--nsclc-text-secondary)",
                                            "fontVariantNumeric": "tabular-nums", "fontSize": "11px"}),
                html.Td(html.B(name) if tier == 1 else name,
                        style={"padding": "5px 0", "color": tier_color, "fontSize": "11px"}),
                html.Td(target, style={"padding": "5px 0", "color": "var(--nsclc-text-secondary)",
                                        "fontSize": "10px"}),
                html.Td(f"T{tier}", style={"textAlign": "center", "padding": "5px 0",
                                           "color": tier_color, "fontWeight": "500", "fontSize": "11px"}),
            ])
        )
    return rows


# ── Callback 3: Mutation chip 클릭 → store 업데이트 ────────────────────────────

@callback(
    Output("pt-mutations-store", "data"),
    Input({"type": "pt-chip-remove", "gene": ALL}, "n_clicks"),
    Input({"type": "pt-chip-add", "gene": ALL}, "n_clicks"),
    Input("pt-mode-store", "data"),
    Input("pt-patient-selector", "value"),
    State("pt-mutations-store", "data"),
    prevent_initial_call=True,
)
def _toggle_chip(remove_clicks, add_clicks, mode, sample_id, current):
    """
    Chip 클릭 토글 + mode/환자 변경 시 mutation set 자동 동기화.

    - 실제 모드: 환자 선택 시 그 환자의 mutation을 store에 채움
    - 조립 모드: chip 클릭으로 토글
    """
    current = current or []
    triggered = ctx.triggered_id

    # 실제 모드 + 환자 선택 변경 시에만 자동 동기화
    if triggered in ("pt-mode-store", "pt-patient-selector"):
        if mode == "real" and sample_id:
            from .loader import get_patient_mutations
            return get_patient_mutations(sample_id)
        # compose 모드 또는 sample_id 없으면 그대로 유지
        return current

    # Chip 클릭 (조립 모드만 의미 있음)
    if mode != "compose":
        return current

    if isinstance(triggered, dict):
        gene = triggered.get("gene")
        chip_type = triggered.get("type")
        if not gene:
            return current
        # n_clicks=None/0이면 component 생성 시 자동 trigger. 무시.
        trigger_value = ctx.triggered[0].get("value") if ctx.triggered else None
        if not trigger_value:
            return current
        if chip_type == "pt-chip-remove":
            return [g for g in current if g != gene]
        elif chip_type == "pt-chip-add":
            if gene not in current:
                return current + [gene]
    return current


# ── Callback 4: Mutation store → chip 영역 re-render ────────────────────────

@callback(
    Output("pt-mutation-chips", "children"),
    Input("pt-mutations-store", "data"),
)
def _render_chips(selected_mutations):
    """Selected + add chips re-render."""
    selected_mutations = selected_mutations or []
    all_genes = ACTIONABLE_GENES

    selected_chips = [
        html.Span(
            [
                f"{gene} ",
                html.Span("✕", className="chip-remove",
                          id={"type": "pt-chip-remove", "gene": gene},
                          style={"cursor": "pointer", "marginLeft": "4px"}),
            ],
            className="mutation-chip",
            id={"type": "pt-chip", "gene": gene},
        )
        for gene in selected_mutations
    ]

    available = [g for g in all_genes if g not in selected_mutations]
    add_chips = [
        html.Span(
            f"+ {gene}",
            className="mutation-chip-add",
            id={"type": "pt-chip-add", "gene": gene},
            style={"cursor": "pointer"},
        )
        for gene in available
    ]

    return selected_chips + add_chips
