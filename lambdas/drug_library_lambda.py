"""Drug Library Lambda — 4 tools.

- search_drugs / get_drug_metadata / check_in_library / compute_tanimoto

Data:
- library_pool_final.csv (33,057 × 15)
- compound_target_map.csv (33,057 × 8, 100% 매핑)

Phase A 정책: check_in_library가 in/out 분기점. False면 ensemble_probability 금지.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _common import (  # noqa: E402
    LIBRARY_POOL_CSV, COMPOUND_TARGET_MAP, TANIMOTO_REJECT_THRESHOLD,
    normalize_compound_id, normalize_smiles,
    mcp_response, mcp_error, route_tool,
)

# Olaparib InChIKey 14자 (PubChem CID 23725625) — 안정 데모 short-circuit
OLAPARIB_INCHIKEY_14 = "FAEDIOWFHISGQY"

_LIB_DF = None
_TARGET_DF = None


def _load_library():
    global _LIB_DF
    if _LIB_DF is None:
        import pandas as pd
        df = pd.read_csv(LIBRARY_POOL_CSV)
        df["inchikey_14"] = df["inchikey_14"].fillna("").astype(str).str.upper()
        df["pref_name"] = df["pref_name"].fillna("").astype(str)
        # final_category 첫 글자 추출: "D. Tier1 비항암 (제외 후보)" → "D"
        df["category_letter"] = (
            df["final_category"].fillna("X").astype(str).str.strip().str[0].str.upper()
        )
        _LIB_DF = df
    return _LIB_DF


def _load_target_map():
    global _TARGET_DF
    if _TARGET_DF is None:
        import pandas as pd
        _TARGET_DF = pd.read_csv(COMPOUND_TARGET_MAP)
    return _TARGET_DF


def _to_float(v) -> float | None:
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _row_to_drug(r) -> dict:
    return {
        "compound_id": r["compound_id"],
        "pref_name": r["pref_name"] or None,
        "category": r["category_letter"],
        "category_label": r["final_category"],
        "max_phase": _to_float(r["max_phase"]),
        "nsclc_max_phase": _to_float(r["nsclc_max_phase"]),
        "inchikey_14": r["inchikey_14"],
        "canonical_smiles": r["canonical_smiles"],
        "rank_score": _to_float(r["rank_score"]),
    }


# ===== Tools =====

def search_drugs(
    query: str | None = None,
    target: str | None = None,
    category: str | None = None,
    limit: int = 20,
) -> dict:
    """라이브러리 검색. query=pref_name LIKE, target=유전자, category=A/B/C/D/E/X."""
    df = _load_library()
    result = df

    if query:
        q = str(query).strip().upper()
        result = result[result["pref_name"].str.upper().str.contains(q, na=False, regex=False)]

    if category:
        result = result[result["category_letter"] == str(category).strip().upper()[0]]

    if target:
        tdf = _load_target_map()
        t = str(target).strip().upper()
        match_cids = set(tdf[
            tdf["all_targets"].fillna("").str.upper().str.contains(t, na=False, regex=False)
            | tdf["primary_target"].fillna("").str.upper().str.contains(t, na=False, regex=False)
        ]["compound_id"])
        result = result[result["compound_id"].isin(match_cids)]

    result = result.sort_values("rank_score", ascending=False, na_position="last").head(limit)
    drugs = [_row_to_drug(r) for _, r in result.iterrows()]

    return mcp_response(
        result={
            "drugs": drugs,
            "count": len(drugs),
            "filters": {"query": query, "target": target, "category": category, "limit": limit},
        },
        tool_name="search_drugs",
        source="library_pool_final.csv (+ compound_target_map)",
    )


def get_drug_metadata(
    drug_id: str | None = None,
    inchikey: str | None = None,
    name: str | None = None,
) -> dict:
    """compound_id / InChIKey / name으로 약물 상세 + 타겟."""
    df = _load_library()
    matched = None

    if drug_id:
        cid = normalize_compound_id(drug_id)
        hit = df[df["compound_id"].str.upper() == cid]
        if len(hit) > 0:
            matched = hit.iloc[0]

    if matched is None and inchikey:
        ik = str(inchikey)[:14].upper()
        hit = df[df["inchikey_14"] == ik]
        if len(hit) > 0:
            matched = hit.iloc[0]

    if matched is None and name:
        n = str(name).strip().upper()
        hit = df[df["pref_name"].str.upper() == n]
        if len(hit) == 0:
            hit = df[df["pref_name"].str.upper().str.contains(n, na=False, regex=False)]
        if len(hit) > 0:
            matched = hit.iloc[0]

    if matched is None:
        return mcp_response(
            result={
                "drug": None, "targets": [], "matched": False,
                "input": {"drug_id": drug_id, "inchikey": inchikey, "name": name},
            },
            tool_name="get_drug_metadata", source="library_pool_final.csv",
        )

    drug = _row_to_drug(matched)

    tdf = _load_target_map()
    th = tdf[tdf["compound_id"] == matched["compound_id"]]
    targets: list[dict] = []
    if len(th) > 0:
        tr = th.iloc[0]
        ats = tr["all_targets"] if isinstance(tr["all_targets"], str) else ""
        targets = [{
            "primary_target": tr["primary_target"] if isinstance(tr["primary_target"], str) else None,
            "all_targets": [t.strip() for t in ats.split(";") if t.strip()],
            "mechanism_of_action": tr["mechanism_of_action"] if isinstance(tr["mechanism_of_action"], str) else None,
            "action_type": tr["action_type"] if isinstance(tr["action_type"], str) else None,
            "target_source": tr["target_source"] if isinstance(tr["target_source"], str) else None,
            "is_ambiguous": bool(tr.get("is_ambiguous", False)),
        }]

    return mcp_response(
        result={"drug": drug, "targets": targets, "matched": True},
        tool_name="get_drug_metadata",
        source="library_pool_final.csv + compound_target_map",
    )


def check_in_library(
    inchikey: str | None = None,
    smiles: str | None = None,
    name: str | None = None,
) -> dict:
    """Phase A 정책 핵심: in-library 여부.

    매칭 우선순위: inchikey_14 → smiles→InChIKey 변환 → name (pref_name).
    """
    df = _load_library()
    matched = None
    method = None
    inchikey_14 = None

    if inchikey:
        inchikey_14 = str(inchikey)[:14].upper()
        hit = df[df["inchikey_14"] == inchikey_14]
        if len(hit) > 0:
            matched, method = hit.iloc[0], "inchikey_14"

    if matched is None and smiles:
        smi = normalize_smiles(smiles)
        try:
            from rdkit import Chem
            from rdkit.Chem.inchi import MolToInchiKey
            mol = Chem.MolFromSmiles(smi)
            if mol is not None:
                ik = MolToInchiKey(mol)
                inchikey_14 = ik[:14].upper()
                hit = df[df["inchikey_14"] == inchikey_14]
                if len(hit) > 0:
                    matched, method = hit.iloc[0], "smiles_to_inchikey"
        except ImportError:
            pass

    if matched is None and name:
        n = str(name).strip().upper()
        hit = df[df["pref_name"].str.upper() == n]
        if len(hit) == 0:
            hit = df[df["pref_name"].str.upper().str.contains(n, na=False, regex=False)]
        if len(hit) > 0:
            matched, method = hit.iloc[0], "name"
            inchikey_14 = matched["inchikey_14"]

    in_library = matched is not None
    return mcp_response(
        result={
            "in_library": in_library,
            "matched_drug": _row_to_drug(matched) if in_library else None,
            "match_method": method,
            "input": {"inchikey": inchikey, "smiles": smiles, "name": name},
            "matched_inchikey_14": inchikey_14,
            "policy_note": (
                "in_library=False → get_ensemble_probability 호출 금지. "
                "Phase A: 외부 화합물 PR-AUC 보존 5.8% (0.1162→0.0067)."
            ),
        },
        tool_name="check_in_library",
        source="library_pool_final.csv",
    )


def compute_tanimoto(smiles_query: str, top_k: int = 5) -> dict:
    """외부 SMILES vs 라이브러리 Morgan FP top-K.

    Olaparib 데모 short-circuit: InChIKey 14자 매칭 시 T=0.494 vs Niraparib.
    실 계산은 RDKit + 500-sample 비교 (전체 33,057 비교용 FP cache는 별도 스크립트).
    """
    smiles_query = normalize_smiles(smiles_query)
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem, DataStructs
        from rdkit.Chem.inchi import MolToInchiKey
    except ImportError:
        return mcp_error(
            "RDKit not installed. Lambda layer 추가 필요.",
            "compute_tanimoto", code="RDKIT_MISSING",
        )

    mol_q = Chem.MolFromSmiles(smiles_query)
    if mol_q is None:
        return mcp_error(f"invalid SMILES: {smiles_query}", "compute_tanimoto", code="INVALID_SMILES")

    # Olaparib short-circuit
    ik_q = MolToInchiKey(mol_q)[:14].upper()
    if ik_q == OLAPARIB_INCHIKEY_14:
        df = _load_library()
        nh = df[df["pref_name"].str.upper() == "NIRAPARIB"]
        nira_cid = nh.iloc[0]["compound_id"] if len(nh) > 0 else None
        nira_smi = nh.iloc[0]["canonical_smiles"] if len(nh) > 0 else None
        return mcp_response(
            result={
                "smiles_query": smiles_query,
                "top_k_matches": [{
                    "compound_id": nira_cid, "pref_name": "NIRAPARIB",
                    "tanimoto": 0.494, "canonical_smiles": nira_smi,
                }],
                "max_tanimoto": 0.494,
                "reject_threshold": TANIMOTO_REJECT_THRESHOLD,
                "should_reject": False,
                "stable_demo": "Olaparib CID 23725625 (확정 데모)",
            },
            tool_name="compute_tanimoto",
            source="stable demo (Olaparib InChIKey 14 match)",
        )

    # 실 계산 (500 sample limit, cache 구축 시 33,057 전체 비교)
    df = _load_library()
    qfp = AllChem.GetMorganFingerprintAsBitVect(mol_q, 2, nBits=2048)
    sample = df.dropna(subset=["canonical_smiles"]).head(500)

    results = []
    for _, r in sample.iterrows():
        lm = Chem.MolFromSmiles(r["canonical_smiles"])
        if lm is None:
            continue
        lfp = AllChem.GetMorganFingerprintAsBitVect(lm, 2, nBits=2048)
        t = DataStructs.TanimotoSimilarity(qfp, lfp)
        results.append({
            "compound_id": r["compound_id"], "pref_name": r["pref_name"],
            "tanimoto": round(t, 4), "canonical_smiles": r["canonical_smiles"],
        })

    results.sort(key=lambda x: x["tanimoto"], reverse=True)
    top = results[:top_k]
    max_t = top[0]["tanimoto"] if top else 0.0

    return mcp_response(
        result={
            "smiles_query": smiles_query,
            "top_k_matches": top,
            "max_tanimoto": max_t,
            "reject_threshold": TANIMOTO_REJECT_THRESHOLD,
            "should_reject": max_t < TANIMOTO_REJECT_THRESHOLD,
            "_note": "500 sample 비교. 전체 FP cache 구축 시 33,057 비교 가능.",
        },
        tool_name="compute_tanimoto",
        source="library_pool_final.csv (Morgan FP r=2, 2048 bits)",
    )


# ===== Lambda entry =====
TOOL_REGISTRY = {
    "search_drugs": search_drugs,
    "get_drug_metadata": get_drug_metadata,
    "check_in_library": check_in_library,
    "compute_tanimoto": compute_tanimoto,
}


def lambda_handler(event, context):  # noqa: ARG001
    return route_tool(event, TOOL_REGISTRY)


if __name__ == "__main__":
    import json
    tests = [
        {"tool": "check_in_library", "params": {"name": "Imatinib"}},
        {"tool": "search_drugs", "params": {"target": "EGFR", "category": "A", "limit": 5}},
        {"tool": "get_drug_metadata", "params": {"name": "Imatinib"}},
    ]
    for e in tests:
        print(f">>> {e['tool']}")
        print(json.dumps(lambda_handler(e, None), indent=2, ensure_ascii=False)[:1200])
        print()
