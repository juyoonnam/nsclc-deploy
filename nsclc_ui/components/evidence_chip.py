"""
NSCLC Insight Engine — Evidence chip component.

Renders a compact inline chip for clinical-trial / literature references.
Example output:  NCT04009317 · Phase III · NSCLC · ALK+
"""

import dash_mantine_components as dmc

from nsclc_ui.layout.theme import COLORS, FONT_MONO


def evidence_chip(source: str, identifier: str, note: str = ""):
    """Compact evidence reference chip.

    Parameters
    ----------
    source : str
        One of "NCT", "PMID", "DC" (DrugCentral).
    identifier : str
        The ID string (e.g. "NCT04009317", "PMID:34521432").
    note : str, optional
        Extra context shown after the identifier (e.g. "Phase III · NSCLC · ALK+").
    """

    children = [
        dmc.Text(
            identifier,
            span=True,
            style={
                "fontFamily": FONT_MONO,
                "color": COLORS["info_text"],
                "fontSize": "11px",
                "fontWeight": 500,
            },
        ),
    ]

    if note:
        children.append(
            dmc.Text(
                f" · {note}",
                span=True,
                style={
                    "color": COLORS["text_secondary"],
                    "fontSize": "11px",
                },
            ),
        )

    return dmc.Paper(
        children=children,
        style={
            "background": COLORS["bg_secondary"],
            "borderRadius": "4px",
            "padding": "6px 8px",
            "fontSize": "11px",
            "display": "inline-block",
        },
    )
