"""
nsclc_ui.data.cell_line
가상세포실험 탭 데이터 레이어.

Public API:
- get_cell_options()         : 98 cell dropdown options
- get_drug_options()         : 4,684 drug dropdown options
- get_cell_drug_response()   : (cell, drug, dose) → 종합 응답
- get_dose_response_figure() : Plotly dose-response curve
- get_concordance()          : 4-source 검증 dict

Cache 전략: 모듈 로드 시 1회만 parquet 로드, 이후 메모리 lookup.
"""

from .loader import (
    get_cell_options,
    get_drug_options,
    get_cell_drug_response,
)
from .dose_response import get_dose_response_figure
from .concordance import get_concordance

__all__ = [
    "get_cell_options",
    "get_drug_options",
    "get_cell_drug_response",
    "get_dose_response_figure",
    "get_concordance",
]
