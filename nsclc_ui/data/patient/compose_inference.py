"""
nsclc_ui.data.patient.compose_inference

조립 모드 — user-input mutation set → 실시간 cosine sim → top-K cell → drug ranking.

Pipeline (실시간):
1. user mutation set → 20-dim binary vector
2. CCLE 98 cell mutation matrix와 cosine similarity (1 × 98)
3. top-K=5 cell 추출 + similarity
4. A v3 prediction에서 top-K cell의 lfc_pred → drug별 평균 (단순 + cosine-weighted)
5. drug target overlap 계산 (mutation set ∩ drug target)
6. Hybrid rank: Tier 1 (overlap > 0) + Tier 2, 각 tier 내 z-score sub-rank

70_train_patient_transfer.py + 73_patient_drug_hybrid_ranking.py와 동일 로직.
실시간 호출이라 빠름 (cosine sim 1×98 + drug average 4684 = ~50ms).
"""

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

_BASE = Path(__file__).resolve().parents[3]
CCLE_MUT = _BASE / "data/derived/ccle_nsclc_mutation_matrix.parquet"
A_V3_PRED = _BASE / "data/derived/cell_line_response_predictions_v3.parquet"

ACTIONABLE_GENES = [
    "ALK", "BRAF", "CDKN2A", "EGFR", "ERBB2", "KEAP1", "KRAS", "MAP2K1",
    "MET", "NF1", "NTRK1", "NTRK2", "NTRK3", "PIK3CA", "PTEN", "RB1",
    "RET", "ROS1", "STK11", "TP53",
]
ACTIONABLE_SET = set(ACTIONABLE_GENES)
STD_FLOOR = 0.1


@lru_cache(maxsize=1)
def _load_ccle_mut():
    return pd.read_parquet(CCLE_MUT)


@lru_cache(maxsize=1)
def _load_pred_pivot():
    """A v3 lfc_pred pivot (depmap_id × broad_id)."""
    a_v3 = pd.read_parquet(A_V3_PRED)
    pivot = a_v3.pivot_table(
        index="depmap_id", columns="broad_id", values="lfc_pred", aggfunc="mean"
    )
    return pivot


@lru_cache(maxsize=1)
def _load_pred_pivot_z():
    """A v3 lfc_pred row-wise z-score pivot (cell baseline 제거)."""
    pivot = _load_pred_pivot()
    row_mean = pivot.mean(axis=1)
    row_std = pivot.std(axis=1).replace(0, np.nan)
    return pivot.sub(row_mean, axis=0).div(row_std + 1e-6, axis=0)


@lru_cache(maxsize=1)
def _load_drug_meta():
    """Drug metadata + actionable target parsing."""
    a_v3 = pd.read_parquet(A_V3_PRED)
    cols = [c for c in ["broad_id", "drug_name", "target", "phase"] if c in a_v3.columns]
    meta = a_v3[cols].drop_duplicates(subset=["broad_id"]).copy()

    def parse_targets(s):
        if not isinstance(s, str) or not s.strip():
            return set()
        parts = [p.strip().upper() for p in s.replace(";", ",").split(",")]
        return {p for p in parts if p and p != "NAN"}

    meta["target_set"] = meta["target"].apply(parse_targets)
    meta["target_set_actionable"] = meta["target_set"].apply(lambda s: s & ACTIONABLE_SET)
    return meta


def compose_inference(mutation_set, top_k: int = 5, top_n_drugs: int = 10):
    """
    User-input mutation set에서 drug ranking 실시간 추론.

    Args:
        mutation_set: list[str] — actionable gene 이름 (e.g., ["EGFR", "TP53"])
        top_k: similar cell 개수 (default 5)
        top_n_drugs: 반환 drug 개수 (default 10)

    Returns:
        dict:
            mutation_set: list of input genes
            user_vector: 20-dim binary
            top_cells: list of {rank, depmap_id, ccle_name, sim}
            mean_top_sim: float
            top_drugs: list of dicts (top-N by hybrid rank):
                broad_id, drug_name, target, phase,
                pred_lfc_mean, pred_lfc_weighted,
                pred_zscore_mean, pred_zscore_weighted,
                target_overlap_count, target_overlap_genes,
                hybrid_tier, rank_hybrid
            n_tier1: tier 1 drug 수
            error
    """
    if not mutation_set:
        return {"error": "no mutation provided", "top_drugs": [], "top_cells": []}

    valid_muts = [g for g in mutation_set if g in ACTIONABLE_SET]
    if not valid_muts:
        return {"error": f"no actionable gene in {mutation_set}", "top_drugs": [], "top_cells": []}

    # [1] User vector
    user_vec = np.zeros(len(ACTIONABLE_GENES), dtype=np.float32)
    for g in valid_muts:
        user_vec[ACTIONABLE_GENES.index(g)] = 1.0

    # [2] Cosine sim with CCLE 98 cell
    ccle = _load_ccle_mut()
    C = ccle[ACTIONABLE_GENES].values.astype(np.float32)
    sim = cosine_similarity(user_vec.reshape(1, -1), C)[0]  # shape (98,)
    sim = np.nan_to_num(sim, nan=0.0)

    # [3] Top-K cells
    top_idx = np.argsort(-sim)[:top_k]
    top_depmaps = ccle.iloc[top_idx]["depmap_id"].tolist()
    top_sims = sim[top_idx]

    # ccle_name lookup
    a_v3 = pd.read_parquet(A_V3_PRED)
    name_map = a_v3[["depmap_id", "ccle_name"]].drop_duplicates().set_index("depmap_id")["ccle_name"].to_dict()

    top_cells = [
        {
            "rank": k + 1,
            "depmap_id": top_depmaps[k],
            "ccle_name": name_map.get(top_depmaps[k], ""),
            "sim": float(top_sims[k]),
        }
        for k in range(min(top_k, len(top_depmaps)))
    ]

    # [4] Drug-level prediction averaging
    pred_pivot = _load_pred_pivot()
    pred_pivot_z = _load_pred_pivot_z()

    valid_depmaps = [d for d in top_depmaps if d in pred_pivot.index]
    valid_sims = np.array([top_sims[i] for i, d in enumerate(top_depmaps) if d in pred_pivot.index])
    if not valid_depmaps:
        return {
            "mutation_set": valid_muts,
            "user_vector": user_vec.tolist(),
            "top_cells": top_cells,
            "mean_top_sim": float(top_sims.mean()),
            "top_drugs": [],
            "n_tier1": 0,
            "error": "no cell with predictions",
        }

    sub_pred = pred_pivot.loc[valid_depmaps]
    sub_z = pred_pivot_z.loc[valid_depmaps]

    # Simple + weighted mean
    pred_mean = sub_pred.mean(axis=0)
    z_mean = sub_z.mean(axis=0)
    w_sum = valid_sims.sum()
    if w_sum > 1e-8:
        weights = valid_sims / w_sum
        pred_weighted = (sub_pred.values * weights[:, None]).sum(axis=0)
        z_weighted = (sub_z.values * weights[:, None]).sum(axis=0)
    else:
        pred_weighted = pred_mean.values
        z_weighted = z_mean.values

    # [5] Drug metadata + target overlap
    drug_meta = _load_drug_meta()
    drug_meta_indexed = drug_meta.set_index("broad_id")
    pat_gene_set = set(valid_muts)

    # Build drug-level DataFrame
    drug_df = pd.DataFrame({
        "broad_id": pred_pivot.columns,
        "pred_lfc_mean": pred_mean.values.astype(np.float32),
        "pred_lfc_weighted": pred_weighted.astype(np.float32),
        "pred_zscore_mean": z_mean.values.astype(np.float32),
        "pred_zscore_weighted": z_weighted.astype(np.float32),
    })

    # Merge metadata
    drug_df = drug_df.merge(
        drug_meta[["broad_id", "drug_name", "target", "phase", "target_set",
                   "target_set_actionable"]],
        on="broad_id", how="left"
    )

    # target_overlap per drug
    def compute_overlap(target_set):
        if not isinstance(target_set, (set, frozenset)):
            return 0, ""
        overlap = pat_gene_set & target_set
        return len(overlap), ", ".join(sorted(overlap)) if overlap else ""

    drug_df["_overlap"] = drug_df["target_set"].apply(compute_overlap)
    drug_df["target_overlap_count"] = drug_df["_overlap"].apply(lambda x: x[0]).astype(np.int8)
    drug_df["target_overlap_genes"] = drug_df["_overlap"].apply(lambda x: x[1])
    drug_df["drug_targets_actionable"] = drug_df["target_set_actionable"].apply(
        lambda s: ", ".join(sorted(s)) if s else ""
    )
    drug_df = drug_df.drop(columns=["_overlap", "target_set", "target_set_actionable"])

    # [6] Hybrid rank
    drug_df["hybrid_tier"] = np.where(drug_df["target_overlap_count"] > 0, 1, 2).astype(np.int8)
    drug_df["_zsort"] = drug_df["pred_zscore_weighted"].fillna(np.inf)
    drug_df = drug_df.sort_values(["hybrid_tier", "_zsort"]).reset_index(drop=True)
    drug_df["rank_hybrid"] = (drug_df.index + 1).astype(np.int32)
    drug_df = drug_df.drop(columns=["_zsort"])

    # Top-N
    top_drugs = drug_df.head(top_n_drugs).to_dict("records")

    return {
        "mutation_set": valid_muts,
        "user_vector": user_vec.tolist(),
        "top_cells": top_cells,
        "mean_top_sim": float(top_sims.mean()),
        "top_drugs": top_drugs,
        "n_tier1": int((drug_df["hybrid_tier"] == 1).sum()),
        "error": None,
    }
