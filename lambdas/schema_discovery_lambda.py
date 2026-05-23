"""Schema Discovery Lambda — 3 tools.

- list_data_sources    : 카테고리별 데이터 자산 listing
- get_table_schema     : 특정 자산의 컬럼 + shape + meta
- count_records        : row count

이 Lambda는 LLM에게 "어떤 데이터가 있는가"를 미리 알려줘서 잘못된 가정으로 다른 tool을
호출하기 전에 자산을 정확히 파악하게 함. 카탈로그는 정적 dict (lazy load 안 함).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _common import mcp_response, mcp_error, route_tool  # noqa: E402


# ===== Data Catalog (2026-05 D-7 기준) =====
DATA_CATALOG: dict[str, dict[str, dict]] = {
    "drug_library": {
        "library_pool_final": {
            "path": "final/data/derived/library_pool_final.csv",
            "shape": [33057, 15],
            "key_cols": [
                "compound_id", "canonical_smiles", "inchikey", "inchikey_14",
                "pref_name", "max_phase", "final_category", "rank_score",
            ],
            "categories": {
                "A": 20, "B": 79, "C": 11, "D": 29, "E": 108, "X": 32810,
            },
            "category_legend": "A=NSCLC승인, B=임상, C=재창출, D=비항암, E=ATC없음, X=전임상",
            "desc": "NSCLC drug repurposing library (33,057 compounds)",
        },
        "compound_target_map": {
            "path": "final/data/derived/compound_target_map.csv",
            "shape": [33057, 8],
            "key_cols": ["compound_id", "primary_target", "all_targets", "mechanism_of_action"],
            "desc": "100% mapped (ChEMBL → KEGG → pIC50 fallback)",
        },
    },
    "drug_cell_response": {
        "prism_nsclc_long": {
            "path": "final/data/derived/prism_nsclc_long.parquet",
            "shape": [18800, 7],
            "key_cols": [
                "compound_id", "molecule_chembl_id", "cell_line_name",
                "model_id", "lfc", "oncotree_subtype",
            ],
            "desc": "204 compounds × 95 NSCLC cells. cell_line_name 형식: HCC827, NCIH1975",
            "interpretation": "lfc < 0 = cytotoxic, lfc > 0 = 증식. 강한 효과 ≈ lfc < -0.5",
        },
        "ccle_nsclc_mutation_matrix": {
            "path": "final/data/derived/ccle_nsclc_mutation_matrix.parquet",
            "shape": [98, 21],
            "key_cols": ["depmap_id", "20 actionable genes (binary 0/1)"],
            "desc": "98 NSCLC cells × 20 actionable genes",
        },
        "ccle_nsclc_expression_pca100": {
            "path": "final/data/derived/ccle_nsclc_expression_pca100.parquet",
            "shape": [97, 97],
            "key_cols": ["ccle_name", "pc1...pc96"],
            "desc": "96 PCA dims (filename pca100 historical naming)",
        },
        "gdsc2_chembl_mapping": {
            "path": "final/data/curated/gdsc2_chembl_mapping.csv",
            "shape": [30, 5],
            "desc": "GDSC2 release 8.4. PRISM ∩ GDSC2 cross-source pool = 28 drugs",
        },
    },
    "patient": {
        "cbio_mutation_detail": {
            "path": "final/data/curated/cbio_mutation_detail.csv",
            "shape": [1608, 14],
            "key_cols": [
                "patient_id", "gene", "protein_change", "mutation_type", "variant_type",
            ],
            "desc": "cBioPortal LUAD pan-cancer atlas 2018 mutation detail",
        },
        "cbio_mutation_freq": {
            "path": "final/data/curated/cbio_mutation_freq.csv",
            "shape": [16, 6],
            "key_cols": [
                "gene", "mutated_patients", "total_patients",
                "frequency_pct", "top_mutation",
            ],
            "top_5_genes": [
                "KRAS 25.7% (G12C top)", "EGFR 15.4% (L858R top)",
                "PIK3CA 6.9% (E545K)", "BRAF 5.6% (V600E)", "ALK 4.5% (P542R)",
            ],
            "total_patients": 1897,
        },
        "patient_drug_ranking": {
            "path": "final/data/derived/patient_drug_ranking.parquet",
            "shape": [4412328, 23],
            "key_cols": [
                "patient_id", "broad_id", "drug_name", "target", "phase",
                "pred_lfc_weighted", "rank_hybrid", "hybrid_tier",
                "drug_targets_actionable", "target_overlap_genes",
            ],
            "desc": "Model B 사전 계산: 942 patients × 4,684 drugs ranking",
            "ranking": "rank_hybrid 오름차순 (낮을수록 우선). hybrid_tier 1=actionable+low rank",
        },
        "patient_top_cells": {
            "path": "final/data/derived/patient_top_cells.parquet",
            "shape": [942, 19],
            "desc": "patient → top-5 유사 cell lines (cosine sim 기반)",
        },
        "patient_transfer_meta": {
            "path": "final/data/derived/patient_transfer_meta.json",
            "desc": "Model B method: TCGA mutation cosine sim → top-K=5 cells → A v3 lfc_pred avg",
            "stats": {
                "n_patients": 942, "n_cells": 98, "n_drugs": 4684, "top_k": 5,
                "mean_top_sim": 0.794,
            },
            "actionable_genes_20": [
                "ALK", "BRAF", "CDKN2A", "EGFR", "ERBB2", "KEAP1", "KRAS",
                "MAP2K1", "MET", "NF1", "NTRK1", "NTRK2", "NTRK3", "PIK3CA",
                "PTEN", "RB1", "RET", "ROS1", "STK11", "TP53",
            ],
        },
    },
    "model_artifacts": {
        "e6_oof_predictions": {
            "path": "final/results/e6/oof_predictions.csv",
            "shape": [198342, 8],
            "key_cols": ["compound_id", "y_true", "prob", "fold", "seed", "protocol"],
            "desc": "Champion E6 OOF (frozen). 33,057 compounds × 6 folds, seed 42",
            "metrics": {
                "PR-AUC_scaffold": "0.1253±0.0063",
                "PR-AUC_w_stratified": "0.1383±0.0054",
                "n_features": 947,
                "vs_pre_baseline": "+37.3%",
            },
        },
        "e6_shap_top": {
            "path": "final/results/e6/shap_top.csv",
            "shape": [30, 3],
            "key_cols": ["feature", "mean_abs_shap", "rank"],
            "meta": "XGB_proxy_single_seed (fold 0, seed 42, n_train=26,445, n_pos=92)",
            "top_5_features": [
                "pic50_std 0.387", "pic50_mean 0.131", "pic50_max 0.105",
                "crispr_ess_min_active 0.086", "morgan_428 0.085",
            ],
        },
        "cell_line_response_v3": {
            "path": "final/data/derived/cell_line_response_predictions_v3.parquet",
            "shape": [449400, 10],
            "key_cols": [
                "broad_id", "depmap_id", "ccle_name", "drug_name", "target",
                "phase", "lfc_obs", "lfc_pred", "fold", "delta",
            ],
            "desc": "Model A v3 사전 계산 (CCLE PCA96 + 2,695 features)",
            "metrics": {
                "Spearman_strict": "0.1821±0.0131",
                "Spearman_relaxed": "0.3564±0.0022",
            },
        },
    },
}


def _flatten_catalog() -> dict[str, dict]:
    """{ source_name: meta } 평탄화."""
    flat = {}
    for category, sources in DATA_CATALOG.items():
        for name, meta in sources.items():
            flat[name] = {"category": category, **meta}
    return flat


# ===== Tools =====

def list_data_sources(category: str | None = None) -> dict:
    """카테고리별 데이터 자산 listing. category=None이면 전체."""
    if category:
        cat = category.lower().strip()
        if cat not in DATA_CATALOG:
            return mcp_response(
                result={
                    "category": cat,
                    "matched": False,
                    "available_categories": list(DATA_CATALOG.keys()),
                },
                tool_name="list_data_sources",
                source="DATA_CATALOG",
            )
        sources = list(DATA_CATALOG[cat].keys())
        return mcp_response(
            result={
                "category": cat,
                "source_count": len(sources),
                "sources": sources,
                "summaries": {
                    name: {
                        "shape": meta.get("shape"),
                        "desc": meta.get("desc"),
                    } for name, meta in DATA_CATALOG[cat].items()
                },
            },
            tool_name="list_data_sources",
            source="DATA_CATALOG",
        )

    # 전체
    overview = {
        cat: {
            "source_count": len(sources),
            "sources": list(sources.keys()),
        }
        for cat, sources in DATA_CATALOG.items()
    }
    total = sum(len(s) for s in DATA_CATALOG.values())
    return mcp_response(
        result={
            "total_sources": total,
            "categories": overview,
            "model_status": {
                "champion_E6": "frozen (PR-AUC_w 0.1383±0.0054, 947 features)",
                "model_A_v3": "complete (449,400 rows sufficient cache)",
                "model_B": "complete (4,412,328 rows ranking, 942 patients × 4684 drugs)",
            },
        },
        tool_name="list_data_sources",
        source="DATA_CATALOG",
    )


def get_table_schema(source_name: str) -> dict:
    """특정 데이터 자산의 컬럼 + shape + 설명."""
    if not source_name:
        return mcp_error(
            "source_name 필수 (e.g. 'library_pool_final', 'patient_drug_ranking')",
            "get_table_schema", code="MISSING_SOURCE_NAME",
        )

    flat = _flatten_catalog()
    name_norm = source_name.strip()
    if name_norm not in flat:
        # case-insensitive 시도
        match = next((k for k in flat if k.lower() == name_norm.lower()), None)
        if not match:
            return mcp_response(
                result={
                    "source_name": name_norm,
                    "matched": False,
                    "available_sources": list(flat.keys()),
                },
                tool_name="get_table_schema",
                source="DATA_CATALOG",
            )
        name_norm = match

    meta = flat[name_norm]
    return mcp_response(
        result={
            "source_name": name_norm,
            "category": meta.get("category"),
            "path": meta.get("path"),
            "shape": meta.get("shape"),
            "key_cols": meta.get("key_cols"),
            "desc": meta.get("desc"),
            "meta": {k: v for k, v in meta.items()
                     if k not in {"category", "path", "shape", "key_cols", "desc"}},
        },
        tool_name="get_table_schema",
        source="DATA_CATALOG",
    )


def count_records(source_name: str) -> dict:
    """row count 반환 (카탈로그 박혀있는 값. 실파일 read 안 함)."""
    flat = _flatten_catalog()
    name_norm = source_name.strip() if source_name else ""
    if name_norm not in flat:
        match = next((k for k in flat if k.lower() == name_norm.lower()), None)
        if not match:
            return mcp_error(
                f"source_name '{name_norm}' not in catalog",
                "count_records", code="SOURCE_NOT_FOUND",
            )
        name_norm = match

    shape = flat[name_norm].get("shape")
    n_records = shape[0] if isinstance(shape, list) and len(shape) > 0 else None

    return mcp_response(
        result={
            "source_name": name_norm,
            "n_records": n_records,
            "shape": shape,
            "note": "Catalog 박힌 값. 실파일 row count는 다를 수 있음.",
        },
        tool_name="count_records",
        source="DATA_CATALOG",
    )


# ===== Lambda entry =====
TOOL_REGISTRY = {
    "list_data_sources": list_data_sources,
    "get_table_schema": get_table_schema,
    "count_records": count_records,
}


def lambda_handler(event, context):  # noqa: ARG001
    return route_tool(event, TOOL_REGISTRY)


if __name__ == "__main__":
    import json
    tests = [
        {"tool": "list_data_sources", "params": {}},
        {"tool": "list_data_sources", "params": {"category": "patient"}},
        {"tool": "get_table_schema", "params": {"source_name": "patient_drug_ranking"}},
        {"tool": "get_table_schema", "params": {"source_name": "e6_shap_top"}},
        {"tool": "count_records", "params": {"source_name": "library_pool_final"}},
    ]
    for e in tests:
        print(f">>> {e['tool']}({e['params']})")
        print(json.dumps(lambda_handler(e, None), indent=2, ensure_ascii=False)[:1500])
        print()
