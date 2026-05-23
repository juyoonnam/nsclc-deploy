"""
Drug Ranking — Modality-filtered ranking with Scaffold + Activity Cliff.
"""

import dash
from dash import html, dcc, callback, Input, Output, State
import dash_mantine_components as dmc

from nsclc_ui.components.kpi_card import kpi_card
from nsclc_ui.components.pipeline_status import training_job_badge, AWS_META
from nsclc_ui.data.loaders import (
    get_ranking_for_modality, load_scaffold_info, detect_activity_cliffs,
    normalize_compound_id, load_scaffold_info_derived, load_activity_cliffs_derived,
)
from nsclc_ui.layout.theme import COLORS, card_style, MOD_COLORS

dash.register_page(__name__, path="/drug-ranking", name="Drug Ranking")

_MOD_LABELS = {"drug": "Drug", "adc": "ADC", "protac": "PROTAC", "glue": "Mol. Glue", "rlt": "RLT"}

# Load scaffold + cliff data (prefer derived pkl, fallback to computed)
_SCAFFOLDS = load_scaffold_info_derived() or load_scaffold_info()
_CLIFFS = load_activity_cliffs_derived() or detect_activity_cliffs(top_n=50)

# Build cliff lookup: compound_id → list of cliff partners
_CLIFF_MAP: dict[str, list[dict]] = {}
for cliff in _CLIFFS:
    for side in ["compound_a", "compound_b"]:
        cid = cliff[side]
        other = cliff["compound_b"] if side == "compound_a" else cliff["compound_a"]
        _CLIFF_MAP.setdefault(cid, []).append({
            "partner": other,
            "similarity": cliff["similarity"],
            "score_diff": cliff["score_diff"],
        })

def _build_table(data: list[dict], decisions: dict | None = None):
    """Build ranking table with scaffold + cliff columns + blocked badges."""
    decisions = decisions or {}
    if not data:
        return dmc.Text("No compounds match filters", size="xs", c="dimmed")

    header = dmc.TableThead(dmc.TableTr([
        dmc.TableTh("#", style={"width": "32px"}),
        dmc.TableTh("Compound"),
        dmc.TableTh("rank_score", style={"textAlign": "right"}),
        dmc.TableTh("prob", style={"textAlign": "right"}),
        dmc.TableTh("Primary"),
        dmc.TableTh("Scaffold"),
        dmc.TableTh("Fam.", style={"textAlign": "right"}),
        dmc.TableTh("MW", style={"textAlign": "right"}),
        dmc.TableTh("Lip."),
        dmc.TableTh("Cliff"),
    ]))

    prev_scaffold = None
    rows = []
    for i, r in enumerate(data):
        cid = r["compound_id"]
        scaf = _SCAFFOLDS.get(cid, {})
        scaf_smi = scaf.get("scaffold_smiles", "—")
        fam_size = scaf.get("family_size", "—")
        scaf_short = scaf_smi[:22] + "…" if len(scaf_smi) > 22 else scaf_smi

        # Group highlight: same scaffold as previous row
        same_group = scaf_smi == prev_scaffold and scaf_smi != "—"
        row_bg = COLORS["bg_tertiary"] if same_group else "transparent"
        prev_scaffold = scaf_smi

        # Cliff badge
        cliff_info = _CLIFF_MAP.get(cid, [])
        if cliff_info:
            best = max(cliff_info, key=lambda x: x["similarity"])
            cliff_cell = dmc.Badge(
                f"⚠ cliff",
                color="orange", variant="light", size="xs",
                style={"cursor": "help"},
            )
        else:
            cliff_cell = dmc.Text("—", size="xs", c="dimmed")

        # Primary modality color
        pm = r.get("primary_modality", "")
        pm_color = MOD_COLORS.get(pm, COLORS["text_secondary"])

        rows.append(dmc.TableTr([
            dmc.TableTd(str(i + 1)),
            dmc.TableTd(
                dmc.Group([
                    dcc.Link(
                        dmc.Text(cid, fw=500, size="xs", style={"color": COLORS["accent"], "fontSize": "11px"}),
                        href=f"/candidate-explorer?compound={cid}",
                        style={"textDecoration": "none"},
                    ),
                    dmc.Badge(
                        {"confirmed": "✓ confirmed", "review": "? review", "blocked": "✕ blocked"}.get(decisions.get(cid, ""), ""),
                        color={"confirmed": "green", "review": "yellow", "blocked": "red"}.get(decisions.get(cid, ""), "gray"),
                        variant="light", size="xs",
                    ) if cid in decisions else None,
                ], gap=4),
            ),
            dmc.TableTd(f"{r['rank_score']:.4f}", style={"textAlign": "right", "fontVariantNumeric": "tabular-nums", "fontWeight": "500"}),
            dmc.TableTd(f"{r['prob']:.4f}", style={"textAlign": "right", "fontVariantNumeric": "tabular-nums"}),
            dmc.TableTd(dmc.Badge(pm, size="xs", variant="light", style={"color": pm_color, "border": "none"})),
            dmc.TableTd(dmc.Text(scaf_short, size="xs", ff="monospace", c="dimmed", style={"fontSize": "9px"})),
            dmc.TableTd(str(fam_size), style={"textAlign": "right", "fontVariantNumeric": "tabular-nums"}),
            dmc.TableTd(f"{r['mw']:.0f}" if r.get("mw") else "—", style={"textAlign": "right"}),
            dmc.TableTd(
                dmc.Badge("✓", color="green", variant="light", size="xs") if r.get("lipinski_pass")
                else dmc.Badge(f"{r.get('lipinski_violations', 0)}", color="yellow", variant="light", size="xs"),
            ),
            dmc.TableTd(cliff_cell),
        ], style={"background": row_bg}))

    return dmc.Table(
        [header, dmc.TableTbody(rows)],
        striped=True, highlightOnHover=True, withTableBorder=True,
        withColumnBorders=False, style={"fontSize": "11px"},
    )

# ── Cliff warning banner ──────────────────────────────────────────────────
_cliff_banner = None
if _CLIFFS:
    _cliff_banner = dmc.Alert(
        title=f"⚠ {len(_CLIFFS)} activity cliff(s) detected",
        children="구조 유사도 ≥0.85이지만 rank_score 차이 ≥0.15인 쌍이 존재합니다. "
                 "동일 scaffold 내 점수 차이는 모델 불확실성 또는 SAR 단절을 시사합니다.",
        color="orange", variant="light", radius="md",
    )


# ── Layout (function-based for URL query param support) ───────────────────
def layout(modality=None, **kwargs):
    initial_mod = modality if modality in _MOD_LABELS else ""
    return dmc.Stack([
        # Filter bar
        dmc.Paper(
            dmc.Group([
                dmc.Select(
                    id="ranking-modality-filter",
                    label="Modality",
                    data=[{"value": "", "label": "All"}] + [{"value": m, "label": _MOD_LABELS[m]} for m in _MOD_LABELS],
                    value=initial_mod, size="xs", style={"width": "140px"},
                    styles={
                        "input": {"background": COLORS["bg_tertiary"], "color": COLORS["text_primary"],
                                  "border": f"1px solid {COLORS['border']}"},
                        "dropdown": {"background": COLORS["bg_secondary"], "border": f"1px solid {COLORS['border']}"},
                        "option": {"color": COLORS["text_primary"]},
                    },
                ),
                dmc.Checkbox(id="ranking-pains-free", label="PAINS-free", size="xs", checked=False),
                dmc.Checkbox(id="ranking-lipinski", label="Lipinski pass", size="xs", checked=False),
                training_job_badge(),
                dmc.Badge(f"Last trained: {AWS_META['sagemaker_training']['duration']}", color="gray", variant="light", size="sm"),
            ], gap="md", align="flex-end"),
            style=card_style(padding="10px"),
        ),

        # Cliff warning
        *([_cliff_banner] if _cliff_banner else []),

        # KPI row (dynamic)
        html.Div(id="ranking-kpi-row"),

        # Table
        dmc.Paper(
            html.Div(id="ranking-table-container"),
            style=card_style(),
        ),
    ], gap="md")


# ── Callback ──────────────────────────────────────────────────────────────
@callback(
    Output("ranking-kpi-row", "children"),
    Output("ranking-table-container", "children"),
    Input("ranking-modality-filter", "value"),
    Input("ranking-pains-free", "checked"),
    Input("ranking-lipinski", "checked"),
    Input("decisions-store", "data"),
)
def _update_ranking(modality, pains_free, lipinski, decisions):
    mod = modality if modality else None
    data = get_ranking_for_modality(mod, pains_free=bool(pains_free), lipinski_pass=bool(lipinski), top_n=50)

    top_score = data[0]["rank_score"] if data else 0
    pos_count = sum(1 for d in data if d.get("is_positive"))
    mod_label = _MOD_LABELS.get(mod, "All") if mod else "All"

    # Count scaffolds in view
    scaf_set = set()
    for d in data:
        s = _SCAFFOLDS.get(d["compound_id"], {}).get("scaffold_smiles")
        if s:
            scaf_set.add(s)

    kpis = dmc.SimpleGrid(cols=5, spacing="sm", children=[
        kpi_card("Filter", mod_label),
        kpi_card("Compounds", str(len(data))),
        kpi_card("Top rank_score", f"{top_score:.4f}"),
        kpi_card("Scaffolds", str(len(scaf_set))),
        kpi_card("Positives", str(pos_count)),
    ])

    return kpis, _build_table(data, decisions=decisions)
