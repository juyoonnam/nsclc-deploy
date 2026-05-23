"""
nsclc_ui.data.cell_line.callbacks

가상세포실험 탭 callbacks.

cell_line.py에서 한 줄 import만 추가하면 활성화:
    from nsclc_ui.data.cell_line.callbacks import *  # noqa: F401

3 callbacks:
1. _populate_options       : 페이지 로드 시 dropdown options + default values
2. _update_response        : (cell, drug, dose) → metric cards + figure + 4-source
3. _update_concordance     : (cell, drug) → concordance badge

Component IDs (cell_line.py와 sync):
- 입력: cl-cell-input, cl-drug-input, cl-dose-input
- 출력 metrics: cl-metric-pred, cl-metric-pred-hint, cl-metric-prism,
              cl-metric-ec50, cl-metric-ec50-hint
- 출력 viz: cl-dose-response-chart, cl-4source-rows, cl-concordance
"""

import dash
from dash import callback, Input, Output, State, html, dcc, no_update

from . import (
    get_cell_options, get_drug_options,
    get_cell_drug_response, get_dose_response_figure, get_concordance,
)


# Source code styling (color, icon)
_SOURCE_BADGE_CLASS = {
    "P": "source-badge source-badge-prism",      # PRISM (cyan)
    "A": "source-badge source-badge-model",      # A model (purple)
    "G": "source-badge source-badge-gdsc",       # GDSC2 (cyan)
    "Z": "source-badge source-badge-zscore",     # Z-score (amber)
}

_INTERP_COLOR = {
    "sensitive": "var(--accent-cyan)",
    "intermediate": "var(--accent-amber)",
    "resistant": "var(--accent-orange, #D85A30)",
}


# ── Callback 2: (cell, drug, dose) → metrics + dose-response figure ────────────

@callback(
    Output("cl-metric-pred", "children"),
    Output("cl-metric-pred-hint", "children"),
    Output("cl-metric-prism", "children"),
    Output("cl-metric-ec50", "children"),
    Output("cl-metric-ec50-hint", "children"),
    Output("cl-dose-response-chart", "children"),
    Input("cl-cell-input", "value"),
    Input("cl-drug-input", "value"),
    Input("cl-dose-input", "value"),
)
def _update_response(cell_id, drug_id, dose_um):
    """입력 변경 시 메트릭 + dose-response curve 업데이트."""
    if not cell_id or not drug_id:
        empty_fig = dcc.Graph(figure={"data": [], "layout": {"height": 280}}, config={"displayModeBar": False})
        return "—", "입력 후 예측 표시", "—", "—", "데이터 없음", empty_fig

    resp = get_cell_drug_response(cell_id, drug_id, dose=dose_um)

    if resp.get("error"):
        empty_fig = dcc.Graph(figure={"data": [], "layout": {"height": 280}}, config={"displayModeBar": False})
        return ("—", resp["error"], "—", "—", "—", empty_fig)

    # A 모델 예측
    pred_lfc = resp.get("a_pred_lfc")
    if pred_lfc is not None:
        pred_str = f"{pred_lfc:+.3f}"
        pred_hint = f"fold {resp.get('fold', '?')} OOF · scaffold-split"
    else:
        pred_str = "—"
        pred_hint = "예측 정보 없음"

    # PRISM 실측
    prism_lfc = resp.get("prism_lfc_obs")
    prism_dose = resp.get("prism_dose")
    if prism_lfc is not None:
        prism_str = f"{prism_lfc:+.3f}"
    else:
        prism_str = "—"

    # EC50: GDSC2 measured 우선 → PRISM Hill simulated fallback
    conc = get_concordance(cell_id, drug_id)
    gdsc2_src = next((s for s in conc["sources"] if s["code"] == "G"), None)
    if gdsc2_src and gdsc2_src["available"]:
        ec50_str = gdsc2_src["value"].replace("IC50 ", "")
        ec50_hint = "GDSC2 measured · cross-source"
    elif prism_lfc is not None and prism_dose:
        # Hill simulated EC50 (loader._estimate_ec50_from_lfc과 동일 로직)
        from .dose_response import _estimate_ec50_from_lfc
        ec50_um = _estimate_ec50_from_lfc(prism_lfc, prism_dose)
        if ec50_um and ec50_um < 100:
            if ec50_um < 1.0:
                ec50_str = f"{ec50_um * 1000:.0f} nM"
            else:
                ec50_str = f"{ec50_um:.2f} μM"
            ec50_hint = "PRISM 1-point Hill simulated"
        else:
            ec50_str = "—"
            ec50_hint = "데이터 부족"
    else:
        ec50_str = "—"
        ec50_hint = "데이터 없음"

    # Dose-response figure
    fig_dict = get_dose_response_figure(cell_id, drug_id, current_dose_um=dose_um)
    fig = dcc.Graph(
        figure=fig_dict,
        config={"displayModeBar": False, "responsive": True},
        style={"height": "280px"},
    )

    return pred_str, pred_hint, prism_str, ec50_str, ec50_hint, fig


# ── Callback 3: (cell, drug) → 4-source rows + concordance badge ──────────────

@callback(
    Output("cl-4source-rows", "children"),
    Output("cl-concordance", "children"),
    Output("cl-concordance", "className"),
    Input("cl-cell-input", "value"),
    Input("cl-drug-input", "value"),
)
def _update_concordance(cell_id, drug_id):
    """4-source rows + overall concordance badge."""
    if not cell_id or not drug_id:
        return [], "입력 대기", "concordance-badge concordance-partial"

    conc = get_concordance(cell_id, drug_id)

    rows = []
    for s in conc["sources"]:
        badge_letter = s["code"]
        badge_class = _SOURCE_BADGE_CLASS.get(badge_letter, "source-badge")
        label = s["label"]
        value = s["value"]
        interp = s["interpretation"]
        color = _INTERP_COLOR.get(interp, "var(--nsclc-text-secondary)") if interp else "var(--nsclc-text-tertiary)"

        rows.append(
            html.Div(
                [
                    html.Span(
                        [
                            html.Span(badge_letter, className=badge_class),
                            f" {label}",
                        ],
                    ),
                    html.Span(value, style={"color": color, "fontVariantNumeric": "tabular-nums"}),
                ],
                style={
                    "display": "flex",
                    "justifyContent": "space-between",
                    "alignItems": "center",
                    "fontSize": "11px",
                    "opacity": "1" if s["available"] else "0.5",
                },
            )
        )

    # Concordance badge
    overall = conc["overall"]
    note = conc["note"]
    if overall.startswith("concordant_"):
        verdict = overall.replace("concordant_", "")
        verdict_kr = {"sensitive": "Sensitive", "intermediate": "Intermediate", "resistant": "Resistant"}.get(verdict, verdict)
        badge_text = f"✓ Concordant — {verdict_kr} ({note})"
        badge_class = "concordance-badge concordance-concordant"
    elif overall == "partial":
        badge_text = f"◐ Partial — {note}"
        badge_class = "concordance-badge concordance-partial"
    elif overall == "discordant":
        badge_text = f"⚠ Discordant — {note}"
        badge_class = "concordance-badge concordance-discordant"
    else:  # insufficient
        badge_text = f"— {note}"
        badge_class = "concordance-badge concordance-partial"

    return rows, badge_text, badge_class
