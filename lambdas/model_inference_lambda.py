"""Model Inference Lambda — 4 tools.

- get_oof_prediction       : E6 OOF (frozen 198,342 rows) compound 별 fold 분포
- get_shap_explanation     : 사전 계산된 shap_top.csv top-K (global). per_drug는 TODO.
- get_ensemble_probability : OOF prob 평균 = cross-validated ensemble proxy. 외부 거부.
- predict_cell_response    : Model A v3 사전 계산 결과 lookup (cell_response_v3)

SHAP: shap_top.csv (feature, mean_abs_shap, rank), meta=XGB_proxy_single_seed.
      xgb_seed42.pkl 의존 제거. 사전 계산만 사용.

Policy: get_ensemble_probability는 in_library=True 일 때만. False면 POLICY_REJECT_EXTERNAL.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _common import (  # noqa: E402
    E6_OOF, FINAL_RESULTS_E6, DERIVED_DATA, LIBRARY_POOL_CSV,
    CHAMPION_MODEL,
    normalize_compound_id,
    mcp_response, mcp_error, route_tool,
)

# SHAP 사전 계산 (XGB proxy single seed=42, fold 0)
SHAP_TOP_CSV = FINAL_RESULTS_E6 / "shap_top.csv"
SHAP_META_JSON = FINAL_RESULTS_E6 / "shap_meta.json"

# Model A v3 사전 계산 (449,400 rows × 10 cols)
CELL_RESPONSE_V3 = DERIVED_DATA / "cell_line_response_predictions_v3.parquet"

_OOF_DF = None
_SHAP_DF = None
_SHAP_META = None
_CELL_RESP_V3 = None
_LIB_NAME_LOOKUP = None  # compound_id → pref_name 사전


def _load_oof():
    global _OOF_DF
    if _OOF_DF is None:
        import pandas as pd
        df = pd.read_csv(E6_OOF)
        df["compound_id"] = df["compound_id"].astype(str).str.upper()
        _OOF_DF = df
    return _OOF_DF


def _load_shap_top():
    global _SHAP_DF
    if _SHAP_DF is None:
        import pandas as pd
        _SHAP_DF = pd.read_csv(SHAP_TOP_CSV)
    return _SHAP_DF


def _load_shap_meta():
    global _SHAP_META
    if _SHAP_META is None:
        with open(SHAP_META_JSON) as f:
            _SHAP_META = json.load(f)
    return _SHAP_META


def _load_cell_response_v3():
    global _CELL_RESP_V3
    if _CELL_RESP_V3 is None:
        import pandas as pd
        df = pd.read_parquet(CELL_RESPONSE_V3)
        df["drug_name"] = df["drug_name"].astype(str).str.upper()
        df["ccle_name"] = df["ccle_name"].astype(str).str.upper()
        _CELL_RESP_V3 = df
    return _CELL_RESP_V3


def _load_library_name_lookup() -> dict:
    """compound_id (CHEMBL...) → pref_name 사전. 작은 메모리 (33,057 × 2 cols)."""
    global _LIB_NAME_LOOKUP
    if _LIB_NAME_LOOKUP is None:
        import pandas as pd
        lib = pd.read_csv(LIBRARY_POOL_CSV, usecols=["compound_id", "pref_name"])
        lib["compound_id"] = lib["compound_id"].astype(str).str.upper()
        lib["pref_name"] = lib["pref_name"].fillna("").astype(str).str.upper()
        _LIB_NAME_LOOKUP = dict(zip(lib["compound_id"], lib["pref_name"]))
    return _LIB_NAME_LOOKUP


def _safe_float(v):
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _safe_int(v):
    try:
        f = float(v)
        return None if math.isnan(f) else int(f)
    except (TypeError, ValueError):
        return None


# ===== Tools =====

def get_oof_prediction(drug_id: str) -> dict:
    """E6 OOF prediction (frozen 198,342 rows). compound 별 fold 분포 + 평균."""
    df = _load_oof()
    cid = normalize_compound_id(drug_id)
    hit = df[df["compound_id"] == cid]

    if len(hit) == 0:
        return mcp_response(
            result={"drug_id": cid, "matched": False, "n_folds": 0},
            tool_name="get_oof_prediction",
            source="final/results/e6/oof_predictions.csv",
            model_version=CHAMPION_MODEL["name"],
        )

    probs = hit["prob"].astype(float).tolist()
    p_mean = sum(probs) / len(probs)
    p_std = (sum((p - p_mean) ** 2 for p in probs) / len(probs)) ** 0.5
    y_true_vals = hit["y_true"].astype(int).unique().tolist()

    return mcp_response(
        result={
            "drug_id": cid,
            "matched": True,
            "n_folds": len(hit),
            "y_true": y_true_vals[0] if len(y_true_vals) == 1 else y_true_vals,
            "oof_prob_mean": _safe_float(p_mean),
            "oof_prob_std": _safe_float(p_std),
            "oof_prob_min": _safe_float(min(probs)),
            "oof_prob_max": _safe_float(max(probs)),
            "fold_probs": [
                {"fold": int(r["fold"]), "prob": float(r["prob"])}
                for _, r in hit.iterrows()
            ],
            "protocol": hit.iloc[0]["protocol"],
        },
        tool_name="get_oof_prediction",
        source="final/results/e6/oof_predictions.csv (198,342 rows, frozen)",
        model_version=CHAMPION_MODEL["name"],
        pr_auc_w=CHAMPION_MODEL["pr_auc_w"],
        pr_auc_w_std=CHAMPION_MODEL["pr_auc_w_std"],
    )


def get_shap_explanation(
    drug_id: str | None = None,
    top_k: int = 10,
    mode: str = "global",
) -> dict:
    """SHAP top-K. shap_top.csv 사전 계산 결과 직접 lookup.

    - mode='global' (default): shap_top.csv 의 top-K (mean_abs_shap 기준)
    - mode='per_drug': TODO (per-drug feature row + TreeExplainer)
    """
    if mode == "global" or drug_id is None:
        try:
            df = _load_shap_top()
            meta = _load_shap_meta()
        except FileNotFoundError as e:
            return mcp_error(
                f"SHAP precomputed files not found: {e}",
                "get_shap_explanation", code="SHAP_FILES_MISSING",
            )

        # shap_top.csv 컬럼: feature, mean_abs_shap, rank
        if "rank" in df.columns:
            top = df.nsmallest(top_k, "rank")
        else:
            top = df.sort_values("mean_abs_shap", ascending=False).head(top_k)

        top_features = [
            {
                "feature": str(r["feature"]),
                "mean_abs_shap": _safe_float(r["mean_abs_shap"]),
                "rank": _safe_int(r.get("rank")),
            }
            for _, r in top.iterrows()
        ]

        return mcp_response(
            result={
                "mode": "global",
                "drug_id": drug_id,
                "top_features": top_features,
                "n_features_in_csv": len(df),
                "shap_meta": meta,
                "disclosure": (
                    f"Global SHAP (mean_abs_shap, 사전 계산). "
                    f"model_type={meta.get('model_type', 'XGB_proxy_single_seed')} — "
                    f"LGB 15-seed 미반영. Per-drug SHAP은 별도 작업."
                ),
            },
            tool_name="get_shap_explanation",
            source="final/results/e6/shap_top.csv + shap_meta.json",
            model_version=f"{CHAMPION_MODEL['name']} ({meta.get('model_type', 'XGB proxy')})",
        )

    # per_drug mode (TODO)
    return mcp_response(
        result={
            "mode": "per_drug",
            "drug_id": normalize_compound_id(drug_id),
            "top_features": [],
            "global_top_features_available": True,
            "TODO": "Per-drug SHAP은 그 compound의 947 feature row 생성 + TreeExplainer 호출 필요.",
        },
        tool_name="get_shap_explanation",
        source="TODO (per_drug)",
    )


def get_ensemble_probability(drug_id: str, in_library: bool | None = None) -> dict:
    """E6 ensemble 확률. POLICY: in_library=True 일 때만.

    구현: OOF prob 평균 = cross-validated ensemble proxy.
    """
    if in_library is False:
        return mcp_error(
            "외부 화합물에 대한 champion 확률 표시는 정책상 금지. "
            "Phase A: PR-AUC 보존 5.8% (0.1162→0.0067). "
            "compute_tanimoto + check_scope 경로 사용 권장.",
            "get_ensemble_probability",
            code="POLICY_REJECT_EXTERNAL",
        )
    if in_library is None:
        return mcp_error(
            "in_library 미지정. check_in_library 먼저 호출 필요.",
            "get_ensemble_probability",
            code="MISSING_IN_LIBRARY_FLAG",
        )

    cid = normalize_compound_id(drug_id)
    df = _load_oof()
    hit = df[df["compound_id"] == cid]

    if len(hit) == 0:
        return mcp_response(
            result={"drug_id": cid, "ensemble_prob": None, "matched": False},
            tool_name="get_ensemble_probability",
            source="final/results/e6/oof_predictions.csv",
            model_version=CHAMPION_MODEL["name"],
        )

    probs = hit["prob"].astype(float).tolist()
    p_mean = sum(probs) / len(probs)

    return mcp_response(
        result={
            "drug_id": cid,
            "ensemble_prob": _safe_float(p_mean),
            "n_folds": len(hit),
            "y_true": int(hit.iloc[0]["y_true"]),
            "weights": CHAMPION_MODEL["ensemble_alpha"],
            "n_models_target": CHAMPION_MODEL["n_ensemble"],
            "note": "OOF 평균 = cross-validated ensemble proxy.",
        },
        tool_name="get_ensemble_probability",
        source="final/results/e6/oof_predictions.csv (cross-validated proxy)",
        model_version=CHAMPION_MODEL["name"],
        pr_auc_w=CHAMPION_MODEL["pr_auc_w"],
        pr_auc_w_std=CHAMPION_MODEL["pr_auc_w_std"],
    )


def predict_cell_response(drug_id: str, cell_line: str | None = None) -> dict:
    """Model A v3 사전 계산 lookup.

    매칭 경로:
      drug_id (CHEMBL) → library_pool.pref_name → cell_response_v3.drug_name (UPPER)
      cell_line (e.g. H1975) → ccle_name (NCIH1975_LUNG 등) — alias 시도

    cell_response_v3 컬럼: broad_id, depmap_id, ccle_name, drug_name, target, phase,
                          lfc_obs, lfc_pred, fold, delta
    """
    cid = normalize_compound_id(drug_id)
    cell_norm = str(cell_line).strip().upper() if cell_line else None

    try:
        df = _load_cell_response_v3()
    except FileNotFoundError:
        return mcp_error(
            f"cell_line_response_predictions_v3.parquet 없음: {CELL_RESPONSE_V3}",
            "predict_cell_response", code="FILE_MISSING",
        )

    # CHEMBL ID → pref_name 변환 (library lookup)
    pref_name = None
    if cid.startswith("CHEMBL"):
        try:
            lookup = _load_library_name_lookup()
            pref_name = lookup.get(cid) or None
        except Exception:
            pass

    drug_match = pref_name if pref_name else cid
    hit = df[df["drug_name"] == drug_match]

    if len(hit) == 0:
        return mcp_response(
            result={
                "drug_id": cid, "pref_name": pref_name, "cell_line": cell_norm,
                "matched": False, "n_predictions": 0,
                "note": (
                    f"drug_name '{drug_match}' not found in cell_response_v3. "
                    "pref_name 변환 실패 또는 Model A v3 학습 set에 없음."
                ),
            },
            tool_name="predict_cell_response",
            source="cell_line_response_predictions_v3.parquet",
            model_version="Model A v3",
        )

    # cell_line 매칭 (옵션). ccle_name 형식 = "NCIH1975_LUNG", "HCC827_LUNG" 등.
    if cell_norm:
        candidates = [
            cell_norm,
            f"{cell_norm}_LUNG",
            f"NCI{cell_norm}_LUNG",
            cell_norm.replace("-", ""),
        ]
        cell_hits = hit[hit["ccle_name"].isin(candidates)]
        if len(cell_hits) == 0:
            cell_hits = hit[
                hit["ccle_name"].str.startswith(cell_norm + "_")
                | hit["ccle_name"].str.startswith("NCI" + cell_norm + "_")
            ]
        hit = cell_hits

    if len(hit) == 0:
        return mcp_response(
            result={
                "drug_id": cid, "pref_name": pref_name, "cell_line": cell_norm,
                "matched": False, "n_predictions": 0,
                "note": "drug 매칭됐지만 cell_line 매칭 실패.",
            },
            tool_name="predict_cell_response",
            source="cell_line_response_predictions_v3.parquet",
            model_version="Model A v3",
        )

    predictions = []
    for _, r in hit.iterrows():
        predictions.append({
            "ccle_name": str(r["ccle_name"]),
            "depmap_id": str(r["depmap_id"]) if "depmap_id" in r else None,
            "drug_name": str(r["drug_name"]),
            "lfc_pred": _safe_float(r["lfc_pred"]),
            "lfc_obs": _safe_float(r.get("lfc_obs")),
            "delta": _safe_float(r.get("delta")),
            "fold": _safe_int(r.get("fold")),
        })

    return mcp_response(
        result={
            "drug_id": cid,
            "pref_name": pref_name,
            "cell_line": cell_norm,
            "matched": True,
            "n_predictions": len(predictions),
            "predictions": predictions[:50],
            "interpretation": (
                "lfc_pred=Model A v3 예측, lfc_obs=PRISM 실측, delta=pred-obs. "
                "음수 lfc=cell viability 감소(cytotoxic)."
            ),
        },
        tool_name="predict_cell_response",
        source="cell_line_response_predictions_v3.parquet",
        model_version="Model A v3 (CCLE PCA96 + 2695 features)",
        spearman_strict_mean=0.1821,
        spearman_relaxed_mean=0.3564,
    )


# ===== Lambda entry =====
TOOL_REGISTRY = {
    "get_oof_prediction": get_oof_prediction,
    "get_shap_explanation": get_shap_explanation,
    "get_ensemble_probability": get_ensemble_probability,
    "predict_cell_response": predict_cell_response,
}


def lambda_handler(event, context):  # noqa: ARG001
    return route_tool(event, TOOL_REGISTRY)


if __name__ == "__main__":
    tests = [
        {"tool": "get_shap_explanation", "params": {"mode": "global", "top_k": 10}},
        {"tool": "get_oof_prediction", "params": {"drug_id": "CHEMBL1009"}},
        {"tool": "get_ensemble_probability", "params": {"drug_id": "CHEMBL1009", "in_library": True}},
        {"tool": "get_ensemble_probability", "params": {"drug_id": "OLAPARIB", "in_library": False}},
        {"tool": "predict_cell_response", "params": {"drug_id": "CHEMBL941", "cell_line": "H1975"}},
    ]
    for e in tests:
        print(f">>> {e['tool']}({e['params']})")
        print(json.dumps(lambda_handler(e, None), indent=2, ensure_ascii=False)[:1500])
        print()
