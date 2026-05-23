"""
Risk Radar — 4-axis signal light for compound risk assessment.
"""

from dash import html
import dash_mantine_components as dmc

from nsclc_ui.layout.theme import COLORS

_MODS = ["drug", "adc", "protac", "glue", "rlt"]


def _signal(color: str, label: str, detail: str = ""):
    """Single signal light: green/yellow/red circle + label."""
    c = {"green": COLORS["success_text"], "yellow": COLORS["warning_text"], "red": COLORS["danger_text"]}
    return html.Div([
        html.Div(style={
            "width": "12px", "height": "12px", "borderRadius": "50%",
            "background": c.get(color, COLORS["text_tertiary"]),
            "flexShrink": 0,
        }),
        dmc.Stack([
            dmc.Text(label, size="xs", fw=500, style={"fontSize": "11px", "color": COLORS["text_primary"]}),
            dmc.Text(detail, size="xs", style={"fontSize": "10px", "color": COLORS["text_tertiary"]}) if detail else None,
        ], gap=0),
    ], style={"display": "flex", "gap": "6px", "alignItems": "flex-start"})


def risk_radar(compound: dict, uncertainty: dict | None = None, evidence: dict | None = None):
    """Build 4-axis risk radar panel.

    Args:
        compound: from get_compound_detail()
        uncertainty: from load_uncertainty().get(cid)
        evidence: from load_evidence_map().get(cid)
    """
    axes = []
    warnings = []

    # 1. Gate Risk
    n_fail = sum(1 for m in _MODS if not compound.get(f"{m}_eligible", False))
    if n_fail <= 1:
        axes.append(_signal("green", "Gate Risk", f"{5 - n_fail}/5 pass"))
    elif n_fail <= 3:
        axes.append(_signal("yellow", "Gate Risk", f"{5 - n_fail}/5 pass"))
        warnings.append(f"Gate: {n_fail} modalities failed")
    else:
        axes.append(_signal("red", "Gate Risk", f"Only {5 - n_fail}/5 pass"))
        warnings.append(f"Gate: {n_fail}/5 failed")

    # 2. PAINS Risk
    pains = compound.get("pains_flag") if "pains_flag" in compound else None
    if pains is True:
        axes.append(_signal("red", "PAINS", "Alert detected"))
        warnings.append("PAINS structural alert")
    elif pains is False:
        axes.append(_signal("green", "PAINS", "Clean"))
    else:
        axes.append(_signal("yellow", "PAINS", "Unknown"))

    # 3. Data Confidence
    ev = evidence or {}
    if ev.get("is_positive"):
        axes.append(_signal("green", "Data", f"Positive · {ev.get('tier', '?')}"))
    elif ev.get("label_source") and ev["label_source"] != "none":
        axes.append(_signal("yellow", "Data", f"Source: {ev['label_source']}"))
    else:
        axes.append(_signal("red", "Data", "No evidence"))
        warnings.append("No supporting evidence")

    # 4. Model Uncertainty
    unc = uncertainty or {}
    std = unc.get("std", None)
    if std is not None:
        if std < 0.05:
            axes.append(_signal("green", "Uncertainty", f"σ={std:.3f}"))
        elif std <= 0.1:
            axes.append(_signal("yellow", "Uncertainty", f"σ={std:.3f}"))
            warnings.append(f"Moderate variance (σ={std:.3f})")
        else:
            axes.append(_signal("red", "Uncertainty", f"σ={std:.3f}"))
            warnings.append(f"High variance (σ={std:.3f})")
    else:
        axes.append(_signal("yellow", "Uncertainty", "No OOF data"))

    # Overall verdict
    has_red = any("red" in str(a) for a in warnings) or len(warnings) > 1
    if not warnings:
        verdict = dmc.Text("✓ Low Risk — Proceed to experiment", size="xs", fw=500,
                           style={"color": COLORS["success_text"], "fontSize": "11px"})
    elif has_red:
        verdict = dmc.Text(f"⚠ {'; '.join(warnings)}", size="xs", fw=500,
                           style={"color": COLORS["danger_text"], "fontSize": "11px"})
    else:
        verdict = dmc.Text("△ Review recommended", size="xs", fw=500,
                           style={"color": COLORS["warning_text"], "fontSize": "11px"})

    return dmc.Paper([
        dmc.Text("Risk Radar", size="xs", fw=500, mb=6),
        dmc.SimpleGrid(cols=4, spacing="xs", children=[
            html.Div(a) for a in axes
        ]),
        html.Div(verdict, style={"marginTop": "8px"}),
    ], style={
        "background": COLORS["bg_tertiary"],
        "border": f"1px solid {COLORS['border']}",
        "borderRadius": "8px",
        "padding": "10px",
    })
