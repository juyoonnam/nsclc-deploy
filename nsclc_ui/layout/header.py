"""NSCLC Insight Engine v2.4 — Global header bar.

v2.4 변경: 최상단 "홈" 탭 제거. 메인 화면이 채팅이므로 nav 자체 불필요.
로고 클릭 시 / 로 이동. about links (약물 라이브러리, 모델 카드, GitHub)만 유지.

발표용 정리: 메인 nav 0개. 보조 페이지는 URL 직접 접근.
"""

import dash
from dash import html
import dash_mantine_components as dmc


# ── Navigation Config ─────────────────────────────────────────────────────────

# 메인 탭 제거 (v2.4). 빈 리스트로 유지 — 향후 nav 복원 시 항목만 추가하면 됨.
_MAIN_TABS: list = []

_ABOUT_ITEMS = [
    (("약물 라이브러리", "Drug Library"), "/library"),
    (("모델 카드", "Model Card"), "/model-card"),
    (("GitHub", "GitHub"), "https://github.com/juyoonnam/nsclc-deploy"),
]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _lang_text(ko: str, en: str):
    return html.Span(
        [
            html.Span(ko, className="lang-ko"),
            html.Span(en, className="lang-en"),
        ],
        className="lang-switch",
    )


def _about_link(label_pair: tuple[str, str], href: str):
    is_external = href.startswith("http")
    return html.A(
        _lang_text(label_pair[0], label_pair[1]),
        href=href,
        target="_blank" if is_external else None,
        style={
            "textDecoration": "none",
            "color": "var(--nsclc-text-tertiary)",
            "fontSize": "13px",
            "whiteSpace": "nowrap",
        },
    )


# ── Main Header ──────────────────────────────────────────────────────────────


def header():
    """v2.4 헤더: 로고만 + about links. 메인 nav 제거."""
    logo_box = dmc.Center(
        dmc.Text("N", size="xs", fw=700, c="var(--accent-purple)"),
        style={
            "width": "22px",
            "height": "22px",
            "borderRadius": "4px",
            "background": "var(--accent-purple-bg)",
        },
    )

    left = html.A(
        dmc.Group(
            [
                logo_box,
                dmc.Text("NSCLC Insight Engine", size="lg", fw=500,
                         c="var(--nsclc-text-primary)"),
            ],
            gap="xs",
        ),
        href="/",
        style={
            "display": "inline-flex",
            "alignItems": "center",
            "textDecoration": "none",
            "cursor": "pointer",
            "flex": "0 0 auto",
        },
    )

    about_links = dmc.Group(
        [_about_link(label_pair, href) for label_pair, href in _ABOUT_ITEMS],
        gap=12,
    )

    right = dmc.Group(
        [about_links],
        gap="md",
        style={"flex": "0 0 auto"},
    )

    # 메인 nav 없으므로 left + right만. justify=space-between 유지.
    return dmc.Group(
        [left, right],
        justify="space-between",
        align="center",
        style={
            "height": "52px",
            "padding": "0 32px",
            "borderBottom": "1px solid var(--nsclc-border)",
            "background": "var(--nsclc-bg-secondary)",
            "color": "var(--nsclc-text-primary)",
            "position": "relative",
            "zIndex": 100,
        },
    )


# v2.3의 active nav highlight callback은 _MAIN_TABS가 비어있으므로 제거됨.
