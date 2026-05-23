"""
Patient Mode — mock patient multi-modal recommendation view.

Implements Part C from presentation_data/codex_prompt_v1.md against
mockup_5_v2.svg. Patient data is presentation mock data only.
"""

from __future__ import annotations

import dash
from dash import dcc, html

from nsclc_ui.data.gdsc2_loader import get_cross_source_pool


dash.register_page(
    __name__,
    path="/patient-mode",
    name="Patient Mode",
    title="NSCLC Insight Engine — Patient Mode",
    order=8,
)


PATIENT_ID = "MSK_LUAD_042"
XS_POOL: set[str] = {item["chembl_id"] for item in get_cross_source_pool()}

TOP5_MOCK = [
    {
        "rank": 1,
        "name": "Osimertinib",
        "chembl_id": "CHEMBL3353410",
        "score": 0.89,
        "confidence": 4,
        "sub_text": "Champion OOF prob 0.82 ±0.07 (실측)",
        "sub_tone": "muted",
        "tone": "green",
    },
    {
        "rank": 2,
        "name": "Afatinib",
        "chembl_id": "CHEMBL1173655",
        "score": 0.74,
        "confidence": 3,
        "sub_text": "Champion OOF prob 0.82 ±0.05 (실측 · Osi 동률)",
        "sub_tone": "muted",
        "tone": "blue",
    },
    {
        "rank": 3,
        "name": "Erlotinib",
        "chembl_id": "CHEMBL553",
        "score": 0.62,
        "confidence": 3,
        "sub_text": "Champion OOF prob 0.27 ±0.12 — 화학구조만으론 누락",
        "sub_tone": "orange",
        "tone": "orange",
    },
    {
        "rank": 4,
        "name": "Gefitinib",
        "chembl_id": "CHEMBL939",
        "score": 0.47,
        "confidence": 1,
        "sub_text": "Champion OOF prob 0.49 ±0.19 (경계, std 큼)",
        "sub_tone": "muted",
        "tone": "gray",
    },
    {
        "rank": 5,
        "name": "Dacomitinib",
        "chembl_id": "CHEMBL2110732",
        "score": 0.38,
        "confidence": 1,
        "sub_text": "Champion OOF prob 0.07 ±0.02 — 화학구조만으론 누락",
        "sub_tone": "orange",
        "tone": "gray",
    },
]

for drug in TOP5_MOCK:
    drug["xs_pool"] = drug["chembl_id"] in XS_POOL

assert {drug["name"]: drug["xs_pool"] for drug in TOP5_MOCK} == {
    "Osimertinib": True,
    "Afatinib": True,
    "Erlotinib": True,
    "Gefitinib": True,
    "Dacomitinib": False,
}


def _helix() -> html.Div:
    return html.Div(
        [
            html.Div(className="patient-helix-strand patient-helix-left"),
            html.Div(className="patient-helix-strand patient-helix-right"),
            *[
                html.Div(className="patient-helix-rung", style={"top": f"{top}px"})
                for top in (7, 14, 21, 28, 35)
            ],
        ],
        className="patient-helix",
    )


def _header() -> html.Div:
    return html.Div(
        [
            html.Div("☰", className="patient-menu"),
            _helix(),
            html.Div("Simulator — Triple-Mode Validation Engine", className="patient-title"),
            html.Div("NSCLC Living Atlas", className="patient-atlas-label"),
            html.Div("⚠ 가설 생성용 · 진료 추천 아님", className="patient-header-warning"),
            html.Div([html.Strong("한"), html.Span(" / EN")], className="patient-lang"),
            html.Div("⛶", className="patient-expand"),
        ],
        className="patient-header",
    )


def _tabs() -> html.Div:
    return html.Div(
        [
            html.A("📖 ① Library", href="/simulator", className="patient-tab"),
            html.A("⚗ ② Cell-line", href="/cell-line-mode", className="patient-tab"),
            html.Div("👤 ③ Patient", className="patient-tab is-active"),
        ],
        className="patient-tabs",
    )


def _patient_picker() -> html.Div:
    return html.Div(
        [
            html.Div("Patient:", className="patient-picker-label"),
            html.Div(
                dcc.Dropdown(
                    id="patient-mode-picker",
                    options=[
                        {"label": "MSK_LUAD_042", "value": "MSK_LUAD_042"},
                        {"label": "MSK_LUAD_017", "value": "MSK_LUAD_017"},
                        {"label": "MSK_LUSC_109", "value": "MSK_LUSC_109"},
                    ],
                    value=PATIENT_ID,
                    clearable=False,
                    searchable=False,
                    className="patient-select",
                ),
                className="patient-select-wrap",
            ),
            html.Div(
                ["Source: ", html.Span("MSK-IMPACT 합성 예시"), " · cBioPortal 통합 (stretch)"],
                className="patient-source-label",
            ),
        ],
        className="patient-picker-row",
    )


def _profile_card() -> html.Div:
    fields = [
        ("🧬 주요 변이", "EGFR L858R + T790M, TP53 R273H"),
        ("📊 Stage", "IV"),
        ("≡ Line", "2"),
        ("⚗ Histology", "Adenocarcinoma"),
    ]
    return html.Div(
        [
            html.Div("👤 환자 프로필", className="patient-panel-title"),
            html.Div(
                [
                    html.Div([html.Span(label), html.Strong(value)], className="patient-profile-field")
                    for label, value in fields
                ],
                className="patient-profile-fields",
            ),
            html.Div(
                [
                    html.Div("💊 실제 치료 (Actual treatment)", className="patient-actual-title"),
                    html.Div([html.Span("⏱ Received"), html.Strong("Osimertinib (line 2)")], className="patient-actual-row"),
                    html.Div([html.Span("ⓘ Outcome"), html.Strong("PFS 14.2 mo, PR")], className="patient-actual-row"),
                    html.Div([html.Span("⊕ Source"), html.Em("MSK-IMPACT clinical (예시)")], className="patient-actual-row"),
                    html.Div("실제 치료가 모델 추천 #1과 일치 — 검증 케이스.", className="patient-actual-note"),
                ],
                className="patient-actual-box",
            ),
        ],
        className="patient-panel patient-profile-panel",
    )


def _xs_badge(xs_pool: bool) -> html.Span:
    if xs_pool:
        return html.Span("X-S", className="patient-xs-badge")
    return html.Span("NO X-S", className="patient-no-xs-badge")


def _confidence_dots(active: int) -> html.Div:
    return html.Div(
        [
            html.Span(className="patient-confidence-dot is-active" if idx < active else "patient-confidence-dot")
            for idx in range(4)
        ],
        className="patient-confidence",
    )


def _top5_row(drug: dict) -> html.Div:
    return html.Div(
        [
            html.Div(str(drug["rank"]), className=f"patient-rank patient-rank-{drug['tone']}"),
            html.Div(
                [
                    html.Div(drug["name"], className=f"patient-drug-name patient-drug-{drug['tone']}"),
                    html.Div(
                        drug["sub_text"],
                        className=f"patient-drug-sub patient-drug-sub-{drug['sub_tone']}",
                    ),
                ],
                className="patient-drug-copy",
            ),
            html.Div(f"{drug['score']:.2f}", className="patient-mm-score"),
            _confidence_dots(int(drug["confidence"])),
            html.Div(_xs_badge(bool(drug["xs_pool"])), className="patient-xs-cell"),
        ],
        className="patient-top5-row is-first" if drug["rank"] == 1 else "patient-top5-row",
    )


def _top5_panel() -> html.Div:
    return html.Div(
        [
            html.Div("⭐ 모델 추천 Top-5", className="patient-panel-title"),
            html.Div(
                "Multi-modal score ⓘ — 구조·네트워크·표현형 통합 (★ 발표 단계 예시값)",
                className="patient-panel-subtitle",
            ),
            html.Div(
                [
                    html.Span("Rank"),
                    html.Span("약물"),
                    html.Span("Multi-modal ⓘ"),
                    html.Span("신뢰도"),
                    html.Span("X-S"),
                ],
                className="patient-top5-header",
            ),
            html.Div([_top5_row(drug) for drug in TOP5_MOCK], className="patient-top5-list"),
            html.Div(
                "ⓘ Multi-modal = 구조 (champion OOF prob) + 네트워크 (target-pathway) + 표현형 (PRISM·GDSC2). Top-5 점수 = 발표 시연용 placeholder.",
                className="patient-mm-definition",
            ),
        ],
        className="patient-panel patient-top5-panel",
    )


def _comparison_panel() -> html.Div:
    return html.Div(
        [
            html.Div("⚖ 실제 치료와 비교", className="patient-panel-title"),
            html.Div(
                [
                    html.Div([html.Span("실제 치료의 모델 rank:"), html.Strong("1")], className="patient-comparison-metric"),
                    html.Div([html.Span("Top-3 hit:"), html.Strong("✓")], className="patient-comparison-metric"),
                    html.Div([html.Span("28풀 cross-source:"), html.Strong("✓ (Osimertinib X-S)")], className="patient-comparison-metric"),
                ],
                className="patient-comparison-metrics",
            ),
            html.Div(
                [
                    html.Div("✓", className="patient-match-icon"),
                    html.Div(
                        [
                            html.Div("일치 (high)", className="patient-match-title"),
                            html.Div("실제 치료(Osimertinib)와 일치", className="patient-treatment-match-badge"),
                            html.Div("모델 추천이 실제 치료(Osimertinib)와 일치.", className="patient-match-copy"),
                            html.Div("Cell-line 검증 + GDSC2 IC50 37.7 nM ✓.", className="patient-match-copy"),
                        ],
                        className="patient-match-copy-wrap",
                    ),
                ],
                className="patient-match-box",
            ),
            html.Div(
                [
                    html.Div("ⓘ 해석", className="patient-interpret-title"),
                    html.Div([html.Span("✓"), html.P("EGFR L858R/T790M 변이에 EGFR TKI 민감도 예측 (1, 2, 3세대 모두 상위).")], className="patient-interpret-row"),
                    html.Div([html.Span("✓"), html.P("TP53 R273H는 세포 사멸 회피 강화 — 약물 반응 약화 요인.")], className="patient-interpret-row"),
                    html.Div([html.Span("✓"), html.P("실제 치료(Osi)가 모델 #1과 일치 — 가설 검증 케이스.")], className="patient-interpret-row"),
                ],
                className="patient-interpretation",
            ),
        ],
        className="patient-panel patient-comparison-panel",
    )


def _variant_card(label: str, variant: str, tone: str) -> html.Div:
    return html.Div(
        [
            html.Div(f"🧬 {label}", className="patient-sankey-card-title"),
            html.Div(variant, className="patient-variant-chip"),
        ],
        className=f"patient-sankey-card patient-sankey-{tone}",
    )


def _pathway_card(title: str, subtitle: str, tone: str) -> html.Div:
    return html.Div(
        [
            html.Div(title, className="patient-sankey-card-title"),
            html.Div(subtitle, className="patient-sankey-card-subtitle"),
        ],
        className=f"patient-sankey-card patient-sankey-{tone}",
    )


def _drug_card(drug: dict) -> html.Div:
    return html.Div(
        [
            html.Span(f"{drug['rank']} {drug['name']}", className="patient-sankey-drug-name"),
            _xs_badge(bool(drug["xs_pool"])),
        ],
        className=f"patient-sankey-drug patient-sankey-drug-{drug['tone']}",
    )


def _sankey_edges() -> html.Div:
    return html.Div(
        [
            html.Div(className="patient-edge-line patient-edge-strong e-egfr-path"),
            html.Div(className="patient-edge-line patient-edge-strong e-path-osi"),
            html.Div(className="patient-edge-line patient-edge-blue e-path-afa"),
            html.Div(className="patient-edge-line patient-edge-orange e-path-erl"),
            html.Div(className="patient-edge-line patient-edge-medium e-tp53-apop"),
            html.Div(className="patient-edge-line patient-edge-medium e-tp53-cycle"),
            html.Div(className="patient-edge-line patient-edge-weak e-apop-osi"),
            html.Div(className="patient-edge-line patient-edge-weak e-apop-afa"),
            html.Div(className="patient-edge-line patient-edge-weak e-apop-erl"),
            html.Div(className="patient-edge-line patient-edge-weak e-cycle-gef"),
            html.Div(className="patient-edge-line patient-edge-weak e-cycle-daco"),
        ],
        className="patient-sankey-edges",
    )


def _sankey_panel() -> html.Div:
    return html.Div(
        [
            html.Div("🧬 변이 → 경로 → 약물 연결 맵 (Sankey-style)", className="patient-panel-title"),
            html.Div(
                [
                    html.Div("환자 변이", className="patient-sankey-col-title patient-sankey-title-variants"),
                    html.Div("주요 경로/기전", className="patient-sankey-col-title patient-sankey-title-pathways"),
                    html.Div("추천 약물 (Top-5)", className="patient-sankey-col-title patient-sankey-title-drugs"),
                    html.Div("범례: 연결 해설", className="patient-sankey-col-title patient-sankey-title-legend"),
                    _sankey_edges(),
                    html.Div(
                        [
                            _variant_card("EGFR", "L858R + T790M", "green"),
                            _variant_card("TP53", "R273H", "red"),
                        ],
                        className="patient-sankey-variants",
                    ),
                    html.Div(
                        [
                            _pathway_card("🔗 EGFR 신호 경로", "PI3K/AKT · MAPK", "green"),
                            _pathway_card("⊘ 세포 사멸", "Apoptosis · BAX/BAK · BCL-2", "red"),
                            _pathway_card("↻ 세포 주기", "Cell Cycle · CDK · RB1/E2F", "cyan"),
                        ],
                        className="patient-sankey-pathways",
                    ),
                    html.Div([_drug_card(drug) for drug in TOP5_MOCK], className="patient-sankey-drugs"),
                    html.Div(
                        [
                            html.Div([html.Span(className="patient-legend-line is-strong"), html.Strong("강한 근거"), html.P("변이→경로→약물에 다수 근거")], className="patient-legend-item"),
                            html.Div([html.Span(className="patient-legend-line is-medium"), html.Strong("중간 근거"), html.P("실험·임상 근거가 일부 존재")], className="patient-legend-item"),
                            html.Div([html.Span(className="patient-legend-line is-weak"), html.Strong("약한 근거"), html.P("간접 영향 또는 근거 제한적")], className="patient-legend-item"),
                            html.Div([html.Span(className="patient-inhibit-symbol"), html.Strong("억제 관계"), html.P("해당 변이가 경로/기전을 억제")], className="patient-legend-item"),
                        ],
                        className="patient-sankey-legend",
                    ),
                ],
                className="patient-sankey-body",
            ),
        ],
        className="patient-panel patient-sankey-panel",
    )


def _bottom_actions() -> html.Div:
    return html.Div(
        [
            html.A("🔗 Pathway Map에서 변이 보기 →", href="/pathway", className="patient-bottom-button"),
            html.A("📄 관련 논문 보기 →", href="/literature", className="patient-bottom-button"),
        ],
        className="patient-bottom-actions",
    )


def layout() -> html.Div:
    return html.Div(
        [
            _header(),
            _tabs(),
            _patient_picker(),
            html.Div(
                [_profile_card(), _top5_panel(), _comparison_panel()],
                className="patient-top-grid",
            ),
            _sankey_panel(),
            _bottom_actions(),
            html.Div(
                "면책: 본 화면은 환자별 가설 생성용 시뮬레이션이며 실제 진료 추천이나 임상 의사결정을 대체하지 않습니다.",
                className="patient-footer-note",
            ),
        ],
        className="patient-page-shell",
    )
