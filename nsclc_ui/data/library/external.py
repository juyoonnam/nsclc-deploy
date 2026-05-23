"""
nsclc_ui/data/library/external.py

External Compound Analyzer 백엔드.
입력: SMILES (PubChem CID / InChIKey는 UI에서 SMILES 변환 후 호출)
출력: in-library Top-K 유사 화합물 (Tanimoto)

원칙 (Phase AA 외부 화합물 정책):
- champion 모델 직접 적용 절대 X (KNN imputation 결과 PR-AUC 5.8% 보존)
- analog evidence만 제공, UI에 정직 disclaimer

v2 변경:
- AllChem.GetMorganFingerprintAsBitVect → rdFingerprintGenerator (deprecation 제거)
- RDLogger.DisableLog로 C++ 레벨 로그 폭탄 차단
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import pandas as pd
from rdkit import Chem, DataStructs, RDLogger
from rdkit.Chem import rdFingerprintGenerator

# 33K compound × deprecation message → 출력 잡아먹는 문제 차단
RDLogger.DisableLog("rdApp.*")

from nsclc_ui.data.library.cards import load_library_cards
from nsclc_ui.data.library.loader import load_library_full

MORGAN_RADIUS = 2
MORGAN_BITS = 2048

DISCLAIMER = (
    "champion 직접 적용 불가 (Phase A KNN imputation 결과 외부 PR-AUC "
    "0.1162 → 0.0067, 5.8% 보존). 아래는 in-library 유사 화합물 "
    "기반 analog evidence — 정량 예측 아님."
)

_MORGAN_GEN = rdFingerprintGenerator.GetMorganGenerator(
    radius=MORGAN_RADIUS, fpSize=MORGAN_BITS
)


def _mol_from_input(query: str) -> Chem.Mol | None:
    """현재 SMILES만 지원. CID/InChIKey는 UI에서 변환 후 호출."""
    query = (query or "").strip()
    if not query:
        return None
    return Chem.MolFromSmiles(query)


def _fp(mol: Chem.Mol):
    return _MORGAN_GEN.GetFingerprint(mol)


@lru_cache(maxsize=1)
def _library_fps() -> tuple[list[str], list[Any]]:
    """library의 모든 SMILES → Morgan FP. 첫 호출 5-10초, 이후 캐시."""
    df = load_library_full()
    cids: list[str] = []
    fps: list[Any] = []
    for _, r in df.iterrows():
        smi = r.get("canonical_smiles")
        if not smi or not isinstance(smi, str):
            continue
        m = Chem.MolFromSmiles(smi)
        if m is None:
            continue
        fps.append(_fp(m))
        cids.append(str(r["compound_id"]))
    return cids, fps


def warmup() -> None:
    """앱 시작 시 호출 권장 — FP precompute로 첫 분석 즉시 응답."""
    _library_fps()


def analyze_external(query: str, top_k: int = 5) -> dict[str, Any]:
    mol = _mol_from_input(query)
    if mol is None:
        return {
            "ok": False,
            "error": (
                "SMILES 파싱 실패. PubChem CID/InChIKey는 SMILES로 "
                "변환 후 입력하세요."
            ),
            "query": query,
            "query_smiles": None,
            "top_analogs": [],
            "warning": DISCLAIMER,
        }

    query_fp = _fp(mol)
    query_smiles = Chem.MolToSmiles(mol)

    cids, fps = _library_fps()
    sims = DataStructs.BulkTanimotoSimilarity(query_fp, fps)

    pairs = sorted(zip(cids, sims), key=lambda x: -x[1])[: top_k]

    by_id = {c["compound_id"]: c for c in load_library_cards()}
    top_analogs: list[dict] = []
    for cid, sim in pairs:
        card = by_id.get(cid)
        if not card:
            continue
        top_analogs.append({
            "compound_id": cid,
            "name": card["name"],
            "tanimoto": round(float(sim), 3),
            "rank_score": card["rank_score"],
            "phase_chip": card["phase_chip"],
            "primary_target": card.get("primary_target"),
            "targets": card.get("targets", []),
            "x_s_verified": card["x_s_verified"],
            "discovery_type": card.get("discovery_type"),
            "actions": card["actions"],
        })

    return {
        "ok": True,
        "error": None,
        "query": query,
        "query_smiles": query_smiles,
        "top_analogs": top_analogs,
        "warning": DISCLAIMER,
    }


if __name__ == "__main__":
    import json

    # 테스트: Crizotinib SMILES
    test_smiles = "CC(C1=C(C=CC(=C1Cl)F)Cl)OC2=C(N=CC(=C2)C3=CN(N=C3)C4CCNCC4)N"
    result = analyze_external(test_smiles, top_k=5)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
