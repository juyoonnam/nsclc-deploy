"""
NSCLC Insight Engine — 2D molecule image via RDKit or SVG placeholder.
"""

import base64
import io
import logging

from dash import html
import dash_mantine_components as dmc

from nsclc_ui.layout.theme import COLORS

logger = logging.getLogger(__name__)

# Placeholder SVG (fallback)
_SVG_PLACEHOLDER = (
    "<svg xmlns='http://www.w3.org/2000/svg' width='150' height='120' viewBox='0 0 150 120'>"
    "<polygon points='30,25 50,15 70,25 70,45 50,55 30,45' stroke='#5A6A7A' stroke-width='1.2' fill='none'/>"
    "<polygon points='70,25 90,15 110,25 110,45 90,55 70,45' stroke='#5A6A7A' stroke-width='1.2' fill='none'/>"
    "<polygon points='50,55 70,45 90,55 90,75 70,85 50,75' stroke='#5A6A7A' stroke-width='1.2' fill='none'/>"
    "<text x='48' y='42' font-size='10' fill='#4DABF7' font-family='monospace'>N</text>"
    "<text x='108' y='38' font-size='10' fill='#4DABF7' font-family='monospace'>F</text>"
    "<text x='88' y='82' font-size='10' fill='#4DABF7' font-family='monospace'>Cl</text>"
    "</svg>"
)


def _smiles_to_img_src(smiles: str, size: tuple = (250, 180)) -> str | None:
    """Convert SMILES to SVG data URI via RDKit."""
    try:
        from rdkit import Chem
        from rdkit.Chem.Draw import rdMolDraw2D
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        drawer = rdMolDraw2D.MolDraw2DSVG(size[0], size[1])
        drawer.drawOptions().clearBackground = False
        drawer.DrawMolecule(mol)
        drawer.FinishDrawing()
        svg = drawer.GetDrawingText()
        # Encode as data URI
        import urllib.parse
        encoded = urllib.parse.quote(svg)
        return f"data:image/svg+xml,{encoded}"
    except Exception as e:
        logger.warning("RDKit SVG failed: %s", e)
        return None


def molecule_2d(smiles: str | None = None, placeholder: bool = True):
    """Render 2D molecule. Uses RDKit if SMILES provided, else SVG placeholder."""
    if smiles:
        src = _smiles_to_img_src(smiles)
        if src:
            return dmc.Paper(
                children=[
                    html.Div(
                        html.Img(src=src, style={"maxWidth": "250px", "maxHeight": "180px"}),
                        style={"display": "flex", "justifyContent": "center", "alignItems": "center", "minHeight": "120px"},
                    ),
                    dmc.Text("RDKit 2D (SVG)", size="xs", c="dimmed", ta="center", mt=4, style={"fontSize": "10px"}),
                ],
                style={"background": COLORS["bg_tertiary"], "borderRadius": "8px", "padding": "8px"},
            )

    # Fallback: SVG placeholder
    return dmc.Paper(
        children=[
            html.Div(
                html.Img(
                    src="data:image/svg+xml;utf8," + _SVG_PLACEHOLDER,
                    style={"width": "150px", "height": "120px"},
                ),
                style={"display": "flex", "justifyContent": "center", "alignItems": "center", "height": "120px"},
            ),
            dmc.Text("placeholder · SMILES 없음", size="xs", c="dimmed", ta="center", mt=4, style={"fontSize": "10px"}),
        ],
        style={"background": COLORS["bg_tertiary"], "borderRadius": "8px", "padding": "8px"},
    )
