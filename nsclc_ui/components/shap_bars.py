"""
NSCLC Insight Engine — Horizontal SHAP contribution bars (pure HTML/dmc).
"""

from dash import html
import dash_mantine_components as dmc

from nsclc_ui.layout.theme import COLORS


def shap_bars(items: list):
    """Render a diverging bar chart for SHAP contributions.

    Parameters
    ----------
    items : list[dict]
        Each dict has ``"feature"`` (str) and ``"contribution"`` (float).
        Positive values extend right from center; negative extend left.
    """
    if not items:
        return dmc.Text("No SHAP data", size="xs", c="dimmed")

    abs_max = max(abs(it["contribution"]) for it in items) or 1.0

    rows = []
    for it in items:
        feat = it["feature"]
        val = it["contribution"]
        pct = abs(val) / abs_max * 40  # max 40% of track width

        is_pos = val >= 0
        bar_color = COLORS["success_text"] if is_pos else COLORS["danger_text"]

        # Bar sits in a flex track; positive goes right of center, negative left
        if is_pos:
            bar_style = {
                "position": "absolute",
                "left": "50%",
                "top": "0",
                "height": "100%",
                "width": f"{pct}%",
                "background": bar_color,
                "borderRadius": "0 2px 2px 0",
            }
        else:
            bar_style = {
                "position": "absolute",
                "right": "50%",
                "top": "0",
                "height": "100%",
                "width": f"{pct}%",
                "background": bar_color,
                "borderRadius": "2px 0 0 2px",
            }

        track = html.Div(
            [
                # background track
                html.Div(style={
                    "position": "absolute",
                    "inset": "0",
                    "background": COLORS["bg_tertiary"],
                    "borderRadius": "2px",
                }),
                # center divider
                html.Div(style={
                    "position": "absolute",
                    "left": "50%",
                    "top": "0",
                    "width": "0.5px",
                    "height": "100%",
                    "background": COLORS["border_strong"],
                }),
                # value bar
                html.Div(style=bar_style),
            ],
            style={
                "position": "relative",
                "flex": "1",
                "height": "8px",
                "margin": "0 8px",
            },
        )

        row = html.Div(
            [
                # feature name
                html.Div(
                    feat,
                    style={
                        "width": "72px",
                        "minWidth": "72px",
                        "fontSize": "11px",
                        "color": COLORS["text_secondary"],
                        "overflow": "hidden",
                        "textOverflow": "ellipsis",
                        "whiteSpace": "nowrap",
                    },
                ),
                track,
                # numeric value
                html.Div(
                    f"{val:+.3f}",
                    style={
                        "width": "40px",
                        "minWidth": "40px",
                        "fontSize": "11px",
                        "textAlign": "right",
                        "fontVariantNumeric": "tabular-nums",
                        "color": COLORS["text_primary"],
                    },
                ),
            ],
            style={
                "display": "flex",
                "alignItems": "center",
                "marginBottom": "4px",
            },
        )
        rows.append(row)

    return html.Div(rows)
