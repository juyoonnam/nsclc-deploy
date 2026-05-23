"""
nsclc_ui/data/library/loader.py

33,057개 NSCLC 약물 재창출 후보 library 풀 통합 로더.

소스 (compound_id 기준 join):
- library_pool_final.csv (base, rank_score)
- compound_target_map.csv (primary_target, all_targets)
- scaffold_info.pkl (scaffold_smiles, family_size)
- cross_source_pool.csv (PRISM ∩ GDSC2, 28풀)
- pubmed_mention_full.csv (Surprising 룰용)
- chembl_mechanisms_full.csv (Repurpose-ready 룰용, cmpd당 max_phase aggregate)
- ct_gov_nsclc_full.csv (Repurpose-ready 룰용)

v2 변경:
- CHEMBL_MAX_PHASE_PATH → CHEMBL_MECHANISMS_FULL_PATH
- _load_chembl_max_phase_optional: groupby aggregate (한 cmpd 여러 target row 합산)
"""
from __future__ import annotations

import pickle
from functools import lru_cache
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[3]  # 5team/final/
DATA_DIR = BASE_DIR / "data"


LIBRARY_POOL_PATH = DATA_DIR / "derived" / "library_pool_final.csv"
TARGET_MAP_PATH = DATA_DIR / "derived" / "compound_target_map.csv"
SCAFFOLD_PKL_PATH = DATA_DIR / "cache" / "scaffold_info.pkl"
CROSS_SOURCE_PATH = DATA_DIR / "derived" / "cross_source_pool.csv"

PUBMED_FULL_PATH = BASE_DIR / "results" / "f1_litmining" / "pubmed_mention_full.csv"
CHEMBL_MECHANISMS_FULL_PATH = DATA_DIR / "derived" / "chembl_mechanisms_full.csv"
CT_GOV_PATH = DATA_DIR / "derived" / "ct_gov_nsclc_full.csv"


def _normalize_id(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.upper()


def _load_base_pool() -> pd.DataFrame:
    df = pd.read_csv(LIBRARY_POOL_PATH)
    df["compound_id"] = _normalize_id(df["compound_id"])
    df["category"] = df["final_category"].astype(str).str.split(".").str[0].str.strip()
    df.loc[~df["category"].isin(list("ABCDEX")), "category"] = "X"
    return df


def _load_targets() -> pd.DataFrame:
    df = pd.read_csv(TARGET_MAP_PATH)
    df["compound_id"] = _normalize_id(df["compound_id"])
    df["targets_list"] = (
        df["all_targets"].astype(str).str.split(";").apply(
            lambda xs: [x.strip() for x in xs if x and x.strip() and x.strip() != "nan"]
        )
    )
    return df[["compound_id", "primary_target", "targets_list", "action_type", "is_ambiguous"]]


def _load_scaffold() -> pd.DataFrame:
    with open(SCAFFOLD_PKL_PATH, "rb") as f:
        df = pickle.load(f)
    df = df.copy()
    df["compound_id"] = _normalize_id(df["compound_id"])
    return df[["compound_id", "scaffold_smiles", "family_size"]]


def _load_cross_source() -> pd.DataFrame:
    if not CROSS_SOURCE_PATH.exists():
        return pd.DataFrame(
            {"compound_id": [], "x_s_verified": [], "prism_n_cells": [], "gdsc2_n_cells": []}
        )
    df = pd.read_csv(CROSS_SOURCE_PATH)
    df = df.rename(columns={"molecule_chembl_id": "compound_id"})
    df["compound_id"] = _normalize_id(df["compound_id"])
    return df[["compound_id", "x_s_verified", "prism_n_cells", "gdsc2_n_cells"]]


def _load_pubmed_optional() -> pd.DataFrame:
    if not PUBMED_FULL_PATH.exists():
        return pd.DataFrame({"compound_id": [], "pubmed_hits": []})
    df = pd.read_csv(PUBMED_FULL_PATH)
    df = df.rename(columns={"molecule_chembl_id": "compound_id"})
    df["compound_id"] = _normalize_id(df["compound_id"])
    # no_pref_name 케이스는 실제 query 못 한 unknown → NaN 보존
    # ("pubmed mention 0" 으로 잘못 해석되는 것 방지)
    if "error" in df.columns:
        df.loc[df["error"] == "no_pref_name", "pubmed_hits"] = pd.NA
    return df[["compound_id", "pubmed_hits"]]


def _load_chembl_max_phase_optional() -> pd.DataFrame:
    """ChEMBL mechanisms_full.csv → cmpd당 max_phase aggregate."""
    if not CHEMBL_MECHANISMS_FULL_PATH.exists():
        return pd.DataFrame({"compound_id": [], "chembl_max_phase_any": []})
    df = pd.read_csv(CHEMBL_MECHANISMS_FULL_PATH)
    df["compound_id"] = _normalize_id(df["compound_id"])
    agg = (
        df.dropna(subset=["max_phase"])
        .groupby("compound_id", as_index=False)["max_phase"]
        .max()
        .rename(columns={"max_phase": "chembl_max_phase_any"})
    )
    return agg


def _load_ct_gov_optional() -> pd.DataFrame:
    if not CT_GOV_PATH.exists():
        return pd.DataFrame({"compound_id": [], "has_nsclc_trial": []})
    df = pd.read_csv(CT_GOV_PATH)
    df["compound_id"] = _normalize_id(df["compound_id"])
    return df[["compound_id", "has_nsclc_trial"]]


@lru_cache(maxsize=1)
def load_library_full() -> pd.DataFrame:
    base = _load_base_pool()
    targets = _load_targets()
    scaffold = _load_scaffold()
    xs = _load_cross_source()

    df = base.merge(targets, on="compound_id", how="left")
    df = df.merge(scaffold, on="compound_id", how="left")
    df = df.merge(xs, on="compound_id", how="left")
    df["x_s_verified"] = df["x_s_verified"].fillna(False).astype(bool)

    pm = _load_pubmed_optional()
    cm = _load_chembl_max_phase_optional()
    ct = _load_ct_gov_optional()

    if not pm.empty:
        df = df.merge(pm, on="compound_id", how="left")
    else:
        df["pubmed_hits"] = pd.NA

    if not cm.empty:
        df = df.merge(cm, on="compound_id", how="left")
    else:
        df["chembl_max_phase_any"] = pd.NA

    if not ct.empty:
        df = df.merge(ct, on="compound_id", how="left")
    else:
        df["has_nsclc_trial"] = pd.NA

    return df


def diagnose() -> dict:
    df = load_library_full()
    return {
        "total_rows": len(df),
        "columns": list(df.columns),
        "category_distribution": df["category"].value_counts().to_dict(),
        "x_s_verified_count": int(df["x_s_verified"].sum()),
        "has_target": int(df["primary_target"].notna().sum()),
        "has_scaffold": int(df["scaffold_smiles"].notna().sum()),
        "has_pubmed_hits": int(df["pubmed_hits"].notna().sum()),
        "pubmed_hits_gt0": int((df["pubmed_hits"].fillna(0) > 0).sum()),
        "has_chembl_max_phase": int(df["chembl_max_phase_any"].notna().sum()),
        "chembl_max_phase_ge3": int((df["chembl_max_phase_any"].fillna(0) >= 3).sum()),
        "has_ct_gov": int(df["has_nsclc_trial"].notna().sum()),
        "ct_gov_true": int((df["has_nsclc_trial"] == True).sum()),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(diagnose(), indent=2, ensure_ascii=False, default=str))
