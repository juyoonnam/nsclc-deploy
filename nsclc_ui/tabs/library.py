"""
약물 라이브러리 — 33,057 NSCLC 후보 화합물 카탈로그.

데이터 소스: data/derived/library_pool_final.csv (33,057 × 15)
- Champion E6 frozen ranking (rank_score, rank_score_std)
- 6 Library category: A 승인 / B 임상 / C 재창출 / D 비항암 / E 없음 / X 전임상
- ATC L1, max_phase, NSCLC max_phase

기본 정렬: rank_score 내림차순 (Champion E6 추천 상위)
"""

from functools import lru_cache
from pathlib import Path

import dash
from dash import html, dcc, callback, Input, Output
import dash_mantine_components as dmc
import pandas as pd

from nsclc_ui.layout.theme import COLORS, card_style

dash.register_page(__name__, path="/library", name="Library")

# nsclc_ui/tabs/library.py → parents[2] = 5team/final
_BASE = Path(__file__).resolve().parents[2]
LIBRARY_CSV = _BASE / "data/derived/library_pool_final.csv"


@lru_cache(maxsize=1)
def _load_library():
    df = pd.read_csv(LIBRARY_CSV)
    # Category 그룹 단순화 (시연용)
    df["category_short"] = df["final_category"].fillna("X. 전임상/unknown")
    return df


@lru_cache(maxsize=1)
def _category_options():
    df = _load_library()
    cats = df["category_short"].value_counts().to_dict()
    options = [{"label": "전체", "value": "ALL"}]
    for cat, n in sorted(cats.items()):
        options.append({"label": f"{cat} ({n:,})", "value": cat})
    return options


@lru_cache(maxsize=1)
def _summary_stats():
    df = _load_library()
    total = len(df)
    cats = df["category_short"].value_counts().to_dict()
    # 핵심 카테고리만
    n_a = sum(v for k, v in cats.items() if k.startswith("A"))
    n_b = sum(v for k, v in cats.items() if k.startswith("B"))
    n_c = sum(v for k, v in cats.items() if k.startswith("C"))
    n_d = sum(v for k, v in cats.items() if k.startswith("D"))
    n_e = sum(v for k, v in cats.items() if k.startswith("E"))
    n_x = sum(v for k, v in cats.items() if k.startswith("X"))
    n_boost = int(df["domain_boosted"].sum()) if "domain_boosted" in df.columns else 0
    return {
        "total": total,
        "A": n_a, "B": n_b, "C": n_c, "D": n_d, "E": n_e, "X": n_x,
        "boosted": n_boost,
    }


def _kpi_row():
    s = _summary_stats()
    return dmc.SimpleGrid(cols=4, spacing="xs", children=[
        dmc.Paper(
            children=[
                dmc.Text("Total compounds", size="xs", c="dimmed"),
                dmc.Text(f"{s['total']:,}", size="xl", fw=500),
                dmc.Text("Champion E6 ranked", size="xs", c="dimmed"),
            ],
            style=card_style(padding="12px"),
        ),
        dmc.Paper(
            children=[
                dmc.Text("승인/임상 (A+B+C)", size="xs", c="dimmed"),
                dmc.Text(f"{s['A'] + s['B'] + s['C']:,}", size="xl", fw=500,
                         style={"color": "var(--accent-cyan)"}),
                dmc.Text(f"A승인 {s['A']} · B임상 {s['B']} · C재창출 {s['C']}",
                         size="xs", c="dimmed"),
            ],
            style=card_style(padding="12px"),
        ),
        dmc.Paper(
            children=[
                dmc.Text("Non-oncology + unknown", size="xs", c="dimmed"),
                dmc.Text(f"{s['D'] + s['E']:,}", size="xl", fw=500,
                         style={"color": "var(--accent-amber)"}),
                dmc.Text(f"D비항암 {s['D']} · E없음 {s['E']}",
                         size="xs", c="dimmed"),
            ],
            style=card_style(padding="12px"),
        ),
        dmc.Paper(
            children=[
                dmc.Text("Preclinical (X)", size="xs", c="dimmed"),
                dmc.Text(f"{s['X']:,}", size="xl", fw=500, c="dimmed"),
                dmc.Text(f"domain boosted: {s['boosted']}",
                         size="xs", c="dimmed"),
            ],
            style=card_style(padding="12px"),
        ),
    ])


def _build_layout(**kwargs):
    return dmc.Stack([
        dmc.Group([
            dmc.Title("약물 라이브러리 — 33,057 NSCLC 후보", order=3,
                      style={"color": COLORS["text_primary"]}),
            dmc.Badge("Champion E6 frozen", color="grape", variant="filled"),
        ], gap=8),
        dmc.Text(
            "Champion E6 (XGB+LGB 947 features, PR-AUC 0.1253) 산출 ranking. "
            "6-tier category (A 승인 / B 임상 / C 재창출 / D 비항암 / E 없음 / X 전임상).",
            size="sm", c="dimmed",
        ),
        _kpi_row(),
        dmc.Paper(
            children=[
                dmc.Group([
                    dmc.Text("Category 필터:", size="sm", fw=500),
                    dcc.Dropdown(
                        id="lib-category-filter",
                        options=_category_options(),
                        value="ALL",
                        clearable=False,
                        style={"width": "320px"},
                    ),
                    dmc.Text("정렬: rank_score 내림차순 (Champion E6)",
                             size="xs", c="dimmed"),
                ], gap=12, mb=12),
                html.Div(id="lib-table-container"),
            ],
            style=card_style(padding="14px"),
        ),
    ], gap="md", style={"padding": "20px"})


layout = _build_layout()


# ── Callback: 카테고리 필터 → 테이블 렌더 ─────────────────────────────────

@callback(
    Output("lib-table-container", "children"),
    Input("lib-category-filter", "value"),
)
def _filter_table(category):
    df = _load_library()
    if category and category != "ALL":
        df = df[df["category_short"] == category]
    # rank_score 내림차순, top 100만 표시
    df = df.sort_values("rank_score", ascending=False).head(100)

    # Header
    headers = ["#", "Compound", "Pref name", "Category", "Phase", "ATC L1",
               "rank_score", "Boosted"]
    header_row = html.Tr([
        html.Th(h, style={"padding": "6px 8px", "fontSize": "11px",
                          "color": "var(--nsclc-text-secondary)",
                          "borderBottom": "0.5px solid var(--nsclc-border)",
                          "textAlign": "left" if h not in ("#", "rank_score", "Boosted") else "right"})
        for h in headers
    ])

    # Body
    body_rows = []
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        cat = row.get("category_short", "")
        # Category color
        if cat.startswith("A"):
            cat_color = "var(--accent-cyan)"
        elif cat.startswith("B"):
            cat_color = "var(--accent-cyan)"
        elif cat.startswith("C"):
            cat_color = "var(--accent-purple)"
        elif cat.startswith("D"):
            cat_color = "var(--accent-amber)"
        elif cat.startswith("E"):
            cat_color = "var(--accent-amber)"
        else:
            cat_color = "var(--nsclc-text-tertiary)"

        rank = row.get("rank_score", 0)
        boosted = row.get("domain_boosted", False)
        boost_str = "★" if boosted else "—"

        pref = row.get("pref_name", "") or "—"
        cmpd_id = row.get("compound_id", "")
        phase = row.get("max_phase", "")
        phase_str = f"P{int(phase)}" if pd.notna(phase) else "—"
        atc = row.get("atc_l1", "") or "—"

        body_rows.append(
            html.Tr([
                html.Td(str(i), style={"padding": "6px 8px", "color": "var(--nsclc-text-secondary)",
                                        "fontSize": "11px", "fontVariantNumeric": "tabular-nums",
                                        "textAlign": "right"}),
                html.Td(cmpd_id, style={"padding": "6px 8px", "fontSize": "11px",
                                         "color": "var(--nsclc-text-secondary)", "fontFamily": "monospace"}),
                html.Td(pref, style={"padding": "6px 8px", "fontSize": "11px",
                                      "color": "var(--nsclc-text-primary)", "fontWeight": "500"}),
                html.Td(cat[:30], style={"padding": "6px 8px", "fontSize": "10px",
                                          "color": cat_color}),
                html.Td(phase_str, style={"padding": "6px 8px", "fontSize": "11px",
                                           "color": "var(--nsclc-text-secondary)"}),
                html.Td(atc, style={"padding": "6px 8px", "fontSize": "10px",
                                     "color": "var(--nsclc-text-tertiary)"}),
                html.Td(f"{rank:.4f}", style={"padding": "6px 8px", "fontSize": "11px",
                                               "color": "var(--accent-purple)",
                                               "fontVariantNumeric": "tabular-nums",
                                               "textAlign": "right"}),
                html.Td(boost_str, style={"padding": "6px 8px", "fontSize": "11px",
                                           "color": "var(--accent-amber)" if boosted else "var(--nsclc-text-tertiary)",
                                           "textAlign": "right"}),
            ], style={"borderBottom": "0.5px solid var(--nsclc-border)"})
        )

    return html.Div([
        dmc.Text(f"표시: top 100 (전체 {len(df):,}개 중 rank_score 상위)",
                 size="xs", c="dimmed", mb=6),
        html.Table(
            [html.Thead(header_row), html.Tbody(body_rows)],
            style={"width": "100%", "borderCollapse": "collapse"},
        ),
    ])
