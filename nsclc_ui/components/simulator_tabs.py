"""
Triple-mode tab strip for the Simulator page.
"""

from dash import html


SIMULATOR_MODES = [
    {
        "value": "library",
        "icon": "▤",
        "label": "① Library",
    },
    {
        "value": "cell_line",
        "icon": "⊹",
        "label": "② Cell-line",
    },
    {
        "value": "patient",
        "icon": "♙",
        "label": "③ Patient",
    },
]


def render_simulator_tabs(active_mode: str = "library") -> html.Div:
    return html.Div(
        [
            html.Button(
                [
                    html.Span(mode["icon"], className="simulator-mode-icon"),
                    html.Span(mode["label"], className="simulator-mode-label"),
                ],
                id={"type": "simulator-mode-tab", "mode": mode["value"]},
                n_clicks=0,
                className=(
                    "simulator-mode-tab is-active"
                    if mode["value"] == active_mode
                    else "simulator-mode-tab"
                ),
                title=mode["label"],
            )
            for mode in SIMULATOR_MODES
        ],
        className="simulator-mode-tabs",
    )
