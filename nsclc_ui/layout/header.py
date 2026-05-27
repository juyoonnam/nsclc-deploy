"""NSCLC Insight Engine v3.0 — Global header bar (chat-first redesign).

v3.0 변경 (kiro-redesign-v3):
- 64px 고정 height
- 좌측: 기존 N 로고 + "NSCLC Insight Engine" (1회만)
- 우측: status 배지 5개 (home _hero에서 이전) + about nav 3개
- nav는 실제 route 확인된 것만: /library, /model-card, GitHub
- 기존 callback/id 없으므로 변경 영향 없음

기존 nav(_MAIN_TABS 빈 리스트)는 v2.4부터 비어있던 상태 유지.
새 이미지 자산 없음 — 기존 N 박스 아이콘 그대로 사용.
"""

import dash
from dash import html
import dash_mantine_components as dmc


# ── Navigation Config ─────────────────────────────────────────────────────────

_MAIN_TABS: list = []

_ABOUT_ITEMS = [
    (("약물 라이브러리", "Drug Library"), "/library"),
    (("모델 카드", "Model Card"), "/model-card"),
    (("GitHub", "GitHub"), "https://github.com/juyoonnam/nsclc-deploy"),
]

# Status 배지 — 기존 home._hero()에서 이전. 화면 어디에서나 동일하게 노출.
_STATUS_BADGES = [
    ("Champion E6", "violet"),
    ("PR-AUC 0.1383", "blue"),
    ("22 MCP Tools", "teal"),
    ("Model B ✓", "green"),
    ("Streaming ✓", "grape"),
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
        className="header-nav-link",
    )


def _status_badge(label: str, color: str):
    return dmc.Badge(
        label,
        color=color,
        variant="light",
        size="sm",
        className="status-badge",
    )


# ── Main Header ──────────────────────────────────────────────────────────────


def header():
    """v3.0 헤더: 64px 고정. 좌측 브랜드 + 우측 status badges + about links."""
    logo_box = dmc.Center(
        dmc.Text("N", size="xs", fw=700, c="var(--accent-purple)"),
        className="app-brand-icon",
    )

    left = html.A(
        dmc.Group(
            [
                logo_box,
                dmc.Text(
                    "NSCLC Insight Engine",
                    fw=700,
                    c="var(--nsclc-text-primary)",
                    className="app-brand-text",
                ),
            ],
            gap="xs",
            className="app-brand-group",
        ),
        href="/",
        className="app-brand",
    )

    badges = html.Div(
        [_status_badge(label, color) for label, color in _STATUS_BADGES],
        className="header-badges",
    )

    nav_links = html.Div(
        [_about_link(label_pair, href) for label_pair, href in _ABOUT_ITEMS],
        className="header-nav",
    )

    right = html.Div(
        [badges, nav_links],
        className="header-right",
    )

    return html.Div(
        [left, right],
        className="nsclc-header",
    )


# v2.3의 active nav highlight callback은 _MAIN_TABS가 비어있으므로 제거됨.
