"""
가상세포실험 — Cell-line × Drug × Dose response prediction.

Mockup v2.2 기반 full UI. 데이터 레이어 연결 전 placeholder 값 사용.
"""
from __future__ import annotations

import dash
from dash import html, dcc, callback, Input, Output, State, no_update

from nsclc_ui.data.cell_line import get_cell_options, get_drug_options

dash.register_page(
    __name__,
    path="/cell-line",
    name="가상세포실험",
    title="NSCLC Insight Engine — 가상세포실험",
    order=3,
)


# ── Placeholder data (Claude data layer 연결 전) ──────────────────────────────

_PLACEHOLDER_CELLS = [
    {"label": "NCIH1975 — EGFR L858R+T790M", "value": "NCIH1975_LUNG"},
    {"label": "HCC827 — EGFR del19", "value": "HCC827_LUNG"},
    {"label": "A549 — KRAS G12S", "value": "A549_LUNG"},
]

_PLACEHOLDER_DRUGS = [
    {"label": "Osimertinib", "value": "BRD-K00003"},
    {"label": "Erlotinib", "value": "BRD-K00001"},
    {"label": "Crizotinib", "value": "BRD-K00002"},
]


# ── Components ────────────────────────────────────────────────────────────────


def _header():
    return html.Div(
        [
            html.H2(
                "🧪 가상세포실험",
                style={"margin": "0", "fontSize": "18px", "fontWeight": "500"},
            ),
            html.Span(
                "98 cells · 4,686 cmpd · 8 dose points",
                style={"fontSize": "11px", "color": "var(--nsclc-text-secondary)"},
            ),
        ],
        style={
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "space-between",
            "marginBottom": "16px",
        },
    )


def _input_box():
    return html.Div(
        [
            html.Div(
                "→ 입력",
                className="input-label",
            ),
            html.Div(
                [
                    # Cell line
                    html.Div(
                        [
                            html.Label("Cell line (98 NSCLC)", style={
                                "fontSize": "11px", "color": "var(--nsclc-text-secondary)",
                                "display": "block", "marginBottom": "4px",
                            }),
                            dcc.Dropdown(
                                id="cl-cell-input",
                                options=get_cell_options(),
                                value="ACH-000587",  # NCIH1975 default
                                searchable=True,
                                placeholder="세포주 선택...",
                                className="cl-dropdown",
                            ),
                        ],
                    ),
                    # Drug
                    html.Div(
                        [
                            html.Label("Drug (4,686 cmpd)", style={
                                "fontSize": "11px", "color": "var(--nsclc-text-secondary)",
                                "display": "block", "marginBottom": "4px",
                            }),
                            dcc.Dropdown(
                                id="cl-drug-input",
                                options=get_drug_options(),
                                value="BRD-K42805893-001-04-9",  # osimertinib default
                                searchable=True,
                                placeholder="약물 선택...",
                                className="cl-dropdown",
                            ),
                        ],
                    ),
                    # Dose
                    html.Div(
                        [
                            html.Label("Dose (μM)", style={
                                "fontSize": "11px", "color": "var(--nsclc-text-secondary)",
                                "display": "block", "marginBottom": "4px",
                            }),
                            dcc.Input(
                                id="cl-dose-input",
                                type="number",
                                value=0.04,
                                min=0.001,
                                max=10,
                                step=0.01,
                                style={
                                    "width": "100%",
                                    "padding": "8px",
                                    "background": "var(--nsclc-bg-elevated)",
                                    "color": "var(--nsclc-text-primary)",
                                    "border": "0.5px solid var(--nsclc-border)",
                                    "borderRadius": "6px",
                                    "fontSize": "13px",
                                },
                            ),
                        ],
                    ),
                ],
                style={
                    "display": "grid",
                    "gridTemplateColumns": "1.2fr 1fr 1fr",
                    "gap": "12px",
                },
            ),
        ],
        className="input-box-purple",
    )


def _metrics_row():
    return html.Div(
        [
            # 예측 lfc
            html.Div(
                [
                    html.Span("A 모델", className="model-badge"),
                    html.Div("예측 lfc (현재 농도)", className="metric-label"),
                    html.Div(
                        "—",
                        id="cl-metric-pred",
                        className="metric-value",
                        style={"color": "var(--accent-purple)"},
                    ),
                    html.Div(
                        "입력 후 예측 표시",
                        id="cl-metric-pred-hint",
                        className="metric-hint",
                        style={"color": "var(--accent-cyan)"},
                    ),
                ],
                className="metric-card",
            ),
            # PRISM 실측
            html.Div(
                [
                    html.Div("PRISM lfc (실측)", className="metric-label"),
                    html.Div(
                        "—",
                        id="cl-metric-prism",
                        className="metric-value",
                    ),
                    html.Div(
                        "primary screen · 단일 농도",
                        className="metric-hint",
                    ),
                ],
                className="metric-card",
            ),
            # 추천 농도
            html.Div(
                [
                    html.Div("추천 농도 (EC50)", className="metric-label"),
                    html.Div(
                        "—",
                        id="cl-metric-ec50",
                        className="metric-value",
                    ),
                    html.Div(
                        "데이터 레이어 연결 대기",
                        id="cl-metric-ec50-hint",
                        className="metric-hint",
                        style={"color": "var(--accent-cyan)"},
                    ),
                ],
                className="metric-card",
            ),
        ],
        className="metrics-row",
    )


def _dose_response_placeholder():
    """Dose-response curve placeholder (Plotly 연결 전)."""
    svg = (
        '<svg viewBox="0 0 320 150" style="width:100%;height:150px;">'
        '<line x1="35" y1="125" x2="305" y2="125" stroke="#3a4459" stroke-width="0.5"/>'
        '<line x1="35" y1="15" x2="35" y2="125" stroke="#3a4459" stroke-width="0.5"/>'
        '<text x="35" y="140" font-size="9" fill="#6b7689" text-anchor="middle">1 nM</text>'
        '<text x="115" y="140" font-size="9" fill="#6b7689" text-anchor="middle">10 nM</text>'
        '<text x="195" y="140" font-size="9" fill="#6b7689" text-anchor="middle">100 nM</text>'
        '<text x="275" y="140" font-size="9" fill="#6b7689" text-anchor="middle">1 μM</text>'
        '<text x="28" y="19" font-size="9" fill="#6b7689" text-anchor="end">100%</text>'
        '<text x="28" y="128" font-size="9" fill="#6b7689" text-anchor="end">0%</text>'
        '<path d="M 35 25 Q 90 28, 145 45 T 225 115 Q 270 122, 305 124" '
        'stroke="#7F77DD" stroke-width="1.8" fill="none" stroke-dasharray="4,3"/>'
        '<g fill="#85B7EB">'
        '<circle cx="60" cy="32" r="3"/><circle cx="100" cy="40" r="3"/>'
        '<circle cx="150" cy="55" r="3"/><circle cx="190" cy="80" r="3"/>'
        '<circle cx="225" cy="108" r="3"/><circle cx="260" cy="118" r="3"/>'
        '<circle cx="290" cy="122" r="3"/></g>'
        '<line x1="195" y1="15" x2="195" y2="125" stroke="#5DCAA5" stroke-width="1" stroke-dasharray="4,3"/>'
        '<text x="200" y="25" font-size="9" fill="#5DCAA5">EC50 = 38 nM</text>'
        '</svg>'
    )
    return html.Div(
        [
            html.Div(
                [
                    html.Span("Dose–response curve", style={"fontSize": "12px", "fontWeight": "500"}),
                    html.Span("예측 · 실측 겹쳐 표시", style={"fontSize": "10px", "color": "var(--nsclc-text-secondary)"}),
                ],
                style={"display": "flex", "justifyContent": "space-between", "marginBottom": "8px"},
            ),
            html.Div(
                html.Iframe(srcDoc=svg, style={"width":"100%","height":"100%","border":"none","background":"transparent"}),
                id="cl-dose-response-chart",
            ),
        ],
        className="viz-panel",
    )


def _four_source_panel():
    """4-source 검증 패널."""
    sources = [
        ("P", "PRISM", "source-badge-prism", "—", "var(--accent-cyan)"),
        ("A", "예측", "source-badge-model", "—", "var(--accent-purple)"),
        ("G", "GDSC2", "source-badge-gdsc", "—", "var(--accent-cyan)"),
        ("Z", "Z-score", "source-badge-zscore", "—", "var(--accent-amber)"),
    ]
    rows = []
    for badge_letter, label, badge_class, value, color in sources:
        rows.append(
            html.Div(
                [
                    html.Span(
                        [
                            html.Span(badge_letter, className=f"source-badge {badge_class}"),
                            f" {label}",
                        ],
                    ),
                    html.Span(value, style={"color": color}),
                ],
                style={
                    "display": "flex",
                    "justifyContent": "space-between",
                    "alignItems": "center",
                    "fontSize": "11px",
                },
            )
        )

    return html.Div(
        [
            html.Div("🛡 4-source 검증", style={"fontSize": "12px", "fontWeight": "500", "marginBottom": "12px"}),
            html.Div(rows, id="cl-4source-rows", style={"display": "flex", "flexDirection": "column", "gap": "8px"}),
            html.Div(
                "데이터 연결 대기 중",
                id="cl-concordance",
                className="concordance-badge concordance-partial",
            ),
        ],
        className="viz-panel",
    )


# ── Layout ────────────────────────────────────────────────────────────────────


def _build_layout(**kwargs):
    return html.Div(
        [
            _header(),
            _input_box(),
            _metrics_row(),
            html.Div(
                [_dose_response_placeholder(), _four_source_panel()],
                className="viz-2col",
            ),
        ],
        style={
            "padding": "20px",
            "background": "var(--nsclc-bg-secondary)",
            "borderRadius": "12px",
        },
    )


# Module-level layout variable
# Activate callbacks (must be after Dash app context)
from nsclc_ui.data.cell_line import callbacks as _cl_callbacks  # noqa: F401

layout = _build_layout()
