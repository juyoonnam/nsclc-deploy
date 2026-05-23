"""Floating chatbot popup for the Pathway Map route."""
from __future__ import annotations

from urllib.parse import quote

from dash import dcc, html
import dash_mantine_components as dmc

CHAT_POPUP_OPEN_STORE_ID = "pathway-chat-popup-open-store"
CHAT_POPUP_HISTORY_STORE_ID = "pathway-chat-popup-history-store"
CHAT_POPUP_FAB_ID = "pathway-chat-fab"
CHAT_POPUP_CLOSE_ID = "pathway-chat-popup-close"
CHAT_POPUP_BACKDROP_ID = "pathway-chat-popup-backdrop"
CHAT_POPUP_SHELL_ID = "pathway-chat-popup-shell"
CHAT_POPUP_ESCAPE_LISTENER_ID = "pathway-chat-popup-escape-listener"


def _chat_icon():
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' "
        "fill='none' stroke='white' stroke-width='2' stroke-linecap='round' "
        "stroke-linejoin='round'>"
        "<path d='M21 11.5a8.38 8.38 0 0 1-.9 3.8 "
        "8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9 "
        "L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 "
        "8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5 "
        "a8.48 8.48 0 0 1 8 8v.5z'/>"
        "</svg>"
    )
    return html.Img(
        src=f"data:image/svg+xml;utf8,{quote(svg)}",
        alt="",
        className="pathway-chat-fab-icon",
        **{"aria-hidden": "true"},
    )


def chatbot_popup(children):
    """Render a fixed FAB plus an off-canvas popup containing chatbot UI."""
    return html.Div(
        [
            dcc.Store(id=CHAT_POPUP_OPEN_STORE_ID, data=False, storage_type="memory"),
            dcc.Store(id=CHAT_POPUP_HISTORY_STORE_ID, data=[], storage_type="memory"),
            html.Div(id=CHAT_POPUP_ESCAPE_LISTENER_ID, style={"display": "none"}),
            dmc.Tooltip(
                html.Button(
                    [_chat_icon(), html.Span("AI", className="pathway-chat-fab-label")],
                    id=CHAT_POPUP_FAB_ID,
                    n_clicks=0,
                    type="button",
                    className="pathway-chat-fab",
                    title="AI 가설 챗봇",
                    **{"aria-label": "AI 가설 챗봇"},
                ),
                label="AI 가설 챗봇",
                position="left",
                withArrow=True,
            ),
            html.Div(
                [
                    html.Button(
                        "",
                        id=CHAT_POPUP_BACKDROP_ID,
                        n_clicks=0,
                        type="button",
                        className="pathway-chat-popup-backdrop",
                        **{"aria-label": "Close chatbot"},
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Span("Ask anything", className="pathway-chat-popup-title"),
                                            html.Span(
                                                "Pathway context assistant",
                                                className="pathway-chat-popup-subtitle",
                                            ),
                                        ],
                                        className="pathway-chat-popup-heading",
                                    ),
                                    html.Button(
                                        "×",
                                        id=CHAT_POPUP_CLOSE_ID,
                                        n_clicks=0,
                                        type="button",
                                        className="pathway-chat-popup-close",
                                        title="Close",
                                        **{"aria-label": "Close chatbot"},
                                    ),
                                ],
                                className="pathway-chat-popup-header",
                            ),
                            html.Div(
                                html.Div(children, className="atlas-chat-panel pathway-chat-popup-chat"),
                                className="pathway-chat-popup-body",
                            ),
                        ],
                        className="pathway-chat-popup-panel",
                        role="dialog",
                        **{"aria-modal": "true", "aria-label": "Ask anything"},
                    ),
                ],
                id=CHAT_POPUP_SHELL_ID,
                className="pathway-chat-popup-shell",
                **{"aria-hidden": "true"},
            ),
        ],
        className="pathway-chat-popup-root",
    )
