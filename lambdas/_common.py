"""Lambda 공통 헬퍼 모듈.

- 데이터 경로 상수 (inspect_schemas.py 결과 기반 확정)
- compound ID / SMILES 정규화
- 표준 MCP 응답 포맷 (provenance 강제)
- Tool router (event → handler 분기)
- 정책 상수 (Tanimoto 임계값, Guardrail ID, KB ID, actionable genes)

v3 patch: DATA_MODE 환경변수로 로컬/S3 경로 전환.
  - DATA_MODE=local (기본): 기존 Path 그대로 — 로컬 dev 깨지지 않음
  - DATA_MODE=s3:          s3://bucket/prefix/... 문자열
  pandas.read_parquet / read_csv 는 둘 다 native 지원 → 호출부 0줄 수정.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Union

# ===== 경로 모드 스위치 =====
DATA_MODE = os.environ.get("DATA_MODE", "local")  # "local" | "s3"
S3_BUCKET = os.environ.get("S3_DATA_BUCKET", "say2-5team-use1")
S3_PREFIX = os.environ.get("S3_DATA_PREFIX", "nsclc-insight-engine")

# ===== 로컬 경로 기준 =====
PROJECT_ROOT = Path(os.environ.get("NSCLC_PROJECT_ROOT", "/Users/yj/Desktop/5team"))
FINAL_DIR = PROJECT_ROOT / "final"
FINAL_DATA = FINAL_DIR / "data"
DERIVED_DATA = FINAL_DATA / "derived"
CURATED_DATA = FINAL_DATA / "curated"
RAW_DATA = FINAL_DATA / "raw"
PRE_DIR = PROJECT_ROOT / "pre"
RESULTS_E6 = PROJECT_ROOT / "results" / "e2_tcga_crispr"
FINAL_RESULTS_E6 = FINAL_DIR / "results" / "e6"
FINAL_RESULTS_E6_FULL = FINAL_DIR / "results" / "e6_full"


def _path(local_path: Path, s3_subpath: str) -> Union[str, Path]:
    """DATA_MODE에 따라 로컬 Path 또는 s3:// 문자열 반환.

    pandas.read_parquet / read_csv 둘 다 두 형태 모두 받음.
    """
    if DATA_MODE == "s3":
        return f"s3://{S3_BUCKET}/{S3_PREFIX}/{s3_subpath}"
    return local_path


# ===== 데이터 파일 경로 (inspect_schemas.py 확정) =====

# Drug library + target
LIBRARY_POOL_CSV = _path(
    DERIVED_DATA / "library_pool_final.csv",
    "data/derived/library_pool_final.csv",
)  # 33,057 × 15
COMPOUND_TARGET_MAP = _path(
    DERIVED_DATA / "compound_target_map.csv",
    "data/derived/compound_target_map.csv",
)  # 33,057 × 8, 100% 매핑

# Drug-cell response (PRISM, GDSC2)
PRISM_NSCLC_LONG = _path(
    DERIVED_DATA / "prism_nsclc_long.parquet",
    "data/derived/prism_nsclc_long.parquet",
)  # 18,800 rows
GDSC2_CHEMBL_MAPPING = _path(
    DERIVED_DATA / "gdsc2_chembl_mapping.csv",
    "data/derived/gdsc2_chembl_mapping.csv",
)  # 30 drugs mapped
GDSC2_DOSE_RESPONSE = _path(
    RAW_DATA / "gdsc2" / "GDSC2_fitted_dose_response_24Jul22.csv",
    "data/raw/gdsc2/GDSC2_fitted_dose_response_24Jul22.csv",
)  # 242,036 rows
GDSC2_SCREENED_COMPOUNDS = _path(
    RAW_DATA / "gdsc2" / "screened_compounds_rel_8.4.csv",
    "data/raw/gdsc2/screened_compounds_rel_8.4.csv",
)  # 621 drugs
CROSS_SOURCE_POOL = _path(
    DERIVED_DATA / "cross_source_pool.csv",
    "data/derived/cross_source_pool.csv",
)

# Cell line meta (CCLE)
CCLE_MUTATION_MATRIX = _path(
    DERIVED_DATA / "ccle_nsclc_mutation_matrix.parquet",
    "data/derived/ccle_nsclc_mutation_matrix.parquet",
)  # 98 cells × 20 genes
CCLE_EXPRESSION_PCA = _path(
    DERIVED_DATA / "ccle_nsclc_expression_pca100.parquet",
    "data/derived/ccle_nsclc_expression_pca100.parquet",
)  # 97 cells × pc1-pc96

# Patient (cBioPortal TCGA + Model B 결과물)
TCGA_MUTATION = _path(
    CURATED_DATA / "cbio_mutation_detail.csv",
    "data/curated/cbio_mutation_detail.csv",
)
TCGA_MUTATION_FREQ = _path(
    CURATED_DATA / "cbio_mutation_freq.csv",
    "data/curated/cbio_mutation_freq.csv",
)
PATIENT_DRUG_RANKING = _path(
    DERIVED_DATA / "patient_drug_ranking.parquet",
    "data/derived/patient_drug_ranking.parquet",
)  # 106 MB
PATIENT_CELL_SIMILARITY = _path(
    DERIVED_DATA / "patient_cell_similarity.parquet",
    "data/derived/patient_cell_similarity.parquet",
)
PATIENT_TOP_CELLS = _path(
    DERIVED_DATA / "patient_top_cells.parquet",
    "data/derived/patient_top_cells.parquet",
)
PATIENT_TRANSFER_META = _path(
    DERIVED_DATA / "patient_transfer_meta.json",
    "data/derived/patient_transfer_meta.json",
)

# Model artifacts (E6 champion)
E6_OOF = _path(
    FINAL_RESULTS_E6 / "oof_predictions.csv",
    "results/e6/oof_predictions.csv",
)  # 198,342 rows, frozen
E6_XGB_PKL = _path(
    FINAL_RESULTS_E6 / "xgb_seed42.pkl",
    "results/e6/xgb_seed42.pkl",
)  # SHAP

# ===== 모델 / 정책 상수 =====
CHAMPION_MODEL = {
    "name": "E6_tcga_crispr",
    "n_features": 947,
    "pr_auc_w": 0.1383,
    "pr_auc_w_std": 0.0054,
    "delta_vs_pre": "+37.3%",
    "ensemble_alpha": {"xgb": 0.6, "lgb": 0.4},
    "n_ensemble": 30,
}

# Actionable genes (CCLE mutation matrix 컬럼 확정, 20개)
ACTIONABLE_GENES = [
    "ALK", "BRAF", "CDKN2A", "EGFR", "ERBB2", "KEAP1", "KRAS", "MAP2K1",
    "MET", "NF1", "NTRK1", "NTRK2", "NTRK3", "PIK3CA", "PTEN", "RB1",
    "RET", "ROS1", "STK11", "TP53",
]

TANIMOTO_REJECT_THRESHOLD = 0.3
GUARDRAIL_ID = "19ys87squ5mz"
GUARDRAIL_VERSION = "9"

# Bedrock Knowledge Base (FDA labels + ESMO + FLAURA2, 5 PDFs, Titan v2 1024 dim, S3 Vectors)
KNOWLEDGE_BASE_ID = os.environ.get("BEDROCK_KB_ID", "PHZTHHSMZC")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "us-east-1")


# ===== 정규화 =====
def normalize_compound_id(x: Any) -> str:
    return str(x).strip().upper()


def normalize_smiles(s: Any) -> str:
    return str(s).strip().rstrip(",")


# ===== 표준 MCP 응답 =====
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mcp_response(
    result: Any,
    tool_name: str,
    source: str,
    model_version: str | None = None,
    **extra: Any,
) -> dict:
    prov = {"tool": tool_name, "source": source, "computed_at": _now_iso()}
    if model_version:
        prov["model_version"] = model_version
    prov.update(extra)
    return {"result": result, "provenance": prov}


def mcp_error(message: str, tool_name: str, code: str = "ERROR") -> dict:
    return {
        "error": {"code": code, "message": message, "tool": tool_name},
        "provenance": {"tool": tool_name, "source": "lambda_error", "computed_at": _now_iso()},
    }


def route_tool(event: dict, tool_handlers: dict[str, Callable]) -> dict:
    tool_name = event.get("tool")
    if not tool_name:
        return mcp_error("missing 'tool' field in event", "router", code="INVALID_EVENT")

    handler = tool_handlers.get(tool_name)
    if not handler:
        return mcp_error(
            f"unknown tool: {tool_name}. available: {list(tool_handlers.keys())}",
            "router", code="UNKNOWN_TOOL",
        )

    params = event.get("params") or {}
    try:
        return handler(**params)
    except TypeError as e:
        return mcp_error(f"invalid params for {tool_name}: {e}", tool_name, code="INVALID_PARAMS")
    except Exception as e:
        return mcp_error(f"{type(e).__name__}: {e}", tool_name, code="HANDLER_EXCEPTION")
