"""
Candidate Explorer — Full adjudication workbench with real data connections.
D1: Essentiality · D2: Cell Lines · D3: Target Map · D4: Variant Evidence · D5: Scaffold · Copilot.
"""

import dash
from dash import html, dcc, callback, Input, Output, State
import dash_mantine_components as dmc

from nsclc_ui.components.radar_chart import radar_chart
from nsclc_ui.components.shap_bars import shap_bars
from nsclc_ui.components.molecule_2d import molecule_2d
from nsclc_ui.components.risk_radar import risk_radar
from nsclc_ui.components.decision_copilot import copilot_panel
from nsclc_ui.components.pipeline_status import inference_meta_panel, lineage_timeline
from nsclc_ui.data.loaders import (
    get_compound_detail, get_ranking_for_modality,
    load_kegg_targets, load_evidence_map, load_uncertainty,
    load_essentiality, generate_batch, get_counterfactual,
    normalize_compound_id, load_compound_target_map,
    load_essentiality_derived, load_scaffold_info_derived,
    load_smiles_map,
)
from nsclc_ui.data.mock import (
    SHAP_TOP5, VARIANT_EVIDENCE, VARIANT_EVIDENCE_BY_GENE,
    CELL_LINE_MAP_V2,
)
from nsclc_ui.layout.theme import COLORS, card_style, MOD_COLORS
from nsclc_ui.layout.i18n import t

dash.register_page(__name__, path="/candidate-explorer", name="Candidate Explorer")

_KEGG = load_kegg_targets()
_EVIDENCE = load_evidence_map()
_UNCERTAINTY = load_uncertainty()
_TARGET_MAP = load_compound_target_map()
_ESSENTIALITY = load_essentiality_derived()
_SCAFFOLD = load_scaffold_info_derived()
_SMILES = load_smiles_map()
_MODS = ["drug", "adc", "protac", "glue", "rlt"]
_MOD_LABELS = {"drug": "Drug", "adc": "ADC", "protac": "PROTAC", "glue": "Mol. Glue", "rlt": "RLT"}

def _get_target(cid: str) -> str | None:
    """Get primary target for a compound."""
    nid = normalize_compound_id(cid)
    info = _TARGET_MAP.get(nid, {})
    return info.get("primary_target")


def _essentiality_section(target: str | None):
    """D1: Target essentiality badge."""
    if not target or target.upper() not in _ESSENTIALITY:
        return dmc.Text("Target essentiality: 데이터 없음", size="xs", c="dimmed", style={"fontSize": "10px"})
    ess = _ESSENTIALITY[target.upper()]
    color = "red" if ess["is_essential"] else "gray"
    label = "★Essential" if ess["is_essential"] else "Non-essential"
    return dmc.Group([
        dmc.Text("Essentiality:", size="xs", fw=500, style={"fontSize": "11px"}),
        dmc.Badge(f"{label} ({ess['mean_score']:.2f})", color=color, variant="light", size="xs"),
        dmc.Text(f"n={ess['n_cell_lines']} NSCLC lines", size="xs", c="dimmed", style={"fontSize": "10px"}),
    ], gap=6)


def _cell_line_section(target: str | None):
    """D2: Experiment planner cell lines."""
    if not target or target.upper() not in CELL_LINE_MAP_V2:
        return dmc.Text("Target-specific cell line 정보 없음", size="xs", c="dimmed", style={"fontSize": "10px"})
    info = CELL_LINE_MAP_V2[target.upper()]
    return dmc.Stack([
        dmc.Text(f"권장 세포주: {', '.join(info['lines'])}", size="xs", fw=500, style={"fontSize": "11px"}),
        dmc.Text(info["note"], size="xs", c="dimmed", style={"fontSize": "10px"}),
        dmc.Text("농도: 0.001 ~ 10 μM (10-point serial dilution)", size="xs", c="dimmed", style={"fontSize": "10px"}),
        dmc.Text("Readout: Cell viability (CellTiter-Glo, 72h)", size="xs", c="dimmed", style={"fontSize": "10px"}),
    ], gap=2)


def _variant_section(target: str | None):
    """D4: Variant-aware evidence."""
    if not target:
        return dmc.Text("이 타겟에 대한 actionable variant 정보 없음", size="xs", c="dimmed", style={"fontSize": "10px"})
    matches = [v for v in VARIANT_EVIDENCE_BY_GENE if v["gene"].upper() == target.upper()]
    if not matches:
        return dmc.Text("이 타겟에 대한 actionable variant 정보 없음", size="xs", c="dimmed", style={"fontSize": "10px"})
    rows = [
        dmc.TableTr([
            dmc.TableTd(dmc.Text(v["variant"], fw=500, size="xs")),
            dmc.TableTd(dmc.Text(v["frequency"], size="xs")),
            dmc.TableTd(dmc.Text(", ".join(v["drugs"]), size="xs", style={"fontSize": "10px"})),
            dmc.TableTd(dmc.Badge(f"Level {v['evidence_level']}", color="green", variant="light", size="xs")),
        ])
        for v in matches
    ]
    return dmc.Table([
        dmc.TableThead(dmc.TableTr([
            dmc.TableTh("Variant"), dmc.TableTh("Frequency"), dmc.TableTh("Drugs"), dmc.TableTh("Evidence"),
        ])),
        dmc.TableTbody(rows),
    ], withTableBorder=True, style={"fontSize": "11px"})


def _scaffold_section(cid: str):
    """D5: Scaffold intelligence."""
    nid = normalize_compound_id(cid)
    info = _SCAFFOLD.get(nid)
    if not info:
        return dmc.Text("Scaffold 정보 없음", size="xs", c="dimmed", style={"fontSize": "10px"})
    fs = info["family_size"]
    smi = info["scaffold_smiles"]
    smi_short = smi[:30] + "…" if len(smi) > 30 else smi
    if fs > 50:
        badge = dmc.Badge("Common scaffold", color="yellow", variant="light", size="xs")
    elif fs < 5:
        badge = dmc.Badge("Unique scaffold", color="cyan", variant="light", size="xs")
    else:
        badge = dmc.Badge(f"Family: {fs}", color="gray", variant="light", size="xs")
    return dmc.Group([
        dmc.Text(smi_short, size="xs", ff="monospace", c="dimmed", style={"fontSize": "9px"}),
        badge,
    ], gap=6)

def _build_left_panel(c: dict):
    """Left: info → risk → structure → evidence → variant → essentiality → cell lines → copilot → adjudication."""
    cid = c.get("compound_id", "—")
    ev = _EVIDENCE.get(cid, {})
    unc = _UNCERTAINTY.get(cid)
    target = _get_target(cid)
    pm = c.get("primary_modality", "drug")

    # External links
    chembl_url = f"https://www.ebi.ac.uk/chembl/compound_report_card/{cid}"
    source = ev.get("label_source", "none")
    links = [dmc.Anchor(dmc.Badge("🔗 ChEMBL", variant="light", color="blue", size="xs"), href=chembl_url, target="_blank")]
    if source in ("both", "ct_only"):
        links.insert(0, dmc.Anchor(dmc.Badge("🔗 CT.gov", variant="light", color="cyan", size="xs"),
                                    href=f"https://clinicaltrials.gov/search?intr={cid}", target="_blank"))

    # Variant evidence (compound-specific)
    var_ev = VARIANT_EVIDENCE.get(cid)
    variant_card = None
    if var_ev:
        variant_card = dmc.Paper([
            dmc.Text(f"Variant: {var_ev['variant']}", size="xs", style={"color": COLORS["accent"]}),
            dmc.Text(f"Response: {var_ev['response']}", size="xs"),
            dmc.Text(f"Source: {var_ev['source']}", size="xs", c="dimmed", style={"fontSize": "10px"}),
        ], style={"background": COLORS["bg_tertiary"], "borderRadius": "6px", "padding": "8px"})

    return dmc.Stack([
        # Header
        dmc.Text(cid, size="sm", fw=600, ff="monospace", style={"color": COLORS["text_primary"]}),
        dmc.Group([
            dmc.Badge(f"rank_score {c.get('rank_score', 0):.4f}", color="cyan", variant="light", size="sm"),
            dmc.Badge(pm.upper(), variant="light", size="sm",
                      style={"color": MOD_COLORS.get(pm, COLORS["text_secondary"])}),
            dmc.Badge(f"Target: {target or 'Unknown'}", variant="light", color="gray", size="sm"),
            *([dmc.Badge(
                {"chembl_mechanism": "FDA/Clinical", "kegg_moa": "KEGG", "pic50": "pIC50",
                 "pic50_ambiguous": "⚠ Ambiguous", "unmapped": "Unknown"}.get(
                    _TARGET_MAP.get(normalize_compound_id(cid), {}).get("target_source_type", "unmapped"), "Unknown"),
                color={"chembl_mechanism": "green", "kegg_moa": "blue", "pic50": "gray",
                       "pic50_ambiguous": "yellow", "unmapped": "red"}.get(
                    _TARGET_MAP.get(normalize_compound_id(cid), {}).get("target_source_type", "unmapped"), "gray"),
                variant="light", size="xs",
            )] if target else []),
        ], gap=4),

        # Risk Radar
        risk_radar(c, unc, ev),

        # Structure + Scaffold
        molecule_2d(smiles=_SMILES.get(cid.upper()) or _SMILES.get(cid)),
        _scaffold_section(cid),

        # Evidence
        dmc.Paper([
            dmc.Text(t("evidence"), size="xs", fw=500, mb=4),
            dmc.SimpleGrid(cols=2, spacing=4, children=[
                dmc.Stack([dmc.Text("Phase", size="xs", c="dimmed", style={"fontSize": "10px"}),
                           dmc.Text(f"Phase {ev.get('phase', '—')}" if ev.get("phase") else "—", size="sm")], gap=0),
                dmc.Stack([dmc.Text("Tier", size="xs", c="dimmed", style={"fontSize": "10px"}),
                           dmc.Text(str(ev.get("tier", "—")), size="sm")], gap=0),
            ]),
            dmc.Group(links, gap=4, mt=6),
        ], style={"background": COLORS["bg_tertiary"], "borderRadius": "8px", "padding": "10px"}, mt=4),

        # Variant evidence (compound-specific)
        variant_card if variant_card else html.Div(),

        # D1: Essentiality
        _essentiality_section(target),

        # D4: Variant evidence (gene-based)
        dmc.Accordion([dmc.AccordionItem(value="variant-ev", children=[
            dmc.AccordionControl(dmc.Text("Actionable Variants", size="xs", fw=500)),
            dmc.AccordionPanel(_variant_section(target)),
        ])], variant="separated", radius="md"),

        # D2: Cell lines
        dmc.Accordion([dmc.AccordionItem(value="cell-lines", children=[
            dmc.AccordionControl(dmc.Text(t("experiment_plan"), size="xs", fw=500)),
            dmc.AccordionPanel(_cell_line_section(target)),
        ])], variant="separated", radius="md"),

        # Copilot
        copilot_panel(c, unc),

        # Adjudication
        dmc.Group([
            dmc.Button(t("confirm"), id="adj-confirm-btn", color="green", variant="outline", size="xs", style={"flex": 1}),
            dmc.Button(t("review"), id="adj-review-btn", color="yellow", variant="outline", size="xs", style={"flex": 1}),
            dmc.Button(t("block"), id="adj-block-btn", color="red", variant="outline", size="xs", style={"flex": 1}),
        ], grow=True, gap="xs", mt=4),
    ], gap=6)

def _build_right_panel(c: dict):
    """Right: radar → uncertainty → counterfactual → SHAP → modality → AWS."""
    cid = c.get("compound_id", "—")
    unc = _UNCERTAINTY.get(cid, {})
    cf = get_counterfactual(cid)

    prob = c.get("prob", 0)
    ts = c.get("total_score", 0)
    rs = c.get("rank_score", 0)
    formula = f"rank_score = 0.7 × {prob:.3f} + 0.3 × {ts:.3f} = {rs:.4f}"

    # Uncertainty
    std = unc.get("std", 0)
    seeds = unc.get("seeds", {})
    var_color = "green" if std < 0.05 else "yellow" if std <= 0.1 else "red"
    var_label = "✓ Low" if std < 0.05 else "△ Moderate" if std <= 0.1 else "⚠ High"
    seed_text = " | ".join(f"s{s}: {v:.3f}" for s, v in sorted(seeds.items())) if seeds else "No seed data"

    uncertainty_panel = dmc.Paper([
        dmc.Group([
            dmc.Text(f"prob: {unc.get('mean', prob):.3f} ± {std:.3f}", size="sm", fw=500,
                     style={"fontVariantNumeric": "tabular-nums"}),
            dmc.Badge(var_label, color=var_color, variant="light", size="xs"),
        ], gap=8),
        dmc.Text(seed_text, size="xs", c="dimmed", style={"fontSize": "10px", "marginTop": "4px"}),
    ], style={"background": COLORS["bg_tertiary"], "borderRadius": "8px", "padding": "8px"})

    # Counterfactual
    cf_content = html.Div()
    if cf:
        gap = cf.get("gap", 0)
        if cf.get("in_top10"):
            cf_content = dmc.Badge("✓ Already in Top-10", color="green", variant="light", size="sm")
        else:
            cf_content = dmc.Text(
                f"Top-10 gap: {gap:+.4f} (threshold: {cf['top10_threshold']:.4f})",
                size="xs", style={"fontSize": "11px", "fontVariantNumeric": "tabular-nums"},
            )

    # Modality comparison
    mod_rows = []
    for m in _MODS:
        score = c.get(f"{m}_score", 0)
        eligible = c.get(f"{m}_eligible", False)
        gate = c.get(f"{m}_gate_reason")
        conf = c.get(f"{m}_confidence", "—")
        conf_color = {"high": "green", "medium": "yellow", "low": "red"}.get(conf, "gray")
        mod_rows.append(dmc.TableTr([
            dmc.TableTd(dmc.Text(_MOD_LABELS.get(m, m), fw=500, size="xs",
                                  style={"color": MOD_COLORS.get(m, COLORS["text_primary"])})),
            dmc.TableTd(f"{score:.3f}", style={"textAlign": "right", "fontVariantNumeric": "tabular-nums"}),
            dmc.TableTd(dmc.Badge("✓" if eligible else "✗", color="green" if eligible else "red", variant="light", size="xs")),
            dmc.TableTd(dmc.Text(gate or "—", size="xs", c="dimmed", style={"fontSize": "10px", "maxWidth": "180px"}, lineClamp=1)),
            dmc.TableTd(dmc.Badge(conf, color=conf_color, variant="light", size="xs")),
        ]))

    return dmc.Stack([
        dmc.Paper([
            dmc.Text("5-Modality Radar", size="sm", fw=500, mb=4),
            radar_chart(c, height=260),
            dmc.Text(formula, size="xs", ff="monospace", c="dimmed", ta="center", mt=4, style={"fontSize": "11px"}),
            dmc.Text(c.get("rationale", ""), size="xs", c="dimmed", mt=4, style={"fontSize": "11px"}),
        ], style=card_style(padding="12px")),
        uncertainty_panel,
        cf_content,
        dmc.Paper([
            dmc.Text("SHAP Top-5 (Global)", size="sm", fw=500, mb=4),
            shap_bars(SHAP_TOP5),
            dmc.Text("Global SHAP · XGBoost proxy", size="xs", c="dimmed", style={"fontSize": "10px", "marginTop": "4px"}),
        ], style=card_style(padding="12px")),
        dmc.Paper([
            dmc.Text(t("modality_comparison"), size="sm", fw=500, mb=8),
            dmc.Table([
                dmc.TableThead(dmc.TableTr([
                    dmc.TableTh("Modality"), dmc.TableTh("Score", style={"textAlign": "right"}),
                    dmc.TableTh("Elig."), dmc.TableTh("Gate"), dmc.TableTh("Conf."),
                ])),
                dmc.TableTbody(mod_rows),
            ], striped=True, withTableBorder=True, withColumnBorders=False, style={"fontSize": "11px"}),
        ], style=card_style(padding="12px")),
        inference_meta_panel(),
        dmc.Paper([
            dmc.Text(t("pipeline_lineage"), size="xs", fw=500, mb=4),
            lineage_timeline(),
        ], style=card_style(padding="10px")),
    ], gap=12)

# ── Layout (function-based for URL query param) ──────────────────────────
_default = get_ranking_for_modality(top_n=1)
_default_cid = _default[0]["compound_id"] if _default else "CHEMBL3353410"


def layout(compound=None, **kwargs):
    """Explorer layout. Reads ?compound= from URL."""
    cid = compound if compound else _default_cid
    detail = get_compound_detail(cid)
    if not detail:
        detail = get_compound_detail(_default_cid)
        cid = _default_cid

    return dmc.Stack([
        dmc.Paper(
            dmc.Group([
                dmc.TextInput(
                    id="explorer-compound-input", label="Compound ID",
                    placeholder="CHEMBL3353410", value=cid, size="xs",
                    style={"width": "240px"},
                    styles={"input": {"background": COLORS["bg_tertiary"], "color": COLORS["text_primary"],
                                      "border": f"1px solid {COLORS['border']}"}},
                ),
                dmc.Button("Load", id="explorer-load-btn", size="xs", color="cyan",
                           style={"alignSelf": "flex-end"}),
            ], gap="md", align="flex-end"),
            style=card_style(padding="10px"),
        ),
        html.Div(id="explorer-content", children=[
            dmc.Grid([
                dmc.GridCol(dmc.Paper(_build_left_panel(detail), style=card_style(padding="14px")), span=5),
                dmc.GridCol(_build_right_panel(detail), span=7),
            ], gutter="md"),
        ]),
        dmc.Alert(title="연구용 도구", children=t("disclaimer"), color="gray", variant="light"),
    ], gap="md")


@callback(
    Output("explorer-content", "children"),
    Input("explorer-load-btn", "n_clicks"),
    Input("explorer-compound-input", "value"),
    prevent_initial_call=True,
)
def _load_compound(n_clicks, compound_id):
    if not compound_id or not compound_id.strip():
        return dmc.Alert("Compound ID를 입력하세요.", color="red")
    detail = get_compound_detail(compound_id.strip())
    if not detail:
        return dmc.Alert(f"{compound_id} not found.", color="red")
    return dmc.Grid([
        dmc.GridCol(dmc.Paper(_build_left_panel(detail), style=card_style(padding="14px")), span=5),
        dmc.GridCol(_build_right_panel(detail), span=7),
    ], gutter="md")


@callback(
    Output("decisions-store", "data"),
    Input("adj-confirm-btn", "n_clicks"),
    Input("adj-review-btn", "n_clicks"),
    Input("adj-block-btn", "n_clicks"),
    State("explorer-compound-input", "value"),
    State("decisions-store", "data"),
    prevent_initial_call=True,
)
def _decide_compound(n_confirm, n_review, n_block, compound_id, decisions):
    if not compound_id:
        return decisions or {}
    decisions = decisions or {}
    cid = compound_id.strip().upper()
    triggered = dash.ctx.triggered_id
    if triggered == "adj-confirm-btn":
        decisions[cid] = "confirmed"
    elif triggered == "adj-review-btn":
        decisions[cid] = "review"
    elif triggered == "adj-block-btn":
        decisions[cid] = "blocked"
    return decisions
