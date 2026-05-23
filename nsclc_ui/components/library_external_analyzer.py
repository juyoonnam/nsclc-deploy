"""
Library Mode — External Compound Analyzer 컴포넌트.

render_external_analyzer(): 상단 입력 UI (항상 표시, ~100px)
render_external_result(): 분석 결과 뷰 (메인 영역 교체)
"""
from __future__ import annotations

from dash import html, dcc

from nsclc_ui.components.library_colors import (
    BG_CARD,
    BG_INPUT,
    BORDER_DEFAULT,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
    TEXT_MUTED,
    PHASE_COLORS,
    PHASE_LABELS,
    XS_FG,
    ACCENT_CYAN,
    EA_BORDER,
    EA_BUTTON_BG,
    EA_BUTTON_FG,
    WARNING_BORDER,
    FONT_SIZE_CAPTION,
    FONT_SIZE_BODY,
    FONT_SIZE_HEADER,
)


# ── Main: render_external_analyzer ────────────────────────────────────────────


def render_external_analyzer() -> html.Div:
    """
    외부 화합물 분석 입력 UI (항상 표시, ~100px 높이).

    Returns:
        html.Div: cyan border 컨테이너
            - 헤더: "🧪 외부 화합물 분석"
            - 설명 텍스트 (1줄)
            - 입력 필드 (820px) + 분석 버튼 (120px) + 결과 힌트 (350px)
    """
    return html.Div(
        [
            # 헤더
            html.Div(
                "🧪 외부 화합물 분석",
                style={
                    "fontSize": f"{FONT_SIZE_HEADER}px",
                    "fontWeight": "500",
                    "color": ACCENT_CYAN,
                    "marginBottom": "4px",
                },
            ),
            # 설명
            html.Div(
                "champion 직접 적용 불가 — in-library 유사 화합물 Top-5 + Tanimoto + analog prob 표시",
                style={
                    "fontSize": f"{FONT_SIZE_CAPTION}px",
                    "color": TEXT_SECONDARY,
                    "marginBottom": "12px",
                },
            ),
            # 입력 행: input + 버튼 + 결과 힌트
            html.Div(
                [
                    # 입력 필드
                    dcc.Input(
                        id="lib-external-input",
                        type="text",
                        placeholder="PubChem CID, SMILES, InChIKey 붙여넣기...",
                        style={
                            "width": "820px",
                            "backgroundColor": BG_INPUT,
                            "border": f"1px solid {BORDER_DEFAULT}",
                            "borderRadius": "8px",
                            "padding": "10px 14px",
                            "color": TEXT_PRIMARY,
                            "fontSize": f"{FONT_SIZE_BODY}px",
                        },
                    ),
                    # 분석 버튼
                    html.Button(
                        "유사도 분석",
                        id="lib-external-analyze-btn",
                        n_clicks=0,
                        style={
                            "width": "120px",
                            "backgroundColor": EA_BUTTON_BG,
                            "color": EA_BUTTON_FG,
                            "border": "none",
                            "borderRadius": "8px",
                            "padding": "10px 0",
                            "fontSize": f"{FONT_SIZE_BODY}px",
                            "fontWeight": "500",
                            "cursor": "pointer",
                        },
                    ),
                    # 결과 힌트 영역
                    html.Div(
                        "결과: Imatinib (T=0.94) | Dasatinib (T=0.81) ...",
                        id="lib-external-hint",
                        style={
                            "width": "350px",
                            "border": f"1px dashed {BORDER_DEFAULT}",
                            "borderRadius": "8px",
                            "padding": "10px 14px",
                            "color": TEXT_MUTED,
                            "fontSize": f"{FONT_SIZE_CAPTION}px",
                            "display": "flex",
                            "alignItems": "center",
                        },
                    ),
                ],
                style={
                    "display": "flex",
                    "gap": "12px",
                    "alignItems": "center",
                },
            ),
        ],
        id="lib-external-analyzer",
        style={
            "border": f"1px solid {EA_BORDER}",
            "borderRadius": "12px",
            "padding": "20px",
            "marginBottom": "20px",
        },
    )


# ── Main: render_external_result ──────────────────────────────────────────────


def render_external_result(result_data: dict | None) -> html.Div:
    """
    외부 화합물 분석 결과를 메인 영역에 렌더링한다.

    Args:
        result_data: analyze_external_compound() 반환값
            {
                "input_meta": {"cid": str, "smiles": str, "inchikey": str},
                "top5": [
                    {
                        "compound_id": str,
                        "name": str,
                        "tanimoto": float,
                        "analog_prob": float,
                        "target_overlap": list[str],
                        "phase_chip": str,
                        "rank_score": float,
                    }, ...
                ]
            }

    Returns:
        html.Div: External Result View (메인 영역 교체)
    """
    if not result_data:
        return html.Div(
            "분석 결과가 없습니다.",
            style={"color": TEXT_MUTED, "padding": "40px", "textAlign": "center"},
        )

    input_meta = result_data.get("input_meta", {})
    top5 = result_data.get("top5", [])

    # 입력 화합물 메타 카드
    meta_card = html.Div(
        [
            html.Div("입력 화합물", style={
                "fontSize": f"{FONT_SIZE_HEADER}px",
                "fontWeight": "500",
                "color": TEXT_PRIMARY,
                "marginBottom": "8px",
            }),
            html.Div(
                [
                    _meta_field("CID", input_meta.get("cid", "—")),
                    _meta_field("SMILES", input_meta.get("smiles", "—")),
                    _meta_field("InChIKey", input_meta.get("inchikey", "—")),
                ],
                style={"display": "flex", "gap": "24px", "flexWrap": "wrap"},
            ),
            # Structure preview placeholder
            html.Div(
                "[구조 미리보기]",
                style={
                    "width": "200px",
                    "height": "80px",
                    "backgroundColor": "#1F2937",
                    "borderRadius": "6px",
                    "display": "flex",
                    "alignItems": "center",
                    "justifyContent": "center",
                    "color": TEXT_MUTED,
                    "fontSize": f"{FONT_SIZE_CAPTION}px",
                    "marginTop": "12px",
                },
            ),
        ],
        style={
            "backgroundColor": BG_CARD,
            "borderRadius": "12px",
            "padding": "16px",
            "marginBottom": "16px",
        },
    )

    # 경고 박스
    warning_box = html.Div(
        "⚠️ champion 직접 적용 불가 (Phase A KNN imputation 5.8% 보존). "
        "아래는 in-library 유사 화합물 기반 analog 추정.",
        style={
            "border": f"1px solid {WARNING_BORDER}",
            "borderRadius": "8px",
            "padding": "12px 16px",
            "color": WARNING_BORDER,
            "fontSize": f"{FONT_SIZE_BODY}px",
            "marginBottom": "16px",
        },
    )

    # Top-5 유사 화합물 카드
    top5_cards = html.Div(
        [_render_top5_card(item, idx + 1) for idx, item in enumerate(top5[:5])],
        style={"display": "flex", "flexDirection": "column", "gap": "12px"},
    )

    # 닫기 버튼
    close_btn = html.Button(
        "✕ 닫기",
        id="lib-external-close-btn",
        n_clicks=0,
        style={
            "position": "absolute",
            "top": "16px",
            "right": "16px",
            "background": "none",
            "border": f"1px solid {BORDER_DEFAULT}",
            "borderRadius": "6px",
            "color": TEXT_SECONDARY,
            "padding": "6px 12px",
            "fontSize": f"{FONT_SIZE_BODY}px",
            "cursor": "pointer",
        },
    )

    return html.Div(
        [close_btn, meta_card, warning_box, top5_cards],
        id="lib-external-result-view",
        style={"position": "relative", "padding": "16px 0"},
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _meta_field(label: str, value: str) -> html.Div:
    """메타 필드 (라벨 + 값)."""
    display_value = value
    if len(value) > 40:
        display_value = value[:37] + "..."
    return html.Div(
        [
            html.Span(f"{label}: ", style={
                "color": TEXT_MUTED,
                "fontSize": f"{FONT_SIZE_CAPTION}px",
            }),
            html.Span(display_value, style={
                "color": TEXT_PRIMARY,
                "fontSize": f"{FONT_SIZE_CAPTION}px",
                "fontFamily": "monospace",
            }),
        ],
    )


def _render_top5_card(item: dict, rank: int) -> html.Div:
    """Top-5 유사 화합물 개별 카드."""
    name = item.get("name", "Unknown")
    compound_id = item.get("compound_id", "")
    tanimoto = item.get("tanimoto", 0.0)
    analog_prob = item.get("analog_prob", 0.0)
    target_overlap = item.get("target_overlap", [])
    phase_cat = item.get("phase_chip", "X")
    rank_score = item.get("rank_score", 0.0)

    phase_bg, phase_fg = PHASE_COLORS.get(phase_cat, PHASE_COLORS["X"])

    # 액션 버튼
    action_btn_style = {
        "padding": "4px 10px",
        "borderRadius": "4px",
        "fontSize": f"{FONT_SIZE_CAPTION}px",
        "cursor": "pointer",
        "border": f"1px solid {BORDER_DEFAULT}",
        "color": TEXT_SECONDARY,
        "backgroundColor": "transparent",
        "textDecoration": "none",
    }

    return html.Div(
        [
            # 좌측: 순위 + 이름 + 메트릭
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(f"#{rank}", style={
                                "color": ACCENT_CYAN,
                                "fontWeight": "500",
                                "marginRight": "12px",
                                "fontSize": f"{FONT_SIZE_BODY}px",
                            }),
                            html.Span(name, style={
                                "color": TEXT_PRIMARY,
                                "fontWeight": "500",
                                "fontSize": "14px",
                            }),
                            html.Span(
                                PHASE_LABELS.get(phase_cat, ""),
                                style={
                                    "backgroundColor": phase_bg,
                                    "color": phase_fg,
                                    "padding": "2px 6px",
                                    "borderRadius": "4px",
                                    "fontSize": "10px",
                                    "marginLeft": "8px",
                                },
                            ),
                            html.Span(f" — {compound_id}", style={
                                "color": TEXT_MUTED,
                                "fontSize": f"{FONT_SIZE_CAPTION}px",
                                "marginLeft": "8px",
                            }),
                        ],
                        style={"display": "flex", "alignItems": "center"},
                    ),
                    html.Div(
                        [
                            html.Span(f"Tanimoto: {tanimoto:.2f}", style={
                                "color": ACCENT_CYAN,
                                "fontWeight": "500",
                                "marginRight": "16px",
                            }),
                            html.Span(f"Analog prob: {analog_prob:.2f}", style={
                                "color": TEXT_SECONDARY,
                                "marginRight": "16px",
                            }),
                            html.Span(f"Target overlap: {', '.join(target_overlap[:3]) or '—'}", style={
                                "color": TEXT_TERTIARY,
                            }),
                        ],
                        style={
                            "fontSize": f"{FONT_SIZE_CAPTION}px",
                            "marginTop": "6px",
                        },
                    ),
                ],
                style={"flex": "1"},
            ),
            # 우측: rank_score + 액션
            html.Div(
                [
                    html.Div(f"{rank_score:.2f}", style={
                        "fontSize": "18px",
                        "fontWeight": "500",
                        "color": TEXT_PRIMARY,
                        "textAlign": "right",
                    }),
                    html.Div(
                        [
                            html.A("상세", href=f"/candidate-explorer?cid={compound_id}", style=action_btn_style),
                            html.A("패스웨이", href=f"/pathway?cid={compound_id}", style=action_btn_style),
                            html.A("Cell-line", href=f"/simulator?cid={compound_id}&mode=cell-line", style={
                                **action_btn_style,
                                "border": f"1px solid {ACCENT_CYAN}",
                                "color": ACCENT_CYAN,
                            }),
                        ],
                        style={"display": "flex", "gap": "6px", "marginTop": "6px"},
                    ),
                ],
                style={"textAlign": "right"},
            ),
        ],
        style={
            "display": "flex",
            "justifyContent": "space-between",
            "alignItems": "center",
            "backgroundColor": BG_CARD,
            "borderRadius": "10px",
            "padding": "14px 16px",
            "border": f"1px solid {BORDER_DEFAULT}",
        },
    )
