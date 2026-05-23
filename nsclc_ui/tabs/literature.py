"""
Literature Explorer tab (placeholder)
"""

import dash
from dash import html


dash.register_page(
    __name__,
    path="/literature",
    name="Literature",
    title="NSCLC Insight Engine",
    order=7,
)


def layout():
    return html.Div(
        [
            html.H2(
                "Literature Explorer",
                style={"margin": "0 0 8px", "fontWeight": 500, "fontSize": "22px"},
            ),
            html.P(
                "논문 탐색 화면은 현재 분리 작업 중입니다.",
                style={"margin": "0 0 6px", "fontSize": "14px", "color": "#94A3B8"},
            ),
            html.P(
                "임시로 Pathway Map의 AI 논문 분석 섹션을 사용해 주세요.",
                style={"margin": 0, "fontSize": "13px", "color": "#94A3B8"},
            ),
        ],
        style={
            "background": "#0a0e1a",
            "border": "1px solid #334155",
            "borderRadius": "12px",
            "padding": "24px",
            "minHeight": "520px",
            "color": "#E2E8F0",
        },
    )

