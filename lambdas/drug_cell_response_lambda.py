"""Drug-Cell Response Lambda — 3 tools.

- get_drug_response       : PRISM lfc 조회 (cell_line alias 매핑)
- get_cell_line_meta      : 세포주 mutation + tissue (CCLE)
- cross_source_lookup     : PRISM ∩ GDSC2 cross-source 일치도

Data:
- prism_nsclc_long.parquet (18,800 rows, 95 cells)
- ccle_nsclc_mutation_matrix.parquet (98 cells × 20 genes binary)
- ccle_nsclc_expression_pca100.parquet (97 × pc1-pc96)
- gdsc2_chembl_mapping.csv (30 mapped)

Cell-line alias: PRISM cell_line_name 형식 = "HCC827", "NCIH1975" 등.
                 사용자 입력 "H1975" → "NCIH1975" 자동 시도.
                 CCLE ccle_name 형식 = "NCIH1975_LUNG", "HCC827_LUNG" 등.

안정 데모: H1975 (EGFR L858R+T790M) × Osimertinib → lfc=-0.7526 (메모리 §23).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _common import (  # noqa: E402
    PRISM_NSCLC_LONG, CCLE_MUTATION_MATRIX, CCLE_EXPRESSION_PCA,
    GDSC2_CHEMBL_MAPPING,
    normalize_compound_id,
    mcp_response, mcp_error, route_tool,
)

_PRISM_DF = None
_CCLE_MUT = None
_CCLE_EXPR = None
_GDSC2_MAP = None


def _load_prism():
    global _PRISM_DF
    if _PRISM_DF is None:
        import pandas as pd
        df = pd.read_parquet(PRISM_NSCLC_LONG)
        df["cell_line_name"] = df["cell_line_name"].fillna("").astype(str).str.upper()
        df["molecule_chembl_id"] = df["molecule_chembl_id"].fillna("").astype(str).str.upper()
        _PRISM_DF = df
    return _PRISM_DF


def _load_ccle_mutation():
    global _CCLE_MUT
    if _CCLE_MUT is None:
        import pandas as pd
        _CCLE_MUT = pd.read_parquet(CCLE_MUTATION_MATRIX)
    return _CCLE_MUT


def _load_ccle_expression():
    global _CCLE_EXPR
    if _CCLE_EXPR is None:
        import pandas as pd
        df = pd.read_parquet(CCLE_EXPRESSION_PCA)
        df["ccle_name"] = df["ccle_name"].fillna("").astype(str).str.upper()
        _CCLE_EXPR = df
    return _CCLE_EXPR


def _load_gdsc2_mapping():
    global _GDSC2_MAP
    if _GDSC2_MAP is None:
        import pandas as pd
        df = pd.read_csv(GDSC2_CHEMBL_MAPPING)
        df["molecule_chembl_id"] = df["molecule_chembl_id"].fillna("").astype(str).str.upper()
        df["DRUG_NAME"] = df["DRUG_NAME"].fillna("").astype(str).str.upper()
        _GDSC2_MAP = df
    return _GDSC2_MAP


def _resolve_cell_line_prism(cell_input: str) -> tuple[str | None, str | None]:
    """PRISM cell_line_name 매칭. (matched_name, method) 반환.

    PRISM 형식: "HCC827", "NCIH1975", "A549" 등.
    사용자 입력 "H1975" → "NCIH1975" 자동 시도.
    """
    if not cell_input:
        return None, None
    cn = str(cell_input).strip().upper()
    df = _load_prism()
    cells = set(df["cell_line_name"].unique())

    if cn in cells:
        return cn, "exact"
    if f"NCI{cn}" in cells:
        return f"NCI{cn}", "nci_prefix"
    if cn.startswith("NCI-") and cn.replace("-", "") in cells:
        return cn.replace("-", ""), "dash_strip"
    # last-resort: contains
    for c in cells:
        if cn in c or c in cn:
            return c, "contains"
    return None, None


# ===== Tools =====

def get_drug_response(
    drug_id: str | None = None,
    chembl_id: str | None = None,
    cell_line: str | None = None,
    source: str = "prism",
) -> dict:
    """약물-세포주 반응 (lfc) 조회.

    PRISM lfc < 0 → cytotoxic. 강한 효과 = lfc < -0.5 정도.
    cell_line 입력은 alias 자동 시도 (H1975 → NCIH1975).
    """
    target_chembl = None
    if chembl_id:
        target_chembl = normalize_compound_id(chembl_id)
    elif drug_id and drug_id.upper().startswith("CHEMBL"):
        target_chembl = normalize_compound_id(drug_id)

    # cell_line alias 해소
    cell_resolved, cell_method = _resolve_cell_line_prism(cell_line) if cell_line else (None, None)

    if source == "prism":
        df = _load_prism()
        result = df
        if target_chembl:
            result = result[result["molecule_chembl_id"] == target_chembl]
        if cell_resolved:
            result = result[result["cell_line_name"] == cell_resolved]
        elif cell_line:
            # 입력은 있지만 alias 해소 실패
            return mcp_response(
                result={
                    "query": {"chembl_id": target_chembl, "cell_line": cell_line, "source": source},
                    "responses": [], "count": 0,
                    "note": (
                        f"cell_line '{cell_line}' 매칭 실패. "
                        "PRISM 형식 예: HCC827, NCIH1975, A549."
                    ),
                },
                tool_name="get_drug_response",
                source="prism_nsclc_long.parquet",
            )

        if len(result) == 0:
            return mcp_response(
                result={
                    "query": {
                        "chembl_id": target_chembl,
                        "cell_line": cell_line, "cell_resolved": cell_resolved,
                        "source": source,
                    },
                    "responses": [], "count": 0,
                    "note": "조건에 맞는 lfc 측정 없음.",
                },
                tool_name="get_drug_response",
                source="prism_nsclc_long.parquet",
            )

        # ★ v2: 강제 cap (둘 다 없으면 LFC 음수 큰 순 100개, 한쪽만 있으면 200개)
        original_count = len(result)
        cap_applied = False
        if not target_chembl and not cell_resolved and original_count > 100:
            result = result.nsmallest(100, "lfc")
            cap_applied = True
        elif original_count > 200:
            result = result.nsmallest(200, "lfc")
            cap_applied = True

        responses = [{
            "molecule_chembl_id": r["molecule_chembl_id"],
            "compound_id_brd": r["compound_id"],
            "cell_line_name": r["cell_line_name"],
            "model_id": r["model_id"],
            "oncotree_subtype": r["oncotree_subtype"],
            "lfc": float(r["lfc"]),
        } for _, r in result.iterrows()]

        return mcp_response(
            result={
                "query": {
                    "chembl_id": target_chembl,
                    "cell_line": cell_line,
                    "cell_resolved": cell_resolved,
                    "cell_match_method": cell_method,
                    "source": "prism",
                },
                "responses": responses,
                "count": len(responses),
                "total_available": original_count,
                "cap_applied": cap_applied,
                "interpretation": (
                    "PRISM lfc: 음수=cell viability 감소(cytotoxic), 양수=증식. "
                    "강한 효과는 lfc < -0.5 정도."
                ),
            },
            tool_name="get_drug_response",
            source="prism_nsclc_long.parquet",
        )

    return mcp_error(
        f"source={source} not yet implemented (only 'prism').",
        "get_drug_response", code="SOURCE_NOT_IMPLEMENTED",
    )


def get_cell_line_meta(cell_line: str) -> dict:
    """세포주 메타: CCLE mutation (20 actionable genes binary) + tissue.

    매칭 경로:
      cell_line → PRISM cell_line_name (alias 해소) → PRISM model_id (= CCLE depmap_id)
                → CCLE mutation matrix
    """
    cell_input = str(cell_line).strip().upper()
    cell_resolved, cell_method = _resolve_cell_line_prism(cell_input)

    if cell_resolved is None:
        return mcp_response(
            result={
                "cell_line": cell_input,
                "matched": False,
                "note": "PRISM에서 매칭 실패. 형식 예: HCC827, NCIH1975, A549.",
            },
            tool_name="get_cell_line_meta",
            source="prism + ccle_nsclc_mutation_matrix",
        )

    prism = _load_prism()
    ph = prism[prism["cell_line_name"] == cell_resolved]
    depmap_id = ph.iloc[0]["model_id"] if len(ph) > 0 else None
    oncotree = ph.iloc[0]["oncotree_subtype"] if len(ph) > 0 else None

    mutations_active: list[str] = []
    if depmap_id:
        ccle = _load_ccle_mutation()
        mh = ccle[ccle["depmap_id"] == depmap_id]
        if len(mh) > 0:
            row = mh.iloc[0]
            for gene in ccle.columns:
                if gene == "depmap_id":
                    continue
                try:
                    if int(row[gene]) == 1:
                        mutations_active.append(gene)
                except (TypeError, ValueError):
                    pass

    expr = _load_ccle_expression()
    eh = expr[expr["ccle_name"].str.startswith(cell_resolved + "_")]
    has_expression = len(eh) > 0
    ccle_name = eh.iloc[0]["ccle_name"] if has_expression else None

    return mcp_response(
        result={
            "cell_line": cell_input,
            "cell_resolved": cell_resolved,
            "cell_match_method": cell_method,
            "depmap_id": depmap_id,
            "ccle_name": ccle_name,
            "oncotree_subtype": oncotree,
            "mutations_active": mutations_active,
            "n_mutations_active": len(mutations_active),
            "has_expression_pca": has_expression,
            "matched": True,
        },
        tool_name="get_cell_line_meta",
        source="prism + ccle_nsclc_mutation_matrix + ccle_nsclc_expression_pca100",
    )


def cross_source_lookup(
    drug_id: str | None = None,
    chembl_id: str | None = None,
) -> dict:
    """PRISM ∩ GDSC2 cross-source 일치도.

    PRISM molecule_chembl_id ∩ GDSC2 mapping = cross-source pool.
    Mode 2 Spearman ρ = -0.1355 (n=1224, 메모리 §23).
    """
    target_chembl = None
    if chembl_id:
        target_chembl = normalize_compound_id(chembl_id)
    elif drug_id and drug_id.upper().startswith("CHEMBL"):
        target_chembl = normalize_compound_id(drug_id)

    gdsc_map = _load_gdsc2_mapping()
    prism = _load_prism()

    prism_chembls = set(c for c in prism["molecule_chembl_id"].dropna().unique() if c)
    gdsc_chembls = set(c for c in gdsc_map["molecule_chembl_id"].dropna().unique() if c)
    cross_pool = sorted(prism_chembls & gdsc_chembls)

    in_cross = (target_chembl in cross_pool) if target_chembl else None
    gdsc_name = None
    if target_chembl:
        gh = gdsc_map[gdsc_map["molecule_chembl_id"] == target_chembl]
        if len(gh) > 0:
            gdsc_name = gh.iloc[0]["DRUG_NAME"]

    return mcp_response(
        result={
            "drug_chembl_id": target_chembl,
            "gdsc2_drug_name": gdsc_name,
            "in_cross_source": in_cross,
            "cross_pool_size": len(cross_pool),
            "cross_pool_first_5": cross_pool[:5],
            "mode2_spearman_rho": -0.1355,
            "mode2_n": 1224,
            "interpretation": (
                "PRISM lfc vs GDSC2 LN_IC50. 음의 상관관계는 측정 차원 차이로 해석 "
                "(LN_IC50↑ = 저항성, lfc↓ = cytotoxic)."
            ),
        },
        tool_name="cross_source_lookup",
        source="PRISM ∩ GDSC2 mapping (release 8.4)",
    )


# ===== Lambda entry =====
TOOL_REGISTRY = {
    "get_drug_response": get_drug_response,
    "get_cell_line_meta": get_cell_line_meta,
    "cross_source_lookup": cross_source_lookup,
}


def lambda_handler(event, context):  # noqa: ARG001
    return route_tool(event, TOOL_REGISTRY)


if __name__ == "__main__":
    import json
    tests = [
        # 안정 데모: H1975 → NCIH1975 자동 alias
        {"tool": "get_cell_line_meta", "params": {"cell_line": "H1975"}},
        # H1975의 모든 약물 반응 (alias 해소)
        {"tool": "get_drug_response", "params": {"cell_line": "H1975"}},
        # cross-source pool
        {"tool": "cross_source_lookup", "params": {}},
    ]
    for e in tests:
        print(f">>> {e['tool']}({e['params']})")
        print(json.dumps(lambda_handler(e, None), indent=2, ensure_ascii=False)[:1500])
        print()
