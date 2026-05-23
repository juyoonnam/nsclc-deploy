"""
nsclc_ui.data.cell_line.loader

Cell/drug dropdown options + (cell, drug, dose) → response data lookup.

데이터 소스:
- PRISM long parquet: 449,584 rows (cell × drug × single dose)
- A v3 predictions: 449,400 rows (OOF prediction)
- TCGA mutation matrix: 942 환자 (cell-line의 marker mutation 표시용)
"""

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

# 5team/ 루트 기준. tabs/*.py → parents[3]. data/*.py → parents[3].
# nsclc_ui/data/cell_line/loader.py → parents[3] = /Users/yj/Desktop/5team/final
_BASE = Path(__file__).resolve().parents[3]

PRISM_LONG = _BASE / "data/derived/prism_nsclc_full_long.parquet"
A_V3_PRED = _BASE / "data/derived/cell_line_response_predictions_v3.parquet"
CCLE_MUT = _BASE / "data/derived/ccle_nsclc_mutation_matrix.parquet"

ACTIONABLE_GENES = [
    "ALK", "BRAF", "CDKN2A", "EGFR", "ERBB2", "KEAP1", "KRAS", "MAP2K1",
    "MET", "NF1", "NTRK1", "NTRK2", "NTRK3", "PIK3CA", "PTEN", "RB1",
    "RET", "ROS1", "STK11", "TP53",
]


@lru_cache(maxsize=1)
def _load_prism():
    """PRISM long DataFrame. (449,584 × 15)"""
    df = pd.read_parquet(PRISM_LONG)
    df["broad_id"] = df["broad_id"].astype(str).str.strip().str.upper()
    df["depmap_id"] = df["depmap_id"].astype(str).str.strip()
    df["ccle_name"] = df["ccle_name"].astype(str).str.strip()
    return df


@lru_cache(maxsize=1)
def _load_a_v3_predictions():
    """A v3 OOF predictions. (449,400 × 10)"""
    df = pd.read_parquet(A_V3_PRED)
    df["broad_id"] = df["broad_id"].astype(str).str.strip().str.upper()
    df["depmap_id"] = df["depmap_id"].astype(str).str.strip()
    return df


@lru_cache(maxsize=1)
def _load_ccle_mutations():
    """98 NSCLC × 20 actionable gene mutation matrix."""
    return pd.read_parquet(CCLE_MUT)


@lru_cache(maxsize=1)
def _build_cell_options():
    """98 cell dropdown options: [{label: "NCIH1975 — EGFR L858R+T790M", value: "ACH-001113"}, ...]

    label = ccle_name (LUNG suffix 제거) + 주요 mutation (max 2 genes)
    value = depmap_id (B 모델, cosine sim과 일관)
    """
    prism = _load_prism()
    ccle_mut = _load_ccle_mutations()
    mut_map = ccle_mut.set_index("depmap_id")[ACTIONABLE_GENES].to_dict("index")

    # ccle_name lookup per depmap_id
    name_map = (
        prism[["depmap_id", "ccle_name"]]
        .drop_duplicates()
        .set_index("depmap_id")["ccle_name"]
        .to_dict()
    )

    options = []
    for depmap_id in sorted(prism["depmap_id"].dropna().unique()):
        ccle_name = name_map.get(depmap_id, depmap_id)
        cell_short = ccle_name.replace("_LUNG", "")  # NCIH1975_LUNG → NCIH1975

        # 주요 mutation (최대 2개 표시)
        muts = mut_map.get(depmap_id, {})
        active_muts = [g for g in ACTIONABLE_GENES if muts.get(g, 0) == 1]
        if active_muts:
            mut_str = " + ".join(active_muts[:2])
            if len(active_muts) > 2:
                mut_str += f" + {len(active_muts) - 2}more"
            label = f"{cell_short} — {mut_str}"
        else:
            label = f"{cell_short} — (no actionable mut)"

        options.append({"label": label, "value": depmap_id})
    return options


@lru_cache(maxsize=1)
def _build_drug_options():
    """4,684 drug dropdown options: [{label: "Osimertinib", value: "BRD-K..."}, ...]"""
    prism = _load_prism()
    drugs = prism[["broad_id", "name"]].drop_duplicates(subset=["broad_id"])
    drugs = drugs.dropna(subset=["broad_id"])
    drugs["name_str"] = drugs["name"].fillna("(unnamed)").astype(str)
    drugs = drugs.sort_values("name_str")
    return [
        {"label": row["name_str"], "value": row["broad_id"]}
        for _, row in drugs.iterrows()
    ]


def get_cell_options():
    """Dropdown용 98 cell options."""
    return _build_cell_options()


def get_drug_options():
    """Dropdown용 4,684 drug options."""
    return _build_drug_options()


def get_cell_drug_response(depmap_id: str, broad_id: str, dose: float = None):
    """
    (cell, drug) 조합의 모든 데이터 lookup.

    Returns:
        dict with keys:
            depmap_id, broad_id, ccle_name, drug_name, target, moa, phase,
            prism_dose, prism_lfc_obs, a_pred_lfc, fold,
            mutations (list of mutated genes), error (if any)
    """
    if not depmap_id or not broad_id:
        return {"error": "missing depmap_id or broad_id"}

    depmap_id = str(depmap_id).strip()
    broad_id = str(broad_id).strip().upper()

    prism = _load_prism()
    a_v3 = _load_a_v3_predictions()
    ccle_mut = _load_ccle_mutations()

    # PRISM lookup (single dose 측정)
    prism_match = prism[
        (prism["depmap_id"] == depmap_id) & (prism["broad_id"] == broad_id)
    ]
    # A v3 lookup (OOF prediction)
    a_match = a_v3[
        (a_v3["depmap_id"] == depmap_id) & (a_v3["broad_id"] == broad_id)
    ]

    if len(prism_match) == 0 and len(a_match) == 0:
        return {
            "depmap_id": depmap_id,
            "broad_id": broad_id,
            "error": "no data for this (cell, drug) pair",
        }

    out = {
        "depmap_id": depmap_id,
        "broad_id": broad_id,
        "error": None,
    }

    # PRISM data (실측)
    if len(prism_match) > 0:
        row = prism_match.iloc[0]
        out["ccle_name"] = row.get("ccle_name", "")
        out["drug_name"] = row.get("name", "")
        out["target"] = row.get("target", "")
        out["moa"] = row.get("moa", "")
        out["phase"] = row.get("phase", "")
        out["smiles"] = row.get("smiles", "")
        out["prism_dose"] = float(row.get("dose", np.nan))
        out["prism_lfc_obs"] = float(row.get("lfc", np.nan))
    else:
        out["ccle_name"] = ""
        out["drug_name"] = ""
        out["target"] = ""
        out["moa"] = ""
        out["phase"] = ""
        out["smiles"] = ""
        out["prism_dose"] = None
        out["prism_lfc_obs"] = None

    # A v3 prediction
    if len(a_match) > 0:
        row = a_match.iloc[0]
        out["a_pred_lfc"] = float(row.get("lfc_pred", np.nan))
        out["fold"] = int(row.get("fold", -1))
        # PRISM에 없고 A v3에 있는 경우 drug name 보강
        if not out["drug_name"] and "drug_name" in a_match.columns:
            out["drug_name"] = row.get("drug_name", "")
    else:
        out["a_pred_lfc"] = None
        out["fold"] = None

    # Cell의 active mutations
    mut_row = ccle_mut[ccle_mut["depmap_id"] == depmap_id]
    if len(mut_row) > 0:
        row = mut_row.iloc[0]
        out["mutations"] = [g for g in ACTIONABLE_GENES if row.get(g, 0) == 1]
    else:
        out["mutations"] = []

    return out
