"""
Demo data for Simulator Part A/B.

The backend contract will replace this module later. Keep the public objects
small and predictable so callbacks can be swapped to service calls.
"""

from __future__ import annotations

import math

LIBRARY_TOTAL_COUNT = 128
LIBRARY_PAGE_SIZE = 10

LIBRARY_ROWS = [
    {
        "rank": 1,
        "name": "Crizotinib",
        "drugbank_id": "DB09017",
        "rank_score": 0.91,
        "confidence": 3,
        "clinical_status": "approved",
        "sources": ["drugbank", "drugcentral"],
        "nsclc_unused": True,
    },
    {
        "rank": 2,
        "name": "Vandetanib",
        "drugbank_id": "DB05294",
        "rank_score": 0.82,
        "confidence": 3,
        "clinical_status": "approved_other",
        "sources": ["drugbank", "drugcentral"],
        "nsclc_unused": True,
    },
    {
        "rank": 3,
        "name": "Cabozantinib",
        "drugbank_id": "DB08875",
        "rank_score": 0.76,
        "confidence": 2,
        "clinical_status": "approved_other",
        "sources": ["drugbank", "drugcentral"],
        "nsclc_unused": True,
    },
    {
        "rank": 4,
        "name": "Entrectinib",
        "drugbank_id": "DB11986",
        "rank_score": 0.71,
        "confidence": 2,
        "clinical_status": "phase_2",
        "sources": ["drugbank"],
        "nsclc_unused": True,
    },
    {
        "rank": 5,
        "name": "Tepotinib",
        "drugbank_id": "DB15133",
        "rank_score": 0.66,
        "confidence": 2,
        "clinical_status": "phase_2",
        "sources": ["drugcentral"],
        "nsclc_unused": True,
    },
    {
        "rank": 6,
        "name": "Foretinib",
        "drugbank_id": "DB11886",
        "rank_score": 0.61,
        "confidence": 1,
        "clinical_status": "preclinical",
        "sources": ["drugbank"],
        "nsclc_unused": True,
    },
    {
        "rank": 7,
        "name": "Alectinib",
        "drugbank_id": "DB11363",
        "rank_score": 0.58,
        "confidence": 1,
        "clinical_status": "preclinical",
        "sources": ["drugbank", "drugcentral"],
        "nsclc_unused": True,
    },
    {
        "rank": 8,
        "name": "Lorlatinib",
        "drugbank_id": "DB12130",
        "rank_score": 0.55,
        "confidence": 1,
        "clinical_status": "preclinical",
        "sources": ["drugbank", "drugcentral"],
        "nsclc_unused": True,
    },
    {
        "rank": 9,
        "name": "Bosutinib",
        "drugbank_id": "DB06616",
        "rank_score": 0.52,
        "confidence": 1,
        "clinical_status": "preclinical",
        "sources": ["drugcentral"],
        "nsclc_unused": True,
    },
    {
        "rank": 10,
        "name": "Ponatinib",
        "drugbank_id": "DB08901",
        "rank_score": 0.50,
        "confidence": 1,
        "clinical_status": "preclinical",
        "sources": ["drugbank"],
        "nsclc_unused": True,
    },
    {
        "rank": 11,
        "name": "Nintedanib",
        "drugbank_id": "DB09079",
        "rank_score": 0.48,
        "confidence": 2,
        "clinical_status": "approved_other",
        "sources": ["drugbank", "drugcentral"],
        "nsclc_unused": True,
    },
    {
        "rank": 12,
        "name": "Sunitinib",
        "drugbank_id": "DB01268",
        "rank_score": 0.46,
        "confidence": 1,
        "clinical_status": "approved_other",
        "sources": ["drugbank", "drugcentral"],
        "nsclc_unused": True,
    },
    {
        "rank": 13,
        "name": "Lenvatinib",
        "drugbank_id": "DB09078",
        "rank_score": 0.44,
        "confidence": 1,
        "clinical_status": "approved_other",
        "sources": ["drugbank"],
        "nsclc_unused": True,
    },
    {
        "rank": 14,
        "name": "Regorafenib",
        "drugbank_id": "DB08896",
        "rank_score": 0.43,
        "confidence": 1,
        "clinical_status": "approved_other",
        "sources": ["drugcentral"],
        "nsclc_unused": True,
    },
    {
        "rank": 15,
        "name": "Pazopanib",
        "drugbank_id": "DB06589",
        "rank_score": 0.41,
        "confidence": 1,
        "clinical_status": "phase_2",
        "sources": ["drugbank"],
        "nsclc_unused": True,
    },
    {
        "rank": 16,
        "name": "Tivantinib",
        "drugbank_id": "DB12010",
        "rank_score": 0.39,
        "confidence": 1,
        "clinical_status": "preclinical",
        "sources": ["drugcentral"],
        "nsclc_unused": True,
    },
]

SELECTED_DRUG = {
    "name": "Crizotinib",
    "drugbank_id": "DB09017",
    "external_url": "https://go.drugbank.com/drugs/DB09017",
    "smiles": "CN1CCN(CC1)C2=NC(=NC3=C2N=CN3)C4=CC(=C(C=C4)Cl)F",
    "structure_svg_highlights": [
        {"x": 60, "y": 24, "w": 92, "h": 76, "kind": "red"},
        {"x": 42, "y": 116, "w": 88, "h": 76, "kind": "amber"},
    ],
    "rank_score": 0.91,
    "scaffold_cluster": 7,
    "why_recommend": "MET/ALK 관련 후보",
    "model_note": "다른 암종 승인, NSCLC 재창출 후보",
    "clinical_status": "approved",
}


CELL_LINE_OPTIONS = [
    {"label": "H1975", "value": "H1975"},
    {"label": "HCC827", "value": "HCC827"},
    {"label": "PC9", "value": "PC9"},
    {"label": "A549", "value": "A549"},
    {"label": "H1299", "value": "H1299"},
]

CELL_LINE_DRUG_OPTIONS = [
    {"label": "Osimertinib", "value": "Osimertinib"},
    {"label": "Afatinib", "value": "Afatinib"},
    {"label": "Erlotinib", "value": "Erlotinib"},
    {"label": "Trametinib", "value": "Trametinib"},
    {"label": "Cobimetinib", "value": "Cobimetinib"},
]

CELL_LINE_DRUG_META = {
    "Osimertinib": {"chembl_id": "CHEMBL3353410", "target": "EGFR", "class": "EGFR TKI"},
    "Afatinib": {"chembl_id": "CHEMBL1173655", "target": "EGFR", "class": "EGFR/ERBB2 TKI"},
    "Erlotinib": {"chembl_id": "CHEMBL553", "target": "EGFR", "class": "EGFR TKI"},
    "Trametinib": {"chembl_id": "CHEMBL2103875", "target": "MEK", "class": "MEK inhibitor"},
    "Cobimetinib": {"chembl_id": "CHEMBL2146883", "target": "MEK", "class": "MEK inhibitor"},
}


def _clamp(value: float, low: float = 0.03, high: float = 0.97) -> float:
    return max(low, min(high, value))


def _make_prism_points(drug: str) -> list[dict]:
    cell_names = [f"NSCLC_{idx:02d}" for idx in range(1, 89)]
    cell_names[41] = "H1975"
    offset = {
        "Osimertinib": 0.0,
        "Afatinib": 0.05,
        "Erlotinib": -0.03,
        "Trametinib": 0.1,
        "Cobimetinib": 0.08,
    }.get(drug, 0.0)
    points = []
    for idx, cell in enumerate(cell_names):
        model_prob = _clamp(0.08 + ((idx * 37) % 83) / 100 + offset * 0.12)
        signal = 0.18 + 0.68 * model_prob + 0.25 * math.sin(idx * 1.73 + offset)
        priming = _clamp(signal, 0.02, 0.98)
        lfc = round(-1.0 + priming * 1.19, 3)
        if cell == "H1975":
            model_prob = 0.18
            priming = 0.21
            lfc = -0.75
        points.append(
            {
                "cell_line": cell,
                "model_prob": round(model_prob, 3),
                "priming_score": round(priming, 3),
                "prism_lfc": lfc,
            }
        )
    return points


CELL_LINE_RESPONSE_POINTS = {
    drug["value"]: _make_prism_points(drug["value"])
    for drug in CELL_LINE_DRUG_OPTIONS
}

CELL_LINE_RESPONSE_DEFAULTS = {
    "cell_line": "H1975",
    "drug": "Osimertinib",
    "model_score": 0.83,
    "model_prob": 0.18,
    "prism_lfc": -0.75,
    "priming_score": 0.21,
}

CELL_LINE_COMBO_DEFAULTS = {
    "cell_line": "H1975",
    "drug_a": "Osimertinib",
    "drug_b": "Cobimetinib",
    "heuristic_score": 0.79,
    "combo_score": 18.2,
    "result_label": "SYNERGY",
    "disclaimer": "면책: 본 화면은 시뮬레이션 예시이며 실제 실험 결과를 대체하지 않습니다.",
    "dose_matrix": [
        [2, 6, 9, 8, 5],
        [4, 10, 18.2, 14, 9],
        [3, 7, 12, 15, 11],
        [2, 4, 7, 9, 8],
        [0, 1, 2, 3, 4],
    ],
    "best_index": [1, 2],
}
