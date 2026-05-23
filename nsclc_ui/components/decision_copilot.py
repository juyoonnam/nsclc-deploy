"""
Decision Copilot — Auto-generated adjudication draft.
"""

import dash_mantine_components as dmc

from nsclc_ui.layout.theme import COLORS

_MODS = ["drug", "adc", "protac", "glue", "rlt"]


def generate_copilot_text(compound: dict, uncertainty: dict | None = None) -> str:
    """Generate rule-based adjudication draft text."""
    cid = compound.get("compound_id", "?")
    pm = compound.get("primary_modality", "?")
    pm_score = compound.get(f"{pm}_score", 0) if pm != "?" else 0
    rs = compound.get("rank_score", 0)
    prob = compound.get("prob", 0)

    parts = []
    parts.append(f"{cid}는 {pm.upper()} 양식에 적합 (score {pm_score:.3f}).")
    
    std_text = ""
    if uncertainty:
        std = uncertainty.get("std", 0)
        std_text = f" ± {std:.3f}"
    parts.append(f"Rank score: {rs:.4f} (prob {prob:.3f}{std_text}).")

    # Gate
    n_pass = sum(1 for m in _MODS if compound.get(f"{m}_eligible", False))
    parts.append(f"Gate: {n_pass}/5 통과.")

    # Lipinski
    if compound.get("lipinski_pass"):
        parts.append("Lipinski PASS.")
    else:
        viol = compound.get("lipinski_violations", 0)
        parts.append(f"Lipinski {viol} violations.")

    # Uncertainty warning
    if uncertainty and uncertainty.get("std", 0) > 0.1:
        parts.append("⚠ 높은 예측 분산 — 추가 검증 권장.")

    return " ".join(parts)


def copilot_panel(compound: dict, uncertainty: dict | None = None):
    """Render the copilot text as a read-only textarea."""
    text = generate_copilot_text(compound, uncertainty)
    return dmc.Stack([
        dmc.Text("Decision Copilot (auto-draft)", size="xs", fw=500,
                 style={"color": COLORS["text_secondary"]}),
        dmc.Textarea(
            id="copilot-text",
            value=text,
            minRows=3,
            autosize=True,
            styles={"input": {"fontSize": "11px", "color": COLORS["text_primary"],
                              "background": COLORS["bg_tertiary"],
                              "border": f"1px solid {COLORS['border']}"}},
        ),
    ], gap=4)
