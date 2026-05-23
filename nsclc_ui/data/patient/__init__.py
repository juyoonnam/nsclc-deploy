"""
nsclc_ui.data.patient
가상투약 탭 데이터 레이어.

Public API:
- get_patient_options()          : 942 TCGA 환자 dropdown options
- get_mutation_chip_genes()       : 20 actionable genes (chip 후보)
- get_patient_response()          : 실제 모드 — patient_id → 종합 응답
- compose_inference()             : 조립 모드 — mutation set → 실시간 추천
- get_sankey_figure()             : 변이 → 경로 → 약물 mini-sankey

캐시 전략: 모듈 로드 시 1회만 parquet 로드.
"""

from .loader import (
    get_patient_options,
    get_mutation_chip_genes,
    get_patient_response,
    get_patient_top_drugs,
)
from .compose_inference import compose_inference
from .sankey import get_sankey_figure

ACTIONABLE_GENES = [
    "ALK", "BRAF", "CDKN2A", "EGFR", "ERBB2", "KEAP1", "KRAS", "MAP2K1",
    "MET", "NF1", "NTRK1", "NTRK2", "NTRK3", "PIK3CA", "PTEN", "RB1",
    "RET", "ROS1", "STK11", "TP53",
]

__all__ = [
    "get_patient_options",
    "get_mutation_chip_genes",
    "get_patient_response",
    "get_patient_top_drugs",
    "compose_inference",
    "get_sankey_figure",
    "ACTIONABLE_GENES",
]
