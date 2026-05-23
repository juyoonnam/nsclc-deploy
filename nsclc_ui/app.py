"""
NSCLC Insight Engine — Dash application entry-point.

Uses:
  - dash-mantine-components (dmc) for UI primitives
  - dash.page_registry (Pages) for multi-tab routing
"""

import dash
import os
from dash import dcc, html
import dash_mantine_components as dmc

from nsclc_ui.layout.theme import MANTINE_THEME

# ---------------------------------------------------------------------------
# Header / Footer — will be implemented in layout/header.py & layout/footer.py.
# Until those files exist we fall back to lightweight placeholders.
# ---------------------------------------------------------------------------
try:
    from nsclc_ui.layout.header import header  # noqa: F401
except ImportError:
    def header():
        """Placeholder header until layout/header.py is created."""
        return dmc.Group(
            dmc.Text(
                "NSCLC Insight Engine",
                fw=500,
                size="lg",
                style={"padding": "12px 0"},
            ),
            justify="space-between",
            style={"borderBottom": "0.5px solid rgba(0,0,0,0.08)"},
        )

try:
    from nsclc_ui.layout.footer import footer  # noqa: F401
except ImportError:
    def footer():
        """Placeholder footer until layout/footer.py is created."""
        return dmc.Text(
            "© 2025 NSCLC Insight Engine · Internal use only",
            size="xs",
            c="dimmed",
            ta="center",
            style={"padding": "24px 0 12px"},
        )

# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------
app = dash.Dash(
    __name__,
    use_pages=True,
    pages_folder="tabs",          # nsclc_ui/tabs/ 아래 page 모듈 자동 탐색
    suppress_callback_exceptions=True,
    title="NSCLC Insight Engine",
    update_title=None,
)

# ---------------------------------------------------------------------------
# Root layout
# ---------------------------------------------------------------------------
app.layout = dmc.MantineProvider(
    id="mantine-provider",
    theme=MANTINE_THEME,
    defaultColorScheme="dark",
    forceColorScheme="dark",
    children=[
        dcc.Location(id="url", refresh="callback-nav"),
        dcc.Store(id="lang-store", data="ko", storage_type="local"),
        dcc.Store(id="decisions-store", data={}),
        dmc.Container(
            id="app-shell-container",
            fluid=True,
            children=[
                html.Div(id="global-header-shell", children=header()),
                dash.page_container,
                html.Div(id="global-footer-shell", children=footer()),
            ],
            style={"paddingTop": "8px", "paddingBottom": "24px", "paddingLeft": "40px", "paddingRight": "40px", "maxWidth": "1800px", "margin": "0 auto"},
        ),
        html.Div(id="ui-sync-dummy", style={"display": "none"}),
    ],
)


# ---------------------------------------------------------------------------
# Dev entry-point
# ---------------------------------------------------------------------------
server = app.server  # expose for gunicorn / production WSGI

# Lang toggle removed in v2.2 (Korean fixed)
# Keep lang-store for backward compatibility but default to "ko"


@dash.callback(
    dash.Output("app-shell-container", "style"),
    dash.Output("global-header-shell", "style"),
    dash.Output("global-footer-shell", "style"),
    dash.Input("url", "pathname"),
)
def _apply_page_shell(pathname):
    """Give atlas-style pages their own full-screen shell."""
    if pathname in {"/pathway"}:
        return (
            {
                "paddingTop": "0",
                "paddingBottom": "0",
                "paddingLeft": "0",
                "paddingRight": "0",
                "maxWidth": "100%",
            },
            {},
            {"display": "none"},
        )
    return (
        {"paddingTop": "8px", "paddingBottom": "24px"},
        {},
        {},
    )


# ── v2.2: /simulator → /cell-line redirect ──
@dash.callback(
    dash.Output("url", "pathname", allow_duplicate=True),
    dash.Input("url", "pathname"),
    prevent_initial_call=True,
)
def _redirect_simulator(pathname):
    if pathname == "/simulator":
        return "/cell-line"
    return dash.no_update


# Apply fixed dark theme and language marker to <html> for CSS variables and language visibility
dash.clientside_callback(
    """
    function(lang) {
      const root = document.documentElement;
      const safeLang = (lang === "en" || lang === "ko") ? lang : "ko";
      root.setAttribute("data-theme", "dark");
      root.setAttribute("data-lang", safeLang);
      return "";
    }
    """,
    dash.Output("ui-sync-dummy", "children"),
    dash.Input("lang-store", "data"),
)


# ── BUG1 fix: URL → Explorer Input 동기화 ──
@dash.callback(
    dash.Output("explorer-compound-input", "value"),
    dash.Input("url", "search"),
    prevent_initial_call=True,
)
def _sync_explorer_from_url(search):
    """URL ?compound= 변경 시 Explorer Input 값 교체 + 자동 로드."""
    if not search:
        return dash.no_update
    from urllib.parse import parse_qs
    qs = parse_qs(search.lstrip("?"))
    compound = qs.get("compound", [None])[0]
    if compound:
        return compound.strip().upper()
    return dash.no_update


if __name__ == "__main__":
    debug_mode = os.environ.get("DASH_DEBUG", "false").lower() == "true"
    app.run(debug=debug_mode, host="0.0.0.0", port=8050)
