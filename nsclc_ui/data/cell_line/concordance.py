"""
nsclc_ui.data.cell_line.concordance

4-source 검증 — 같은 (cell, drug) 조합에서 multiple 데이터 소스 일치도.

4 sources:
- P (PRISM): 실측 lfc, single dose, 4,684 drug × 98 cell
- A (A 모델 예측): A v3 OOF prediction, lfc scale
- G (GDSC2): LN_IC50/AUC, cross-source 28 drug 일부에만 존재
- Z (Z-score): cell 내 percentile (이 cell에서 다른 drug 대비 효과 크기)

§1.4 정직 narrative:
- "4-source 검증" = 4 source 중 가능한 만큼만 표시. 없으면 "—" 표시
- GDSC2는 28 drug pool만 cover. 대부분 drug에서 "GDSC2 unavailable"
- Z-score는 cell-line 내 cross-drug ranking (cell baseline 제거)
"""

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from .loader import _load_prism, _load_a_v3_predictions, get_cell_drug_response

_BASE = Path(__file__).resolve().parents[3]
GDSC2_LONG = _BASE / "data/derived/gdsc2_nsclc_long.parquet"
CROSS_SOURCE = _BASE / "data/derived/cross_source_pool.csv"


@lru_cache(maxsize=1)
def _load_gdsc2():
    """GDSC2 long parquet. cols: DRUG_ID, DRUG_NAME, molecule_chembl_id,
    COSMIC_ID, CELL_LINE_NAME, ..., LN_IC50, AUC, Z_SCORE, RMSE"""
    if not GDSC2_LONG.exists():
        return None
    df = pd.read_parquet(GDSC2_LONG)
    return df


@lru_cache(maxsize=1)
def _load_cross_source_chembl_ids():
    """cross_source_pool.csv의 chembl_id set (28 drug)."""
    if not CROSS_SOURCE.exists():
        return set()
    df = pd.read_csv(CROSS_SOURCE)
    return set(df["molecule_chembl_id"].astype(str).str.upper().str.strip())


@lru_cache(maxsize=1)
def _build_zscore_pivot():
    """
    A v3 prediction → cell-row z-score pivot.
    각 cell row에서 4684 drug 중 그 drug의 z-score = (lfc_pred - row_mean) / row_std
    """
    a_v3 = _load_a_v3_predictions()
    pivot = a_v3.pivot_table(
        index="depmap_id", columns="broad_id", values="lfc_pred", aggfunc="mean"
    )
    row_mean = pivot.mean(axis=1)
    row_std = pivot.std(axis=1).replace(0, np.nan)
    pivot_z = pivot.sub(row_mean, axis=0).div(row_std + 1e-6, axis=0)
    return pivot_z


def _get_gdsc2_match(broad_id: str, depmap_id: str, ccle_name: str):
    """
    GDSC2에서 (drug, cell) 매칭 lookup.

    GDSC2는 DRUG_NAME + CELL_LINE_NAME으로 매칭.
    broad_id ↔ GDSC2 DRUG_ID 직접 매핑 없음 → drug_name 기반 비교.
    cross_source_pool은 chembl_id 기준 28 drug.

    Returns:
        dict with LN_IC50, AUC, Z_SCORE if matched, else None
    """
    gdsc2 = _load_gdsc2()
    if gdsc2 is None:
        return None

    # PRISM drug name 기반 GDSC2 lookup
    prism = _load_prism()
    drug_row = prism[prism["broad_id"] == broad_id].head(1)
    if len(drug_row) == 0:
        return None
    drug_name = str(drug_row.iloc[0].get("name", "")).strip().lower()
    if not drug_name:
        return None

    # GDSC2 DRUG_NAME 대소문자 무시 매칭
    g_match = gdsc2[gdsc2["DRUG_NAME"].astype(str).str.strip().str.lower() == drug_name]
    if len(g_match) == 0:
        return None

    # Cell name 매칭. CCLE_name "NCIH1975_LUNG" → GDSC2 "NCI-H1975" 형식 다름
    # 간단히: ccle_short ("NCIH1975") substring 매칭
    ccle_short = ccle_name.replace("_LUNG", "").replace("_", "").upper()
    g_cell_match = g_match[
        g_match["CELL_LINE_NAME"].astype(str).str.replace("-", "").str.replace(" ", "").str.upper().str.contains(ccle_short, na=False)
    ]
    if len(g_cell_match) == 0:
        return None

    row = g_cell_match.iloc[0]
    return {
        "ln_ic50": float(row.get("LN_IC50", np.nan)),
        "ic50_um": float(np.exp(row.get("LN_IC50", np.nan))) if not pd.isna(row.get("LN_IC50")) else None,
        "auc": float(row.get("AUC", np.nan)) if not pd.isna(row.get("AUC")) else None,
        "z_score": float(row.get("Z_SCORE", np.nan)) if not pd.isna(row.get("Z_SCORE")) else None,
    }


def get_concordance(depmap_id: str, broad_id: str):
    """
    4-source 검증 결과.

    Returns:
        dict:
            sources: list of {
                code: "P"|"A"|"G"|"Z",
                label: "PRISM" | "A 예측" | "GDSC2" | "Z-score",
                value: str (display),
                available: bool,
                interpretation: "sensitive" | "intermediate" | "resistant" | None,
            }
            overall: "concordant_sensitive" | "concordant_resistant" | "partial" | "discordant" | "insufficient"
            n_available: int
            n_concordant: int
            note: str (narrative)
    """
    resp = get_cell_drug_response(depmap_id, broad_id)
    if resp.get("error"):
        return {
            "sources": [],
            "overall": "insufficient",
            "n_available": 0,
            "n_concordant": 0,
            "note": resp["error"],
        }

    sources = []
    interpretations = []

    # P: PRISM
    prism_lfc = resp.get("prism_lfc_obs")
    if prism_lfc is not None and not pd.isna(prism_lfc):
        interp = _classify_lfc(prism_lfc)
        sources.append({
            "code": "P",
            "label": "PRISM",
            "value": f"lfc {prism_lfc:+.3f}",
            "available": True,
            "interpretation": interp,
        })
        interpretations.append(interp)
    else:
        sources.append({
            "code": "P",
            "label": "PRISM",
            "value": "—",
            "available": False,
            "interpretation": None,
        })

    # A: A 모델 예측
    a_pred = resp.get("a_pred_lfc")
    if a_pred is not None and not pd.isna(a_pred):
        interp = _classify_lfc(a_pred)
        sources.append({
            "code": "A",
            "label": "A 예측",
            "value": f"lfc {a_pred:+.3f}",
            "available": True,
            "interpretation": interp,
        })
        interpretations.append(interp)
    else:
        sources.append({
            "code": "A",
            "label": "A 예측",
            "value": "—",
            "available": False,
            "interpretation": None,
        })

    # G: GDSC2
    gdsc2_match = _get_gdsc2_match(broad_id, depmap_id, resp.get("ccle_name", ""))
    if gdsc2_match and gdsc2_match.get("ic50_um") is not None:
        ic50 = gdsc2_match["ic50_um"]
        # IC50 < 1 μM = sensitive, > 10 μM = resistant
        if ic50 < 1.0:
            interp = "sensitive"
        elif ic50 > 10.0:
            interp = "resistant"
        else:
            interp = "intermediate"
        sources.append({
            "code": "G",
            "label": "GDSC2",
            "value": f"IC50 {ic50:.2f} μM",
            "available": True,
            "interpretation": interp,
        })
        interpretations.append(interp)
    else:
        sources.append({
            "code": "G",
            "label": "GDSC2",
            "value": "unavailable",
            "available": False,
            "interpretation": None,
        })

    # Z: Z-score (cell row z-score from A v3 predictions)
    z_pivot = _build_zscore_pivot()
    z_val = None
    if depmap_id in z_pivot.index and broad_id in z_pivot.columns:
        z_raw = z_pivot.loc[depmap_id, broad_id]
        if not pd.isna(z_raw):
            z_val = float(z_raw)
    if z_val is not None:
        # z < -1 = sensitive (이 cell에서 강한 효과), z > 1 = resistant
        if z_val < -1.0:
            interp = "sensitive"
        elif z_val > 1.0:
            interp = "resistant"
        else:
            interp = "intermediate"
        sources.append({
            "code": "Z",
            "label": "Z-score",
            "value": f"z {z_val:+.2f}",
            "available": True,
            "interpretation": interp,
        })
        interpretations.append(interp)
    else:
        sources.append({
            "code": "Z",
            "label": "Z-score",
            "value": "—",
            "available": False,
            "interpretation": None,
        })

    # Overall concordance
    n_avail = len(interpretations)
    if n_avail == 0:
        overall = "insufficient"
        n_concordant = 0
        note = "no data sources available"
    else:
        from collections import Counter
        counts = Counter(interpretations)
        most_common, n_concordant = counts.most_common(1)[0]
        if n_concordant == n_avail and n_avail >= 2:
            overall = f"concordant_{most_common}"
            note = f"{n_avail} sources agree: {most_common}"
        elif n_concordant >= 2:
            overall = "partial"
            note = f"{n_concordant}/{n_avail} agree: {most_common}"
        else:
            overall = "discordant"
            note = f"sources disagree: {dict(counts)}"

    return {
        "sources": sources,
        "overall": overall,
        "n_available": n_avail,
        "n_concordant": n_concordant,
        "note": note,
    }


def _classify_lfc(lfc: float):
    """lfc → sensitive/intermediate/resistant."""
    if lfc < -0.5:
        return "sensitive"
    elif lfc > 0.0:
        return "resistant"
    else:
        return "intermediate"
