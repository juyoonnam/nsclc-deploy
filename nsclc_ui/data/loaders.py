"""
Real data loaders — CSV 기반. 파일 없으면 빈 dict 반환.
"""

from pathlib import Path
import csv
import logging

logger = logging.getLogger(__name__)

# final/ 디렉토리 기준 (nsclc_ui의 부모)
_PROJECT = Path(__file__).resolve().parent.parent.parent


def load_kegg_targets() -> dict:
    """drug_target_moa.csv → {chembl_id: [{"target_name": ..., "mechanism_of_action": ..., ...}, ...]}"""
    path = _PROJECT / "data" / "kegg" / "drug_target_moa.csv"
    result: dict[str, list[dict]] = {}
    if not path.exists():
        return result
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid = row["molecule_chembl_id"]
            entry = {
                "target_name": row.get("target_name", ""),
                "mechanism_of_action": row.get("mechanism_of_action", ""),
                "action_type": row.get("action_type", ""),
                "target_chembl_id": row.get("target_chembl_id", ""),
            }
            result.setdefault(cid, []).append(entry)
    return result


def load_ranking_with_pains(top_n: int = 10) -> list[dict]:
    """Load ranking_scaffold.csv joined with pains_lipinski.csv.

    Returns list of dicts (top_n rows) with keys:
        chembl_id, rank, score, std, pains_flag, pains_desc,
        lipinski_pass, lipinski_violations, mw, is_positive
    """
    import pandas as pd

    ranking_path = _PROJECT / "results" / "e1_tuned" / "ranking_scaffold.csv"
    pains_path = _PROJECT / "data" / "pains_lipinski.csv"

    if not ranking_path.exists():
        return []

    rk = pd.read_csv(ranking_path)
    rk["molecule_chembl_id"] = rk["molecule_chembl_id"].astype(str).str.strip()
    rk = rk.sort_values("rank").head(top_n)

    if pains_path.exists():
        pl = pd.read_csv(pains_path)
        pl["chembl_id"] = pl["chembl_id"].astype(str).str.strip()
        merged = rk.merge(
            pl[["chembl_id", "pains_flag", "pains_desc",
                "lipinski_pass", "lipinski_violations", "mw"]],
            left_on="molecule_chembl_id",
            right_on="chembl_id",
            how="left",
        )
    else:
        merged = rk.copy()
        for col in ["pains_flag", "pains_desc", "lipinski_pass", "lipinski_violations", "mw"]:
            merged[col] = None

    rows = []
    for _, r in merged.iterrows():
        rows.append({
            "chembl_id": r["molecule_chembl_id"],
            "rank": int(r["rank"]),
            "score": round(float(r["y_pred_mean"]), 4),
            "std": round(float(r["y_pred_std"]), 3),
            "pains_flag": bool(r["pains_flag"]) if pd.notna(r.get("pains_flag")) else None,
            "pains_desc": str(r["pains_desc"]) if pd.notna(r.get("pains_desc")) else None,
            "lipinski_pass": bool(r["lipinski_pass"]) if pd.notna(r.get("lipinski_pass")) else None,
            "lipinski_violations": int(r["lipinski_violations"]) if pd.notna(r.get("lipinski_violations")) else None,
            "mw": round(float(r["mw"]), 1) if pd.notna(r.get("mw")) else None,
        })
    return rows


def load_selectivity_heatmap(top_n: int = 20) -> dict:
    """Load Top-N compounds' 16 pIC50 features for heatmap.

    Returns:
        {"z": list[list[float|None]], "x": list[str], "y": list[str]}
        z[row][col], x=feature names, y=compound IDs
    """
    import pandas as pd
    import numpy as np

    ranking_path = _PROJECT / "results" / "e1_tuned" / "ranking_scaffold.csv"
    features_path = _PROJECT / "data" / "features_e1" / "nsclc_features_X.csv"

    if not ranking_path.exists() or not features_path.exists():
        return {"z": [], "x": [], "y": []}

    rk = pd.read_csv(ranking_path)
    rk["molecule_chembl_id"] = rk["molecule_chembl_id"].astype(str).str.strip()
    rk = rk.sort_values("rank").head(top_n)

    feat = pd.read_csv(features_path)
    feat["compound_id"] = feat["compound_id"].astype(str).str.strip()
    pic_cols = [c for c in feat.columns if c.startswith("pic50_")]

    merged = rk.merge(
        feat[["compound_id"] + pic_cols],
        left_on="molecule_chembl_id",
        right_on="compound_id",
        how="left",
    )

    # Pretty column names
    col_labels = [c.replace("pic50_", "").replace("_", " ").title() for c in pic_cols]

    # Drug labels: rank + chembl_id
    y_labels = [f"#{int(r['rank'])} {r['molecule_chembl_id']}" for _, r in merged.iterrows()]

    z = merged[pic_cols].values.tolist()
    # Replace NaN with None for JSON/Plotly
    z = [[None if (v != v) else round(float(v), 2) for v in row] for row in z]

    return {"z": z, "x": col_labels, "y": y_labels, "raw_cols": pic_cols}


def load_evidence_map() -> dict:
    """Load label evidence for all compounds.

    Returns:
        {chembl_id: {phase, tier, label_source, match_type, is_positive}}
    """
    import pandas as pd

    labels_path = _PROJECT / "data" / "features_e1" / "nsclc_labels_y.csv"
    if not labels_path.exists():
        return {}

    lab = pd.read_csv(labels_path, usecols=[
        "compound_id", "final_phase", "final_tier",
        "label_source", "match_type", "is_positive",
    ])
    lab["compound_id"] = lab["compound_id"].astype(str).str.strip()

    result = {}
    for _, r in lab.iterrows():
        result[r["compound_id"]] = {
            "phase": int(r["final_phase"]) if pd.notna(r["final_phase"]) else None,
            "tier": str(r["final_tier"]) if pd.notna(r["final_tier"]) else None,
            "label_source": str(r["label_source"]) if pd.notna(r["label_source"]) else None,
            "match_type": str(r["match_type"]) if pd.notna(r["match_type"]) else None,
            "is_positive": bool(r["is_positive"]) if pd.notna(r["is_positive"]) else False,
        }
    return result


# ── Modality Scores v1 (E2 champion) ──────────────────────────

def load_modality_scores():
    """Load modality_scores_v1.csv → DataFrame."""
    import pandas as pd

    path = _PROJECT / "data" / "modality_scores_v1.csv"
    expected = [
        "compound_id", "prob", "drug_score", "adc_score", "protac_score",
        "glue_score", "rlt_score", "total_score", "rank_score",
        "primary_modality", "rationale",
    ]
    if not path.exists():
        import logging
        logging.getLogger(__name__).warning(f"modality_scores not found: {path}")
        return pd.DataFrame(columns=expected)

    df = pd.read_csv(path)
    df["compound_id"] = df["compound_id"].astype(str).str.strip()
    missing = [c for c in expected if c not in df.columns]
    if missing:
        raise ValueError(f"modality_scores_v1.csv missing columns: {missing}")
    return df


def load_modality_top_n(n=50):
    """Top-N by rank_score with modality breakdown."""
    df = load_modality_scores()
    if df.empty:
        return []

    top = df.nlargest(n, "rank_score").copy()
    top["rank"] = range(1, len(top) + 1)
    evidence = load_evidence_map()

    rows = []
    for _, r in top.iterrows():
        cid = r["compound_id"]
        ev = evidence.get(cid, {})
        rows.append({
            "rank": int(r["rank"]),
            "chembl_id": cid,
            "rank_score": round(float(r["rank_score"]), 4),
            "prob": round(float(r["prob"]), 4),
            "total_score": round(float(r["total_score"]), 4),
            "drug_score": round(float(r["drug_score"]), 3),
            "adc_score": round(float(r["adc_score"]), 3),
            "protac_score": round(float(r["protac_score"]), 3),
            "glue_score": round(float(r["glue_score"]), 3),
            "rlt_score": round(float(r["rlt_score"]), 3),
            "primary_modality": str(r["primary_modality"]),
            "rationale": str(r["rationale"]),
            "phase": ev.get("phase"),
            "tier": ev.get("tier"),
            "is_positive": ev.get("is_positive", False),
        })
    return rows


# ---------------------------------------------------------------------------
# Modality scores (v1) — 33,057 compounds × 40 columns
# ---------------------------------------------------------------------------
_modality_df_cache = None

def load_modality_scores():
    """Load full modality_scores_v1.csv. Cached after first call."""
    global _modality_df_cache
    if _modality_df_cache is not None:
        return _modality_df_cache
    import pandas as pd
    path = _PROJECT / "data" / "modality_scores_v1.csv"
    if not path.exists():
        return pd.DataFrame()
    _modality_df_cache = pd.read_csv(path)
    _modality_df_cache["compound_id"] = _modality_df_cache["compound_id"].astype(str).str.strip()
    return _modality_df_cache


def get_modality_summary() -> dict:
    """Aggregate stats for Modality Hub KPIs."""
    df = load_modality_scores()
    if df.empty:
        return {}
    mods = ["drug", "adc", "protac", "glue", "rlt"]
    summary = {"total": len(df), "positives": int(df["is_positive"].sum())}
    for m in mods:
        elig = int(df[f"{m}_eligible"].sum())
        summary[m] = {
            "eligible": elig,
            "pct": round(elig / len(df) * 100, 1),
            "top3": df[df[f"{m}_eligible"] == 1].nlargest(3, f"{m}_score")[
                ["compound_id", "rank_score", f"{m}_score", f"{m}_confidence"]
            ].to_dict("records"),
        }
    elig_counts = df[["drug_eligible", "adc_eligible", "protac_eligible", "glue_eligible", "rlt_eligible"]].sum(axis=1)
    summary["multi_2plus"] = int((elig_counts >= 2).sum())
    summary["multi_pct"] = round(summary["multi_2plus"] / len(df) * 100, 1)
    summary["elig_distribution"] = elig_counts.value_counts().sort_index().to_dict()
    return summary


def get_ranking_for_modality(modality: str = None, pains_free: bool = False,
                              lipinski_pass: bool = False, top_n: int = 50) -> list[dict]:
    """Get ranked compounds, optionally filtered by modality eligibility."""
    import pandas as pd
    df = load_modality_scores()
    if df.empty:
        return []
    if modality and f"{modality}_eligible" in df.columns:
        df = df[df[f"{modality}_eligible"] == 1]
    if pains_free:
        pains_col = "pains_flag" if "pains_flag" in df.columns else None
        if pains_col:
            df = df[df[pains_col] != True]
    if lipinski_pass:
        df = df[df["lipinski_pass"] == 1]
    # Sort by modality-specific score if filtered, else rank_score
    sort_col = f"{modality}_score" if modality and f"{modality}_score" in df.columns else "rank_score"
    df = df.nlargest(top_n, sort_col)
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "compound_id": r["compound_id"],
            "rank_score": round(float(r["rank_score"]), 4),
            "prob": round(float(r["prob"]), 4),
            "total_score": round(float(r["total_score"]), 4),
            "primary_modality": r.get("primary_modality", ""),
            "drug_score": round(float(r.get("drug_score", 0)), 3),
            "adc_score": round(float(r.get("adc_score", 0)), 3),
            "protac_score": round(float(r.get("protac_score", 0)), 3),
            "glue_score": round(float(r.get("glue_score", 0)), 3),
            "rlt_score": round(float(r.get("rlt_score", 0)), 3),
            "mw": round(float(r.get("mw_raw", 0)), 1) if pd.notna(r.get("mw_raw")) else None,
            "lipinski_pass": bool(r.get("lipinski_pass", 0)),
            "lipinski_violations": int(r.get("lipinski_violations", 0)),
            "is_positive": bool(r.get("is_positive", 0)),
            "rationale": str(r.get("rationale", "")),
        })
    return rows


def get_compound_detail(compound_id: str) -> dict:
    """Get full detail for a single compound."""
    import pandas as pd
    df = load_modality_scores()
    if df.empty:
        return {}
    row = df[df["compound_id"] == compound_id.strip()]
    if row.empty:
        return {}
    r = row.iloc[0]
    return {
        "compound_id": r["compound_id"],
        "rank_score": round(float(r["rank_score"]), 4),
        "prob": round(float(r["prob"]), 4),
        "total_score": round(float(r["total_score"]), 4),
        "primary_modality": r.get("primary_modality", ""),
        "drug_score": round(float(r.get("drug_score", 0)), 3),
        "adc_score": round(float(r.get("adc_score", 0)), 3),
        "protac_score": round(float(r.get("protac_score", 0)), 3),
        "glue_score": round(float(r.get("glue_score", 0)), 3),
        "rlt_score": round(float(r.get("rlt_score", 0)), 3),
        "drug_eligible": bool(r.get("drug_eligible", 0)),
        "adc_eligible": bool(r.get("adc_eligible", 0)),
        "protac_eligible": bool(r.get("protac_eligible", 0)),
        "glue_eligible": bool(r.get("glue_eligible", 0)),
        "rlt_eligible": bool(r.get("rlt_eligible", 0)),
        "drug_gate_reason": str(r.get("drug_gate_reason", "")) if pd.notna(r.get("drug_gate_reason")) else None,
        "adc_gate_reason": str(r.get("adc_gate_reason", "")) if pd.notna(r.get("adc_gate_reason")) else None,
        "protac_gate_reason": str(r.get("protac_gate_reason", "")) if pd.notna(r.get("protac_gate_reason")) else None,
        "glue_gate_reason": str(r.get("glue_gate_reason", "")) if pd.notna(r.get("glue_gate_reason")) else None,
        "rlt_gate_reason": str(r.get("rlt_gate_reason", "")) if pd.notna(r.get("rlt_gate_reason")) else None,
        "drug_confidence": str(r.get("drug_confidence", "")),
        "adc_confidence": str(r.get("adc_confidence", "")),
        "protac_confidence": str(r.get("protac_confidence", "")),
        "glue_confidence": str(r.get("glue_confidence", "")),
        "rlt_confidence": str(r.get("rlt_confidence", "")),
        "mw": round(float(r.get("mw_raw", 0)), 1) if pd.notna(r.get("mw_raw")) else None,
        "lipinski_pass": bool(r.get("lipinski_pass", 0)),
        "lipinski_violations": int(r.get("lipinski_violations", 0)),
        "is_positive": bool(r.get("is_positive", 0)),
        "rationale": str(r.get("rationale", "")),
    }


# ---------------------------------------------------------------------------
# Uncertainty data from OOF predictions
# ---------------------------------------------------------------------------
_uncertainty_cache = None

def load_uncertainty() -> dict:
    """Load OOF predictions → {chembl_id: {mean, std, min, max, seeds: {42: v, 123: v, 7: v}}}"""
    global _uncertainty_cache
    if _uncertainty_cache is not None:
        return _uncertainty_cache

    import pandas as pd
    import numpy as np

    # Try e2 first, fall back to e1
    for subdir in ["e6", "e1_tuned"]:
        path = _PROJECT / "results" / subdir / "oof_predictions.csv"
        if path.exists():
            break
    else:
        _uncertainty_cache = {}
        return _uncertainty_cache

    oof = pd.read_csv(path)
    # E6 oof는 'prob' 컬럼명 사용 — 옛 'y_pred' 호환을 위해 alias
    if "y_pred" not in oof.columns and "prob" in oof.columns:
        oof["y_pred"] = oof["prob"]
    id_col = "molecule_chembl_id" if "molecule_chembl_id" in oof.columns else "compound_id"

    result = {}
    for cid, grp in oof.groupby(id_col):
        cid = str(cid).strip()
        seeds = {}
        for seed, sg in grp.groupby("seed"):
            seeds[int(seed)] = round(float(sg.get("y_pred", sg.get("prob")).mean()), 4)
        result[cid] = {
            "mean": round(float(grp.get("y_pred", grp.get("prob")).mean()), 4),
            "std": round(float(grp.get("y_pred", grp.get("prob")).std()), 4) if len(grp) > 1 else 0.0,
            "min": round(float(grp.get("y_pred", grp.get("prob")).min()), 4),
            "max": round(float(grp.get("y_pred", grp.get("prob")).max()), 4),
            "seeds": seeds,
        }

    _uncertainty_cache = result
    return result


# ---------------------------------------------------------------------------
# Target Essentiality (CRISPR DepMap)
# ---------------------------------------------------------------------------
_essentiality_cache = None

def load_essentiality() -> dict:
    """Load CRISPR gene effect → {target: {mean, std, n, essential_pct}}"""
    global _essentiality_cache
    if _essentiality_cache is not None:
        return _essentiality_cache

    import pandas as pd
    path = _PROJECT / "data" / "external" / "CRISPRGeneEffect.csv"
    if not path.exists():
        _essentiality_cache = {}
        return _essentiality_cache

    targets = {
        "EGFR": "EGFR (1956)", "KRAS": "KRAS (3845)", "ALK": "ALK (238)",
        "BRAF": "BRAF (673)", "MET": "MET (4233)", "RET": "RET (5979)",
        "ROS1": "ROS1 (6098)", "ERBB2": "ERBB2 (2064)", "NTRK1": "NTRK1 (4914)",
    }

    try:
        df = pd.read_csv(path, usecols=[c for c in targets.values()])
    except Exception:
        _essentiality_cache = {}
        return _essentiality_cache

    result = {}
    for t, col in targets.items():
        if col in df.columns:
            vals = df[col].dropna()
            result[t] = {
                "mean": round(float(vals.mean()), 3),
                "std": round(float(vals.std()), 3),
                "n": int(len(vals)),
                "essential_pct": round(float((vals < -0.5).sum() / len(vals) * 100), 1),
            }
    _essentiality_cache = result
    return result


# ---------------------------------------------------------------------------
# Batch Planner
# ---------------------------------------------------------------------------
def generate_batch(modality: str = "drug") -> dict:
    """Generate 4-compound batch: anchor, explorer, boundary, negative."""
    import pandas as pd
    df = load_modality_scores()
    if df.empty:
        return {}

    elig_col = f"{modality}_eligible"
    if elig_col not in df.columns:
        return {}

    eligible = df[df[elig_col] == 1].copy()
    if eligible.empty:
        return {}

    unc_data = load_uncertainty()

    # Anchor: top-3 by rank_score, pick lowest std
    top3 = eligible.nlargest(3, "rank_score")
    top3["_std"] = top3["compound_id"].map(lambda x: unc_data.get(str(x), {}).get("std", 999))
    anchor = top3.nsmallest(1, "_std").iloc[0]

    # Explorer: top-10, different from anchor
    top10 = eligible.nlargest(10, "rank_score")
    explorer_pool = top10[top10["compound_id"] != anchor["compound_id"]]
    explorer = explorer_pool.iloc[0] if len(explorer_pool) > 0 else None

    # Boundary: prob 0.4~0.6
    boundary_pool = eligible[(eligible["prob"] >= 0.4) & (eligible["prob"] <= 0.6)]
    boundary = boundary_pool.sample(1, random_state=42).iloc[0] if len(boundary_pool) > 0 else None

    # Negative: bottom 10%
    n_bottom = max(1, len(eligible) // 10)
    bottom = eligible.nsmallest(n_bottom, "rank_score")
    negative = bottom.sample(1, random_state=42).iloc[0] if len(bottom) > 0 else None

    def _to_dict(row):
        if row is None:
            return None
        return {
            "compound_id": str(row["compound_id"]),
            "rank_score": round(float(row["rank_score"]), 4),
            "prob": round(float(row["prob"]), 4),
        }

    return {
        "anchor": _to_dict(anchor),
        "explorer": _to_dict(explorer),
        "boundary": _to_dict(boundary),
        "negative": _to_dict(negative),
    }


# ---------------------------------------------------------------------------
# Counterfactual: gap to Top-10
# ---------------------------------------------------------------------------
def get_counterfactual(compound_id: str) -> dict:
    """Calculate gap to Top-10 threshold."""
    df = load_modality_scores()
    if df.empty:
        return {}

    top10 = df.nlargest(10, "rank_score")
    threshold = float(top10["rank_score"].min())

    row = df[df["compound_id"] == compound_id.strip()]
    if row.empty:
        return {}

    current = float(row["rank_score"].values[0])
    gap = threshold - current

    # Top features that could close the gap (from global importance)
    suggestions = [
        {"feature": "pic50_mean", "current": "varies", "direction": "increase", "impact": "highest"},
        {"feature": "pic50_std", "current": "varies", "direction": "decrease", "impact": "high"},
        {"feature": "phys_tpsa", "current": "varies", "direction": "decrease", "impact": "moderate"},
    ]

    return {
        "current_rank_score": round(current, 4),
        "top10_threshold": round(threshold, 4),
        "gap": round(gap, 4),
        "in_top10": gap <= 0,
        "suggestions": suggestions,
    }


# ---------------------------------------------------------------------------
# Scaffold Intelligence (cached)
# ---------------------------------------------------------------------------
_SCAFFOLD_CACHE = _PROJECT / "data" / "cache" / "scaffold_info.pkl"
_scaffold_cache = None

def load_scaffold_info() -> dict:
    """Load Murcko scaffolds → {compound_id: {scaffold_smiles, family_size}}.
    Cached to pkl after first RDKit computation."""
    global _scaffold_cache
    if _scaffold_cache is not None:
        return _scaffold_cache

    import pandas as pd

    # Try pkl cache first
    if _SCAFFOLD_CACHE.exists():
        try:
            _scaffold_cache = pd.read_pickle(_SCAFFOLD_CACHE).to_dict("index")
            return _scaffold_cache
        except Exception:
            pass

    # Compute from SMILES
    from rdkit import Chem
    from rdkit.Chem.Scaffolds.MurckoScaffold import GetScaffoldForMol
    from collections import Counter

    labels_path = None
    for subdir in ["features_e2", "features_e1"]:
        p = _PROJECT / "data" / subdir / "nsclc_labels_y.csv"
        if p.exists():
            labels_path = p
            break
    if labels_path is None:
        _scaffold_cache = {}
        return _scaffold_cache

    lab = pd.read_csv(labels_path, usecols=["compound_id", "canonical_smiles"])
    lab = lab.dropna(subset=["canonical_smiles"])
    lab["compound_id"] = lab["compound_id"].astype(str).str.strip()

    scaffolds = {}
    for _, row in lab.iterrows():
        mol = Chem.MolFromSmiles(row["canonical_smiles"])
        if mol:
            try:
                scaf = GetScaffoldForMol(mol)
                scaffolds[row["compound_id"]] = Chem.MolToSmiles(scaf)
            except Exception:
                pass

    scaf_counts = Counter(scaffolds.values())

    result = {}
    for cid, scaf_smi in scaffolds.items():
        result[cid] = {
            "scaffold_smiles": scaf_smi,
            "family_size": scaf_counts[scaf_smi],
        }

    # Save cache
    try:
        _SCAFFOLD_CACHE.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame.from_dict(result, orient="index").to_pickle(_SCAFFOLD_CACHE)
    except Exception:
        pass

    _scaffold_cache = result
    return result


# ---------------------------------------------------------------------------
# Activity Cliff Detection (cached)
# ---------------------------------------------------------------------------
_CLIFF_CACHE = _PROJECT / "data" / "cache" / "activity_cliffs.pkl"
_cliff_cache = None

def detect_activity_cliffs(top_n: int = 50, sim_threshold: float = 0.85,
                            score_diff_threshold: float = 0.15) -> list[dict]:
    """Detect activity cliffs among top-N compounds."""
    global _cliff_cache
    if _cliff_cache is not None:
        return _cliff_cache

    import pandas as pd

    # Try pkl cache
    if _CLIFF_CACHE.exists():
        try:
            _cliff_cache = pd.read_pickle(_CLIFF_CACHE)
            return _cliff_cache
        except Exception:
            pass

    from rdkit import Chem
    from rdkit.Chem import AllChem, DataStructs

    df = load_modality_scores()
    if df.empty:
        _cliff_cache = []
        return _cliff_cache

    top = df.nlargest(top_n, "rank_score")

    # Get SMILES
    labels_path = None
    for subdir in ["features_e2", "features_e1"]:
        p = _PROJECT / "data" / subdir / "nsclc_labels_y.csv"
        if p.exists():
            labels_path = p
            break
    if labels_path is None:
        _cliff_cache = []
        return _cliff_cache

    lab = pd.read_csv(labels_path, usecols=["compound_id", "canonical_smiles"])
    lab["compound_id"] = lab["compound_id"].astype(str).str.strip()
    smi_map = dict(zip(lab["compound_id"], lab["canonical_smiles"]))

    # Compute fingerprints
    fps = {}
    for cid in top["compound_id"]:
        cid = str(cid).strip()
        smi = smi_map.get(cid)
        if smi:
            mol = Chem.MolFromSmiles(smi)
            if mol:
                fps[cid] = AllChem.GetMorganFingerprintAsBitVect(mol, 2, 2048)

    scores = dict(zip(top["compound_id"].astype(str).str.strip(), top["rank_score"]))

    cliffs = []
    cids = list(fps.keys())
    for i in range(len(cids)):
        for j in range(i + 1, len(cids)):
            sim = DataStructs.TanimotoSimilarity(fps[cids[i]], fps[cids[j]])
            if sim >= sim_threshold:
                sd = abs(scores.get(cids[i], 0) - scores.get(cids[j], 0))
                if sd >= score_diff_threshold:
                    cliffs.append({
                        "compound_a": cids[i],
                        "compound_b": cids[j],
                        "similarity": round(float(sim), 3),
                        "score_diff": round(float(sd), 4),
                    })

    # Save cache
    try:
        _CLIFF_CACHE.parent.mkdir(parents=True, exist_ok=True)
        pd.to_pickle(cliffs, _CLIFF_CACHE)
    except Exception:
        pass

    _cliff_cache = cliffs
    return cliffs


# ---------------------------------------------------------------------------
# Training Metadata (config + gate summary)
# ---------------------------------------------------------------------------
def load_training_metadata() -> dict:
    """Load training config and gate summary from results."""
    import json

    result = {"experiment_id": "e1_tuned", "config_hash": "unknown"}

    # Best params
    bp_path = _PROJECT / "results" / "e1_tuned" / "best_params.json"
    if bp_path.exists():
        with open(bp_path) as f:
            result["best_params"] = json.load(f)

    # Gate summary
    gs_path = _PROJECT / "results" / "e1_tuned" / "gate_summary.json"
    if gs_path.exists():
        with open(gs_path) as f:
            gs = json.load(f)
            result["pr_auc_mean"] = gs.get("pr_auc_mean")
            result["pr_auc_std"] = gs.get("pr_auc_std")
            result["gate_overall"] = gs.get("overall")
            result["delta_pct"] = gs.get("delta_pct")

    return result


# ---------------------------------------------------------------------------
# Experiment History (scan results/ dirs)
# ---------------------------------------------------------------------------
def load_experiment_history() -> list[dict]:
    """Scan results/ subdirs for summary.csv → experiment comparison table."""
    import pandas as pd

    results_base = _PROJECT / "results"
    if not results_base.exists():
        return []

    experiments = []
    for exp_dir in sorted(results_base.iterdir()):
        if not exp_dir.is_dir():
            continue
        summary_path = exp_dir / "summary.csv"
        if not summary_path.exists():
            continue
        try:
            df = pd.read_csv(summary_path)
            scaffold = df[df["protocol"] == "scaffold"]
            if scaffold.empty:
                continue
            metrics = {}
            for _, row in scaffold.iterrows():
                metrics[row["metric"]] = {
                    "mean": round(float(row["mean"]), 4),
                    "std": round(float(row.get("std", 0)), 4),
                }
            experiments.append({
                "experiment_id": exp_dir.name,
                "pr_auc": metrics.get("pr_auc", {}).get("mean"),
                "pr_auc_std": metrics.get("pr_auc", {}).get("std"),
                "auroc": metrics.get("auroc", {}).get("mean"),
                "ndcg": metrics.get("ndcg@20", {}).get("mean"),
            })
        except Exception:
            continue

    # Inject E6 champion (modality scoring pipeline, not in results/ dirs)
    experiments.append({
        "experiment_id": "e6 ★",
        "pr_auc": 0.1253,
        "pr_auc_std": 0.0063,
        "auroc": 0.7985,
        "ndcg": 0.2580,
    })

    return experiments


# ---------------------------------------------------------------------------
# Calibration (ECE from OOF predictions)
# ---------------------------------------------------------------------------
def compute_calibration(n_bins: int = 10) -> dict:
    """Compute ECE and reliability diagram data from OOF predictions."""
    import pandas as pd
    import numpy as np

    for subdir in ["e6", "e1_tuned"]:
        path = _PROJECT / "results" / subdir / "oof_predictions.csv"
        if path.exists():
            break
    else:
        return {}

    oof = pd.read_csv(path)
    # E6 oof는 'prob' 컬럼명 사용 — 옛 'y_pred' 호환을 위해 alias
    if "y_pred" not in oof.columns and "prob" in oof.columns:
        oof["y_pred"] = oof["prob"]
    id_col = "molecule_chembl_id" if "molecule_chembl_id" in oof.columns else "compound_id"

    # Average across seeds/folds per compound
    grp = oof.groupby(id_col).agg({"y_pred": "mean", "y_true": "first"}).reset_index()
    probs = grp.get("y_pred", grp.get("prob")).values
    labels = grp["y_true"].values

    bins = np.linspace(0, 1, n_bins + 1)
    bin_centers = []
    bin_accs = []
    bin_confs = []
    bin_counts = []
    ece = 0.0

    for i in range(n_bins):
        mask = (probs >= bins[i]) & (probs < bins[i + 1])
        if mask.sum() == 0:
            continue
        acc = labels[mask].mean()
        conf = probs[mask].mean()
        n = int(mask.sum())
        bin_centers.append(round(float(conf), 3))
        bin_accs.append(round(float(acc), 4))
        bin_confs.append(round(float(conf), 4))
        bin_counts.append(n)
        ece += abs(acc - conf) * n

    ece /= len(probs) if len(probs) > 0 else 1

    return {
        "ece": round(float(ece), 4),
        "bin_centers": bin_centers,
        "bin_accs": bin_accs,
        "bin_confs": bin_confs,
        "bin_counts": bin_counts,
        "n_total": len(probs),
    }


# ---------------------------------------------------------------------------
# Compound ID normalization (shared utility)
# ---------------------------------------------------------------------------
def normalize_compound_id(x) -> str:
    """Normalize compound_id for all lookups."""
    return str(x).strip().upper()


# ---------------------------------------------------------------------------
# D3: Compound → Target mapping
# ---------------------------------------------------------------------------
_target_map_cache = None

def load_compound_target_map() -> dict:
    """Load compound_target_map.csv → {CHEMBL_ID: {primary_target, all_targets, action_type, moa}}"""
    global _target_map_cache
    if _target_map_cache is not None:
        return _target_map_cache

    import pandas as pd
    path = _PROJECT / "data" / "derived" / "compound_target_map.csv"
    if not path.exists():
        _target_map_cache = {}
        return _target_map_cache

    df = pd.read_csv(path)
    result = {}
    for _, r in df.iterrows():
        cid = normalize_compound_id(r["compound_id"])
        # Classify target source
        src = str(r.get("target_source", "")) if pd.notna(r.get("target_source")) else ""
        if "chembl" in src:
            src_type = "chembl_mechanism"
        elif "kegg" in src:
            src_type = "kegg_moa"
        elif "ambiguous" in src:
            src_type = "pic50_ambiguous"
        elif "pic50" in src:
            src_type = "pic50"
        else:
            src_type = "unmapped"

        result[cid] = {
            "primary_target": str(r["primary_target"]) if pd.notna(r.get("primary_target")) else None,
            "all_targets": str(r["all_targets"]) if pd.notna(r.get("all_targets")) else None,
            "action_type": str(r["action_type"]) if pd.notna(r.get("action_type")) else None,
            "mechanism_of_action": str(r["mechanism_of_action"]) if pd.notna(r.get("mechanism_of_action")) else None,
            "target_source_type": src_type,
        }
    _target_map_cache = result
    return result


# ---------------------------------------------------------------------------
# D1: Essentiality (NSCLC-filtered CRISPR)
# ---------------------------------------------------------------------------
_essentiality_derived_cache = None

def load_essentiality_derived() -> dict:
    """Load essentiality_nsclc.csv → {GENE: {mean_score, std_score, n_cell_lines, is_essential}}"""
    global _essentiality_derived_cache
    if _essentiality_derived_cache is not None:
        return _essentiality_derived_cache

    import pandas as pd
    path = _PROJECT / "data" / "derived" / "essentiality_nsclc.csv"
    if not path.exists():
        _essentiality_derived_cache = {}
        return _essentiality_derived_cache

    df = pd.read_csv(path)
    result = {}
    for _, r in df.iterrows():
        gene = str(r["gene"]).strip().upper()
        result[gene] = {
            "mean_score": round(float(r["mean_score"]), 4),
            "std_score": round(float(r["std_score"]), 4),
            "n_cell_lines": int(r["n_cell_lines"]),
            "is_essential": bool(r["is_essential"]),
        }
    _essentiality_derived_cache = result
    return result


# ---------------------------------------------------------------------------
# D5: Scaffold info (from pkl cache)
# ---------------------------------------------------------------------------
def load_scaffold_info_derived() -> dict:
    """Load scaffold_info.pkl → {CHEMBL_ID: {scaffold_smiles, family_size}}"""
    import pandas as pd
    path = _PROJECT / "data" / "cache" / "scaffold_info.pkl"
    if not path.exists():
        return {}
    try:
        df = pd.read_pickle(path)
        result = {}
        for _, r in df.iterrows():
            cid = normalize_compound_id(r["compound_id"])
            result[cid] = {
                "scaffold_smiles": str(r["scaffold_smiles"]),
                "family_size": int(r["family_size"]),
            }
        return result
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# D6: Activity Cliffs (from pkl cache)
# ---------------------------------------------------------------------------
def load_activity_cliffs_derived() -> list[dict]:
    """Load activity_cliffs.pkl → list of cliff dicts."""
    import pandas as pd
    path = _PROJECT / "data" / "cache" / "activity_cliffs.pkl"
    if not path.exists():
        return []
    try:
        df = pd.read_pickle(path)
        if isinstance(df, pd.DataFrame) and len(df) > 0:
            return df.to_dict("records")
        return []
    except Exception:
        return []


# ---------------------------------------------------------------------------
# SMILES lookup (from labels CSV)
# ---------------------------------------------------------------------------
_smiles_cache = None

def load_smiles_map() -> dict:
    """Load compound_id → canonical_smiles mapping.
    Prefers derived/smiles_lookup.csv, falls back to labels CSV."""
    global _smiles_cache
    if _smiles_cache is not None:
        return _smiles_cache

    import pandas as pd

    # Prefer pre-built smiles_lookup.csv
    lookup_path = _PROJECT / "data" / "derived" / "smiles_lookup.csv"
    if lookup_path.exists():
        df = pd.read_csv(lookup_path)
        df = df.dropna(subset=["canonical_smiles"])
        _smiles_cache = dict(zip(
            df["compound_id"].astype(str).str.strip().str.upper(),
            df["canonical_smiles"],
        ))
        return _smiles_cache

    # Fallback: labels CSV
    for subdir in ["features_e2", "features_e1"]:
        path = _PROJECT / "data" / subdir / "nsclc_labels_y.csv"
        if path.exists():
            df = pd.read_csv(path, usecols=["compound_id", "canonical_smiles"])
            df = df.dropna(subset=["canonical_smiles"])
            _smiles_cache = dict(zip(
                df["compound_id"].astype(str).str.strip().str.upper(),
                df["canonical_smiles"],
            ))
            return _smiles_cache

    _smiles_cache = {}
    return _smiles_cache


# ============================================================
# Step 4-D: gene → 학습 화합물 top-N (champion prob 내림차순)
# ============================================================
_INTERNAL_TARGET_CACHE: dict = {}
_INTERNAL_LOADED = False


def _ensure_internal_target_index() -> None:
    """compound_target_map + champion oof + drug_name_lookup join.
    모듈 레벨 캐시. 첫 호출 시 한 번만 실행."""
    global _INTERNAL_LOADED, _INTERNAL_TARGET_CACHE
    if _INTERNAL_LOADED:
        return

    import pandas as pd
    from pathlib import Path

    # _PROJECT = final/ (다른 loaders 함수와 통일)
    ctm_path  = _PROJECT / "data" / "derived" / "compound_target_map.csv"
    oof_path  = _PROJECT / "results" / "e6" / "oof_predictions.csv"
    name_path = _PROJECT / "data" / "kegg" / "drug_name_lookup.csv"

    if not ctm_path.exists():
        logger.warning(f"compound_target_map 없음: {ctm_path}")
        _INTERNAL_LOADED = True
        return

    ctm = pd.read_csv(ctm_path)
    ctm["compound_id"] = ctm["compound_id"].map(normalize_compound_id)

    # champion oof: mean prob over folds/seeds
    if oof_path.exists():
        oof = pd.read_csv(oof_path)
        oof["compound_id"] = oof["compound_id"].map(normalize_compound_id)
        prob_map = (oof.groupby("compound_id")["prob"]
                    .mean().to_dict())
    else:
        logger.warning(f"champion oof 없음: {oof_path}")
        prob_map = {}

    # drug_name_lookup: pref_name 매핑
    if name_path.exists():
        nm = pd.read_csv(name_path)
        nm["compound_id"] = nm["molecule_chembl_id"].map(normalize_compound_id)
        name_map = dict(zip(nm["compound_id"], nm["pref_name"]))
    else:
        name_map = {}

    # gene별 그룹: primary_target + all_targets
    cache: dict[str, list[dict]] = {}
    for _, row in ctm.iterrows():
        cid = row["compound_id"]
        prob = prob_map.get(cid)
        pref = name_map.get(cid)

        targets = []
        primary = row.get("primary_target")
        if pd.notna(primary) and primary:
            targets.append(str(primary).strip())
        all_t = row.get("all_targets")
        if pd.notna(all_t) and all_t:
            for t in str(all_t).split(";"):
                t = t.strip()
                if t and t not in targets:
                    targets.append(t)

        entry = {
            "compound_id": cid,
            "rank_score": float(prob) if prob is not None else None,
            "modality": None,   # 5-modality는 strict X (메모리 #13)
            "pref_name": pref,
        }
        for g in targets:
            cache.setdefault(g, []).append(entry)

    # 각 gene 내부 정렬 (rank_score 내림차순, None은 뒤로)
    for g in cache:
        cache[g].sort(
            key=lambda c: (c.get("rank_score") is None, -(c.get("rank_score") or 0.0)),
        )

    _INTERNAL_TARGET_CACHE = cache
    _INTERNAL_LOADED = True
    logger.info(f"internal target cache built: {len(cache)} genes, "
                f"oof matched: {sum(1 for v in cache.values() for c in v if c['rank_score'] is not None)}")


def get_top_compounds_for_target(gene_symbol: str, top_n: int = 5) -> list[dict]:
    """gene_symbol을 타겟으로 가지는 학습 화합물 top-N.
    champion prob 내림차순. ChatbotContext.internal_compounds 형식.

    Returns:
        [{"compound_id", "rank_score", "modality", "pref_name"}, ...]
    """
    _ensure_internal_target_index()
    return _INTERNAL_TARGET_CACHE.get(gene_symbol, [])[:top_n]
