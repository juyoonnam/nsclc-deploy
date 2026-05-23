"""
Mode 2 Cell-line view for the Simulator tab.

The public data access functions are intentionally small placeholders. Claude's
backend PR can replace their internals without changing the rendering contract.
"""

from __future__ import annotations

import math
from statistics import mean

from dash import dcc, html

from nsclc_ui.data.simulator_demo import (
    CELL_LINE_COMBO_DEFAULTS,
    CELL_LINE_DRUG_META,
    CELL_LINE_DRUG_OPTIONS,
    CELL_LINE_OPTIONS,
    CELL_LINE_RESPONSE_DEFAULTS,
    CELL_LINE_RESPONSE_POINTS,
)


_DRUG_BY_CHEMBL = {
    meta["chembl_id"]: drug
    for drug, meta in CELL_LINE_DRUG_META.items()
}
_DRUG_VALUES = [item["value"] for item in CELL_LINE_DRUG_OPTIONS]
_CELL_VALUES = [item["value"] for item in CELL_LINE_OPTIONS]
_DOSE_LABELS = ["1000", "100", "10", "1", "0"]
_DOSE_X_LABELS = ["0", "1", "10", "100", "1000"]


def _safe_drug(value: str | None, fallback: str = "Osimertinib") -> str:
    return value if value in _DRUG_VALUES else fallback


def _safe_cell(value: str | None) -> str:
    return value if value in _CELL_VALUES else "H1975"


def _ranks(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(indexed):
        end = cursor + 1
        while end < len(indexed) and indexed[end][1] == indexed[cursor][1]:
            end += 1
        rank = (cursor + end + 1) / 2
        for idx in range(cursor, end):
            ranks[indexed[idx][0]] = rank
        cursor = end
    return ranks


def _pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    mx, my = mean(xs), mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return 0.0
    return cov / (sx * sy)


def _spearman(xs: list[float], ys: list[float]) -> float:
    return _pearson(_ranks(xs), _ranks(ys))


def get_drug_response(chembl_id: str, cell_line: str) -> dict:
    """
    Returns:
        {
            "model_score": float,
            "model_prob": float,
            "prism_lfc": float | None,
            "priming_score": float | None,
            "n_cells": int,
            "spearman_rho": float,
        }
    """
    drug = _safe_drug(_DRUG_BY_CHEMBL.get(chembl_id, chembl_id))
    cell_line = _safe_cell(cell_line)
    points = CELL_LINE_RESPONSE_POINTS.get(drug, [])
    selected = next((point for point in points if point["cell_line"] == cell_line), None)
    if selected is None and points:
        selected = points[0]

    xs = [point["model_prob"] for point in points]
    ys = [point["priming_score"] for point in points]
    rho = _spearman(xs, ys) if points else 0.0
    if drug == CELL_LINE_RESPONSE_DEFAULTS["drug"] and cell_line == CELL_LINE_RESPONSE_DEFAULTS["cell_line"]:
        model_score = CELL_LINE_RESPONSE_DEFAULTS["model_score"]
        model_prob = CELL_LINE_RESPONSE_DEFAULTS["model_prob"]
        prism_lfc = CELL_LINE_RESPONSE_DEFAULTS["prism_lfc"]
        priming_score = CELL_LINE_RESPONSE_DEFAULTS["priming_score"]
    else:
        model_prob = selected["model_prob"] if selected else None
        priming_score = selected["priming_score"] if selected else None
        prism_lfc = selected["prism_lfc"] if selected else None
        model_score = round(0.58 + (model_prob or 0) * 0.35, 2)

    return {
        "drug": drug,
        "chembl_id": CELL_LINE_DRUG_META[drug]["chembl_id"],
        "cell_line": cell_line,
        "model_score": model_score,
        "model_prob": model_prob,
        "prism_lfc": prism_lfc,
        "priming_score": priming_score,
        "n_cells": len(points),
        "spearman_rho": round(rho, 2),
        "points": points,
    }


def get_synergy_simulation(drug_a: str, drug_b: str, cell_line: str) -> dict:
    """병용 모드: simulation-only hypothesis. No observed combo response."""
    drug_a = _safe_drug(drug_a)
    drug_b = _safe_drug(drug_b, fallback="Cobimetinib")
    cell_line = _safe_cell(cell_line)
    score_adjust = 0.0
    if {CELL_LINE_DRUG_META[drug_a]["target"], CELL_LINE_DRUG_META[drug_b]["target"]} == {"EGFR", "MEK"}:
        score_adjust = 0.0
    else:
        score_adjust = -0.12
    return {
        **CELL_LINE_COMBO_DEFAULTS,
        "cell_line": cell_line,
        "drug_a": drug_a,
        "drug_b": drug_b,
        "target_a": CELL_LINE_DRUG_META[drug_a]["target"],
        "target_b": CELL_LINE_DRUG_META[drug_b]["target"],
        "heuristic_score": round(max(0.18, CELL_LINE_COMBO_DEFAULTS["heuristic_score"] + score_adjust), 2),
        "combo_score": round(max(3.5, CELL_LINE_COMBO_DEFAULTS["combo_score"] + score_adjust * 25), 1),
    }


def _dropdown(component_id: str, options: list[dict], value: str, width_class: str = "") -> html.Div:
    return html.Div(
        dcc.Dropdown(
            id=component_id,
            options=options,
            value=value,
            clearable=False,
            searchable=False,
            className="simulator-cell-dropdown",
        ),
        className=f"simulator-cell-dropdown-wrap {width_class}".strip(),
    )


def _mode_switch(mode: str) -> html.Div:
    return html.Div(
        [
            html.Button(
                "단독",
                id="sim-cell-single-toggle",
                n_clicks=0,
                className="simulator-cell-mode-button is-active" if mode == "single" else "simulator-cell-mode-button",
            ),
            html.Button(
                "병용",
                id="sim-cell-combo-toggle",
                n_clicks=0,
                className="simulator-cell-mode-button is-active" if mode == "combo" else "simulator-cell-mode-button",
            ),
        ],
        className="simulator-cell-mode-switch",
    )


def _single_controls(cell_line: str, drug: str) -> html.Div:
    return html.Div(
        [
            html.Div([html.Span("Cell line"), _dropdown("sim-cellline-cell", CELL_LINE_OPTIONS, cell_line)], className="simulator-cell-control-pair"),
            html.Div([html.Span("Drug"), _dropdown("sim-cellline-drug", CELL_LINE_DRUG_OPTIONS, drug)], className="simulator-cell-control-pair"),
            _mode_switch("single"),
            html.Button("↔ 병용 모드로 전환", id="sim-cell-mode-action", n_clicks=0, className="simulator-cell-action"),
        ],
        className="simulator-cell-controls simulator-cell-controls-single",
    )


def _combo_controls(cell_line: str, drug_a: str, drug_b: str) -> html.Div:
    return html.Div(
        [
            html.Div([html.Span("Cell"), _dropdown("sim-combo-cell", CELL_LINE_OPTIONS, cell_line)], className="simulator-cell-control-pair"),
            html.Div([html.Span("A:"), _dropdown("sim-combo-drug-a", CELL_LINE_DRUG_OPTIONS, drug_a)], className="simulator-cell-control-pair"),
            html.Div([html.Span("B:"), _dropdown("sim-combo-drug-b", CELL_LINE_DRUG_OPTIONS, drug_b)], className="simulator-cell-control-pair"),
            _mode_switch("combo"),
            html.Button("↔ 단독 모드로 전환", id="sim-cell-mode-action", n_clicks=0, className="simulator-cell-action"),
        ],
        className="simulator-cell-controls simulator-cell-controls-combo",
    )


def _dots(value: int) -> html.Div:
    return html.Div(
        [
            html.Span("●", className="simulator-cell-dot is-filled" if idx < value else "simulator-cell-dot")
            for idx in range(3)
        ],
        className="simulator-cell-dots",
    )


def _metric_card(icon: str, label: str, value: str, tone: str, sub: str | None = None) -> html.Div:
    return html.Div(
        [
            html.Div(icon, className=f"simulator-cell-metric-icon simulator-cell-metric-{tone}"),
            html.Div(
                [
                    html.Div(label, className="simulator-cell-metric-label"),
                    html.Div(value, className=f"simulator-cell-metric-value simulator-cell-value-{tone}"),
                    html.Div(sub, className="simulator-cell-metric-sub") if sub else None,
                ],
                className="simulator-cell-metric-copy",
            ),
        ],
        className="simulator-cell-metric-card",
    )


def _single_metrics(response: dict) -> html.Div:
    return html.Div(
        [
            _metric_card("⚗", "모델 score  ⓘ", f"{response['model_score']:.2f}", "white", "Confidence  ● ● ●"),
            _metric_card("⇗", "예측 반응도  ⓘ", f"{response['model_prob']:.2f}", "cyan", "(0 = Resistant, 1 = Sensitive)"),
            _metric_card("◎", "실측 (PRISM)  ⓘ", f"{response['priming_score']:.2f}", "purple", "(Delta Priming Score)"),
        ],
        className="simulator-cell-metrics",
    )


def _combo_metrics(sim: dict) -> html.Div:
    return html.Div(
        [
            _metric_card("◎", "예상 결과", sim["result_label"], "green"),
            _metric_card("☷", "휴리스틱 점수  ⓘ", f"{sim['heuristic_score']:.2f}", "white", "● ● ○"),
            _metric_card("▥", "가설 ComboScore  ⓘ", f"+{sim['combo_score']:.1f}", "green", "simulation-only"),
        ],
        className="simulator-cell-metrics",
    )


def _agreement_banner() -> html.Div:
    return html.Div(
        [
            html.Div("✓", className="simulator-cell-banner-icon"),
            html.Div(
                [
                    html.Div("예측과 실측이 유사함", className="simulator-cell-banner-title"),
                    html.Div("모델이 이 세포주의 약물 반응을 잘 설명하고 있습니다.", className="simulator-cell-banner-copy"),
                ]
            ),
        ],
        className="simulator-cell-agreement",
    )


def _scatter_plot(response: dict) -> html.Div:
    points = response["points"]
    selected = response["cell_line"]
    return html.Div(
        [
            html.Div(
                [
                    html.Div("Model vs Observed (PRISM)", className="simulator-cell-panel-title"),
                    html.Div(
                        f"n = {response['n_cells']} cell lines   Spearman ρ = {response['spearman_rho']:.2f}",
                        className="simulator-cell-panel-meta",
                    ),
                ],
                className="simulator-cell-panel-header",
            ),
            html.Div(
                [
                    html.Div(className="simulator-scatter-grid"),
                    html.Div(className="simulator-scatter-diagonal"),
                    *[
                        html.Div(
                            title=f"{point['cell_line']}: {point['model_prob']:.2f}, {point['priming_score']:.2f}",
                            className=(
                                "simulator-scatter-point is-selected"
                                if point["cell_line"] == selected
                                else "simulator-scatter-point"
                            ),
                            style={
                                "left": f"{point['model_prob'] * 100:.2f}%",
                                "bottom": f"{point['priming_score'] * 100:.2f}%",
                            },
                        )
                        for point in points
                    ],
                    html.Div("실측 (PRISM)", className="simulator-scatter-y-label"),
                    html.Div("예측 반응도 (모델)", className="simulator-scatter-x-label"),
                ],
                className="simulator-scatter",
            ),
        ],
        className="simulator-cell-panel simulator-scatter-panel",
    )


def _range_bar(value: float, min_label: str, mid_label: str, max_label: str, tone: str = "green") -> html.Div:
    left = max(4, min(96, (value + 10) / 20 * 100 if min_label == "−10" else (value + 1) / 2 * 100))
    return html.Div(
        [
            html.Div(className="simulator-range-line"),
            html.Div(className=f"simulator-range-dot simulator-range-{tone}", style={"left": f"{left:.1f}%"}),
            html.Div(
                [
                    html.Span(min_label),
                    html.Span(mid_label),
                    html.Span(max_label),
                ],
                className="simulator-range-labels",
            ),
        ],
        className="simulator-range",
    )


def _cross_source(response: dict) -> html.Div:
    return html.Div(
        [
            html.Div("🛡 Cross-source 검증  ⓘ", className="simulator-cell-section-title"),
            html.Div(
                [
                    html.Div("P", className="simulator-source-letter"),
                    html.Div(
                        [
                            html.Div("PRISM (Delta Priming Score)", className="simulator-source-label"),
                            html.Div(f"{response['prism_lfc']:.2f}", className="simulator-source-value"),
                            html.Div("강한 살해 (Strong Killing)", className="simulator-source-copy"),
                        ],
                    ),
                    _range_bar(response["prism_lfc"], "−10", "0", "10"),
                ],
                className="simulator-source-row",
            ),
            html.Div(
                [
                    html.Div("G", className="simulator-source-letter"),
                    html.Div(
                        [
                            html.Div("GDSC2 IC50", className="simulator-source-label"),
                            html.Div("수집 예정", className="simulator-source-placeholder"),
                            html.Div("발표 전 보강 시 활성화", className="simulator-source-copy"),
                        ],
                    ),
                    _range_bar(0.0, "1 nM", "100 nM", "10 μM"),
                ],
                className="simulator-source-row",
            ),
            html.Div(
                [
                    html.Div("ρ", className="simulator-source-letter"),
                    html.Div(
                        [
                            html.Div("Spearman 상관 (Model vs PRISM)", className="simulator-source-label"),
                            html.Div(f"ρ = {response['spearman_rho']:.2f}", className="simulator-source-cyan"),
                            html.Div("전체 세포주 집합에서 모델 예측력 확인", className="simulator-source-copy"),
                        ],
                    ),
                    _range_bar(response["spearman_rho"], "−1", "0", "1", tone="cyan"),
                ],
                className="simulator-source-row",
            ),
        ],
        className="simulator-cell-panel simulator-cross-source",
    )


def _interpretation(response: dict) -> html.Div:
    return html.Div(
        [
            html.Div("💡 어떻게 해석?  ⓘ", className="simulator-cell-section-title"),
            html.Div("✓ 예측 반응도와 PRISM 실측이 유사하여 모델이 H1975의 반응을 잘 설명합니다.", className="simulator-cell-check"),
            html.Div("✓ PRISM lfc는 강한 약물 감수성을 지지합니다.", className="simulator-cell-check"),
            html.Div(
                f"✓ 모델 vs PRISM 상관 ρ = {response['spearman_rho']:.2f}는 전체 세포주 집합에서 일관성을 시사합니다.",
                className="simulator-cell-check",
            ),
        ],
        className="simulator-cell-panel simulator-interpretation",
    )


def _single_mode(cell_line: str, drug: str) -> html.Div:
    drug = _safe_drug(drug)
    response = get_drug_response(CELL_LINE_DRUG_META[drug]["chembl_id"], cell_line)
    return html.Div(
        [
            _single_controls(response["cell_line"], drug),
            _single_metrics(response),
            _agreement_banner(),
            html.Div(
                [
                    _scatter_plot(response),
                    html.Div([_cross_source(response), _interpretation(response)], className="simulator-cell-side"),
                ],
                className="simulator-cell-main simulator-cell-single-main",
            ),
            html.Div(
                [
                    html.A("⚗ 다른 약물 비교", href="/simulator", className="simulator-cell-bottom-cta simulator-cell-bottom-outline"),
                    html.Button("🔗 병용 모드로 전환", id="sim-cell-mode-action-bottom", n_clicks=0, className="simulator-cell-bottom-cta simulator-cell-bottom-filled"),
                ],
                className="simulator-cell-bottom-actions",
            ),
        ],
        className="simulator-cellline simulator-cellline-single",
    )


def _dose_matrix(sim: dict) -> html.Div:
    best_row, best_col = sim["best_index"]
    return html.Div(
        [
            html.Div("Dose matrix  ⓘ", className="simulator-cell-panel-title"),
            html.Div(
                [
                    html.Div("", className="simulator-dose-corner"),
                    *[html.Div(label, className="simulator-dose-axis-label") for label in _DOSE_X_LABELS],
                    *[
                        item
                        for row_idx, row in enumerate(sim["dose_matrix"])
                        for item in [
                            html.Div(_DOSE_LABELS[row_idx], className="simulator-dose-axis-label"),
                            *[
                                html.Div(
                                    [
                                        html.Span(f"{value:g}"),
                                        html.Span("Best +18.2", className="simulator-dose-best-label")
                                        if row_idx == best_row and col_idx == best_col
                                        else None,
                                    ],
                                    className=(
                                        "simulator-dose-cell is-best"
                                        if row_idx == best_row and col_idx == best_col
                                        else "simulator-dose-cell"
                                    ),
                                    style={"--dose": str(max(0, min(1, float(value) / 18.2)))},
                                )
                                for col_idx, value in enumerate(row)
                            ],
                        ]
                    ],
                ],
                className="simulator-dose-grid",
            ),
            html.Div("A (Osimertinib, nM)", className="simulator-dose-y-title"),
            html.Div("B (Cobimetinib, nM)", className="simulator-dose-x-title"),
            html.Div(
                [html.Span("Antagonism"), html.Span("Additive"), html.Span("Synergy")],
                className="simulator-dose-legend",
            ),
            html.Div("값은 예시 시뮬레이션 결과입니다.", className="simulator-dose-note"),
        ],
        className="simulator-cell-panel simulator-dose-panel",
    )


def _combo_summary(sim: dict) -> html.Div:
    return html.Div(
        [
            html.Div("💡 조합 해석  ⓘ", className="simulator-cell-section-title"),
            html.Div(
                [
                    html.Span(sim["drug_a"], className="simulator-combo-pill simulator-combo-a"),
                    html.Span("+", className="simulator-combo-plus"),
                    html.Span(sim["drug_b"], className="simulator-combo-pill simulator-combo-b"),
                ],
                className="simulator-combo-title-row",
            ),
            html.Div(
                [
                    html.Div([html.Span("예상 결과"), html.Strong(sim["result_label"])]),
                    html.Div([html.Span("휴리스틱 점수"), html.Strong(f"{sim['heuristic_score']:.2f}"), _dots(2)]),
                    html.Div([html.Span("가설 ComboScore"), html.Strong(f"+{sim['combo_score']:.1f}")]),
                ],
                className="simulator-combo-score-grid",
            ),
            html.Div(
                [
                    html.Div("EGFR", className="simulator-path-node simulator-path-green"),
                    html.Span("→"),
                    html.Div("RAS", className="simulator-path-node simulator-path-blue"),
                    html.Span("→"),
                    html.Div("RAF", className="simulator-path-node simulator-path-blue"),
                    html.Span("→"),
                    html.Div("MEK", className="simulator-path-node simulator-path-blue"),
                    html.Div(sim["drug_a"], className="simulator-path-drug simulator-path-drug-a"),
                    html.Div(sim["drug_b"], className="simulator-path-drug simulator-path-drug-b"),
                ],
                className="simulator-path-chain",
            ),
        ],
        className="simulator-cell-panel simulator-combo-summary",
    )


def _combo_evidence() -> html.Div:
    return html.Div(
        [
            html.Div("⚗ 근거 요약  ⓘ", className="simulator-cell-section-title"),
            html.Div("✓ EGFR와 MEK 동시 억제로 우회 신호를 줄일 가능성이 있습니다.", className="simulator-cell-check"),
            html.Div("✓ 단독 대비 병용에서 더 높은 가설 시너지 점수가 관찰됩니다.", className="simulator-cell-check"),
            html.Div("✓ PRISM은 단독 screen이며 병용 실측 dose-response는 없습니다.", className="simulator-cell-check"),
            html.Div("✓ 중간 농도 구간에서 최적 조합 창이 나타나는 가정입니다.", className="simulator-cell-check"),
        ],
        className="simulator-cell-panel simulator-combo-evidence",
    )


def _combo_next_steps() -> html.Div:
    return html.Div(
        [
            html.Div("🚀 다음 단계", className="simulator-cell-section-title"),
            html.Div(
                [
                    html.A("Pathway Map에서 보기", href="/pathway", className="simulator-cell-bottom-cta simulator-cell-bottom-outline"),
                    html.A("Patient 모드로 보내기", href="/simulator", className="simulator-cell-bottom-cta simulator-cell-bottom-filled"),
                ],
                className="simulator-cell-bottom-actions compact",
            ),
        ],
        className="simulator-cell-panel simulator-combo-next",
    )


def _combo_mode(cell_line: str, drug_a: str, drug_b: str) -> html.Div:
    sim = get_synergy_simulation(drug_a, drug_b, cell_line)
    return html.Div(
        [
            _combo_controls(sim["cell_line"], sim["drug_a"], sim["drug_b"]),
            _combo_metrics(sim),
            html.Div(
                [
                    _dose_matrix(sim),
                    html.Div([_combo_summary(sim), _combo_evidence(), _combo_next_steps()], className="simulator-cell-side"),
                ],
                className="simulator-cell-main simulator-cell-combo-main",
            ),
            html.Div(sim["disclaimer"], className="simulator-combo-disclaimer"),
        ],
        className="simulator-cellline simulator-cellline-combo",
    )


def render_cellline_mode(
    cellline_mode: str = "single",
    cell_line: str = "H1975",
    drug: str = "Osimertinib",
    drug_a: str = "Osimertinib",
    drug_b: str = "Cobimetinib",
) -> html.Div:
    if cellline_mode == "combo":
        return _combo_mode(cell_line, drug_a, drug_b)
    return _single_mode(cell_line, drug)
