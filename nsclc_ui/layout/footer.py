"""
NSCLC Insight Engine — Global footer bar.
"""

import dash_mantine_components as dmc


def footer():
    """Minimal footer — left copyright only."""

    left = dmc.Text(
        "© NSCLC Insight Engine · SKKU AWS 바이오헬스케어 AI 아카데미 SAY 2기 5팀 · 남윤주",
        style={
            "fontSize": "11px",
            "color": "var(--nsclc-text-tertiary)",
        },
    )

    return dmc.Group(
        [left],
        justify="flex-start",
        style={
            "padding": "16px 0 8px",
            "borderTop": "1px solid var(--nsclc-border)",
            "marginTop": "24px",
        },
    )
