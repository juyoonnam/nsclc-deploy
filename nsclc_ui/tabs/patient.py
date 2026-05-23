"""
가상투약 — Patient mutation assembly → drug response prediction.

Mockup v2.2 기반 full UI. 모드 토글 + 조립 입력 + Mutation chips + Mini Sankey placeholder.
"""
from __future__ import annotations

import dash
from dash import html, dcc, callback, Input, Output, State, ctx, no_update, ALL

from nsclc_ui.data.cell_line import get_drug_options

dash.register_page(
    __name__,
    path="/patient",
    name="가상투약",
    title="NSCLC Insight Engine — 가상투약",
    order=4,
)


# ── Constants ─────────────────────────────────────────────────────────────────

ACTIONABLE_GENES = [
    "EGFR", "KRAS", "ALK", "ROS1", "BRAF", "MET", "RET", "ERBB2",
    "NTRK1", "NTRK2", "NTRK3", "MAP2K1", "PIK3CA", "TP53",
    "STK11", "KEAP1", "RB1", "CDKN2A", "NF1", "PTEN",
]

_PLACEHOLDER_DRUGS = [
    {"label": "Osimertinib", "value": "Osimertinib"},
    {"label": "Erlotinib", "value": "Erlotinib"},
    {"label": "Afatinib", "value": "Afatinib"},
    {"label": "Crizotinib", "value": "Crizotinib"},
]

_PLACEHOLDER_PATIENTS = [
    {"label": "TCGA-05-4395-01 · LUAD · EGFR+TP53", "value": "TCGA-05-4395-01"},
    {"label": "TCGA-38-4625-01 · LUAD · KRAS+STK11", "value": "TCGA-38-4625-01"},
    {"label": "TCGA-44-2655-01 · LUSC · TP53+CDKN2A", "value": "TCGA-44-2655-01"},
]


# ── Components ────────────────────────────────────────────────────────────────


def _header():
    return html.Div(
        [
            html.H2(
                "🩺 가상투약",
                style={"margin": "0", "fontSize": "18px", "fontWeight": "500"},
            ),
            html.Span(
                "⚠ 가설 생성용 · 진료 추천 아님",
                className="hypothesis-badge",
            ),
        ],
        style={
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "space-between",
            "marginBottom": "14px",
        },
    )


def _mode_toggle():
    return html.Div(
        [
            html.Button(
                "👥 실제 환자 (TCGA 942명)",
                id="pt-mode-real",
                n_clicks=0,
                className="",
            ),
            html.Button(
                "🧩 환자 조립 시뮬 ✓",
                id="pt-mode-compose",
                n_clicks=0,
                className="active",
            ),
        ],
        className="mode-toggle",
    )


def _input_compose():
    """조립 모드 입력 박스."""
    # Initial mutations — callback이 chip 영역 채움
    initial_selected = ["EGFR", "TP53"]
    selected_chips = []
    add_chips = []

    return html.Div(
        [
            html.Div("→ 환자 변이 + 약물 조립", className="input-label"),
            # Cancer + Drug row
            html.Div(
                [
                    html.Div(
                        [
                            html.Label("Cancer subtype", style={
                                "fontSize": "11px", "color": "var(--nsclc-text-secondary)",
                                "display": "block", "marginBottom": "4px",
                            }),
                            dcc.Dropdown(
                                id="pt-cancer-input",
                                options=[
                                    {"label": "LUAD (Adenocarcinoma)", "value": "LUAD"},
                                    {"label": "LUSC (Squamous)", "value": "LUSC"},
                                    {"label": "전체 NSCLC", "value": "NSCLC"},
                                ],
                                value="LUAD",
                                clearable=False,
                                className="pt-dropdown",
                            ),
                        ],
                    ),
                    html.Div(
                        [
                            html.Label("Drug 선택", style={
                                "fontSize": "11px", "color": "var(--nsclc-text-secondary)",
                                "display": "block", "marginBottom": "4px",
                            }),
                            dcc.Dropdown(
                                id="pt-drug-input",
                                options=get_drug_options(),
                                value="BRD-K42805893-001-04-9",  # osimertinib default
                                searchable=True,
                                clearable=False,
                                placeholder="약물 검색...",
                                className="pt-dropdown",
                            ),
                        ],
                    ),
                ],
                style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "12px", "marginBottom": "12px"},
            ),
            # Mutation chips
            html.Div(
                [
                    html.Label(
                        "Mutation 조립 (multi-select · actionable 20 genes)",
                        style={
                            "fontSize": "11px", "color": "var(--nsclc-text-secondary)",
                            "display": "block", "marginBottom": "6px",
                        },
                    ),
                    html.Div(
                        selected_chips + add_chips,
                        id="pt-mutation-chips",
                        style={"display": "flex", "flexWrap": "wrap", "gap": "6px"},
                    ),
                ],
            ),
            # Hidden store for selected mutations
            dcc.Store(id="pt-mutations-store", data=initial_selected),
        ],
        id="pt-input-compose",
        className="input-box-purple",
    )


def _input_real():
    """실제 환자 모드 입력 박스."""
    return html.Div(
        [
            html.Div("→ 실제 환자 선택", className="input-label"),
            html.Div(
                [
                    html.Label("Patient (TCGA 942명)", style={
                        "fontSize": "11px", "color": "var(--nsclc-text-secondary)",
                        "display": "block", "marginBottom": "4px",
                    }),
                    dcc.Dropdown(
                        id="pt-patient-selector",
                        options=_PLACEHOLDER_PATIENTS,
                        value=None,
                        searchable=True,
                        placeholder="TCGA-XX-XXXX-01 검색...",
                        className="pt-dropdown",
                    ),
                    html.Div(
                        "Source: TCGA-LUAD/LUSC PanCancer Atlas 2018 (cBioPortal)",
                        style={"fontSize": "10px", "color": "var(--nsclc-text-tertiary)", "marginTop": "6px"},
                    ),
                ],
            ),
        ],
        id="pt-input-real",
        className="input-box-purple",
        style={"display": "none"},
    )


def _metrics_row():
    return html.Div(
        [
            # 예측 응답
            html.Div(
                [
                    html.Span("B 모델", className="model-badge"),
                    html.Div("예측 응답 (Multi-modal)", className="metric-label"),
                    html.Div("—", id="pt-metric-score", className="metric-value", style={"color": "var(--accent-purple)"}),
                    html.Div("데이터 연결 대기", id="pt-metric-score-hint", className="metric-hint", style={"color": "var(--accent-cyan)"}),
                ],
                className="metric-card",
            ),
            # 유사 TCGA 환자
            html.Div(
                [
                    html.Div("유사 TCGA 환자", className="metric-label"),
                    html.Div("—", id="pt-metric-similar", className="metric-value"),
                    html.Div("cosine sim > 0.85", className="metric-hint"),
                ],
                className="metric-card",
            ),
            # 유사 cell line
            html.Div(
                [
                    html.Div("유사 cell line", className="metric-label"),
                    html.Div("—", id="pt-metric-cells", className="metric-value", style={"fontSize": "15px"}),
                    html.Div("top-3 phenotype match", className="metric-hint"),
                ],
                className="metric-card",
            ),
        ],
        className="metrics-row",
    )


def _mini_sankey_placeholder():
    """Mini Sankey placeholder (변이→경로→약물)."""
    svg = (
        '<svg viewBox="0 0 320 130" style="width:100%;height:130px;">'
        '<rect x="10" y="20" width="60" height="22" rx="3" fill="rgba(133,183,235,0.18)" stroke="#85B7EB" stroke-width="0.5"/>'
        '<text x="40" y="34" font-size="10" text-anchor="middle" fill="#85B7EB">EGFR</text>'
        '<rect x="10" y="80" width="60" height="22" rx="3" fill="rgba(240,153,123,0.18)" stroke="#F0997B" stroke-width="0.5"/>'
        '<text x="40" y="94" font-size="10" text-anchor="middle" fill="#F0997B">TP53</text>'
        '<rect x="125" y="15" width="80" height="20" rx="3" fill="rgba(93,202,165,0.18)" stroke="#5DCAA5" stroke-width="0.5"/>'
        '<text x="165" y="29" font-size="9" text-anchor="middle" fill="#5DCAA5">EGFR signaling</text>'
        '<rect x="125" y="55" width="80" height="20" rx="3" fill="rgba(240,153,123,0.18)" stroke="#F0997B" stroke-width="0.5"/>'
        '<text x="165" y="69" font-size="9" text-anchor="middle" fill="#F0997B">Apoptosis</text>'
        '<rect x="125" y="90" width="80" height="20" rx="3" fill="rgba(240,153,123,0.18)" stroke="#F0997B" stroke-width="0.5"/>'
        '<text x="165" y="104" font-size="9" text-anchor="middle" fill="#F0997B">Cell cycle</text>'
        '<rect x="245" y="20" width="65" height="20" rx="3" fill="rgba(127,119,221,0.18)" stroke="#7F77DD" stroke-width="0.5"/>'
        '<text x="277" y="34" font-size="10" text-anchor="middle" fill="#7F77DD">Osimertinib</text>'
        '<rect x="245" y="55" width="65" height="20" rx="3" fill="rgba(127,119,221,0.18)" stroke="#7F77DD" stroke-width="0.5"/>'
        '<text x="277" y="69" font-size="9" text-anchor="middle" fill="#7F77DD">Afatinib</text>'
        '<rect x="245" y="90" width="65" height="20" rx="3" fill="rgba(58,68,89,0.4)" stroke="#3a4459" stroke-width="0.5"/>'
        '<text x="277" y="104" font-size="9" text-anchor="middle" fill="#a0a8b8">Erlotinib</text>'
        '<path d="M 70 31 Q 95 28, 125 25" stroke="#1D9E75" stroke-width="2.5" fill="none" opacity="0.8"/>'
        '<path d="M 70 91 Q 95 75, 125 65" stroke="#D85A30" stroke-width="1.5" fill="none" stroke-dasharray="3,2" opacity="0.7"/>'
        '<path d="M 70 91 Q 95 98, 125 100" stroke="#D85A30" stroke-width="1.5" fill="none" stroke-dasharray="3,2" opacity="0.7"/>'
        '<path d="M 205 25 Q 225 25, 245 30" stroke="#1D9E75" stroke-width="2.5" fill="none" opacity="0.8"/>'
        '<path d="M 205 25 Q 225 35, 245 65" stroke="#7F77DD" stroke-width="1" fill="none" opacity="0.5"/>'
        '<path d="M 205 25 Q 225 55, 245 100" stroke="#888780" stroke-width="0.8" fill="none" stroke-dasharray="2,2" opacity="0.4"/>'
        '</svg>'
    )
    return html.Div(
        [
            html.Div("🛣 변이 → 경로 → 약물 연결", style={"fontSize": "12px", "fontWeight": "500", "marginBottom": "8px"}),
            html.Div(html.Iframe(srcDoc=svg, style={"width":"100%","height":"100%","border":"none","background":"transparent"}), id="pt-sankey"),
        ],
        className="viz-panel",
    )


def _similar_patients_table():
    """유사 환자 실제 치료 분포 테이블 placeholder."""
    return html.Div(
        [
            html.Div("📜 유사 환자 실제 치료", style={"fontSize": "12px", "fontWeight": "500", "marginBottom": "10px"}),
            html.Table(
                [
                    html.Tr([
                        html.Td("치료", style={"padding": "5px 0", "color": "var(--nsclc-text-secondary)"}),
                        html.Td("n", style={"textAlign": "right", "padding": "5px 0", "color": "var(--nsclc-text-secondary)"}),
                    ], style={"borderBottom": "0.5px solid var(--nsclc-border)"}),
                    html.Tr([
                        html.Td(html.B("Osimertinib"), style={"padding": "5px 0", "color": "var(--accent-cyan)", "fontWeight": "500"}),
                        html.Td("— ", style={"textAlign": "right", "padding": "5px 0", "color": "var(--accent-cyan)", "fontWeight": "500"}),
                    ]),
                    html.Tr([
                        html.Td("Erlotinib", style={"padding": "5px 0"}),
                        html.Td("—", style={"textAlign": "right", "padding": "5px 0"}),
                    ]),
                    html.Tr([
                        html.Td("Afatinib", style={"padding": "5px 0"}),
                        html.Td("—", style={"textAlign": "right", "padding": "5px 0"}),
                    ]),
                ],
                id="pt-treatment-table",
                style={"width": "100%", "fontSize": "11px"},
            ),
            html.Div(
                "데이터 연결 대기 중",
                id="pt-concordance",
                className="concordance-badge concordance-partial",
            ),
        ],
        className="viz-panel",
    )


# ── Layout ────────────────────────────────────────────────────────────────────


def _build_layout(**kwargs):
    return html.Div(
        [
            dcc.Store(id="pt-mode-store", data="compose"),
            _header(),
            _mode_toggle(),
            html.Div(
                [_input_compose(), _input_real()],
                id="pt-input-area",
            ),
            _metrics_row(),
            html.Div(
                [_mini_sankey_placeholder(), _similar_patients_table()],
                style={"display": "grid", "gridTemplateColumns": "1.2fr 1fr", "gap": "12px"},
            ),
        ],
        style={
            "padding": "20px",
            "background": "var(--nsclc-bg-secondary)",
            "borderRadius": "12px",
        },
    )


# Module-level layout variable (Dash Pages requires this)
# Activate callbacks (must be after Dash app context)
from nsclc_ui.data.patient import callbacks as _pt_callbacks  # noqa: F401

layout = _build_layout()


# ── Callbacks ─────────────────────────────────────────────────────────────────


@callback(
    Output("pt-input-compose", "style"),
    Output("pt-input-real", "style"),
    Output("pt-mode-compose", "className"),
    Output("pt-mode-real", "className"),
    Output("pt-mode-store", "data"),
    Input("pt-mode-compose", "n_clicks"),
    Input("pt-mode-real", "n_clicks"),
    State("pt-mode-store", "data"),
    prevent_initial_call=True,
)
def _toggle_mode(_compose_clicks, _real_clicks, current_mode):
    """모드 토글: 조립 ↔ 실제 환자."""
    triggered = ctx.triggered_id
    if triggered == "pt-mode-compose":
        return {"display": "block"}, {"display": "none"}, "active", "", "compose"
    elif triggered == "pt-mode-real":
        return {"display": "none"}, {"display": "block"}, "", "active", "real"
    return no_update, no_update, no_update, no_update, no_update
