"""
nsclc_ui.data.patient.loader

TCGA 환자 dropdown 옵션 + 실제 모드 lookup.

데이터 소스:
- TCGA mutation matrix: 942 × 23 (3 meta + 20 gene)
- patient_drug_ranking: 4.4M rows (B 모델 결과)
- patient_top_cells: 942 × 19 (top-5 cell per patient)
"""

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

# nsclc_ui/data/patient/loader.py → parents[3] = /Users/yj/Desktop/5team/final
_BASE = Path(__file__).resolve().parents[3]

TCGA_MUT = _BASE / "data/external/tcga_nsclc/nsclc_mutation_matrix.parquet"
RANK = _BASE / "data/derived/patient_drug_ranking.parquet"
TOP_CELLS = _BASE / "data/derived/patient_top_cells.parquet"

ACTIONABLE_GENES = [
    "ALK", "BRAF", "CDKN2A", "EGFR", "ERBB2", "KEAP1", "KRAS", "MAP2K1",
    "MET", "NF1", "NTRK1", "NTRK2", "NTRK3", "PIK3CA", "PTEN", "RB1",
    "RET", "ROS1", "STK11", "TP53",
]


@lru_cache(maxsize=1)
def _load_tcga_mut():
    return pd.read_parquet(TCGA_MUT)


@lru_cache(maxsize=1)
def _load_rank():
    return pd.read_parquet(RANK)


@lru_cache(maxsize=1)
def _load_top_cells():
    return pd.read_parquet(TOP_CELLS)


@lru_cache(maxsize=1)
def _build_patient_options():
    """
    942 환자 dropdown options.
    label = "TCGA-XX-XXXX · LUAD · EGFR + TP53"
    value = sample_id
    """
    tcga = _load_tcga_mut()
    options = []
    for _, row in tcga.iterrows():
        sample_id = row["sample_id"]
        cancer = row.get("cancer_type", "")
        muts = [g for g in ACTIONABLE_GENES if row.get(g, 0) == 1]
        mut_str = " + ".join(muts[:3])
        if len(muts) > 3:
            mut_str += f" + {len(muts) - 3}more"
        if not mut_str:
            mut_str = "(no actionable mut)"
        label = f"{sample_id} · {cancer} · {mut_str}"
        options.append({"label": label, "value": sample_id})
    # Sort: 시연 친화적 (mutation 많은 환자 + EGFR 있는 환자 우선)
    return options


def get_patient_options():
    return _build_patient_options()


def get_mutation_chip_genes():
    """Chip 후보 — 20 actionable genes 알파벳 순."""
    return list(ACTIONABLE_GENES)


def get_patient_mutations(sample_id: str):
    """Patient의 active mutations list."""
    tcga = _load_tcga_mut()
    row = tcga[tcga["sample_id"] == sample_id]
    if len(row) == 0:
        return []
    row = row.iloc[0]
    return [g for g in ACTIONABLE_GENES if row.get(g, 0) == 1]


def get_patient_top_cells(sample_id: str):
    """Top-5 similar cells for a patient."""
    top = _load_top_cells()
    row = top[top["sample_id"] == sample_id]
    if len(row) == 0:
        return None
    row = row.iloc[0]
    return {
        "sample_id": sample_id,
        "cells": [
            {
                "rank": k,
                "depmap_id": row.get(f"top{k}_cell"),
                "ccle_name": row.get(f"top{k}_ccle_name"),
                "sim": float(row.get(f"top{k}_sim", 0)),
            }
            for k in range(1, 6)
        ],
        "mean_top_sim": float(row.get("mean_top_sim", 0)),
    }


def get_patient_top_drugs(sample_id: str, n: int = 10, rank_col: str = "rank_hybrid"):
    """
    Patient의 top-N drug ranking.

    rank_col options:
    - "rank_hybrid"           : tier 1 (target match) + z-score sub-rank (default)
    - "rank_zscore_weighted"  : z-score only (cell baseline 제거)
    - "rank_pred_weighted"    : raw lfc_pred only
    """
    rank = _load_rank()
    sub = rank[rank["sample_id"] == sample_id]
    if len(sub) == 0:
        return []
    top = sub.sort_values(rank_col).head(n)
    return top.to_dict("records")


def get_patient_response(sample_id: str):
    """
    실제 모드 통합 응답.

    Returns:
        dict:
            sample_id, patient_id, cancer_type
            mutations (list of active genes)
            top_cells (list of 5 cell dicts)
            mean_top_sim (float)
            top_drugs (list of 10 drug dicts, sorted by rank_hybrid)
            error (if any)
    """
    if not sample_id:
        return {"error": "missing sample_id"}

    tcga = _load_tcga_mut()
    pat_row = tcga[tcga["sample_id"] == sample_id]
    if len(pat_row) == 0:
        return {"error": f"patient {sample_id} not found"}
    pat = pat_row.iloc[0]

    mutations = get_patient_mutations(sample_id)
    top_cells_info = get_patient_top_cells(sample_id)
    top_drugs = get_patient_top_drugs(sample_id, n=10, rank_col="rank_hybrid")

    return {
        "sample_id": sample_id,
        "patient_id": pat.get("patient_id", ""),
        "cancer_type": pat.get("cancer_type", ""),
        "mutations": mutations,
        "n_mutations": len(mutations),
        "top_cells": top_cells_info["cells"] if top_cells_info else [],
        "mean_top_sim": top_cells_info["mean_top_sim"] if top_cells_info else 0.0,
        "top_drugs": top_drugs,
        "error": None,
    }
