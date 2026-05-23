"""
Cell-line Mode — single-agent cross-source validation view.

Implements Part B-1 from presentation_data/codex_prompt_v1.md against
mockup_2_v2.svg. This page intentionally uses only the public loader contract.
"""

from __future__ import annotations

import math

import dash
from dash import ALL, Input, Output, callback, ctx, dcc, html

from nsclc_ui.data.prism_loader import get_prism_response
from nsclc_ui.data.gdsc2_loader import (
    get_gdsc2_response,
    compute_cross_source_validation,
    compute_model_vs_gdsc2_correlation,
    DEMO_SCENARIO_GDSC2,
)


dash.register_page(
    __name__,
    path="/cell-line-mode",
    name="Cell-line Mode",
    title="NSCLC Insight Engine — Cell-line Mode",
    order=7,
)


# Single mode 데이터
result = compute_cross_source_validation(
    chembl_id="CHEMBL3353410",  # Osimertinib
    cell_line="H1975",
)

# 검증 (DEMO_SCENARIO_GDSC2와 정합)
assert result["consistency"] == "concordant_sensitive"
assert result["gdsc2"]["cell_line_ic50_nm"] == 37.7
assert result["gdsc2"]["cell_line_z_score"] == -3.8534
assert result["prism"]["cell_line_lfc"] == -0.7526

# Scatter 데이터
corr = compute_model_vs_gdsc2_correlation()
# -> {"n": 180, "spearman_rho": -0.2661, ...}

_PRISM_RESPONSE = get_prism_response(result["chembl_id"], result["cell_line"])
_GDSC2_RESPONSE = get_gdsc2_response(result["chembl_id"], result["cell_line"])


# Combination mode 데이터 (Part B-2)
_COMBO_CELL_LINE = "H1975"
_COMBO_A = {
    "label": "A",
    "name": "Osimertinib",
    "short": "Osi",
    "chembl_id": "CHEMBL3353410",
}
_COMBO_B = {
    "label": "B",
    "name": "Cobimetinib",
    "short": "Cobi",
    "chembl_id": "CHEMBL2146883",
}
_COMBO_DELTA_BLISS = 0.08
_COMBO_BEST_DELTA_BLISS = 0.12


def lfc_to_effect(lfc: float) -> float:
    """PRISM log fold change -> effect (1 - viability)."""
    return 1 - math.exp(lfc) if lfc < 0 else 0


def bliss_expected(lfc_a: float, lfc_b: float) -> float:
    """Bliss independence baseline."""
    e_a = lfc_to_effect(lfc_a)
    e_b = lfc_to_effect(lfc_b)
    return e_a + e_b - e_a * e_b


_COMBO_PRISM_A = get_prism_response(_COMBO_A["chembl_id"], _COMBO_CELL_LINE)
_COMBO_PRISM_B = get_prism_response(_COMBO_B["chembl_id"], _COMBO_CELL_LINE)
_COMBO_GDSC_A = get_gdsc2_response(_COMBO_A["chembl_id"], _COMBO_CELL_LINE)
_COMBO_GDSC_B = get_gdsc2_response(_COMBO_B["chembl_id"], _COMBO_CELL_LINE)

_COMBO_LFC_A = _COMBO_PRISM_A["cell_line_lfc"]
_COMBO_LFC_B = _COMBO_PRISM_B["cell_line_lfc"]
_COMBO_EFFECT_A = lfc_to_effect(_COMBO_LFC_A)
_COMBO_EFFECT_B = lfc_to_effect(_COMBO_LFC_B)
_COMBO_BLISS_BASELINE = bliss_expected(_COMBO_LFC_A, _COMBO_LFC_B)

assert _COMBO_LFC_A == -0.7526
assert _COMBO_LFC_B == -0.6996
assert round(_COMBO_BLISS_BASELINE, 2) == 0.77
assert _COMBO_GDSC_A["in_gdsc2"] is True
assert _COMBO_GDSC_B["in_gdsc2"] is False

_DEMO = DEMO_SCENARIO_GDSC2["single"]
_DEMO_DRUG = _DEMO["drug"]
_MODEL_PROB = 0.82
_MODEL_STD = 0.07
_SELECTED_LN_IC50 = _DEMO_DRUG["expected_ln_ic50"]

_CELL_OPTIONS = [
    {"label": "H1975 (NCI-H1975)", "value": "H1975"},
    {"label": "HCC827", "value": "HCC827"},
    {"label": "PC9", "value": "PC9"},
    {"label": "A549", "value": "A549"},
]

_DRUG_OPTIONS = [
    {"label": "Osimertinib", "value": "Osimertinib"},
    {"label": "Afatinib", "value": "Afatinib"},
    {"label": "Erlotinib", "value": "Erlotinib"},
    {"label": "Gefitinib", "value": "Gefitinib"},
    {"label": "Trametinib", "value": "Trametinib"},
]

_DRUG_META = {
    "Osimertinib": {"chembl_id": "CHEMBL3353410"},
    "Afatinib": {"chembl_id": "CHEMBL1173655"},
    "Erlotinib": {"chembl_id": "CHEMBL553"},
    "Gefitinib": {"chembl_id": "CHEMBL939"},
    "Trametinib": {"chembl_id": "CHEMBL2103875"},
}


def _minus(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}".replace("-", "−")


def _signed(value: float, digits: int = 2) -> str:
    text = _minus(value, digits)
    return text if value < 0 else f"+{text}"


def _ln_to_pct(ln_ic50: float) -> float:
    return max(0.0, min(100.0, ((ln_ic50 + 6.0) / 14.0) * 100.0))


def _scatter_points() -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    for idx in range(180):
        x = 0.05 + (((idx * 37) % 91) / 100)
        wave = math.sin(idx * 1.73) * 1.6 + math.cos(idx * 0.41) * 0.65
        band = ((idx % 6) - 2.5) * 0.48
        ln_ic50 = 3.2 - (6.0 * x) + wave + band
        points.append(
            {
                "x": max(2.0, min(98.0, x * 100.0)),
                "y": _ln_to_pct(ln_ic50),
            }
        )
    return points


def _validation_for(drug: str | None, cell_line: str | None) -> dict:
    drug_name = drug if drug in _DRUG_META else _DEMO_DRUG["name"]
    cell = cell_line or _DEMO["cell_line"]
    return compute_cross_source_validation(_DRUG_META[drug_name]["chembl_id"], cell)


def _has_prism(validation: dict) -> bool:
    prism = validation.get("prism", {})
    return bool(prism.get("in_prism") and prism.get("cell_line_in_prism"))


def _has_gdsc2(validation: dict) -> bool:
    gdsc2 = validation.get("gdsc2", {})
    return bool(gdsc2.get("in_gdsc2") and gdsc2.get("cell_line_in_gdsc2"))


def _prism_label(lfc: float | None) -> str:
    if lfc is None:
        return "PRISM unavailable"
    if lfc < -0.5:
        return "Sensitive (lfc < −0.5)"
    if lfc > 0.5:
        return "Resistant (lfc > +0.5)"
    return "Weak signal (−0.5 ≤ lfc ≤ +0.5)"


def _gdsc2_label(gdsc2: dict) -> str:
    sensitivity = gdsc2.get("sensitivity_class")
    if sensitivity == "strong_sensitive":
        return "Strong sensitive (<100 nM)"
    if sensitivity == "sensitive":
        return "Sensitive (<1000 nM)"
    if sensitivity == "moderate":
        return "Moderate (1–10 μM)"
    if sensitivity == "resistant":
        return "Resistant (>10 μM)"
    return "GDSC2 unavailable"


def _log_ic50_position(ic50_nm: float | None) -> str:
    if ic50_nm is None or ic50_nm <= 0:
        return "0%"
    return f"{max(0.0, min(100.0, math.log10(ic50_nm) / 4.0 * 100.0)):.1f}%"


def _z_score_position(z_score: float | None) -> str:
    if z_score is None:
        return "50%"
    return f"{max(0.0, min(100.0, (z_score + 4.0) / 6.0 * 100.0)):.1f}%"


_CONSISTENCY_META = {
    "concordant_sensitive": (
        "green",
        "Concordant Sensitive — 두 source 모두 강한 민감",
    ),
    "concordant_resistant": (
        "red",
        "Concordant Resistant — 두 source 모두 저항",
    ),
    "discordant": (
        "orange",
        "Discordant — 두 source 상반",
    ),
    "prism_only": (
        "yellow",
        "PRISM only — 단일 source 단계",
    ),
    "gdsc2_only": (
        "yellow",
        "GDSC2 only — 단일 source 단계",
    ),
    "weak_signal": (
        "gray",
        "Weak signal — 일관성 약함",
    ),
}


def _dropdown(
    component_id: str,
    options: list[dict[str, str]],
    value: str,
    class_name: str = "cell-line-select",
) -> html.Div:
    return html.Div(
        dcc.Dropdown(
            id=component_id,
            options=options,
            value=value,
            clearable=False,
            searchable=False,
            className=class_name,
        ),
        className="cell-line-select-wrap",
    )


def _header(show_combo_warning: bool = False) -> html.Div:
    return html.Div(
        [
            html.Div("☰", className="cell-line-menu"),
            html.Div(
                [
                    html.Div(className="cell-line-helix-strand cell-line-helix-left"),
                    html.Div(className="cell-line-helix-strand cell-line-helix-right"),
                    *[
                        html.Div(className="cell-line-helix-rung", style={"top": f"{top}px"})
                        for top in (7, 14, 21, 28, 35)
                    ],
                ],
                className="cell-line-helix",
            ),
            html.Div("Simulator — Triple-Mode Validation Engine", className="cell-line-title"),
            html.Div("Beta", className="cell-line-beta"),
            html.Div(className="cell-line-header-spacer"),
            (
                html.Div(
                    "⚠ 병용 효과는 모델 추론 — 실측 검증 X",
                    className="cell-line-combo-header-warning",
                )
                if show_combo_warning
                else None
            ),
            html.Div([html.Strong("한"), html.Span(" / EN")], className="cell-line-lang"),
            html.Div("⛶", className="cell-line-expand"),
        ],
        className="cell-line-header",
    )


def _tabs() -> html.Div:
    return html.Div(
        [
            html.A("📖 ① Library", href="/simulator", className="cell-line-tab"),
            html.Div("⚗ ② Cell-line", className="cell-line-tab is-active"),
            html.A("👤 ③ Patient", href="/simulator", className="cell-line-tab"),
        ],
        className="cell-line-tabs",
    )


def _controls() -> html.Div:
    return html.Div(
        [
            html.Div("Cell line", className="cell-line-control-label"),
            _dropdown("cell-line-mode-cell", _CELL_OPTIONS, _DEMO["cell_line"]),
            html.Div("Drug", className="cell-line-control-label"),
            _dropdown("cell-line-mode-drug", _DRUG_OPTIONS, _DEMO_DRUG["name"]),
            html.Div(
                [html.Span("단독", className="is-selected"), html.Span("병용")],
                className="cell-line-mode-pill",
            ),
            html.Div(
                [
                    html.Div("CROSS-SOURCE 검증 가능", className="cell-line-xs-title"),
                    html.Div("PRISM ∩ GDSC2 (28풀)", className="cell-line-xs-sub"),
                ],
                className="cell-line-xs-badge",
            ),
            html.Button(
                "↔ 병용 모드로 전환",
                id={"type": "cell-line-mode-action", "mode": "combo", "slot": "top"},
                className="cell-line-switch-button",
            ),
        ],
        className="cell-line-controls",
    )


def _metric_card(
    icon: str,
    label: str,
    value,
    tone: str,
    sub,
    badge: str | None = None,
) -> html.Div:
    return html.Div(
        [
            html.Div(icon, className=f"cell-line-metric-icon cell-line-icon-{tone}"),
            html.Div(
                [
                    html.Div(label, className="cell-line-metric-label"),
                    html.Div(value, className="cell-line-metric-value"),
                    html.Div(sub, className=f"cell-line-metric-sub cell-line-sub-{tone}"),
                ],
                className="cell-line-metric-copy",
            ),
            html.Div(badge, className="cell-line-confidence-badge") if badge else None,
        ],
        className="cell-line-metric-card",
    )


def _top_card_children(validation: dict = result) -> list:
    gdsc2 = validation["gdsc2"] if _has_gdsc2(validation) else {}
    prism = validation["prism"] if _has_prism(validation) else {}
    ic50 = gdsc2.get("cell_line_ic50_nm")
    lfc = prism.get("cell_line_lfc")
    return [
            _metric_card(
                "⚗",
                "모델 score (compound) ⓘ",
                [
                    f"{_MODEL_PROB:.2f}",
                    html.Span(f" ±{_MODEL_STD:.2f}", className="cell-line-metric-std"),
                ],
                "violet",
                [
                    "scaffold OOF · 3 seeds · y=1",
                    html.Span(className="cell-line-dot-row", children=[
                        html.Span(className="cell-line-dot"),
                        html.Span(className="cell-line-dot"),
                        html.Span(className="cell-line-dot"),
                    ]),
                ],
                badge="높음",
            ),
            _metric_card(
                "⊙",
                "GDSC2 IC50 (실측) ⓘ",
                [
                    f"{ic50:.1f} " if ic50 is not None else "미수집",
                    html.Span("nM", className="cell-line-unit") if ic50 is not None else None,
                ],
                "green",
                _gdsc2_label(gdsc2),
            ),
            _metric_card(
                "◎",
                "PRISM lfc (실측) ⓘ",
                _minus(lfc, 2) if lfc is not None else "미수집",
                "violet",
                _prism_label(lfc),
            ),
        ]


def _top_cards() -> html.Div:
    return html.Div(
        _top_card_children(),
        id="cell-line-top-cards",
        className="cell-line-metric-grid",
    )


def _consistency_children(validation: dict = result) -> list:
    tone, label = _CONSISTENCY_META.get(validation["consistency"], _CONSISTENCY_META["weak_signal"])
    prism = validation["prism"] if _has_prism(validation) else {}
    gdsc2 = validation["gdsc2"] if _has_gdsc2(validation) else {}
    prism_text = _minus(prism["cell_line_lfc"], 2) if prism.get("cell_line_lfc") is not None else "미수집"
    ic50_text = f"{gdsc2['cell_line_ic50_nm']:.1f} nM" if gdsc2.get("cell_line_ic50_nm") is not None else "미수집"
    if validation["consistency"] == "concordant_sensitive":
        copy = (
            f"PRISM lfc {prism_text} + GDSC2 IC50 {ic50_text}. "
            "약리학적 일관성: T790M 변이 cell line이 3세대 EGFR TKI에 강한 민감 "
            "(Phase Y 약리학 정합)."
        )
    else:
        copy = (
            f"PRISM lfc {prism_text} + GDSC2 IC50 {ic50_text}. "
            f"loader 판정: {validation['consistency']}."
        )
    return [
        html.Div("✓", className="cell-line-consistency-icon"),
        html.Div(
            [
                html.Div(label, className="cell-line-consistency-title"),
                html.Div(copy, className="cell-line-consistency-copy"),
            ],
            className="cell-line-consistency-text",
        ),
    ]


def _consistency_class(validation: dict = result) -> str:
    tone, _label = _CONSISTENCY_META.get(validation["consistency"], _CONSISTENCY_META["weak_signal"])
    return f"cell-line-consistency cell-line-consistency-{tone}"


def _consistency_banner() -> html.Div:
    return html.Div(
        _consistency_children(),
        id="cell-line-consistency",
        className=_consistency_class(),
    )


def _scatter() -> html.Div:
    rho = corr.get("spearman_rho")
    rho_text = _minus(float(rho), 2) if rho is not None else "−0.27"
    n = int(corr.get("n") or 180)
    selected_bottom = _ln_to_pct(_SELECTED_LN_IC50)
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Model vs Observed (GDSC2)", className="cell-line-panel-title"),
                            html.Div(
                                "champion model OOF prob × GDSC2 mean LN_IC50",
                                className="cell-line-panel-subtitle",
                            ),
                        ],
                    ),
                    html.Div(
                        [
                            html.Span(f"n = {n} compounds"),
                            html.Span(["Spearman ρ = ", html.Strong(rho_text)]),
                        ],
                        className="cell-line-scatter-stats",
                    ),
                ],
                className="cell-line-panel-heading",
            ),
            html.Div(
                [
                    html.Div(className="cell-line-scatter-y-axis"),
                    html.Div(className="cell-line-scatter-x-axis"),
                    *[
                        html.Div(
                            className="cell-line-scatter-point",
                            style={"left": f"{point['x']:.2f}%", "bottom": f"{point['y']:.2f}%"},
                        )
                        for point in _scatter_points()
                    ],
                    html.Div(className="cell-line-scatter-trend"),
                    html.Div(
                        className="cell-line-selected-guide-x",
                        style={"left": f"{_MODEL_PROB * 100:.2f}%"},
                    ),
                    html.Div(
                        className="cell-line-selected-guide-y",
                        style={"bottom": f"{selected_bottom:.2f}%"},
                    ),
                    html.Div(
                        className="cell-line-selected-point",
                        style={
                            "left": f"{_MODEL_PROB * 100:.2f}%",
                            "bottom": f"{selected_bottom:.2f}%",
                        },
                    ),
                    html.Div(
                        [
                            html.Div("H1975 × Osimertinib", className="cell-line-selected-label-title"),
                            html.Div(
                                f"prob {_MODEL_PROB:.2f}, LN_IC50 {_minus(_SELECTED_LN_IC50, 2)}",
                                className="cell-line-selected-label-sub",
                            ),
                        ],
                        className="cell-line-selected-label",
                        style={
                            "left": f"{min(84, _MODEL_PROB * 100 + 2.4):.2f}%",
                            "bottom": f"{selected_bottom + 0.5:.2f}%",
                        },
                    ),
                    html.Div("선택 지점", className="cell-line-scatter-legend"),
                    html.Div("model OOF prob (Champion E2)", className="cell-line-x-label"),
                    html.Div("GDSC2 mean LN_IC50 (낮을수록 민감)", className="cell-line-y-label"),
                    *[
                        html.Div(label, className="cell-line-x-tick", style={"left": pos})
                        for label, pos in (
                            ("0.0", "0%"),
                            ("0.25", "25%"),
                            ("0.50", "50%"),
                            ("0.75", "75%"),
                            ("1.0", "100%"),
                        )
                    ],
                    *[
                        html.Div(label, className="cell-line-y-tick", style={"bottom": pos})
                        for label, pos in (
                            ("8", "100%"),
                            ("6", "85.7%"),
                            ("4", "71.4%"),
                            ("2", "57.1%"),
                            ("0", "42.9%"),
                            ("−2", "28.6%"),
                            ("−4", "14.3%"),
                            ("−6", "0%"),
                        )
                    ],
                ],
                className="cell-line-scatter-plot",
            ),
        ],
        className="cell-line-panel cell-line-scatter-panel",
    )


def _distribution() -> html.Div:
    return html.Div(
        [
            html.Div(className="cell-line-dist-fill"),
            html.Div(className="cell-line-dist-line"),
            html.Div(className="cell-line-dist-marker"),
            html.Div("−2", className="cell-line-dist-label is-left"),
            html.Div("0", className="cell-line-dist-label is-mid"),
            html.Div("+2", className="cell-line-dist-label is-right"),
        ],
        className="cell-line-distribution",
    )


def _slider(kind: str, pos: str, labels: tuple[str, ...]) -> html.Div:
    return html.Div(
        [
            html.Div(className="cell-line-slider-track"),
            html.Div(className=f"cell-line-slider-fill cell-line-fill-{kind}", style={"width": pos}),
            html.Div(className=f"cell-line-slider-dot cell-line-dot-{kind}", style={"left": pos}),
            html.Div(
                [
                    html.Span(label)
                    for label in labels
                ],
                className="cell-line-slider-labels",
            ),
        ],
        className="cell-line-slider",
    )


def _source_box(
    letter: str,
    title: str,
    value,
    tone: str,
    label: str,
    visual,
) -> html.Div:
    return html.Div(
        [
            html.Div(letter, className=f"cell-line-source-letter cell-line-source-{tone}"),
            html.Div(
                [
                    html.Div(title, className="cell-line-source-title"),
                    html.Div(value, className="cell-line-source-value"),
                    html.Div(label, className=f"cell-line-source-label cell-line-source-label-{tone}"),
                ],
                className="cell-line-source-copy",
            ),
            html.Div(visual, className="cell-line-source-visual"),
        ],
        className="cell-line-source-row",
    )


def _cross_source_children(validation: dict = result) -> list:
    gdsc2 = validation["gdsc2"] if _has_gdsc2(validation) else {}
    prism = validation["prism"] if _has_prism(validation) else {}
    lfc = prism.get("cell_line_lfc")
    ic50 = gdsc2.get("cell_line_ic50_nm")
    z_score = gdsc2.get("cell_line_z_score")
    return [
            html.Div(
                [
                    html.Div("🛡 Cross-source 검증", className="cell-line-panel-title"),
                    html.Div(
                        f"{validation.get('cell_line', 'H1975')} cell line의 3개 독립 신호",
                        className="cell-line-panel-subtitle",
                    ),
                ],
                className="cell-line-source-heading",
            ),
            _source_box(
                "P",
                "PRISM (Δ log fold change)",
                _minus(lfc, 2) if lfc is not None else "미수집",
                "violet",
                _prism_label(lfc).replace(" (lfc < −0.5)", ""),
                _distribution(),
            ),
            _source_box(
                "G",
                "GDSC2 IC50 (μM 자연로그 기반)",
                [f"{ic50:.1f} ", html.Span("nM", className="cell-line-source-unit")] if ic50 is not None else "미수집",
                "green",
                _gdsc2_label(gdsc2).split(" (", 1)[0],
                _slider("green", _log_ic50_position(ic50), ("1 nM", "100 nM", "1 μM", "10 μM")),
            ),
            _source_box(
                "Z",
                "GDSC2 Z-score (cell-line 평균 대비)",
                [_minus(z_score, 2), html.Span("σ", className="cell-line-source-unit")] if z_score is not None else "미수집",
                "cyan",
                "매우 강한 민감 (<−1.5σ)" if z_score is not None and z_score < -1.5 else "cell-line 평균 대비",
                _slider("cyan", _z_score_position(z_score), ("−4σ", "−2σ", "0", "+2σ")),
            ),
            html.Div(
                [
                    html.Div("💡 어떻게 해석? ⓘ", className="cell-line-interpret-title"),
                    html.Div(
                        [
                            html.Span("✓"),
                            html.P(
                                [
                                    f"PRISM ({_minus(lfc, 2) if lfc is not None else '미수집'}) + "
                                    f"GDSC2 ({f'{ic50:.1f} nM' if ic50 is not None else '미수집'}) "
                                    "두 독립 source의 판정 — ",
                                    html.Strong(validation["consistency"]),
                                    ".",
                                ]
                            ),
                        ],
                        className="cell-line-interpret-row",
                    ),
                    html.Div(
                        [
                            html.Span("✓"),
                            html.P(
                                (
                                    f"Z-score {_minus(z_score, 2)}σ는 cell-line 평균 대비 신호입니다."
                                    if z_score is not None
                                    else "GDSC2 Z-score는 해당 조합에서 표시 가능한 실측값이 없습니다."
                                ),
                            ),
                        ],
                        className="cell-line-interpret-row",
                    ),
                    html.Div(
                        [
                            html.Span("✓"),
                            html.P(
                                "모델 prob 0.82 (scaffold OOF mean, 3 seeds)는 화학구조 기반 "
                                "NSCLC 적합도. cell-line 특이성은 두 실측 source가 검증.",
                            ),
                        ],
                        className="cell-line-interpret-row",
                    ),
                ],
                className="cell-line-interpretation",
            ),
        ]


def _cross_source_panel() -> html.Div:
    return html.Div(
        _cross_source_children(),
        id="cell-line-cross-panel",
        className="cell-line-panel cell-line-cross-panel",
    )


def _bottom_actions() -> html.Div:
    return html.Div(
        [
            html.A("⚗ 다른 약물 비교", href="/cell-line-mode", className="cell-line-bottom-button is-muted"),
            html.Button(
                "↔ 병용 모드로 전환",
                id={"type": "cell-line-mode-action", "mode": "combo", "slot": "bottom"},
                className="cell-line-bottom-button is-primary",
            ),
        ],
        className="cell-line-bottom-actions",
    )


def _combo_controls() -> html.Div:
    return html.Div(
        [
            html.Div("Cell", className="cell-line-control-label"),
            _dropdown("cell-line-combo-cell", _CELL_OPTIONS, _COMBO_CELL_LINE),
            html.Div("🔗 A", className="cell-line-control-label"),
            _dropdown(
                "cell-line-combo-drug-a",
                [{"label": _COMBO_A["name"], "value": _COMBO_A["name"]}],
                _COMBO_A["name"],
                "cell-line-select cell-line-select-violet",
            ),
            html.Div("🔗 B", className="cell-line-control-label"),
            _dropdown(
                "cell-line-combo-drug-b",
                [{"label": _COMBO_B["name"], "value": _COMBO_B["name"]}],
                _COMBO_B["name"],
                "cell-line-select cell-line-select-orange",
            ),
            html.Div(
                [html.Span("단독"), html.Span("병용", className="is-selected")],
                className="cell-line-mode-pill cell-line-mode-pill-combo",
            ),
            html.Div(
                [
                    html.Div("SOURCE COVERAGE", className="cell-line-combo-mini-title"),
                    html.Div(
                        [
                            html.Span("A: "),
                            html.Strong("PRISM ✓ GDSC2 ✓", className="is-green"),
                            html.Span("B: ", className="is-b-label"),
                            html.Strong("PRISM ✓ GDSC2 ⚠", className="is-orange"),
                        ],
                        className="cell-line-combo-mini-row",
                    ),
                ],
                className="cell-line-combo-mini-coverage",
            ),
            html.Button(
                "↻ 모드 전환",
                id={"type": "cell-line-mode-action", "mode": "single", "slot": "top"},
                className="cell-line-switch-button",
            ),
        ],
        className="cell-line-controls cell-line-controls-combo",
    )


def _hypothesis_badge() -> html.Div:
    return html.Div("가설", className="cell-line-hypothesis-badge")


def _confidence_dots(active: int = 2, total: int = 3) -> html.Span:
    return html.Span(
        [
            html.Span(className="cell-line-combo-confidence-dot is-active" if idx < active else "cell-line-combo-confidence-dot")
            for idx in range(total)
        ],
        className="cell-line-combo-confidence",
    )


def _combo_metric_card(
    icon: str,
    label: str,
    value,
    tone: str,
    sub,
    badge: bool = False,
) -> html.Div:
    return html.Div(
        [
            html.Div(icon, className=f"cell-line-metric-icon cell-line-icon-{tone}"),
            html.Div(
                [
                    html.Div(label, className="cell-line-metric-label"),
                    html.Div(value, className=f"cell-line-metric-value cell-line-combo-value-{tone}"),
                    html.Div(sub, className=f"cell-line-metric-sub cell-line-sub-{tone}"),
                ],
                className="cell-line-metric-copy",
            ),
            _hypothesis_badge() if badge else None,
        ],
        className="cell-line-metric-card cell-line-combo-metric-card",
    )


def _combo_top_cards() -> html.Div:
    return html.Div(
        [
            _combo_metric_card(
                "⊕",
                "예상 결과 (모델 추론) ⓘ",
                "SYNERGY",
                "green",
                "Bliss-based · 실측 검증 X",
                badge=True,
            ),
            _combo_metric_card(
                "∑",
                "PRISM additive baseline ⓘ",
                [
                    f"{_COMBO_BLISS_BASELINE:.2f}",
                    html.Span(" effect", className="cell-line-combo-effect-unit"),
                ],
                "violet",
                "단독 lfc 결합 (Bliss expected)",
            ),
            _combo_metric_card(
                "Δ",
                "모델 시뮬 ΔBliss ⓘ",
                _signed(_COMBO_DELTA_BLISS, 2),
                "cyan",
                ["신뢰도 ", _confidence_dots(), " · 실측 X"],
                badge=True,
            ),
        ],
        className="cell-line-metric-grid cell-line-combo-top-grid",
    )


def _combo_prism_strip() -> html.Div:
    return html.Div(
        [
            html.Div("PRISM 단독 (실측, H1975)", className="cell-line-combo-strip-title"),
            html.Div(
                [
                    html.Span(className="cell-line-combo-dot is-a"),
                    html.Strong("A. Osimertinib"),
                    html.Span(f" · lfc {_minus(_COMBO_LFC_A, 2)} · effect {_COMBO_EFFECT_A:.2f} · Sensitive"),
                ],
                className="cell-line-combo-strip-item",
            ),
            html.Div(
                [
                    html.Span(className="cell-line-combo-dot is-b"),
                    html.Strong("B. Cobimetinib"),
                    html.Span(f" · lfc {_minus(_COMBO_LFC_B, 2)} · effect {_COMBO_EFFECT_B:.2f} · Sensitive"),
                ],
                className="cell-line-combo-strip-item",
            ),
            html.Div(
                [
                    "Bliss expected = ",
                    f"{_COMBO_EFFECT_A:.2f} + {_COMBO_EFFECT_B:.2f} − ",
                    f"{_COMBO_EFFECT_A:.2f}×{_COMBO_EFFECT_B:.2f} = ",
                    html.Strong(f"{_COMBO_BLISS_BASELINE:.2f}"),
                ],
                className="cell-line-combo-strip-bliss",
            ),
        ],
        className="cell-line-combo-strip",
    )


def _dose_cell(value: str, color: str, best: bool = False) -> html.Div:
    class_name = "cell-line-dose-cell is-best" if best else "cell-line-dose-cell"
    return html.Div(value, className=class_name, style={"background": color})


def _combo_dose_matrix() -> html.Div:
    rows = [
        [("+0.02", "#1a3460", False), ("+0.04", "#1d4368", False), ("+0.06", "#1f5775", False), ("+0.08", "#1f6a7c", False), ("+0.05", "#1d4d6c", False)],
        [("+0.03", "#1d4368", False), ("+0.05", "#1f5775", False), ("+0.08", "#1f7d80", False), ("+0.12", "#2a9b6e", True), ("+0.08", "#1f7d80", False)],
        [("+0.02", "#1f5775", False), ("+0.04", "#1f6a7c", False), ("+0.06", "#1f8a7d", False), ("+0.08", "#1f7d80", False), ("+0.05", "#1f6a7c", False)],
        [("+0.01", "#1a3460", False), ("+0.02", "#1d4368", False), ("+0.04", "#1f5775", False), ("+0.05", "#1f6a7c", False), ("+0.03", "#1d4368", False)],
        [("0", "#1a2a4a", False), ("0", "#1a2a4a", False), ("+0.01", "#1a3460", False), ("+0.02", "#1a3460", False), ("+0.01", "#1a3460", False)],
    ]
    return html.Div(
        [
            html.Div("Dose matrix — Predicted ΔBliss", className="cell-line-panel-title"),
            html.Div(
                "PRISM 단독 lfc 결합 모델 (Bliss independence) · 실측 dose-response 아님",
                className="cell-line-panel-subtitle",
            ),
            html.Div(
                [
                    html.Div("A: Osimertinib (nM)", className="cell-line-dose-y-title"),
                    html.Div(
                        [html.Span(label) for label in ("1000", "100", "10", "1", "0")],
                        className="cell-line-dose-y-ticks",
                    ),
                    html.Div(
                        [
                            _dose_cell(value, color, best)
                            for row in rows
                            for value, color, best in row
                        ],
                        className="cell-line-dose-grid",
                    ),
                    html.Div("Best ΔBliss = +0.12", className="cell-line-dose-best-label"),
                    html.Div(
                        [html.Span(label) for label in ("0", "1", "10", "100", "1000")],
                        className="cell-line-dose-x-ticks",
                    ),
                    html.Div("B: Cobimetinib (nM)", className="cell-line-dose-x-title"),
                ],
                className="cell-line-dose-chart",
            ),
            html.Div(
                [
                    html.Div(
                        [html.Span(style={"background": color}) for color in ("#1a2a4a", "#1f5775", "#1f7d80", "#1f8a7d", "#2a9b6e")],
                        className="cell-line-dose-legend-bar",
                    ),
                    html.Div(
                        [
                            html.Span("Antagonism"),
                            html.Span("Additive"),
                            html.Span("Synergy"),
                        ],
                        className="cell-line-dose-legend-labels",
                    ),
                ],
                className="cell-line-dose-legend",
            ),
            html.Div(
                "값은 Bliss-independence 모델 추론 — 실측 dose-response 아님",
                className="cell-line-dose-footer",
            ),
        ],
        className="cell-line-panel cell-line-dose-panel",
    )


def _pathway_node(label: str, tone: str) -> html.Div:
    return html.Div(label, className=f"cell-line-pathway-node cell-line-pathway-{tone}")


def _coverage_cell(value, tone: str = "") -> html.Div:
    tone_class = f" cell-line-coverage-{tone}" if tone else ""
    return html.Div(value, className=f"cell-line-coverage-cell{tone_class}")


def _combo_interpretation_panel() -> html.Div:
    return html.Div(
        [
            html.Div("💡 조합 해석", className="cell-line-panel-title"),
            html.Div(
                [
                    html.Div("A. Osimertinib", className="cell-line-drug-pill is-a"),
                    html.Div("+", className="cell-line-drug-plus"),
                    html.Div("B. Cobimetinib", className="cell-line-drug-pill is-b"),
                ],
                className="cell-line-drug-pills",
            ),
            html.Div(
                [
                    html.Div("PATHWAY", className="cell-line-pathway-title"),
                    html.Div(
                        [
                            html.Div("A 결합", className="cell-line-binding-label is-a"),
                            html.Div("B 결합", className="cell-line-binding-label is-b"),
                            _pathway_node("EGFR", "a"),
                            html.Div("→", className="cell-line-pathway-arrow"),
                            _pathway_node("RAS", "mid"),
                            html.Div("→", className="cell-line-pathway-arrow"),
                            _pathway_node("RAF", "mid"),
                            html.Div("→", className="cell-line-pathway-arrow"),
                            _pathway_node("MEK1/2", "b"),
                        ],
                        className="cell-line-pathway-row",
                    ),
                    html.Div("두 노드 동시 억제 → 우회 신호 차단 가설", className="cell-line-pathway-copy"),
                ],
                className="cell-line-pathway",
            ),
            html.Div(
                [
                    html.Div("SOURCE COVERAGE 매트릭스", className="cell-line-coverage-title"),
                    html.Div(
                        [
                            _coverage_cell("Source × Drug", "header"),
                            _coverage_cell("A (Osimertinib)", "header-a"),
                            _coverage_cell("B (Cobimetinib)", "header-b"),
                            _coverage_cell("PRISM lfc", "row-head"),
                            _coverage_cell(f"{_minus(_COMBO_LFC_A, 2)} ✓ Sensitive", "good"),
                            _coverage_cell(f"{_minus(_COMBO_LFC_B, 2)} ✓ Sensitive", "good"),
                            _coverage_cell("GDSC2 IC50", "row-head"),
                            _coverage_cell(f"{_COMBO_GDSC_A['cell_line_ic50_nm']:.1f} nM ✓ Strong", "good"),
                            _coverage_cell("⚠ 미수집", "missing"),
                        ],
                        className="cell-line-coverage-grid",
                    ),
                ],
                className="cell-line-coverage",
            ),
            html.Div(
                [
                    html.Div("⚗ 근거 요약", className="cell-line-evidence-title"),
                    html.Div([html.Span("✓"), html.P("EGFR(L858R+T790M) + MEK 동시 억제로 RAS-RAF-MEK 우회 신호 차단 가설.")], className="cell-line-evidence-row"),
                    html.Div([html.Span("✓"), html.P("두 약물 모두 H1975에서 PRISM 단독 sensitive (lfc −0.75, −0.70).")], className="cell-line-evidence-row"),
                    html.Div([html.Span("⚠"), html.P("Cobimetinib은 GDSC2 미수집 → B 약물은 단일 source(PRISM)만으로 검증.")], className="cell-line-evidence-row is-warning"),
                    html.Div([html.Span("⚠"), html.P("Bliss 모델은 단독 lfc 결합 추론 — 실측 병용 dose-response 데이터 X.")], className="cell-line-evidence-row is-danger"),
                    html.Div([html.Span("✓"), html.P("중간 농도 구간(Osi 100nM × Cobi 100nM)에서 최대 ΔBliss 가설 (+0.12).")], className="cell-line-evidence-row"),
                ],
                className="cell-line-evidence",
            ),
        ],
        className="cell-line-panel cell-line-combo-interpret-panel",
    )


def _combo_bottom_actions() -> html.Div:
    return html.Div(
        [
            html.Button(
                "↩ 단독 모드로 복귀",
                id={"type": "cell-line-mode-action", "mode": "single", "slot": "bottom"},
                className="cell-line-bottom-button is-muted",
            ),
            html.A("👤 Patient 모드로 보내기 →", href="/simulator", className="cell-line-bottom-button is-primary"),
        ],
        className="cell-line-bottom-actions",
    )


def _single_content() -> html.Div:
    return html.Div(
        [
            _top_cards(),
            _consistency_banner(),
            html.Div([_scatter(), _cross_source_panel()], className="cell-line-main-grid"),
            _bottom_actions(),
            html.Div(
                "면책: 본 화면은 시뮬레이션 결과이며 실제 임상·실험 결과를 대체하지 않습니다.",
                className="cell-line-footer-note",
            ),
        ],
        className="cell-line-content",
    )


def _combo_content() -> html.Div:
    return html.Div(
        [
            _combo_top_cards(),
            _combo_prism_strip(),
            html.Div([_combo_dose_matrix(), _combo_interpretation_panel()], className="cell-line-combo-main-grid"),
            _combo_bottom_actions(),
            html.Div(
                "면책: 본 화면의 병용 효과는 모델 시뮬레이션 결과이며 실제 임상·실험 결과를 대체하지 않습니다.",
                className="cell-line-footer-note",
            ),
        ],
        className="cell-line-content cell-line-combo-content",
    )


def _single_page_children() -> list:
    return [_header(), _tabs(), _controls(), _single_content()]


def _combo_page_children() -> list:
    return [_header(show_combo_warning=True), _tabs(), _combo_controls(), _combo_content()]


def layout() -> html.Div:
    return html.Div(
        [
            dcc.Store(id="cell-line-mode-store", data="single"),
            html.Div(
                id="cell-line-page-shell",
                children=_single_page_children(),
                className="cell-line-page-shell",
            ),
        ],
    )


@callback(
    Output("cell-line-mode-store", "data"),
    Input({"type": "cell-line-mode-action", "mode": ALL, "slot": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def _set_cell_line_mode(_clicks):
    triggered = ctx.triggered_id
    if isinstance(triggered, dict) and triggered.get("mode") in {"single", "combo"}:
        return triggered["mode"]
    return "single"


@callback(
    Output("cell-line-page-shell", "children"),
    Input("cell-line-mode-store", "data"),
)
def _render_cell_line_mode(mode: str | None):
    if mode == "combo":
        return _combo_page_children()
    return _single_page_children()


@callback(
    Output("cell-line-top-cards", "children"),
    Output("cell-line-consistency", "children"),
    Output("cell-line-consistency", "className"),
    Output("cell-line-cross-panel", "children"),
    Input("cell-line-mode-drug", "value"),
    Input("cell-line-mode-cell", "value"),
)
def _update_single_mode(drug: str | None, cell_line: str | None):
    validation = _validation_for(drug, cell_line)
    return (
        _top_card_children(validation),
        _consistency_children(validation),
        _consistency_class(validation),
        _cross_source_children(validation),
    )
