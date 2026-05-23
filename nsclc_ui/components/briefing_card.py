"""
briefing_card.py
사전 브리핑 카드 렌더 — pathway / target / drug 3종.

briefing.py의 실제 dict 키와 정확히 매칭 (Step 4-C v2).
오류 모델: 키 빠지면 '—', KeyError 발생 안 시킴.
"""
from __future__ import annotations
from typing import Optional, Any

from dash import html
import dash_mantine_components as dmc

from nsclc_ui.layout.theme import COLORS
from nsclc_ui.data.briefing import (
    get_briefing_for_pathway,
    get_briefing_for_target,
    get_briefing_for_drug,
)

# 색·라벨
TYPE_COLOR = {"pathway": "violet", "target": "cyan", "drug": "grape"}
TYPE_LABEL_KO = {"pathway": "경로", "target": "표적", "drug": "약물"}

# Mantine v8은 c="cyan" 등 raw 색명 못 받음 → hex 사용
ACCENT_HEX = "#22D3EE"   # cyan-400
DIMMED_HEX = "#9CA3AF"
DRUG_NAME_ALIASES = {
    "CHEMBL1173655": "Afatinib",
    "CHEMBL3353410": "Osimertinib",
    "CHEMBL939": "Gefitinib",
    "CHEMBL1738797": "Alectinib",
    "CHEMBL601719": "Crizotinib",
    "CHEMBL507361": "Trametinib",
}

_MOLECULE_PLACEHOLDER = (
    "<svg xmlns='http://www.w3.org/2000/svg' width='180' height='120' viewBox='0 0 180 120'>"
    "<polygon points='45,25 65,14 85,25 85,48 65,60 45,48' stroke='#CBD5E1' stroke-width='2' fill='none'/>"
    "<polygon points='85,25 105,14 125,25 125,48 105,60 85,48' stroke='#CBD5E1' stroke-width='2' fill='none'/>"
    "<line x1='65' y1='60' x2='65' y2='88' stroke='#CBD5E1' stroke-width='2'/>"
    "<text x='35' y='76' font-size='14' fill='#22D3EE' font-family='monospace'>N</text>"
    "<text x='126' y='32' font-size='14' fill='#51CF66' font-family='monospace'>Cl</text>"
    "<text x='118' y='65' font-size='14' fill='#22D3EE' font-family='monospace'>F</text>"
    "</svg>"
)


# ============================================================
# Helpers
# ============================================================
def _fmt(v: Any, default: str = "—", precision: int = 3) -> str:
    if v is None or v == "":
        return default
    if isinstance(v, bool):
        return "예" if v else "아니오"
    if isinstance(v, float):
        return f"{v:.{precision}f}"
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, (list, tuple)):
        if not v:
            return default
        head = ", ".join(str(x) for x in v[:5])
        return f"{head}{' …' if len(v) > 5 else ''}"
    return str(v)


def _kv_row(label: str, value: Any, *, mono: bool = False, accent: bool = False):
    style = {}
    if mono:
        style["fontFamily"] = "ui-monospace, monospace"
    if accent:
        style["color"] = ACCENT_HEX
    return dmc.Group(
        [
            dmc.Text(label, size="xs", c="dimmed"),
            dmc.Text(_fmt(value), size="sm",
                     fw=600 if accent else 400,
                     style=style or None),
        ],
        gap=8,
        justify="space-between",
        wrap="nowrap",
        style={
            "borderBottom": f"1px solid {COLORS.get('border', '#2D2E36')}",
            "padding": "4px 0",
        },
    )


def _header(badge_text: str, color: str, title: str, subtitle: Optional[str] = None):
    children = [
        dmc.Group(
            [
                dmc.Badge(badge_text, color=color, variant="light", size="sm"),
                dmc.Text(title, size="lg", fw=700,
                         style={"color": COLORS.get("text_primary", "#E4E4E7")}),
            ],
            gap=8,
            wrap="nowrap",
        ),
    ]
    if subtitle:
        children.append(dmc.Text(subtitle, size="xs", c="dimmed"))
    return dmc.Stack(children, gap=2)


def _empty_card(title: str, msg: str):
    return dmc.Alert(msg, color="gray", variant="light", title=title)


def _drug_display_name(compound_id: str) -> str:
    return DRUG_NAME_ALIASES.get(str(compound_id).upper(), compound_id)


def _model_row(label: str, value: Any, *, accent: bool = False):
    return html.Div(
        [
            html.Span(label),
            html.Span(
                _fmt(value),
                className="atlas-model-value" if accent else None,
                title=_fmt(value),
                style={
                    "minWidth": 0,
                    "maxWidth": "150px",
                    "overflow": "hidden",
                    "textOverflow": "ellipsis",
                    "whiteSpace": "nowrap",
                    "textAlign": "right",
                },
            ),
        ],
        className="atlas-model-row",
    )


def _model_row_content(label: str, content):
    return html.Div(
        [
            html.Span(label),
            html.Span(
                content,
                style={
                    "minWidth": 0,
                    "maxWidth": "150px",
                    "overflow": "hidden",
                    "textOverflow": "ellipsis",
                    "whiteSpace": "nowrap",
                    "textAlign": "right",
                },
            ),
        ],
        className="atlas-model-row",
    )


def _confidence_signal(grade: str, label: str):
    if not grade and not label:
        return "—"
    return html.Span(
        [
            html.Span(
                grade,
                className="atlas-model-value",
                style={"fontSize": "15px", "letterSpacing": "2px"},
            ),
            html.Span(
                f" {label}" if label else "",
                style={"color": "rgba(148, 163, 184, 0.82)", "fontSize": "12px"},
            ),
        ]
    )


def _split_targets(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        raw_items = [str(v) for v in value if v]
    else:
        raw = str(value or "")
        raw_items = raw.replace(",", ";").split(";")
    return [item.strip() for item in raw_items if item.strip()]


def _target_chips(value: Any):
    targets = _split_targets(value)
    if not targets:
        return "—"
    return html.Div(
        [
            html.Span(
                target,
                style={
                    "display": "inline-flex",
                    "alignItems": "center",
                    "height": "20px",
                    "padding": "0 7px",
                    "borderRadius": "999px",
                    "border": "1px solid rgba(34, 211, 238, 0.34)",
                    "background": "rgba(34, 211, 238, 0.08)",
                    "color": "#BAE6FD",
                    "fontSize": "11px",
                    "fontWeight": 700,
                    "lineHeight": 1,
                },
            )
            for target in targets[:6]
        ],
        style={"display": "flex", "flexWrap": "wrap", "gap": "5px", "marginTop": "5px"},
    )


def _svg_fit_document(svg_doc: str) -> str:
    return (
        "<!doctype html><html><head><style>"
        "html,body{margin:0;width:100%;height:100%;background:transparent;overflow:hidden;}"
        "body{display:flex;align-items:center;justify-content:center;}"
        "svg{width:100%!important;height:100%!important;max-width:100%;max-height:100%;display:block;}"
        "</style></head><body>"
        f"{svg_doc}"
        "</body></html>"
    )


def _compact_molecule_2d(smiles: str | None):
    svg_doc = None
    if smiles:
        try:
            from rdkit import Chem
            from rdkit.Chem.Draw import rdMolDraw2D

            mol = Chem.MolFromSmiles(smiles)
            if mol is not None:
                drawer = rdMolDraw2D.MolDraw2DSVG(210, 132)
                drawer.drawOptions().clearBackground = False
                drawer.DrawMolecule(mol)
                drawer.FinishDrawing()
                svg_doc = drawer.GetDrawingText()
        except Exception:
            svg_doc = None

    if not svg_doc:
        svg_doc = _MOLECULE_PLACEHOLDER

    return html.Div(
        [
            html.Div(
                html.Iframe(
                    srcDoc=_svg_fit_document(svg_doc),
                    style={
                        "width": "100%",
                        "height": "108px",
                        "border": 0,
                        "background": "transparent",
                        "display": "block",
                    },
                ),
                style={
                    "height": "112px",
                    "width": "100%",
                    "display": "flex",
                    "alignItems": "center",
                    "justifyContent": "center",
                    "overflow": "hidden",
                },
            ),
            html.Div(
                "RDKit 2D (SVG)" if smiles else "SMILES 없음",
                style={
                    "marginTop": "2px",
                    "color": "rgba(148, 163, 184, 0.78)",
                    "fontSize": "10px",
                    "lineHeight": 1,
                    "textAlign": "center",
                },
            ),
        ],
        style={
            "background": "transparent",
            "borderRadius": "6px",
            "padding": "2px 0 0",
            "width": "100%",
            "boxSizing": "border-box",
        },
    )


def _neighbor_id(item: Any) -> str | None:
    if item is None:
        return None
    if isinstance(item, str):
        return item.split(",")[0].strip() or None
    if isinstance(item, dict):
        for key in ("compound_id", "chembl_id", "neighbor_id", "id", "name"):
            if item.get(key):
                return str(item[key]).split(",")[0].strip()
    if isinstance(item, (list, tuple)) and item:
        return str(item[0]).split(",")[0].strip()
    return str(item).split(",")[0].strip()


def _closest_neighbor_label(cliffs: list[Any]) -> str:
    ids = []
    for item in cliffs or []:
        nid = _neighbor_id(item)
        if nid and nid not in ids:
            ids.append(nid)
    if not ids:
        return "—"
    suffix = f" +{len(ids) - 1} more" if len(ids) > 1 else ""
    return f"{ids[0]}{suffix}"


# ============================================================
# Pathway 카드
# ============================================================
def render_pathway_card(pathway_id: str):
    b = get_briefing_for_pathway(pathway_id) or {}
    if not b or not b.get("available", True):
        return _empty_card("브리핑 데이터 없음", f"pathway {pathway_id}")

    return dmc.Stack(
        [
            _header(
                badge_text=TYPE_LABEL_KO["pathway"],
                color=TYPE_COLOR["pathway"],
                title=b.get("name") or pathway_id,
                subtitle=b.get("id") or pathway_id,
            ),
            dmc.Divider(),
            _kv_row("전체 노드", b.get("n_nodes")),
            _kv_row("Gene 수", b.get("n_genes"), accent=True),
            _kv_row("엣지 수", b.get("n_edges")),
            _kv_row("프로젝트 타겟", b.get("n_project_targets"), accent=True),
            _kv_row("약물 보유 타겟", b.get("n_targets_with_drugs")),
            _kv_row("관련 화합물(중복포함)", b.get("total_drugs")),
            _kv_row("프로젝트 타겟 목록", b.get("project_targets")),
        ],
        gap=6,
    )


# ============================================================
# Target 카드
# ============================================================
def render_target_card(gene_symbol: str):
    b = get_briefing_for_target(gene_symbol) or {}
    if not b or not b.get("available", True):
        return _empty_card("브리핑 데이터 없음", f"target {gene_symbol}")

    ess = b.get("essentiality") or {}
    related_shap = b.get("related_shap") or []

    is_ess = ess.get("is_essential")
    mean_score = ess.get("mean_score")
    if is_ess is True:
        ess_display = f"필수 (mean={_fmt(mean_score)})"
        ess_accent = True
    elif is_ess is False:
        ess_display = f"비필수 (mean={_fmt(mean_score)})"
        ess_accent = False
    else:
        ess_display = "—"
        ess_accent = False

    rows = [
        _header(
            badge_text=TYPE_LABEL_KO["target"],
            color=TYPE_COLOR["target"],
            title=b.get("gene_symbol") or gene_symbol,
        ),
        dmc.Divider(),
        _kv_row("약물 수", b.get("n_drugs"), accent=True),
        _kv_row("Essentiality", ess_display, accent=ess_accent),
        _kv_row("CRISPR 셀라인 수", ess.get("n_cell_lines")),
    ]

    if related_shap:
        rows.append(dmc.Space(h=4))
        rows.append(
            dmc.Text("관련 SHAP feature (top 5)", size="xs", c="dimmed", fw=600)
        )
        for s in related_shap[:5]:
            label = s.get("kr_label") or s.get("feature") or "—"
            rank = s.get("rank")
            shap_val = s.get("mean_abs_shap")
            rows.append(
                dmc.Group(
                    [
                        dmc.Text(
                            f"  · #{rank} {label}" if rank else f"  · {label}",
                            size="xs",
                        ),
                        dmc.Text(
                            _fmt(shap_val, precision=4),
                            size="xs",
                            style={"fontFamily": "ui-monospace, monospace",
                                   "color": ACCENT_HEX},
                        ),
                    ],
                    gap=8,
                    justify="space-between",
                    wrap="nowrap",
                )
            )

    return dmc.Stack(rows, gap=6)


# ============================================================
# Drug 카드
# ============================================================
_PHASE_LABEL = {0: "전임상", 1: "Phase I", 2: "Phase II", 3: "Phase III", 4: "승인"}


def render_drug_card(compound_id: str):
    b = get_briefing_for_drug(compound_id) or {}
    if not b or not b.get("available", True):
        return _empty_card("브리핑 데이터 없음", f"drug {compound_id}")

    conf = b.get("confidence") or {}
    cliffs = b.get("cliff_partners") or []
    closest = _closest_neighbor_label(cliffs)
    max_phase = b.get("max_phase")
    phase_disp = (
        _PHASE_LABEL.get(max_phase, str(max_phase))
        if max_phase is not None else "—"
    )

    conf_grade = conf.get("grade", "")
    conf_label = conf.get("label", "")
    cid = b.get("compound_id") or compound_id
    title = b.get("pref_name") or _drug_display_name(cid)
    primary_target = b.get("primary_target") or "—"
    all_targets = b.get("all_targets") or primary_target
    moa = b.get("mechanism_of_action") or f"{primary_target} 연관 mechanism hypothesis"
    smiles = b.get("smiles")

    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H2(title, className="atlas-card-title"),
                            html.Div(cid, className="atlas-card-subtitle"),
                        ],
                    ),
                    html.Div("약물 (Drug)", className="atlas-card-badge atlas-card-badge-drug"),
                ],
                className="atlas-card-header",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div("Chemical structure", className="atlas-section-label"),
                                    html.Div("i", className="atlas-info-dot"),
                                ],
                                className="atlas-section-head",
                            ),
                            html.Div(_compact_molecule_2d(smiles), className="atlas-molecule-box"),
                            html.Div(
                                [
                                    html.Div([html.Span(className="atlas-swatch atlas-swatch-red"), "빨강: top contrib"]),
                                    html.Div([html.Span(className="atlas-swatch atlas-swatch-amber"), "앰버: mid"]),
                                ],
                                className="atlas-molecule-legend",
                            ),
                        ],
                        className="atlas-structure-panel",
                        style={"padding": "8px 10px", "boxSizing": "border-box"},
                    ),
                    html.Div(
                        [
                            html.Div("General", className="atlas-section-title"),
                            html.Ul(
                                [
                                    html.Li(moa),
                                    html.Li(f"{primary_target} 중심 신호축과 연결"),
                                    html.Li(
                                        [
                                            html.Span("관련 target"),
                                            _target_chips(all_targets),
                                        ]
                                    ),
                                    html.Li(f"max phase: {phase_disp}"),
                                ],
                                className="atlas-general-list",
                                style={
                                    "paddingLeft": "15px",
                                    "marginTop": "8px",
                                    "marginBottom": "0",
                                },
                            ),
                            html.Div("Our model perspective", className="atlas-section-title atlas-section-title-model"),
                            html.Div(
                                [
                                    _model_row("rank_score", b.get("rank_score"), accent=True),
                                    _model_row_content("confidence", _confidence_signal(conf_grade, conf_label)),
                                    _model_row("scaffold cluster", b.get("family_size"), accent=True),
                                    _model_row("primary target", primary_target, accent=True),
                                    _model_row("closest neighbor", closest),
                                ],
                                className="atlas-model-table",
                            ),
                        ],
                        className="atlas-general-panel",
                    ),
                ],
                className="atlas-detail-grid",
            ),
        ],
        className="atlas-detail-card atlas-drug-card",
    )


# ============================================================
# Dispatcher
# ============================================================
def render_card(focus: Optional[dict]):
    """focus = {'id': str, 'type': 'pathway'|'target'|'drug'} or None"""
    if not focus or "type" not in focus or "id" not in focus:
        return dmc.Alert(
            "노드를 클릭하거나 검색창에서 entity를 선택하세요.",
            color="gray",
            variant="light",
        )
    t = focus["type"]
    fid = focus["id"]
    try:
        if t == "pathway":
            return render_pathway_card(fid)
        if t == "target":
            return render_target_card(fid)
        if t == "drug":
            return render_drug_card(fid)
    except Exception as exc:
        return dmc.Alert(
            f"카드 렌더 오류: {exc}", color="red", variant="light"
        )
    return dmc.Alert(
        f"알 수 없는 entity 타입: {t}", color="orange", variant="light"
    )
