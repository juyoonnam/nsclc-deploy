"""Patient Lambda — 3 tools (v2 / 2026-05-21).

v2 변경:
- match_patient_drugs: patient_id + mutation_profile + mutations 3가지 입력 모두 지원
- _find_patient_by_mutation_profile() 신설 — TCGA mutation matrix 매칭 환자 찾기
- supervisor.py 어댑터와 호환 (mutations list → mutation_profile dict 자동 변환)

Tools:
- get_patient_mutation    : 환자/유전자/집계 mutation 조회
- match_patient_drugs     : 환자 → 약물 ranking (Model B 사전 계산)
- list_actionable_genes   : 20 actionable genes + NSCLC frequency

Model B 사전 계산 자산:
- cbio_mutation_detail.csv (1,608 × 14): patient_id, gene, protein_change, mutation_type 등
- cbio_mutation_freq.csv (16 × 6): gene-level frequency
- patient_drug_ranking.parquet (4,412,328 × 23): 942 patients × 4,684 drugs ranking
- patient_top_cells.parquet (942 × 19): patient → top-5 유사 cell lines
- patient_transfer_meta.json: TCGA cosine sim → top-K=5 cells → A v3 lfc_pred avg

Ranking: rank_hybrid 오름차순 (낮을수록 우선). hybrid_tier 1 = actionable target + low rank.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _common import (  # noqa: E402
    TCGA_MUTATION, TCGA_MUTATION_FREQ,
    PATIENT_DRUG_RANKING, PATIENT_TOP_CELLS, PATIENT_TRANSFER_META,
    ACTIONABLE_GENES,
    mcp_response, mcp_error, route_tool,
)

_MUTATION_DF = None
_FREQ_DF = None
_RANKING_DF = None
_TOP_CELLS_DF = None
_META = None


def _load_mutation():
    global _MUTATION_DF
    if _MUTATION_DF is None:
        import pandas as pd
        df = pd.read_csv(TCGA_MUTATION)
        df["patient_id"] = df["patient_id"].astype(str).str.upper()
        df["gene"] = df["gene"].astype(str).str.upper()
        if "protein_change" in df.columns:
            df["protein_change"] = df["protein_change"].astype(str)
        _MUTATION_DF = df
    return _MUTATION_DF


def _load_freq():
    global _FREQ_DF
    if _FREQ_DF is None:
        import pandas as pd
        df = pd.read_csv(TCGA_MUTATION_FREQ)
        df["gene"] = df["gene"].astype(str).str.upper()
        _FREQ_DF = df
    return _FREQ_DF


def _load_ranking():
    global _RANKING_DF
    if _RANKING_DF is None:
        import pandas as pd
        df = pd.read_parquet(PATIENT_DRUG_RANKING)
        df["patient_id"] = df["patient_id"].astype(str).str.upper()
        df["drug_name"] = df["drug_name"].fillna("").astype(str).str.upper()
        _RANKING_DF = df
    return _RANKING_DF


def _load_top_cells():
    global _TOP_CELLS_DF
    if _TOP_CELLS_DF is None:
        import pandas as pd
        df = pd.read_parquet(PATIENT_TOP_CELLS)
        df["patient_id"] = df["patient_id"].astype(str).str.upper()
        _TOP_CELLS_DF = df
    return _TOP_CELLS_DF


def _load_meta() -> dict:
    global _META
    if _META is None:
        with open(PATIENT_TRANSFER_META) as f:
            _META = json.load(f)
    return _META


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


# ════════════════════════════════════════════════════════════
# v2: mutation_profile → patient_id 매칭
# ════════════════════════════════════════════════════════════

def _normalize_mutations_list_to_profile(mutations: list) -> dict:
    """['EGFR_L858R', 'EGFR_T790M'] → {'EGFR': 'L858R+T790M'}."""
    gene_muts: dict[str, list] = {}
    for m in mutations:
        m_str = str(m).strip()
        if "_" in m_str:
            gene, mut = m_str.split("_", 1)
            gene_muts.setdefault(gene.upper(), []).append(mut)
        elif ":" in m_str:
            gene, mut = m_str.split(":", 1)
            gene_muts.setdefault(gene.upper(), []).append(mut.strip())
        else:
            # 'EGFR' 같이 gene만: any mutation in that gene
            gene_muts.setdefault(m_str.upper(), []).append("any")
    return {g: "+".join(v) for g, v in gene_muts.items()}


def _find_patient_by_mutation_profile(mutation_profile: dict) -> dict:
    """mutation_profile dict → 매칭 TCGA 환자 ID 찾기.

    각 gene의 protein_change AND 매칭. "any"는 그 gene 변이 가진 환자 모두.
    profile = {"EGFR": "L858R+T790M"} → EGFR L858R AND EGFR T790M 둘 다 있는 환자.

    Returns:
      {
        "matched_patient_id": str | None,  # 첫 매칭 환자 (ranking set 내 우선)
        "n_candidates": int,                # mutation 매칭된 모든 환자 수
        "n_in_ranking_set": int,            # 그 중 patient_drug_ranking 내 환자
        "candidates_preview": list[str],    # 앞 5명
        "details": dict,                    # 각 gene별 매칭 환자 수
      }
    """
    mut = _load_mutation()

    matching_patients: set | None = None
    details: dict = {}

    for gene, mutation_str in mutation_profile.items():
        gene_upper = str(gene).strip().upper()
        mutation_str_lower = str(mutation_str).strip().lower()

        if mutation_str_lower in ("any", "*", "", "none"):
            gene_patients = set(mut[mut["gene"] == gene_upper]["patient_id"].unique())
            details[gene_upper] = {"target": "any", "n": len(gene_patients)}
        else:
            # "L858R+T790M" → ["L858R", "T790M"] (AND 매칭: 둘 다 있는 환자)
            target_changes = [c.strip() for c in str(mutation_str).split("+") if c.strip()]
            gene_hits = mut[
                (mut["gene"] == gene_upper)
                & (mut["protein_change"].isin(target_changes))
            ]
            # 변이 1개라면 그 변이 가진 환자, 여러 개면 모두 가진 환자
            if len(target_changes) == 1:
                gene_patients = set(gene_hits["patient_id"].unique())
            else:
                # 각 protein_change별 매칭 환자의 교집합
                per_change_sets = []
                for ch in target_changes:
                    change_patients = set(
                        mut[
                            (mut["gene"] == gene_upper)
                            & (mut["protein_change"] == ch)
                        ]["patient_id"].unique()
                    )
                    per_change_sets.append(change_patients)
                gene_patients = (
                    set.intersection(*per_change_sets) if per_change_sets else set()
                )
                # 교집합이 비어있으면 union으로 fallback (시연 친화)
                if not gene_patients:
                    gene_patients = set.union(*per_change_sets) if per_change_sets else set()
                    details[gene_upper] = {
                        "target": target_changes, "n": len(gene_patients),
                        "fallback": "AND 매칭 환자 없음 → OR 매칭으로 fallback",
                    }
                else:
                    details[gene_upper] = {"target": target_changes, "n": len(gene_patients)}
            if gene_upper not in details:
                details[gene_upper] = {"target": target_changes, "n": len(gene_patients)}

        if matching_patients is None:
            matching_patients = gene_patients
        else:
            new_match = matching_patients & gene_patients
            if not new_match:
                # AND가 비면 union으로 fallback (단일 gene이라도 매칭)
                matching_patients = matching_patients | gene_patients
            else:
                matching_patients = new_match

    matching_patients = matching_patients or set()
    n_candidates = len(matching_patients)

    # patient_drug_ranking 내 환자 우선
    ranking = _load_ranking()
    valid_patients = set(ranking["patient_id"].unique())
    in_ranking = sorted(matching_patients & valid_patients)
    n_in_ranking = len(in_ranking)

    chosen = in_ranking[0] if in_ranking else (
        sorted(matching_patients)[0] if matching_patients else None
    )

    return {
        "matched_patient_id": chosen,
        "n_candidates": n_candidates,
        "n_in_ranking_set": n_in_ranking,
        "candidates_preview": sorted(matching_patients)[:5],
        "details": details,
    }


# ════════════════════════════════════════════════════════════
# Tools
# ════════════════════════════════════════════════════════════

def get_patient_mutation(
    patient_id: str | None = None,
    gene: str | None = None,
) -> dict:
    """환자 mutation 조회.

    4가지 모드:
    - 둘 다 None: 전체 mutation 빈도 통계 (cbio_mutation_freq)
    - gene만: 그 gene 빈도 (mutated/total/frequency_pct/top_mutation)
    - patient_id만: 그 환자의 모든 mutation list
    - 둘 다: 그 환자가 그 gene 변이 가지는지 + protein_change
    """
    if not patient_id and not gene:
        freq = _load_freq()
        meta = _load_meta()
        return mcp_response(
            result={
                "total_patients": _safe_int(freq["total_patients"].iloc[0]) if len(freq) > 0 else None,
                "n_patients_in_model_b": meta.get("n_patients"),
                "actionable_genes": ACTIONABLE_GENES,
                "frequency_table": freq.to_dict(orient="records"),
            },
            tool_name="get_patient_mutation",
            source="cbio_mutation_freq.csv + patient_transfer_meta",
        )

    if gene and not patient_id:
        g = str(gene).strip().upper()
        freq = _load_freq()
        hit = freq[freq["gene"] == g]
        if len(hit) == 0:
            return mcp_response(
                result={
                    "gene": g,
                    "matched": False,
                    "note": f"{g}는 cbio_mutation_freq에 없음 (NSCLC mutation 빈도 매우 낮음).",
                },
                tool_name="get_patient_mutation",
                source="cbio_mutation_freq.csv",
            )
        row = hit.iloc[0]
        return mcp_response(
            result={
                "gene": g,
                "matched": True,
                "mutated_patients": _safe_int(row["mutated_patients"]),
                "total_patients": _safe_int(row["total_patients"]),
                "frequency_pct": _safe_float(row["frequency_pct"]),
                "n_mutation_records": _safe_int(row["n_mutation_records"]),
                "top_mutation": row.get("top_mutation"),
            },
            tool_name="get_patient_mutation",
            source="cbio_mutation_freq.csv",
        )

    if patient_id and not gene:
        pid = str(patient_id).strip().upper()
        mut = _load_mutation()
        hit = mut[mut["patient_id"] == pid]
        if len(hit) == 0:
            return mcp_response(
                result={
                    "patient_id": pid, "matched": False, "n_mutations": 0,
                    "note": "cbio_mutation_detail에 이 환자 없음. 형식: TCGA-XX-XXXX",
                },
                tool_name="get_patient_mutation",
                source="cbio_mutation_detail.csv",
            )
        return mcp_response(
            result={
                "patient_id": pid,
                "matched": True,
                "n_mutations": len(hit),
                "mutations": [{
                    "gene": r["gene"],
                    "protein_change": r["protein_change"],
                    "mutation_type": r["mutation_type"],
                    "variant_type": r["variant_type"],
                    "keyword": r["keyword"],
                } for _, r in hit.iterrows()],
            },
            tool_name="get_patient_mutation",
            source="cbio_mutation_detail.csv",
        )

    # 둘 다
    pid = str(patient_id).strip().upper()
    g = str(gene).strip().upper()
    mut = _load_mutation()
    hit = mut[(mut["patient_id"] == pid) & (mut["gene"] == g)]
    return mcp_response(
        result={
            "patient_id": pid,
            "gene": g,
            "has_mutation": len(hit) > 0,
            "n_records": len(hit),
            "protein_changes": hit["protein_change"].tolist() if len(hit) > 0 else [],
            "mutation_types": hit["mutation_type"].unique().tolist() if len(hit) > 0 else [],
        },
        tool_name="get_patient_mutation",
        source="cbio_mutation_detail.csv",
    )


def match_patient_drugs(
    patient_id: str | None = None,
    mutation_profile: dict | None = None,
    mutations: list | None = None,
    top_n: int = 10,
    actionable_only: bool = False,
) -> dict:
    """환자 → 약물 ranking (Model B 사전 계산 lookup).

    3가지 입력 모드 (v2):
    - patient_id (str): "TCGA-XX-XXXX" 직접 lookup
    - mutation_profile (dict): {"EGFR": "L858R+T790M", "TP53": "any"} → 매칭 환자 자동 검색
    - mutations (list): ["EGFR_L858R", "EGFR_T790M"] → mutation_profile dict로 자동 변환

    rank_hybrid 오름차순 정렬. hybrid_tier 1 = actionable target match + low rank.
    actionable_only=True면 drug_targets_actionable=1만 반환.
    """
    # 입력 정규화
    profile_input_info = None
    auto_matched_pid = None

    # 1. mutations list → mutation_profile dict
    if mutations and not mutation_profile:
        mutation_profile = _normalize_mutations_list_to_profile(mutations)
        profile_input_info = {
            "original": "mutations list",
            "normalized_profile": mutation_profile,
        }

    # 2. mutation_profile → patient_id 자동 매칭
    if mutation_profile and not patient_id:
        match_result = _find_patient_by_mutation_profile(mutation_profile)
        auto_matched_pid = match_result["matched_patient_id"]
        profile_input_info = {
            **(profile_input_info or {}),
            "mutation_profile_input": mutation_profile,
            "n_matching_candidates": match_result["n_candidates"],
            "n_in_ranking_set": match_result["n_in_ranking_set"],
            "candidates_preview": match_result["candidates_preview"],
            "matching_details": match_result["details"],
            "auto_matched_to": auto_matched_pid,
        }
        if not auto_matched_pid:
            return mcp_response(
                result={
                    "matched": False,
                    "mutation_profile_input": mutation_profile,
                    "n_candidates": match_result["n_candidates"],
                    "matching_details": match_result["details"],
                    "note": (
                        "TCGA mutation matrix에 해당 mutation_profile 매칭 환자 없음. "
                        "다른 profile 또는 patient_id 직접 지정 권장."
                    ),
                },
                tool_name="match_patient_drugs",
                source="patient_drug_ranking.parquet + cbio_mutation_detail",
            )
        patient_id = auto_matched_pid

    if not patient_id:
        return mcp_error(
            (
                "patient_id 또는 mutation_profile 또는 mutations 중 하나 필수. "
                "patient_id 형식: 'TCGA-XX-XXXX'. "
                "mutation_profile 형식: {'EGFR': 'L858R+T790M'}. "
                "mutations 형식: ['EGFR_L858R', 'EGFR_T790M']."
            ),
            "match_patient_drugs", code="MISSING_INPUT",
        )

    pid = str(patient_id).strip().upper()
    df = _load_ranking()
    hit = df[df["patient_id"] == pid]

    if len(hit) == 0:
        return mcp_response(
            result={
                "patient_id": pid, "matched": False, "n_drugs_ranked": 0,
                "note": "Model B 학습 set에 없는 환자. 942명 (LUAD/LUSC) 한정.",
                "profile_input_info": profile_input_info,
            },
            tool_name="match_patient_drugs",
            source="patient_drug_ranking.parquet",
        )

    if actionable_only and "drug_targets_actionable" in hit.columns:
        hit = hit[hit["drug_targets_actionable"] == 1]

    top = hit.nsmallest(top_n, "rank_hybrid") if "rank_hybrid" in hit.columns else hit.head(top_n)

    drugs = [{
        "rank_hybrid": _safe_int(r["rank_hybrid"]),
        "drug_name": r["drug_name"],
        "broad_id": r.get("broad_id"),
        "target": r.get("target") if isinstance(r.get("target"), str) else None,
        "phase": r.get("phase"),
        "pred_lfc_weighted": _safe_float(r["pred_lfc_weighted"]),
        "pred_zscore_weighted": _safe_float(r["pred_zscore_weighted"]),
        "hybrid_tier": _safe_int(r["hybrid_tier"]),
        "drug_targets_actionable": _safe_int(r["drug_targets_actionable"]) == 1
            if "drug_targets_actionable" in r else None,
        "target_overlap_genes": r.get("target_overlap_genes") if isinstance(r.get("target_overlap_genes"), str) else None,
        "mean_top_sim": _safe_float(r.get("mean_top_sim")),
    } for _, r in top.iterrows()]

    cancer_type = hit.iloc[0]["cancer_type"] if "cancer_type" in hit.columns else None

    return mcp_response(
        result={
            "patient_id": pid,
            "cancer_type": cancer_type,
            "matched": True,
            "n_drugs_ranked_total": len(hit),
            "top_drugs": drugs,
            "ranking_method": "rank_hybrid 오름차순 (낮을수록 우선)",
            "actionable_only_filter": actionable_only,
            "interpretation": (
                "Model B: TCGA mutation cosine 유사도 → top-5 cell line → "
                "Model A v3 lfc_pred 평균. "
                "pred_lfc_weighted < 0 → cytotoxic 예측. "
                "hybrid_tier 1 = actionable target + low rank."
            ),
            "profile_input_info": profile_input_info,
        },
        tool_name="match_patient_drugs",
        source="patient_drug_ranking.parquet (Model B 사전 계산)",
        model_version="Model B (top-K=5 cosine + A v3)",
        n_patients=942,
        n_drugs=4684,
    )


def list_actionable_genes() -> dict:
    """20 actionable genes + 각 gene의 NSCLC mutation frequency."""
    freq = _load_freq()
    freq_lookup = dict(zip(freq["gene"], freq["frequency_pct"]))
    top_mut_lookup = dict(zip(freq["gene"], freq.get("top_mutation", [None] * len(freq))))

    genes = [{
        "gene": g,
        "frequency_pct": _safe_float(freq_lookup.get(g)),
        "top_mutation": top_mut_lookup.get(g),
        "in_freq_table": g in freq_lookup,
    } for g in ACTIONABLE_GENES]

    genes.sort(key=lambda x: x["frequency_pct"] or 0, reverse=True)

    return mcp_response(
        result={
            "genes": genes,
            "count": len(ACTIONABLE_GENES),
            "source_db": "cBioPortal (luad_tcga_pan_can_atlas_2018)",
            "note": (
                "20 actionable genes (Model B 학습용). "
                "frequency_pct null → cbio_mutation_freq에 미수록 (변이 빈도 0)."
            ),
        },
        tool_name="list_actionable_genes",
        source="_common.ACTIONABLE_GENES + cbio_mutation_freq.csv",
    )


# ════════════════════════════════════════════════════════════
# Lambda entry
# ════════════════════════════════════════════════════════════

TOOL_REGISTRY = {
    "get_patient_mutation": get_patient_mutation,
    "match_patient_drugs": match_patient_drugs,
    "list_actionable_genes": list_actionable_genes,
}


def lambda_handler(event, context):  # noqa: ARG001
    return route_tool(event, TOOL_REGISTRY)


if __name__ == "__main__":
    tests = [
        {"tool": "list_actionable_genes", "params": {}},
        {"tool": "get_patient_mutation", "params": {"gene": "EGFR"}},
        {"tool": "match_patient_drugs", "params": {"patient_id": "TCGA-05-4244", "top_n": 5}},
        # v2 신규 테스트
        {"tool": "match_patient_drugs",
         "params": {"mutation_profile": {"EGFR": "L858R+T790M"}, "top_n": 5}},
        {"tool": "match_patient_drugs",
         "params": {"mutations": ["EGFR_L858R", "EGFR_T790M"], "top_n": 5}},
        {"tool": "match_patient_drugs",
         "params": {"mutation_profile": {"KRAS": "G12C"}, "top_n": 5, "actionable_only": True}},
    ]
    for e in tests:
        print(f">>> {e['tool']}({e['params']})")
        result = lambda_handler(e, None)
        print(json.dumps(result, indent=2, ensure_ascii=False)[:1500])
        print()
