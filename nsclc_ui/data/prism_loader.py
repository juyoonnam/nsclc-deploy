"""
PRISM Repurposing 24Q2 NSCLC long-form 어댑터.

시뮬레이터 Mode 2 (Cell-line) 데이터 contract.

데이터:
  final/data/derived/prism_nsclc_long.parquet
    204 compounds × 95 NSCLC cell lines, 18,800 non-null lfc rows
    cols: molecule_chembl_id, compound_id (BRD), model_id (DepMap),
          cell_line_name (NCIH1975 형태), oncotree_subtype, lfc

용법:
  >>> from nsclc_ui.data.prism_loader import get_prism_response
  >>> get_prism_response("CHEMBL3353410", "H1975")
  {'chembl_id': 'CHEMBL3353410', 'in_prism': True, 'n_cells_tested': 88,
   'cell_line_in_prism': True, 'cell_line_name': 'NCIH1975',
   'cell_line_lfc': -0.7496, 'oncotree_subtype': 'Lung Adenocarcinoma', ...}
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_PROJECT = Path(__file__).resolve().parent.parent.parent  # final/
_PARQUET = _PROJECT / "data" / "derived" / "prism_nsclc_long.parquet"

# 모듈 레벨 캐시 (lazy load)
_CACHE: pd.DataFrame | None = None


def normalize_compound_id(x) -> str:
    """loaders.py 표준과 동일."""
    return str(x).strip().upper()


def normalize_cell_line(x) -> str:
    """H1975 / NCI-H1975 / NCIH1975 → NCIH1975 (DepMap 명명).

    PRISM 매트릭스는 'NCIH1975' 형태로 정규화되어 저장됨.
    유저 입력은 'H1975', 'NCI-H1975' 등 다양 → 일관 처리.
    """
    n = str(x).upper().strip()
    n = n.replace("-", "").replace(" ", "")
    return n


def load_prism_long() -> pd.DataFrame:
    """Lazy-load. 파일 없으면 빈 DataFrame (해당 컬럼 스키마 유지)."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    empty_cols = [
        "molecule_chembl_id", "compound_id", "model_id",
        "cell_line_name", "oncotree_subtype", "lfc",
    ]
    if not _PARQUET.exists():
        logger.warning("PRISM long parquet not found: %s", _PARQUET)
        _CACHE = pd.DataFrame(columns=empty_cols)
        return _CACHE

    df = pd.read_parquet(_PARQUET)
    df["molecule_chembl_id"] = df["molecule_chembl_id"].astype(str).str.strip()
    df["cell_line_name"] = df["cell_line_name"].astype(str).str.upper()
    _CACHE = df
    logger.info(
        "PRISM long loaded: %d rows | %d compounds × %d cells",
        len(df), df["molecule_chembl_id"].nunique(), df["cell_line_name"].nunique(),
    )
    return _CACHE


def is_compound_in_prism(chembl_id: str) -> bool:
    """Quick check — Mode 2 카드 활성화 분기용."""
    df = load_prism_long()
    if df.empty:
        return False
    return normalize_compound_id(chembl_id) in df["molecule_chembl_id"].values


def get_prism_response(chembl_id: str, cell_line: str | None = None) -> dict:
    """단일 약물 (× 옵션 cell line)의 PRISM 반응 통계.

    Returns:
        in_prism=False면 reason 포함.
        cell_line 지정 시 cell_line_in_prism + cell_line_lfc 추가.
    """
    df = load_prism_long()
    if df.empty:
        return {"chembl_id": chembl_id, "in_prism": False, "reason": "no_data"}

    cid = normalize_compound_id(chembl_id)
    sub = df[df["molecule_chembl_id"] == cid]
    if sub.empty:
        return {"chembl_id": cid, "in_prism": False, "reason": "compound_not_in_prism"}

    result: dict = {
        "chembl_id": cid,
        "in_prism": True,
        "n_cells_tested": len(sub),
        "lfc_mean": round(float(sub["lfc"].mean()), 4),
        "lfc_median": round(float(sub["lfc"].median()), 4),
        "lfc_min": round(float(sub["lfc"].min()), 4),
        "lfc_max": round(float(sub["lfc"].max()), 4),
        "lfc_std": round(float(sub["lfc"].std()), 4),
        "n_cells_strong": int((sub["lfc"] < -1.0).sum()),
    }

    if cell_line:
        cell_norm = normalize_cell_line(cell_line)
        # contains 매칭 — H1975 ↔ NCIH1975 둘 다 잡힘
        match = sub[sub["cell_line_name"].str.contains(cell_norm, na=False, regex=False)]
        if match.empty:
            result.update({
                "cell_line_query": cell_line,
                "cell_line_in_prism": False,
            })
        else:
            row = match.iloc[0]
            result.update({
                "cell_line_query": cell_line,
                "cell_line_in_prism": True,
                "cell_line_name": row["cell_line_name"],
                "cell_line_lfc": round(float(row["lfc"]), 4),
                "oncotree_subtype": row["oncotree_subtype"],
                "model_id": row["model_id"],
            })
    return result


def get_top_drugs_for_cell_line(cell_line: str, top_n: int = 20) -> list[dict]:
    """세포주에서 효과 강한 약물 Top-N (lfc 오름차순)."""
    df = load_prism_long()
    if df.empty:
        return []
    cell_norm = normalize_cell_line(cell_line)
    sub = df[df["cell_line_name"].str.contains(cell_norm, na=False, regex=False)]
    if sub.empty:
        return []
    sub = sub.sort_values("lfc", ascending=True).head(top_n)
    return [
        {
            "rank": i + 1,
            "chembl_id": r["molecule_chembl_id"],
            "cell_line_name": r["cell_line_name"],
            "lfc": round(float(r["lfc"]), 4),
        }
        for i, (_, r) in enumerate(sub.iterrows())
    ]


def get_compound_distribution(chembl_id: str) -> dict:
    """약물의 NSCLC 전체 cell line 분포 + 강 시그널 + scatter 데이터."""
    df = load_prism_long()
    if df.empty:
        return {"chembl_id": chembl_id, "in_prism": False}

    cid = normalize_compound_id(chembl_id)
    sub = df[df["molecule_chembl_id"] == cid]
    if sub.empty:
        return {"chembl_id": cid, "in_prism": False}

    strong = sub[sub["lfc"] < -1.0].sort_values("lfc")
    return {
        "chembl_id": cid,
        "in_prism": True,
        "n_cells_tested": len(sub),
        "n_cells_strong": len(strong),
        "lfc_distribution": {
            "mean": round(float(sub["lfc"].mean()), 4),
            "median": round(float(sub["lfc"].median()), 4),
            "min": round(float(sub["lfc"].min()), 4),
            "max": round(float(sub["lfc"].max()), 4),
            "std": round(float(sub["lfc"].std()), 4),
            "q25": round(float(sub["lfc"].quantile(0.25)), 4),
            "q75": round(float(sub["lfc"].quantile(0.75)), 4),
        },
        "top_strong_cells": [
            {
                "cell_line_name": r["cell_line_name"],
                "oncotree_subtype": r["oncotree_subtype"],
                "lfc": round(float(r["lfc"]), 4),
            }
            for _, r in strong.head(10).iterrows()
        ],
        "all_cells": [
            {
                "cell_line_name": r["cell_line_name"],
                "oncotree_subtype": r["oncotree_subtype"],
                "lfc": round(float(r["lfc"]), 4),
            }
            for _, r in sub.iterrows()
        ],
    }


def get_nsclc_cell_lines() -> list[dict]:
    """PRISM 측정된 NSCLC cell line 리스트 (Mode 2 picker용).

    측정 화합물 수 내림차순. n_compounds 많은 게 데모/검증에 유리.
    """
    df = load_prism_long()
    if df.empty:
        return []
    grouped = (
        df.groupby(["cell_line_name", "oncotree_subtype", "model_id"])
        .size()
        .reset_index(name="n_compounds")
        .sort_values("n_compounds", ascending=False)
    )
    return [
        {
            "cell_line_name": r["cell_line_name"],
            "oncotree_subtype": r["oncotree_subtype"],
            "model_id": r["model_id"],
            "n_compounds": int(r["n_compounds"]),
        }
        for _, r in grouped.iterrows()
    ]


def compute_model_vs_prism_correlation() -> dict:
    """Champion model OOF prob ↔ PRISM lfc Spearman ρ (compound 단위).

    NOTE:
      - champion model = compound 단위 (cell-line aware 아님)
      - 비교 단위 = compound (PRISM lfc는 compound별 cell line 평균)
      - 발표 메시지: "모델 prob vs PRISM 평균 살해 시그널 상관"
    """
    df = load_prism_long()
    if df.empty:
        return {"in_prism": False, "reason": "no_prism"}

    # OOF 로드 시도 — 메모리에서 두 경로 (results/, final/results/)
    oof_paths = [
        _PROJECT.parent / "results" / "e2_tcga_crispr" / "oof_predictions.csv",
        _PROJECT / "results" / "e2_tcga_crispr" / "oof_predictions.csv",
        _PROJECT / "results" / "e6" / "oof_predictions.csv",
    ]
    oof_path = next((p for p in oof_paths if p.exists()), None)
    if oof_path is None:
        return {"in_prism": True, "spearman_rho": None, "reason": "oof_not_found",
                "tried_paths": [str(p) for p in oof_paths]}

    oof = pd.read_csv(oof_path)

    # ID/pred 컬럼 자동 감지
    id_col = next(
        (c for c in oof.columns if c.lower() in ("compound_id", "molecule_chembl_id", "chembl_id")),
        None,
    )
    pred_col = next(
        (c for c in oof.columns if "pred" in c.lower() or "prob" in c.lower()),
        None,
    )
    if not id_col or not pred_col:
        return {"in_prism": True, "spearman_rho": None, "reason": "oof_schema_unknown",
                "oof_cols": oof.columns.tolist()}

    oof = oof[[id_col, pred_col]].rename(columns={id_col: "molecule_chembl_id", pred_col: "model_prob"})
    oof["molecule_chembl_id"] = oof["molecule_chembl_id"].astype(str).str.strip()

    prism_agg = df.groupby("molecule_chembl_id")["lfc"].mean().reset_index()
    merged = oof.merge(prism_agg, on="molecule_chembl_id", how="inner")

    if len(merged) < 3:
        return {"in_prism": True, "spearman_rho": None, "n": len(merged),
                "reason": "insufficient_overlap"}

    rho = merged[["model_prob", "lfc"]].corr(method="spearman").iloc[0, 1]
    return {
        "in_prism": True,
        "n": int(len(merged)),
        "spearman_rho": round(float(rho), 4),
        "interpretation": (
            "강한 음의 상관 (모델 high prob ↔ PRISM strong kill)"
            if rho < -0.5
            else "중간 음의 상관"
            if rho < -0.2
            else "약한 상관 또는 무관"
        ),
        "oof_source": str(oof_path.relative_to(_PROJECT.parent)),
    }


# Mode 2 디폴트 데모 시나리오 (mockup 3.PNG / 4.PNG와 정합)
DEMO_SCENARIO = {
    "single": {
        "cell_line": "H1975",
        "drug": {"name": "Osimertinib", "chembl_id": "CHEMBL3353410"},
    },
    "combo": {
        "cell_line": "H1975",
        "drug_a": {"name": "Osimertinib", "chembl_id": "CHEMBL3353410", "target": "EGFR"},
        "drug_b": {"name": "Cobimetinib", "chembl_id": "CHEMBL2146883", "target": "MEK1/2"},
    },
}
