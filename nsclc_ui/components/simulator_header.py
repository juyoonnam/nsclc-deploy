"""
Simulator header matching the Pathway Map atlas chrome.
"""

from dash import html


def render_simulator_header(
    title: str = "Simulator — Triple-Mode Validation Engine",
) -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Button("☰", className="atlas-icon-button", title="Menu"),
                    html.Div("🧬", className="atlas-dna-mark", title="NSCLC Atlas"),
                    html.Div(title, className="atlas-title simulator-title"),
                ],
                className="atlas-topbar-left",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("한", className="atlas-lang-muted"),
                            html.Span(" / "),
                            html.Span("EN", className="atlas-lang-active"),
                        ],
                        className="atlas-lang",
                    ),
                    html.Button("□", className="atlas-icon-button", title="Fullscreen"),
                ],
                className="atlas-topbar-right",
                style={"gap": "18px"},
            ),
        ],
        className="atlas-topbar simulator-topbar",
    )
