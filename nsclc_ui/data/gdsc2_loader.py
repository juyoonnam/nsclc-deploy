"""
GDSC2 release 8.4 NSCLC long-form 어댑터.

시뮬레이터 Mode 2 (Cell-line) cross-source 검증 데이터 contract.
prism_loader.py 미러 구조 + cross-source 결합 함수.

데이터:
  final/data/derived/gdsc2_nsclc_long.parquet
    30 compounds × 108 cells, 3,151 rows (NSCLC LUAD+LUSC+other lung_NSCLC)
    cols: DRUG_ID, DRUG_NAME, molecule_chembl_id,
          COSMIC_ID, CELL_LINE_NAME, TCGA_DESC, gdsc_tissue_2,
          LN_IC50, AUC, Z_SCORE, RMSE

용법:
  >>> from nsclc_ui.data.gdsc2_loader import compute_cross_source_validation
  >>> compute_cross_source_validation("CHEMBL3353410", "H1975")
  {'chembl_id': 'CHEMBL3353410', 'cell_line': 'H1975',
   'prism': {..., 'cell_line_lfc': -0.7526},
   'gdsc2': {..., 'cell_line_ic50_nm': 37.7, 'sensitivity_class': 'strong_sensitive'},
   'consistency': 'concordant_sensitive',
   'consistency_kr': '일치 — 둘 다 민감'}

단위 정의:
  - LN_IC50: ln(IC50 in μM), 자연로그
  - IC50_NM:  exp(LN_IC50) × 1000  →  nM 단위
  - 낮을수록 민감 (작은 IC50 = 적은 농도로 50% 살해)
"""
from __future__ import annotations

import logging
import math
from pathlib import Path

import pandas as pd

from nsclc_ui.data.prism_loader import (
    get_prism_response,
    load_prism_long,
    normalize_cell_line,
    normalize_compound_id,
)

logger = logging.getLogger(__name__)

_PROJECT = Path(__file__).resolve().parent.parent.parent  # final/
_PARQUET = _PROJECT / "data" / "derived" / "gdsc2_nsclc_long.parquet"

_CACHE: pd.DataFrame | None = None


def _ln_ic50_to_nm(ln_ic50: float) -> float:
    """GDSC2 LN_IC50 (μM, natural log) → IC50 in nM."""
    return math.exp(ln_ic50) * 1000.0


def _classify_gdsc2_sensitivity(ic50_nm: float) -> str:
    """약리학 통상 분류 (mockup 2.PNG '강한 살해/민감' 라벨 기준)."""
    if ic50_nm < 100:
        return "strong_sensitive"
    if ic50_nm < 1000:
        return "sensitive"
    if ic50_nm < 10000:
        return "moderate"
    return "resistant"


def load_gdsc2_long() -> pd.DataFrame:
    """Lazy-load. 파일 없으면 빈 DataFrame (스키마 유지)."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    empty_cols = [
        "DRUG_ID", "DRUG_NAME", "molecule_chembl_id",
        "COSMIC_ID", "CELL_LINE_NAME", "TCGA_DESC", "gdsc_tissue_2",
        "LN_IC50", "AUC", "Z_SCORE", "RMSE",
        "IC50_NM", "CELL_LINE_NAME_NORM",
    ]
    if not _PARQUET.exists():
        logger.warning("GDSC2 long parquet not found: %s", _PARQUET)
        _CACHE = pd.DataFrame(columns=empty_cols)
        return _CACHE

    df = pd.read_parquet(_PARQUET)
    df["molecule_chembl_id"] = df["molecule_chembl_id"].astype(str).str.strip()
    df["CELL_LINE_NAME"] = df["CELL_LINE_NAME"].astype(str)
    df["IC50_NM"] = df["LN_IC50"].apply(_ln_ic50_to_nm)
    df["CELL_LINE_NAME_NORM"] = df["CELL_LINE_NAME"].apply(normalize_cell_line)
    _CACHE = df
    logger.info(
        "GDSC2 long loaded: %d rows | %d compounds × %d cells",
        len(df), df["molecule_chembl_id"].nunique(), df["COSMIC_ID"].nunique(),
    )
    return _CACHE


def is_compound_in_gdsc2(chembl_id: str) -> bool:
    """Quick check — Mode 2 카드 활성화 분기용."""
    df = load_gdsc2_long()
    if df.empty:
        return False
    return normalize_compound_id(chembl_id) in df["molecule_chembl_id"].values


def get_gdsc2_response(chembl_id: str, cell_line: str | None = None) -> dict:
    """단일 약물 (× 옵션 cell line)의 GDSC2 IC50 응답.

    Returns:
        in_gdsc2=False면 reason 포함.
        cell_line 지정 시 cell_line_in_gdsc2 + ic50_nm + sensitivity_class 추가.
    """
    df = load_gdsc2_long()
    if df.empty:
        return {"chembl_id": chembl_id, "in_gdsc2": False, "reason": "no_data"}

    cid = normalize_compound_id(chembl_id)
    sub = df[df["molecule_chembl_id"] == cid]
    if sub.empty:
        return {"chembl_id": cid, "in_gdsc2": False, "reason": "compound_not_in_gdsc2"}

    result: dict = {
        "chembl_id": cid,
        "in_gdsc2": True,
        "drug_name": str(sub.iloc[0]["DRUG_NAME"]),
        "drug_id": int(sub.iloc[0]["DRUG_ID"]),
        "n_cells_tested": len(sub),
        "ln_ic50_mean": round(float(sub["LN_IC50"].mean()), 4),
        "ln_ic50_median": round(float(sub["LN_IC50"].median()), 4),
        "ic50_nm_median": round(float(_ln_ic50_to_nm(sub["LN_IC50"].median())), 1),
        "auc_mean": round(float(sub["AUC"].mean()), 4),
        "z_score_mean": round(float(sub["Z_SCORE"].mean()), 4),
        "n_cells_strong": int((sub["IC50_NM"] < 100).sum()),
    }

    if cell_line:
        cell_norm = normalize_cell_line(cell_line)
        match = sub[sub["CELL_LINE_NAME_NORM"].str.contains(cell_norm, na=False, regex=False)]
        if match.empty:
            result.update({
                "cell_line_query": cell_line,
                "cell_line_in_gdsc2": False,
            })
        else:
            row = match.iloc[0]
            ic50_nm = float(row["IC50_NM"])
            result.update({
                "cell_line_query": cell_line,
                "cell_line_in_gdsc2": True,
                "cell_line_name": str(row["CELL_LINE_NAME"]),
                "cosmic_id": int(row["COSMIC_ID"]),
                "cell_line_ln_ic50": round(float(row["LN_IC50"]), 4),
                "cell_line_ic50_nm": round(ic50_nm, 1),
                "cell_line_auc": round(float(row["AUC"]), 4),
                "cell_line_z_score": round(float(row["Z_SCORE"]), 4),
                "tcga_desc": str(row["TCGA_DESC"]),
                "gdsc_tissue_2": str(row["gdsc_tissue_2"]),
                "sensitivity_class": _classify_gdsc2_sensitivity(ic50_nm),
            })
    return result


def get_top_drugs_for_cell_gdsc2(cell_line: str, top_n: int = 20) -> list[dict]:
    """세포주에서 IC50 작은 (=민감) 약물 Top-N (LN_IC50 오름차순)."""
    df = load_gdsc2_long()
    if df.empty:
        return []
    cell_norm = normalize_cell_line(cell_line)
    sub = df[df["CELL_LINE_NAME_NORM"].str.contains(cell_norm, na=False, regex=False)]
    if sub.empty:
        return []
    sub = sub.sort_values("LN_IC50", ascending=True).head(top_n)
    return [
        {
            "rank": i + 1,
            "chembl_id": r["molecule_chembl_id"],
            "drug_name": str(r["DRUG_NAME"]),
            "cell_line_name": str(r["CELL_LINE_NAME"]),
            "ln_ic50": round(float(r["LN_IC50"]), 4),
            "ic50_nm": round(float(r["IC50_NM"]), 1),
            "auc": round(float(r["AUC"]), 4),
            "z_score": round(float(r["Z_SCORE"]), 4),
            "sensitivity_class": _classify_gdsc2_sensitivity(float(r["IC50_NM"])),
        }
        for i, (_, r) in enumerate(sub.iterrows())
    ]


def get_compound_distribution_gdsc2(chembl_id: str) -> dict:
    """약물의 NSCLC 전체 cell line IC50 분포 + scatter용 all_cells."""
    df = load_gdsc2_long()
    if df.empty:
        return {"chembl_id": chembl_id, "in_gdsc2": False}

    cid = normalize_compound_id(chembl_id)
    sub = df[df["molecule_chembl_id"] == cid]
    if sub.empty:
        return {"chembl_id": cid, "in_gdsc2": False}

    strong = sub[sub["IC50_NM"] < 100].sort_values("LN_IC50")
    return {
        "chembl_id": cid,
        "in_gdsc2": True,
        "drug_name": str(sub.iloc[0]["DRUG_NAME"]),
        "n_cells_tested": len(sub),
        "n_cells_strong": len(strong),
        "ln_ic50_distribution": {
            "mean": round(float(sub["LN_IC50"].mean()), 4),
            "median": round(float(sub["LN_IC50"].median()), 4),
            "std": round(float(sub["LN_IC50"].std()), 4),
            "min": round(float(sub["LN_IC50"].min()), 4),
            "max": round(float(sub["LN_IC50"].max()), 4),
            "q25": round(float(sub["LN_IC50"].quantile(0.25)), 4),
            "q75": round(float(sub["LN_IC50"].quantile(0.75)), 4),
        },
        "ic50_distribution_nm": {
            "median": round(float(_ln_ic50_to_nm(sub["LN_IC50"].median())), 1),
            "min": round(float(sub["IC50_NM"].min()), 1),
            "max": round(float(sub["IC50_NM"].max()), 1),
            "q25": round(float(_ln_ic50_to_nm(sub["LN_IC50"].quantile(0.25))), 1),
            "q75": round(float(_ln_ic50_to_nm(sub["LN_IC50"].quantile(0.75))), 1),
        },
        "top_strong_cells": [
            {
                "cell_line_name": str(r["CELL_LINE_NAME"]),
                "tcga_desc": str(r["TCGA_DESC"]),
                "ic50_nm": round(float(r["IC50_NM"]), 1),
                "z_score": round(float(r["Z_SCORE"]), 4),
            }
            for _, r in strong.head(10).iterrows()
        ],
        "all_cells": [
            {
                "cell_line_name": str(r["CELL_LINE_NAME"]),
                "tcga_desc": str(r["TCGA_DESC"]),
                "ic50_nm": round(float(r["IC50_NM"]), 1),
                "ln_ic50": round(float(r["LN_IC50"]), 4),
                "z_score": round(float(r["Z_SCORE"]), 4),
            }
            for _, r in sub.iterrows()
        ],
    }


def get_nsclc_cell_lines_gdsc2() -> list[dict]:
    """GDSC2 측정된 NSCLC cell line 리스트 (Mode 2 picker용).

    측정 약물 수 내림차순.
    """
    df = load_gdsc2_long()
    if df.empty:
        return []
    grouped = (
        df.groupby(["CELL_LINE_NAME", "COSMIC_ID", "TCGA_DESC", "gdsc_tissue_2"])
        .size()
        .reset_index(name="n_drugs")
        .sort_values("n_drugs", ascending=False)
    )
    return [
        {
            "cell_line_name": str(r["CELL_LINE_NAME"]),
            "cosmic_id": int(r["COSMIC_ID"]),
            "tcga_desc": str(r["TCGA_DESC"]),
            "gdsc_tissue_2": str(r["gdsc_tissue_2"]),
            "n_drugs": int(r["n_drugs"]),
        }
        for _, r in grouped.iterrows()
    ]


def compute_cross_source_validation(chembl_id: str, cell_line: str) -> dict:
    """PRISM lfc + GDSC2 IC50 cross-source 검증.

    Mode 2 mockup 2.PNG 'Cross-source 검증' 카드 데이터 contract.

    일관성 판정 임계:
      PRISM sensitive: lfc < -0.5
      PRISM resistant: lfc > +0.5
      GDSC2 sensitive: IC50 < 1 μM (1000 nM)
      GDSC2 resistant: IC50 > 10 μM (10000 nM)

    Returns:
        consistency: concordant_sensitive | concordant_resistant |
                     discordant | weak_signal | prism_only | gdsc2_only | no_data
    """
    prism = get_prism_response(chembl_id, cell_line)
    gdsc2 = get_gdsc2_response(chembl_id, cell_line)

    prism_has = prism.get("in_prism") and prism.get("cell_line_in_prism")
    gdsc2_has = gdsc2.get("in_gdsc2") and gdsc2.get("cell_line_in_gdsc2")

    if not prism_has and not gdsc2_has:
        consistency, consistency_kr = "no_data", "데이터 없음"
    elif prism_has and not gdsc2_has:
        consistency, consistency_kr = "prism_only", "PRISM 단독 (GDSC2 미수집)"
    elif gdsc2_has and not prism_has:
        consistency, consistency_kr = "gdsc2_only", "GDSC2 단독 (PRISM 미수집)"
    else:
        prism_lfc = prism["cell_line_lfc"]
        gdsc2_ic50 = gdsc2["cell_line_ic50_nm"]
        prism_sens = prism_lfc < -0.5
        prism_resist = prism_lfc > 0.5
        gdsc2_sens = gdsc2_ic50 < 1000
        gdsc2_resist = gdsc2_ic50 > 10000

        if prism_sens and gdsc2_sens:
            consistency, consistency_kr = "concordant_sensitive", "일치 — 둘 다 민감"
        elif prism_resist and gdsc2_resist:
            consistency, consistency_kr = "concordant_resistant", "일치 — 둘 다 저항"
        elif (prism_sens and gdsc2_resist) or (prism_resist and gdsc2_sens):
            consistency, consistency_kr = "discordant", "불일치 — 두 source 상반"
        else:
            consistency, consistency_kr = "weak_signal", "약한 신호 (둘 중 하나 미달)"

    return {
        "chembl_id": normalize_compound_id(chembl_id),
        "cell_line": cell_line,
        "prism": prism if prism_has else {"available": False, "raw": prism},
        "gdsc2": gdsc2 if gdsc2_has else {"available": False, "raw": gdsc2},
        "both_available": prism_has and gdsc2_has,
        "consistency": consistency,
        "consistency_kr": consistency_kr,
    }


def compute_model_vs_gdsc2_correlation() -> dict:
    """Champion model OOF prob ↔ GDSC2 mean LN_IC50 Spearman ρ (compound 단위).

    NOTE:
      - champion = compound-level (cell-line aware 아님)
      - GDSC2 mean LN_IC50: compound별 NSCLC cell line 평균
      - 음의 상관 기대 (high prob → low IC50)
    """
    df = load_gdsc2_long()
    if df.empty:
        return {"in_gdsc2": False, "reason": "no_gdsc2"}

    oof_paths = [
        _PROJECT.parent / "results" / "e2_tcga_crispr" / "oof_predictions.csv",
        _PROJECT / "results" / "e2_tcga_crispr" / "oof_predictions.csv",
        _PROJECT / "results" / "e6" / "oof_predictions.csv",
    ]
    oof_path = next((p for p in oof_paths if p.exists()), None)
    if oof_path is None:
        return {"in_gdsc2": True, "spearman_rho": None, "reason": "oof_not_found",
                "tried_paths": [str(p) for p in oof_paths]}

    oof = pd.read_csv(oof_path)
    id_col = next(
        (c for c in oof.columns if c.lower() in ("compound_id", "molecule_chembl_id", "chembl_id")),
        None,
    )
    pred_col = next(
        (c for c in oof.columns if "pred" in c.lower() or "prob" in c.lower()),
        None,
    )
    if not id_col or not pred_col:
        return {"in_gdsc2": True, "spearman_rho": None, "reason": "oof_schema_unknown",
                "oof_cols": oof.columns.tolist()}

    oof = oof[[id_col, pred_col]].rename(columns={id_col: "molecule_chembl_id", pred_col: "model_prob"})
    oof["molecule_chembl_id"] = oof["molecule_chembl_id"].astype(str).str.strip()

    gdsc2_agg = df.groupby("molecule_chembl_id")["LN_IC50"].mean().reset_index()
    merged = oof.merge(gdsc2_agg, on="molecule_chembl_id", how="inner")

    if len(merged) < 3:
        return {"in_gdsc2": True, "spearman_rho": None, "n": len(merged),
                "reason": "insufficient_overlap"}

    rho = merged[["model_prob", "LN_IC50"]].corr(method="spearman").iloc[0, 1]
    return {
        "in_gdsc2": True,
        "n": int(len(merged)),
        "spearman_rho": round(float(rho), 4),
        "interpretation": (
            "강한 음의 상관 (모델 high prob ↔ GDSC2 low IC50 = 민감)"
            if rho < -0.5
            else "중간 음의 상관"
            if rho < -0.2
            else "약한 상관 또는 무관"
        ),
        "oof_source": str(oof_path.relative_to(_PROJECT.parent)),
    }


def get_cross_source_pool() -> list[dict]:
    """PRISM ∩ GDSC2 cross-source 약물 풀.

    Mode 2 picker 우선순위 + Library 카드 'Cross-source 검증 가능' 배지 활성화.
    Phase Y 메모리 '28풀' 산출 (PRISM 213 ∩ GDSC2 30).
    """
    g_df = load_gdsc2_long()
    if g_df.empty:
        return []
    p_df = load_prism_long()
    if p_df.empty:
        return []

    g_compounds = set(g_df["molecule_chembl_id"].unique())
    p_compounds = set(p_df["molecule_chembl_id"].unique())
    overlap = g_compounds & p_compounds

    g_meta = g_df[["molecule_chembl_id", "DRUG_NAME"]].drop_duplicates("molecule_chembl_id")
    g_meta_dict = dict(zip(g_meta["molecule_chembl_id"], g_meta["DRUG_NAME"]))

    return sorted(
        [{"chembl_id": cid, "drug_name": str(g_meta_dict.get(cid, ""))} for cid in overlap],
        key=lambda x: x["drug_name"],
    )


# Mode 2 디폴트 데모 시나리오 (mockup 3.PNG / 4.PNG와 정합)
DEMO_SCENARIO_GDSC2 = {
    "single": {
        "cell_line": "H1975",
        "drug": {
            "name": "Osimertinib",
            "chembl_id": "CHEMBL3353410",
            # 검증값 (35_gdsc2_to_long.py 실행 결과)
            "expected_ln_ic50": -3.2783,
            "expected_ic50_nm": 37.7,
            "expected_auc": 0.5205,
            "expected_z_score": -3.8534,
            "expected_sensitivity": "strong_sensitive",
        },
    },
    "combo": {
        "cell_line": "H1975",
        "drug_a": {
            "name": "Osimertinib",
            "chembl_id": "CHEMBL3353410",
            "target": "EGFR",
            "in_gdsc2": True,
            "in_prism": True,
        },
        "drug_b": {
            "name": "Cobimetinib",
            "chembl_id": "CHEMBL2146883",
            "target": "MEK1/2",
            "in_gdsc2": False,
            "in_prism": True,
            "note": "GDSC2 미수집 → 단일 source(PRISM)만 활용 + 모델 추론 표기",
        },
    },
}
