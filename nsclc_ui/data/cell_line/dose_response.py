"""
nsclc_ui.data.cell_line.dose_response

Dose-response curve 생성.

§1.4 정직 narrative:
- PRISM은 single-dose (대부분 2.5 μM 부근 단일 측정점)
- 따라서 실측 1점 + Hill simulated curve (slope=1, top=0, bottom=lfc_min)
- GDSC2 cross-source 28 drug는 실제 LN_IC50 fit 값으로 보강 가능 (concordance.py에서 처리)
- Plotly figure dict 반환 (Dash callback Output에 그대로 전달)
"""

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from .loader import _load_prism, _load_a_v3_predictions

_BASE = Path(__file__).resolve().parents[3]
GDSC2_LONG = _BASE / "data/derived/gdsc2_nsclc_long.parquet"

# Dose grid (1 nM ~ 10 μM, 50 points log scale)
DOSE_GRID_LOG = np.linspace(np.log10(0.001), np.log10(10), 50)  # μM
DOSE_GRID = 10 ** DOSE_GRID_LOG


def _hill_curve(dose_um, ec50_um, hill_slope=1.0, top=0.0, bottom=-3.0):
    """
    Hill equation: viability % at given dose.
    Returns lfc-like values (top=0, bottom=lfc_min).

    Y = bottom + (top - bottom) / (1 + (ec50 / dose)^hill_slope)
    Note: low dose → top, high dose → bottom (viability 감소 = lfc 음수)
    """
    dose_um = np.asarray(dose_um, dtype=np.float64)
    dose_um = np.maximum(dose_um, 1e-6)  # log 0 방지
    ratio = dose_um / ec50_um
    return bottom + (top - bottom) / (1 + ratio ** hill_slope)


def _estimate_ec50_from_lfc(lfc_obs, dose_obs_um):
    """
    단일 측정점 (lfc, dose)에서 EC50 추정.

    가정: Hill slope=1, top=0, bottom=-3.0 (typical strong response)
    Y = (-3) * 1 / (1 + ec50/dose)  →  solve for ec50

    lfc_obs = bottom * 1 / (1 + ec50/dose)
    lfc_obs / bottom = dose / (dose + ec50)
    ec50 = dose * (bottom/lfc_obs - 1)
    """
    if lfc_obs is None or pd.isna(lfc_obs) or dose_obs_um is None or pd.isna(dose_obs_um):
        return None
    bottom = -3.0
    if lfc_obs >= 0:  # 효과 없음 → EC50 매우 크다고 표시
        return 100.0  # 100 μM (out of range)
    if lfc_obs <= bottom * 0.99:  # 거의 saturated
        return dose_obs_um * 0.01  # 작은 값
    ratio = bottom / lfc_obs
    if ratio <= 1:
        return 100.0
    ec50 = dose_obs_um * (ratio - 1)
    return float(np.clip(ec50, 0.0001, 100.0))  # μM range


@lru_cache(maxsize=1)
def _load_gdsc2():
    """GDSC2 long parquet (있으면)."""
    if GDSC2_LONG.exists():
        return pd.read_parquet(GDSC2_LONG)
    return None


def get_dose_response_figure(depmap_id: str, broad_id: str, current_dose_um: float = None):
    """
    Plotly figure dict 생성.

    Layers:
    1. PRISM observed point (1 dot, with error bar if available)
    2. A v3 predicted point (1 dot, same dose as PRISM)
    3. Hill simulated curve (dashed line, from PRISM lfc)
    4. EC50 vertical line + label
    5. Current dose vertical line + label (사용자 input)
    6. GDSC2 IC50 marker (있으면, cross-source 28 drug)

    Returns:
        dict: Plotly figure dict (data + layout)
    """
    from .loader import get_cell_drug_response

    resp = get_cell_drug_response(depmap_id, broad_id, current_dose_um)
    if resp.get("error"):
        return _empty_figure(resp["error"])

    prism_dose = resp.get("prism_dose")
    prism_lfc = resp.get("prism_lfc_obs")
    a_pred = resp.get("a_pred_lfc")
    drug_name = resp.get("drug_name", "")
    ccle_name = resp.get("ccle_name", "")

    data = []
    annotations = []

    # Hill simulated curve (from PRISM observed)
    if prism_lfc is not None and not pd.isna(prism_lfc) and prism_dose:
        ec50_um = _estimate_ec50_from_lfc(prism_lfc, prism_dose)
        if ec50_um is not None and 0.0001 < ec50_um < 100:
            curve_y = _hill_curve(DOSE_GRID, ec50_um, hill_slope=1.0, top=0.0, bottom=-3.0)
            data.append({
                "x": (DOSE_GRID * 1000).tolist(),  # μM → nM for display
                "y": curve_y.tolist(),
                "type": "scatter",
                "mode": "lines",
                "name": "Hill simulated",
                "line": {"color": "#7F77DD", "width": 2, "dash": "dash"},
                "hovertemplate": "Dose %{x:.1f} nM<br>lfc %{y:.2f}<extra></extra>",
            })

            # EC50 vertical line
            ec50_nm = ec50_um * 1000
            data.append({
                "x": [ec50_nm, ec50_nm],
                "y": [-3.5, 0.5],
                "type": "scatter",
                "mode": "lines",
                "name": "EC50",
                "line": {"color": "#5DCAA5", "width": 1.5, "dash": "dot"},
                "showlegend": False,
                "hoverinfo": "skip",
            })
            annotations.append({
                "x": np.log10(ec50_nm),
                "y": 0.3,
                "text": f"EC50 (Hill sim) ≈ {ec50_nm:.0f} nM",
                "showarrow": False,
                "font": {"color": "#5DCAA5", "size": 11},
                "xref": "x",
                "yref": "y",
            })

    # PRISM observed point
    if prism_lfc is not None and not pd.isna(prism_lfc) and prism_dose:
        data.append({
            "x": [prism_dose * 1000],  # μM → nM
            "y": [prism_lfc],
            "type": "scatter",
            "mode": "markers",
            "name": "PRISM 실측",
            "marker": {"color": "#85B7EB", "size": 12, "line": {"color": "#fff", "width": 1.5}},
            "hovertemplate": "PRISM<br>Dose %{x:.1f} nM<br>lfc %{y:.3f}<extra></extra>",
        })

    # A v3 predicted point (PRISM과 같은 dose)
    if a_pred is not None and not pd.isna(a_pred) and prism_dose:
        data.append({
            "x": [prism_dose * 1000],
            "y": [a_pred],
            "type": "scatter",
            "mode": "markers",
            "name": "A 모델 예측",
            "marker": {"color": "#7F77DD", "size": 12, "symbol": "diamond",
                       "line": {"color": "#fff", "width": 1.5}},
            "hovertemplate": "A v3 예측<br>Dose %{x:.1f} nM<br>lfc %{y:.3f}<extra></extra>",
        })

    # Current dose vertical line (사용자 input)
    if current_dose_um and current_dose_um > 0:
        current_dose_nm = current_dose_um * 1000
        data.append({
            "x": [current_dose_nm, current_dose_nm],
            "y": [-3.5, 0.5],
            "type": "scatter",
            "mode": "lines",
            "name": "현재 농도",
            "line": {"color": "#F0997B", "width": 1.5, "dash": "dot"},
            "showlegend": False,
            "hoverinfo": "skip",
        })

    layout = {
        "xaxis": {
            "type": "log",
            "title": "Dose (nM)",
            "showgrid": True,
            "gridcolor": "rgba(255,255,255,0.05)",
            "color": "#a0a8b8",
            "titlefont": {"size": 11, "color": "#a0a8b8"},
            "tickfont": {"size": 10, "color": "#6b7689"},
        },
        "yaxis": {
            "title": "log fold-change (viability)",
            "range": [-3.5, 0.5],
            "showgrid": True,
            "gridcolor": "rgba(255,255,255,0.05)",
            "color": "#a0a8b8",
            "titlefont": {"size": 11, "color": "#a0a8b8"},
            "tickfont": {"size": 10, "color": "#6b7689"},
            "zeroline": True,
            "zerolinecolor": "rgba(255,255,255,0.1)",
        },
        "annotations": annotations,
        "showlegend": True,
        "legend": {
            "orientation": "h",
            "x": 0.02,
            "y": -0.18,
            "font": {"size": 10, "color": "#a0a8b8"},
            "bgcolor": "rgba(0,0,0,0)",
        },
        "margin": {"t": 10, "b": 60, "l": 50, "r": 20},
        "plot_bgcolor": "rgba(0,0,0,0)",
        "paper_bgcolor": "rgba(0,0,0,0)",
        "hovermode": "closest",
        "height": 280,
    }

    if not data:
        return _empty_figure("no measurable response data")

    return {"data": data, "layout": layout}


def _empty_figure(message: str = "no data"):
    """Empty placeholder figure with message."""
    return {
        "data": [],
        "layout": {
            "annotations": [{
                "text": message,
                "x": 0.5, "y": 0.5,
                "xref": "paper", "yref": "paper",
                "showarrow": False,
                "font": {"size": 12, "color": "#6b7689"},
            }],
            "xaxis": {"visible": False},
            "yaxis": {"visible": False},
            "plot_bgcolor": "rgba(0,0,0,0)",
            "paper_bgcolor": "rgba(0,0,0,0)",
            "height": 280,
            "margin": {"t": 10, "b": 10, "l": 10, "r": 10},
        }
    }
