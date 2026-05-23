"""
mock_lib.py
시연용 mock 응답 라이브러리. 발표 안전판.

각 entity에 대해 mechanism description (한국어, 2-3문장, NSCLC 관련 사실 기반)
템플릿을 보유. PMID는 local_retrieval로 동적으로 채움.

이렇게 분리하는 이유:
1. 응답 텍스트는 도메인 검증 필요 → hardcoded 안전
2. PMID는 yj corpus의 실제 수집 결과에 따라 다름 → 동적 매핑이 정확
3. retrieval 실패 시 → "Insufficient evidence" fallback 자동

응답 디자인 원칙:
- 한국어 2-3 문장
- 시작: "{Name}은/는 ..."
- "...라고 보고됨" 으로 끝맺어 grounding 명시
- forbidden words 없음 (예측한다/효과적/치료/권장/처방 등)
- PMID 인용은 add_pmids 함수가 끝에 추가
"""

from __future__ import annotations

from .local_retrieval import retrieve as _retrieve

# ---------------------------------------------------------------------------
# Mock templates (16 target + 30 drug = 46)
# ---------------------------------------------------------------------------

PROTEIN_TEMPLATES: dict[str, str] = {
    "EGFR": (
        "EGFR는 NSCLC adenocarcinoma의 약 15%에서 activating mutation (exon 19 deletion, "
        "L858R 등)을 보유하는 receptor tyrosine kinase. Mutated EGFR은 downstream MAPK 및 "
        "PI3K-AKT 경로 항진을 유발한다고 보고됨"
    ),
    "KRAS": (
        "KRAS는 NSCLC의 약 25-30%에서 mutation을 보유하는 small GTPase로, G12C 변이가 가장 "
        "흔함. Activated KRAS는 RAF-MEK-ERK 경로를 항진하며, G12C 변이는 covalent inhibitor "
        "작용점으로 보고됨"
    ),
    "ALK": (
        "ALK는 NSCLC의 약 3-7%에서 EML4-ALK 등 fusion 형태로 발견되는 receptor tyrosine "
        "kinase. Fusion은 ALK의 constitutive activation을 유발하여 downstream STAT3, PI3K, "
        "MAPK 경로 항진을 동반한다고 보고됨"
    ),
    "ROS1": (
        "ROS1는 NSCLC의 약 1-2%에서 rearrangement (CD74-ROS1 등 fusion) 형태로 발견되는 "
        "receptor tyrosine kinase. ROS1 fusion은 tyrosine kinase 활성을 항진시켜 downstream "
        "PI3K-AKT 및 MAPK 경로 활성화에 기여한다고 보고됨"
    ),
    "BRAF": (
        "BRAF는 NSCLC의 약 1-3%에서 mutation을 보유하며, V600E 변이가 NSCLC actionable 변이의 "
        "대표 형태. Mutated BRAF는 MEK-ERK 경로 항진을 유발하여 NSCLC adenocarcinoma의 "
        "oncogenic driver로 작용한다고 보고됨"
    ),
    "MET": (
        "MET은 receptor tyrosine kinase로, NSCLC에서 amplification 또는 exon 14 skipping "
        "mutation 형태로 발견됨. Activated MET은 downstream PI3K-AKT 및 MAPK 경로 항진을 "
        "유발하며 EGFR TKI 내성 mechanism으로도 보고됨"
    ),
    "ERBB2": (
        "ERBB2 (HER2)는 NSCLC의 약 2-4%에서 mutation 또는 amplification 형태로 발견되는 "
        "receptor tyrosine kinase. Activated HER2는 EGFR family signaling을 항진시켜 NSCLC "
        "adenocarcinoma oncogenic driver로 작용한다고 보고됨"
    ),
    "RET": (
        "RET는 NSCLC의 약 1-2%에서 KIF5B-RET 등 fusion 형태로 발견되는 receptor tyrosine "
        "kinase. RET fusion은 tyrosine kinase 활성화를 유발하여 downstream RAS-MAPK 및 PI3K "
        "경로 항진에 관여한다고 보고됨"
    ),
    "NTRK1": (
        "NTRK1 (TrkA)은 NGF 결합 receptor tyrosine kinase로, NSCLC에서 매우 드물게 (< 1%) "
        "NTRK fusion 형태로 발견됨. Fusion은 NTRK constitutive activation을 유발하여 "
        "downstream MAPK, PI3K-AKT 경로 항진과 관련된다고 보고됨"
    ),
    "NTRK2": (
        "NTRK2 (TrkB)는 BDNF 결합 receptor tyrosine kinase로, NSCLC에서 NTRK fusion 형태로 "
        "매우 드물게 (< 1%) 발견됨. Fusion 시 downstream PI3K-AKT 및 RAS-MAPK 경로 항진이 "
        "보고됨"
    ),
    "NTRK3": (
        "NTRK3 (TrkC)는 NT-3 결합 receptor tyrosine kinase로, NSCLC에서 NTRK fusion 형태로 "
        "매우 드물게 발견됨. Fusion 시 downstream MAPK 및 PI3K-AKT signaling 항진이 보고됨"
    ),
    "PIK3CA": (
        "PIK3CA는 PI3K p110α catalytic subunit으로, NSCLC의 약 1-3%에서 mutation을 보유함. "
        "Activated PIK3CA는 PI3K-AKT-mTOR 경로 항진을 유발하여 cell survival 및 proliferation "
        "신호와 관련된다고 보고됨"
    ),
    "AKT1": (
        "AKT1은 PI3K downstream effector serine/threonine kinase로, NSCLC의 PI3K-AKT 경로 "
        "hub. Activated AKT1은 mTOR 활성화, apoptosis 억제, glucose metabolism 변화 등 다중 "
        "oncogenic 신호와 관련된다고 보고됨"
    ),
    "PTEN": (
        "PTEN은 PI3K-AKT 경로의 tumor suppressor lipid phosphatase로, NSCLC에서 "
        "loss-of-function mutation 또는 expression 감소가 보고됨. PTEN loss는 AKT 항진을 "
        "유발하여 NSCLC progression과 관련된다고 보고됨"
    ),
    "TP53": (
        "TP53는 NSCLC의 약 50% 이상에서 mutation을 보유하는 tumor suppressor transcription "
        "factor로, DNA damage response 및 apoptosis의 hub. p53 loss-of-function은 NSCLC "
        "genomic instability와 관련된다고 보고됨"
    ),
    "MAP2K1": (
        "MAP2K1 (MEK1)은 RAS-RAF-MEK-ERK 경로의 dual-specificity kinase로, ERK1/2 활성화에 "
        "직접 관여. NSCLC에서 BRAF V600E 또는 KRAS mutation downstream effector로 작용한다고 "
        "보고됨"
    ),
}

DRUG_TEMPLATES: dict[str, str] = {
    "Osimertinib": (
        "Osimertinib은 3rd-gen EGFR TKI로, EGFR T790M 내성 변이 NSCLC에서 selectivity를 "
        "보이며 1st-line으로도 승인됨. CNS penetration 특성도 보고됨"
    ),
    "Gefitinib": (
        "Gefitinib은 1st-gen reversible EGFR TKI로, EGFR exon 19 deletion 또는 L858R 변이 "
        "NSCLC에서 1st-line으로 사용된 약제. ATP-competitive binding 메커니즘이 보고됨"
    ),
    "Erlotinib": (
        "Erlotinib은 1st-gen reversible EGFR TKI로, EGFR activating mutation NSCLC에서 "
        "1st-line 옵션 중 하나로 사용. ATP binding pocket에 결합하는 메커니즘이 보고됨"
    ),
    "Afatinib": (
        "Afatinib은 2nd-gen irreversible EGFR/HER2 TKI로, EGFR 및 ErbB family multiple "
        "kinase에 covalent 결합. EGFR activating mutation NSCLC에 사용된 약제로 보고됨"
    ),
    "Dacomitinib": (
        "Dacomitinib은 2nd-gen irreversible pan-HER (EGFR/HER2/HER4) TKI로, NSCLC EGFR "
        "activating mutation 1st-line 옵션으로 보고됨"
    ),
    "Lazertinib": (
        "Lazertinib은 3rd-gen EGFR TKI로, T790M 내성 변이 NSCLC에서 selectivity를 보이며 "
        "amivantamab과 병용이 보고됨. CNS penetration도 보고됨"
    ),
    "Mobocertinib": (
        "Mobocertinib은 EGFR exon 20 insertion 변이에 selective한 TKI로, exon 20 insertion "
        "NSCLC에 대한 작용점이 보고됨"
    ),
    "Alectinib": (
        "Alectinib은 2nd-gen ALK TKI로, ALK rearrangement NSCLC에서 1st-line 옵션 중 하나. "
        "CNS penetration 및 다양한 ALK 내성 변이 활성이 보고됨"
    ),
    "Brigatinib": (
        "Brigatinib은 2nd-gen ALK TKI로, crizotinib 내성 ALK 변이 (C1156Y, L1196M 등)에 "
        "활성. NSCLC ALK 양성에서 사용되는 약제로 보고됨"
    ),
    "Lorlatinib": (
        "Lorlatinib은 3rd-gen macrocyclic ALK/ROS1 TKI로, 다양한 ALK 내성 변이 (G1202R 포함) "
        "활성 및 CNS penetration이 보고됨"
    ),
    "Crizotinib": (
        "Crizotinib은 1st-gen ALK/ROS1/MET TKI로, ALK 또는 ROS1 rearrangement NSCLC에서 "
        "초기 표적치료 옵션으로 사용된 약제로 보고됨"
    ),
    "Ceritinib": (
        "Ceritinib은 2nd-gen ALK TKI로, crizotinib 내성 ALK 변이 일부에 활성. NSCLC ALK "
        "양성에서 사용되는 약제로 보고됨"
    ),
    "Ensartinib": (
        "Ensartinib은 2nd-gen ALK TKI로, NSCLC ALK rearrangement에서 임상 평가된 약제로 "
        "보고됨"
    ),
    "Capmatinib": (
        "Capmatinib은 selective MET TKI로, MET exon 14 skipping mutation NSCLC에서 임상 "
        "활성이 보고됨"
    ),
    "Tepotinib": (
        "Tepotinib은 selective MET TKI로, MET exon 14 skipping mutation NSCLC에서 임상 "
        "활성이 보고됨"
    ),
    "Savolitinib": (
        "Savolitinib은 selective MET TKI로, MET-driven NSCLC 또는 EGFR TKI 내성 MET "
        "amplification context에서 평가된 약제로 보고됨"
    ),
    "Selpercatinib": (
        "Selpercatinib은 selective RET TKI로, RET fusion NSCLC에서 임상 활성이 보고됨"
    ),
    "Pralsetinib": (
        "Pralsetinib은 selective RET TKI로, RET fusion NSCLC에서 임상 활성이 보고됨"
    ),
    "Larotrectinib": (
        "Larotrectinib은 pan-TRK (NTRK1/2/3) TKI로, NTRK fusion NSCLC 포함 다양한 fusion "
        "양성 종양에서 활성이 보고됨"
    ),
    "Repotrectinib": (
        "Repotrectinib은 ROS1/NTRK/ALK TKI로, ROS1 fusion 및 NTRK fusion NSCLC에서 평가된 "
        "약제로 보고됨"
    ),
    "Entrectinib": (
        "Entrectinib은 ROS1/NTRK TKI로, ROS1 fusion NSCLC 및 NTRK fusion 종양에서 임상 "
        "활성과 CNS penetration이 보고됨"
    ),
    "Trametinib": (
        "Trametinib은 allosteric MEK1/MEK2 inhibitor로, BRAF V600E 변이 NSCLC에서 "
        "dabrafenib과 병용 옵션으로 보고됨"
    ),
    "Selumetinib": (
        "Selumetinib은 allosteric MEK1/MEK2 inhibitor로, MAPK 경로 활성화 NSCLC context에서 "
        "임상 평가된 약제로 보고됨"
    ),
    "Cobimetinib": (
        "Cobimetinib은 allosteric MEK1/MEK2 inhibitor로, MAPK 경로 의존성 종양에서 평가된 "
        "약제로 보고됨"
    ),
    "Sotorasib": (
        "Sotorasib은 KRAS G12C covalent inhibitor로, KRAS G12C 변이 NSCLC에서 최초 승인된 "
        "KRAS targeted therapy로 보고됨"
    ),
    "Adagrasib": (
        "Adagrasib은 KRAS G12C covalent inhibitor로, KRAS G12C 변이 NSCLC에서 임상 활성과 "
        "CNS penetration이 보고됨"
    ),
    "Trastuzumab": (
        "Trastuzumab은 HER2 extracellular domain을 표적하는 monoclonal antibody로, NSCLC "
        "HER2 양성 일부 context에서 평가된 약제로 보고됨"
    ),
    "Tucatinib": (
        "Tucatinib은 selective HER2 TKI로, HER2-driven 종양에서 평가된 약제. NSCLC HER2 "
        "변이 context도 평가 대상으로 보고됨"
    ),
    "Bevacizumab": (
        "Bevacizumab은 VEGF-A를 표적하는 monoclonal antibody로, NSCLC non-squamous 진행성 "
        "환자에서 chemotherapy와 병용 옵션으로 사용되는 약제로 보고됨"
    ),
    "Pembrolizumab": (
        "Pembrolizumab은 anti-PD-1 monoclonal antibody로, PD-L1 발현 NSCLC에서 immune "
        "checkpoint inhibition을 통한 항종양 면역 활성화가 보고됨"
    ),
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

INSUFFICIENT = "Insufficient evidence in knowledge base for this node."


def mock_response(
    node_type: str,
    node_name: str,
    role: str = "",
    retrieved: list[dict] | None = None,
) -> tuple[str, list[str]]:
    """Return (text, pmids).

    If node_name has no template OR retrieved evidence has no PMIDs,
    return INSUFFICIENT sentinel.

    Args:
        node_type: "protein" | "drug"
        node_name: gene symbol or drug name (case-sensitive — must match
                   PROTEIN_TEMPLATES / DRUG_TEMPLATES keys exactly).
        role: optional NSCLC role descriptor (unused in mock; passed for API parity).
        retrieved: list of PubMed records from local_retrieval.retrieve().
                   If None, this function retrieves on its own.
    """
    name_type = (node_type or "").lower()
    if name_type in {"protein", "gene", "target"}:
        template = PROTEIN_TEMPLATES.get(node_name)
    elif name_type == "drug":
        # case-insensitive lookup for drugs (UI may pass lowercase variants)
        template = DRUG_TEMPLATES.get(node_name)
        if not template:
            for k, v in DRUG_TEMPLATES.items():
                if k.lower() == node_name.lower():
                    template = v
                    break
    else:
        template = None

    if not template:
        return INSUFFICIENT, []

    # gather PMIDs: prefer provided retrieved, else self-retrieve
    if retrieved is None:
        retrieved = _retrieve(node_name, name_type, k=3)

    pmids = [str(r.get("pmid", "")) for r in (retrieved or [])][:2]
    pmids = [p for p in pmids if p]
    if not pmids:
        return INSUFFICIENT, []

    pmid_str = ", ".join(f"PMID:{p}" for p in pmids)
    text = f"Mechanism hypothesis: {template} [{pmid_str}]."
    return text, pmids


def has_entry(node_type: str, node_name: str) -> bool:
    """Return True if a mock template exists for this entity."""
    name_type = (node_type or "").lower()
    if name_type in {"protein", "gene", "target"}:
        return node_name in PROTEIN_TEMPLATES
    if name_type == "drug":
        if node_name in DRUG_TEMPLATES:
            return True
        return any(k.lower() == node_name.lower() for k in DRUG_TEMPLATES)
    return False


def known_entities() -> dict:
    """Diagnostic — list all mock-supported entities."""
    return {
        "proteins": sorted(PROTEIN_TEMPLATES.keys()),
        "drugs": sorted(DRUG_TEMPLATES.keys()),
        "n_protein": len(PROTEIN_TEMPLATES),
        "n_drug": len(DRUG_TEMPLATES),
    }


if __name__ == "__main__":
    import json as _json
    print("=== mock_lib known entities ===")
    print(_json.dumps(known_entities(), indent=2, ensure_ascii=False))
    print()
    for t, n in [("protein", "EGFR"), ("protein", "KRAS"), ("drug", "Osimertinib"),
                 ("drug", "Trametinib"), ("protein", "SAAL1"), ("drug", "Aspirin")]:
        text, pmids = mock_response(t, n)
        print(f"--- {t}:{n} ---")
        print(text)
        print(f"pmids={pmids}")
        print()
