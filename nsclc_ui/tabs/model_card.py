"""
Model Card — 3 모델 정직 공개.

- Champion E6 (frozen, classification): 임상 적합성 binary
- A v3 (regression): PRISM cell-line lfc
- B (hybrid transfer): TCGA → CCLE cosine sim + target-aware tier ranking

§1.4 약점 먼저 원칙으로 약점 섹션 각 카드에 포함.
"""

import json
from pathlib import Path

import dash
from dash import html
import dash_mantine_components as dmc

from nsclc_ui.components.kpi_card import kpi_card
from nsclc_ui.layout.theme import COLORS, card_style

dash.register_page(__name__, path="/model-card", name="Model Card")

# nsclc_ui/tabs/model_card.py → parents[2] = 5team/final
_BASE = Path(__file__).resolve().parents[2]


def _safe_load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


_A_V3 = _safe_load_json(_BASE / "data/derived/cell_line_model_metrics_v3.json") or {}
_B_META = _safe_load_json(_BASE / "data/derived/patient_transfer_meta.json") or {}

# ── Champion E6 (Pre baseline + Phase A frozen, history-derived) ────────────
_E6 = {
    "model": "XGB + LGB ensemble (E2_tcga_crispr / E6)",
    "pr_auc_scaffold": 0.1253,
    "pr_auc_std": 0.0063,
    "pr_auc_weighted": 0.1383,
    "pr_auc_w_std": 0.0054,
    "n_features": 947,
    "n_positives": 115,
    "n_total": 33057,
    "pre_baseline": 0.0972,
    "delta_pct": "+29%",
}

# ── A v3 metrics ────────────────────────────────────────────────────────────
_a_strict = _A_V3.get("primary_strict", {})
_a_relaxed = _A_V3.get("secondary_relaxed", {})
_a_feat = _A_V3.get("features", {})

# ── B meta ──────────────────────────────────────────────────────────────────
_b_topk = _B_META.get("top_k_sim", {})


# ── 헬퍼 ────────────────────────────────────────────────────────────────────

def _model_card(title, applied_badge_color, applied_text, kpis, technical, weaknesses):
    """공통 모델 카드 layout."""
    return dmc.Paper(
        children=[
            dmc.Group([
                dmc.Text(title, size="md", fw=500),
                dmc.Badge(applied_text, color=applied_badge_color, variant="light", size="sm"),
            ], gap=8, mb=10),
            dmc.SimpleGrid(cols=4, spacing="xs", children=kpis),
            dmc.Text("Technical", size="xs", fw=500, c="dimmed", mt=10, mb=2),
            dmc.Text(technical, size="xs", ff="monospace", c="dimmed", mb=10),
            dmc.Text("§1.4 정직 공개 — 알려진 약점", size="xs", fw=500,
                     style={"color": "#F0997B"}, mb=4),
            dmc.Stack([
                dmc.Text(f"• {w}", size="xs", c="dimmed", lh=1.5)
                for w in weaknesses
            ], gap=2),
        ],
        style=card_style(padding="14px"),
    )


# ── Card 1: Champion E6 ─────────────────────────────────────────────────────

_card_e6 = _model_card(
    title="① Champion E6 — 임상 적합성 분류",
    applied_badge_color="blue",
    applied_text="drug-ranking · candidate-explorer",
    kpis=[
        kpi_card("scaffold PR-AUC",
                 f"{_E6['pr_auc_scaffold']:.4f}±{_E6['pr_auc_std']:.4f}",
                 sublabel=f"vs Pre {_E6['pre_baseline']:.4f} ({_E6['delta_pct']})",
                 sublabel_color="success"),
        kpi_card("PR-AUC_w",
                 f"{_E6['pr_auc_weighted']:.4f}±{_E6['pr_auc_w_std']:.4f}",
                 sublabel="weighted (라벨 신뢰도)", sublabel_color="tertiary"),
        kpi_card("Features", str(_E6["n_features"]),
                 sublabel=f"{_E6['n_total']:,} cmpd · {_E6['n_positives']} pos",
                 sublabel_color="tertiary"),
        kpi_card("Status", "Frozen",
                 sublabel="pre-v3-frozen tag", sublabel_color="tertiary"),
    ],
    technical=f"{_E6['model']} · scaffold-split GroupKFold(5) · α=0.6 (XGB) + 0.4 (LGB)",
    weaknesses=[
        "Phase A KNN imputation: external compound 5.8% preservation — 외부 SMILES 직접 적용 불가",
        "Mordred 1,613 descriptors → −21.9% degradation (information dilution, 재시도 X)",
        "BindingDB pIC50 보강 fail (97% ChEMBL overlap, 동일 source 효과)",
        "PR-AUC 0.1253 < 목표 0.30 — Pre PR-AUC 0.10 정직 공개로 신뢰 얻은 패턴 유지",
    ],
)


# ── Card 2: A v3 ────────────────────────────────────────────────────────────

_strict_sp = _a_strict.get("spearman_mean", 0)
_strict_sp_std = _a_strict.get("spearman_std", 0)
_relaxed_sp = _a_relaxed.get("spearman_mean", 0)
_relaxed_sp_std = _a_relaxed.get("spearman_std", 0)
_n_feat_a = _a_feat.get("total_dim", 2791)

_card_a = _model_card(
    title="② A v3 — Cell-line response regression",
    applied_badge_color="violet",
    applied_text="cell-line 탭 (가상세포실험)",
    kpis=[
        kpi_card("STRICT Spearman",
                 f"{_strict_sp:.4f}±{_strict_sp_std:.4f}",
                 sublabel="scaffold-split · 새 구조", sublabel_color="tertiary"),
        kpi_card("RELAXED Spearman",
                 f"{_relaxed_sp:.4f}±{_relaxed_sp_std:.4f}",
                 sublabel="random-split · 동일 구조", sublabel_color="tertiary"),
        kpi_card("Features", str(_n_feat_a),
                 sublabel="Morgan + MACCS + Target/MOA + CCLE PCA",
                 sublabel_color="tertiary"),
        kpi_card("Data", "449K",
                 sublabel="4,684 cmpd × 98 NSCLC cell",
                 sublabel_color="tertiary"),
    ],
    technical="XGBoost regressor · GroupKFold(5, scaffold) · num_boost_round=1000 (early stop 50)",
    weaknesses=[
        f"STRICT {_strict_sp:.2f} — compound novelty 페널티. RELAXED→STRICT gap {_relaxed_sp - _strict_sp:.2f}",
        "v4 ablation (per-cell z-score label): STRICT 0.18 → 0.19 (Δ=노이즈). feature engineering 천장",
        "v4 NORM 0.13 (z-score 영역) — 신호의 절반은 cell baseline scale 효과, 화합물 차별화는 0.13",
        "STRICT 0.18은 의약화학 모델 normal range. 정량 예측보다 ordering 신뢰 가능",
    ],
)


# ── Card 3: B (hybrid) ──────────────────────────────────────────────────────

_n_patients = _B_META.get("n_patients", 942)
_n_drugs = _B_META.get("n_drugs", 4684)
_topk_mean = _b_topk.get("mean", 0)
_topk_min = _b_topk.get("min", 0)
_topk_max = _b_topk.get("max", 0)

_card_b = _model_card(
    title="③ B — Patient transfer + Target-aware hybrid ranking",
    applied_badge_color="teal",
    applied_text="patient 탭 (가상투약)",
    kpis=[
        kpi_card("Patients", f"{_n_patients}",
                 sublabel="TCGA-LUAD/LUSC", sublabel_color="tertiary"),
        kpi_card("Mean top-5 sim", f"{_topk_mean:.3f}",
                 sublabel=f"range [{_topk_min:.2f}, {_topk_max:.2f}]",
                 sublabel_color="tertiary"),
        kpi_card("Drugs ranked", f"{_n_drugs:,}",
                 sublabel="per patient", sublabel_color="tertiary"),
        kpi_card("Method", "Tier 1+2",
                 sublabel="actionable + ML sub-rank",
                 sublabel_color="tertiary"),
    ],
    technical="20-gene mutation cosine sim → top-K=5 cell → A v3 lfc avg (단순 + weighted) + tier-based hybrid rank",
    weaknesses=[
        "Pure ML transfer만으론 generic cytotoxic (proteasome inhibitor) 우세 — tier 도입 필수성 발견",
        "Z-score normalization 시도 (cell baseline 제거) — raw rank와 거의 동일 (Δ < 30/4684)",
        "EGFR mutant cell 98 중 6개 (~6%) — top-5 cosine sim 신뢰도 환자별 변동 큼",
        "KRAS-only 환자: PRISM library에 KRAS direct drug 부족 (sotorasib 등 신약 미포함)",
        "ERBB2/NTRK1 등 일부 gene: CCLE 98 cell에서 0% mutation — informative gene 18개 / 20개",
    ],
)


# ── Honest narrative ────────────────────────────────────────────────────────

_narrative = dmc.Paper(
    children=[
        dmc.Text("📝 발표 narrative — §1.4 약점 먼저 원칙", size="sm", fw=500, mb=8),
        dmc.Text(
            "Pre 단계에서 PR-AUC 0.0972 (목표 0.30 미달) 정직 공개 → 발표 신뢰 얻음. "
            "Final도 같은 원칙. STRICT/RELAXED 두 metric 동시 공개. "
            "v4 ablation으로 cell baseline vs compound novelty 신호 분리 확인. "
            "B 모델에서 pure transfer 한계 발견 → tier 도입.",
            size="xs", c="dimmed", lh=1.6, mb=10,
        ),
        dmc.Text("3 모델 역할 분담", size="xs", fw=500, mb=4),
        dmc.Stack([
            dmc.Text("• ① Champion E6 — '이 화합물이 NSCLC에 적용 가능한가?' (binary 적합성)",
                     size="xs", c="dimmed"),
            dmc.Text("• ② A v3 — '이 cell × drug 조합에서 lfc는 얼마인가?' (정량 회귀)",
                     size="xs", c="dimmed"),
            dmc.Text("• ③ B (hybrid) — '이 환자에게 어떤 drug 우선인가?' (임상 actionable + ML)",
                     size="xs", c="dimmed"),
        ], gap=2),
        dmc.Text("핵심 contribution: 단일 metric이 아니라 '순증분 가치' (Pre 화학만 → Final multi-source + tier)",
                 size="xs", c="dimmed", fs="italic", mt=10),
    ],
    style=card_style(padding="14px"),
)


# ── Data sources ───────────────────────────────────────────────────────────

_data_sources = dmc.Paper(
    children=[
        dmc.Text("📚 데이터 소스", size="sm", fw=500, mb=8),
        dmc.SimpleGrid(cols=3, spacing="xs", children=[
            dmc.Stack([
                dmc.Text("화학", size="xs", fw=500, c="dimmed"),
                dmc.Text("ChEMBL 34", size="xs"),
                dmc.Text("PRISM Repurposing 19Q4", size="xs"),
                dmc.Text("GDSC2 release 8.4", size="xs"),
            ], gap=2),
            dmc.Stack([
                dmc.Text("유전체", size="xs", fw=500, c="dimmed"),
                dmc.Text("TCGA-LUAD/LUSC PanCancer 2018", size="xs"),
                dmc.Text("DepMap CCLE 22Q2", size="xs"),
                dmc.Text("DepMap CRISPR 26Q1", size="xs"),
            ], gap=2),
            dmc.Stack([
                dmc.Text("Pathway/Network", size="xs", fw=500, c="dimmed"),
                dmc.Text("KEGG hsa05223 (NSCLC)", size="xs"),
                dmc.Text("SIGNOR", size="xs"),
                dmc.Text("OmniPath (Stretch)", size="xs"),
            ], gap=2),
        ]),
    ],
    style=card_style(padding="14px"),
)


# ── Layout ──────────────────────────────────────────────────────────────────

layout = dmc.Stack([
    dmc.Group([
        dmc.Title("Model Card — 3 모델 정직 공개", order=3, c=COLORS["text_primary"]),
        dmc.Badge("Final · D-10", color="grape", variant="filled"),
    ], gap=8),
    dmc.Text(
        "Champion (분류) + A regression (정량) + B hybrid (환자 ranking) 3 모델. "
        "scaffold-split 평가 + §1.4 약점 정직 공개.",
        size="sm", c="dimmed",
    ),
    _card_e6,
    _card_a,
    _card_b,
    _data_sources,
    _narrative,
], gap="md", style={"padding": "20px"})
