"""
briefing.py
사전 브리핑 카드용 통합 lookup. Pathway Map LLM 패널 상단 카드 데이터 조립.

3종 카드:
  1. pathway 카드 — 경로 안 표적 N개, 평균 rank_score, 활성 화합물 수
  2. target 카드 — gene 한 개의 화합물 분포 + essentiality + 관련 SHAP feature
  3. drug 카드 — 약물 한 개의 rank_score + 신뢰도 + scaffold + 가장 가까운 이웃

오류 모델: 데이터 없으면 빈 dict 또는 '(데이터 없음)'. 예외 throw 안 함.
모든 함수 lru_cache — UI 반복 클릭 안전.
"""
from __future__ import annotations
import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional
import pandas as pd

from nsclc_ui.data.loaders import (
    load_kegg_targets,
    load_compound_target_map,
    load_smiles_map,
    load_scaffold_info_derived,
    load_activity_cliffs_derived,
    load_essentiality_derived,
    get_compound_detail,
    normalize_compound_id,
)
import json
from nsclc_ui.data.feature_dict import get_feature_label

logger = logging.getLogger(__name__)

# ============================================================
# Paths
# ============================================================
_BASE = Path(__file__).resolve().parents[2]  # final/
_RESULTS_E6 = _BASE / "results" / "e6"
_DERIVED = _BASE / "data" / "derived"

CHAMPION_ID = "E6"
CHAMPION_DIR = _RESULTS_E6

# ============================================================
# Pathway data (KEGG topology) — pathway_map.py와 동일 소스
# ============================================================
_PATHWAY_JSON_PATH = _BASE / "data" / "derived" / "pathway_data.json"


@lru_cache(maxsize=1)
def _load_pathway_data() -> dict:
    """pathway_data.json 로드. 없으면 빈 dict."""
    if not _PATHWAY_JSON_PATH.exists():
        logger.warning(f"pathway_data.json not found: {_PATHWAY_JSON_PATH}")
        return {}
    try:
        with open(_PATHWAY_JSON_PATH) as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"failed to load pathway_data: {e}")
        return {}



# ============================================================
# 1. Champion metrics (E6 summary.csv)
# ============================================================
@lru_cache(maxsize=1)
def load_champion_metrics() -> dict:
    """E6 summary.csv 일괄 → dict. UI Model Card / 신뢰도 등급에서 사용."""
    summary_path = CHAMPION_DIR / "summary.csv"
    if not summary_path.exists():
        logger.warning(f"champion summary not found: {summary_path}")
        return {"experiment_id": CHAMPION_ID, "available": False}

    df = pd.read_csv(summary_path)
    out = {"experiment_id": CHAMPION_ID, "available": True}
    for _, row in df.iterrows():
        key = f"{row['protocol']}_{row['metric']}"
        out[key] = {"mean": float(row["mean"]), "std": float(row["std"])}
    return out


# ============================================================
# 2. SHAP top features
# ============================================================
@lru_cache(maxsize=4)
def load_shap_top(top_k: int = 10) -> list[dict]:
    """E6 shap_top.csv 읽어서 한국어 라벨 attach. top_k 개 반환."""
    shap_path = CHAMPION_DIR / "shap_top.csv"
    if not shap_path.exists():
        logger.warning(f"shap_top not found: {shap_path}")
        return []

    df = pd.read_csv(shap_path).head(top_k)
    out = []
    for _, row in df.iterrows():
        meta = get_feature_label(row["feature"])
        out.append({
            "rank": int(row["rank"]),
            "feature": row["feature"],
            "mean_abs_shap": float(row["mean_abs_shap"]),
            "kr_label": meta["kr_label"],
            "definition": meta["definition_1line"],
            "category": meta["category"],
            "source": meta["source"],
        })
    return out


# ============================================================
# 3. Confidence grade
# ============================================================
def get_confidence_grade(rank_score: Optional[float], family_size: Optional[int]) -> dict:
    """
    신뢰도 3단계:
      ●●● (high): rank_score > 0.7 AND family_size >= 3
      ●●○ (mid):  둘 중 하나만 충족
      ●○○ (low):  둘 다 미충족
    """
    rs = rank_score if rank_score is not None else 0.0
    fs = family_size if family_size is not None else 0

    rs_ok = rs > 0.7
    fs_ok = fs >= 3

    if rs_ok and fs_ok:
        return {"grade": "●●●", "level": "high", "label": "고신뢰", "color": "green"}
    elif rs_ok or fs_ok:
        return {"grade": "●●○", "level": "mid", "label": "중간", "color": "yellow"}
    else:
        return {"grade": "●○○", "level": "low", "label": "참고용", "color": "gray"}


# ============================================================
# 4. Pathway card
# ============================================================
@lru_cache(maxsize=8)
def get_briefing_for_pathway(pathway_id: str) -> dict:
    """KEGG pathway → 카드 데이터. pathway_data.json 사용 (pathway_map.py와 동일 소스)."""
    data = _load_pathway_data()
    pw = data.get("pathways", {}).get(pathway_id)
    if not pw:
        return {"available": False, "id": pathway_id, "error": "pathway not found"}

    nodes = pw.get("nodes", [])
    edges = pw.get("edges", [])

    # gene + group(complex) 노드만 (pathway_map.py:730 패턴)
    gene_nodes = [n for n in nodes if n.get("type") in ("gene", "group")]
    target_nodes = [n for n in gene_nodes if n.get("is_project_target")]

    # symbol 추출: KEGG 노드 label에 alias가 콤마로 다 붙어있어 첫 번째만 사용.
    # project_target은 우선 노출 (NSCLC 핵심 표적).
    def _first_symbol(node) -> str:
        sym = node.get("gene_symbol") or node.get("label") or node.get("name") or ""
        # 첫 번째 token만 (alias 제거)
        first = str(sym).split(",")[0].split()[0] if sym else ""
        return first.strip().upper()

    project_gene_symbols = []
    seen = set()
    for n in target_nodes:
        s = _first_symbol(n)
        if s and s not in seen:
            project_gene_symbols.append(s)
            seen.add(s)

    other_gene_symbols = []
    for n in gene_nodes:
        if n.get("is_project_target"):
            continue
        s = _first_symbol(n)
        if s and s not in seen:
            other_gene_symbols.append(s)
            seen.add(s)

    gene_symbols = set(project_gene_symbols) | set(other_gene_symbols)

    # 이 pathway gene을 primary로 하는 약물 카운트
    cmap = load_compound_target_map()
    drugs_by_gene: dict[str, list] = {g: [] for g in gene_symbols}
    for cid, info in cmap.items():
        primary = (info.get("primary_target") or "").upper()
        if primary in drugs_by_gene:
            drugs_by_gene[primary].append(cid)

    n_targets_with_drugs = sum(1 for v in drugs_by_gene.values() if v)
    total_drugs = sum(len(v) for v in drugs_by_gene.values())

    return {
        "available": True,
        "id": pathway_id,
        "name": pw.get("pathway_name", pathway_id),
        "n_nodes": len(nodes),
        "n_edges": len(edges),
        "n_genes": len(gene_nodes),
        "n_project_targets": len(target_nodes),
        "n_targets_with_drugs": n_targets_with_drugs,
        "total_drugs": total_drugs,
        "project_targets": project_gene_symbols,
        "sample_other_genes": sorted(other_gene_symbols)[:10],
    }


# ============================================================
# 5. Target card
# ============================================================
@lru_cache(maxsize=64)
def get_briefing_for_target(gene_symbol: str) -> dict:
    """gene → 카드 데이터 (essentiality + 약물 분포 + 관련 SHAP)."""
    gene = gene_symbol.upper().strip()

    # 약물 매핑
    cmap = load_compound_target_map()
    matched_drugs = [cid for cid, info in cmap.items() if (info.get("primary_target") or "").upper() == gene]
    n_drugs = len(matched_drugs)

    # essentiality
    ess_dict = load_essentiality_derived()
    ess = ess_dict.get(gene, {})

    # 관련 SHAP feature (이름에 _active 들어가는 거 + gene 직접 매핑은 raw에 없음)
    # 일반적으로 crispr/tcga _active feature가 모든 active 표적의 통계라 직접 매핑 어려움
    # → SHAP top10 중 crispr/tcga 카테고리만 노출하고 "표적 평균치" 명시
    shap_top = load_shap_top(top_k=10)
    related_shap = [s for s in shap_top if s["category"] in ("crispr", "tcga")]

    return {
        "available": True,
        "gene_symbol": gene,
        "n_drugs": n_drugs,
        "essentiality": {
            "is_essential": bool(ess.get("is_essential", False)),
            "mean_score": float(ess.get("mean_score", 0.0)) if ess else None,
            "n_cell_lines": int(ess.get("n_cell_lines", 0)) if ess else 0,
        },
        "related_shap": related_shap[:3],
    }


# ============================================================
# 6. Drug card
# ============================================================
@lru_cache(maxsize=128)
def get_briefing_for_drug(compound_id: str) -> dict:
    """약물 ID → 카드 데이터 (rank/신뢰도/scaffold/이웃/임상단계/SMILES)."""
    cid = normalize_compound_id(compound_id)

    # raw detail (loaders.py)
    detail = get_compound_detail(cid) or {}
    rank_score = detail.get("rank_score")
    prob = detail.get("prob")
    total_score = detail.get("total_score")

    # primary_target/MoA: cmap이 진짜 출처. detail은 ranking 결과만 있어 비어있을 수 있음.
    cmap = load_compound_target_map()
    cmap_entry = cmap.get(cid, {})
    primary_target = cmap_entry.get("primary_target") or detail.get("primary_target") or ""
    all_targets = cmap_entry.get("all_targets") or ""
    moa = cmap_entry.get("mechanism_of_action") or detail.get("mechanism_of_action") or ""
    target_source = cmap_entry.get("target_source_type") or ""

    # SMILES
    smiles_map = load_smiles_map()
    smiles = smiles_map.get(cid, "")

    # scaffold
    scaffold_dict = load_scaffold_info_derived()
    sc_info = scaffold_dict.get(cid, {})
    family_size = sc_info.get("family_size")
    scaffold_smiles = sc_info.get("scaffold_smiles", "")

    # closest neighbor (activity_cliffs는 cliffs만 있음. 일반 이웃은 별도 로직 필요 — TODO Stretch)
    cliffs = load_activity_cliffs_derived()
    cliff_partners = [
        (c.get("compound_a"), c.get("compound_b"), c.get("similarity"))
        for c in cliffs
        if c.get("compound_a") == cid or c.get("compound_b") == cid
    ]

    # confidence
    conf = get_confidence_grade(rank_score, family_size)

    # max_phase (try/except — fetch 안 끝났으면 None)
    max_phase = _safe_lookup_max_phase(cid)

    return {
        "available": bool(detail),
        "compound_id": cid,
        "primary_target": primary_target,
        "all_targets": all_targets,
        "mechanism_of_action": moa,
        "target_source": target_source,
        "smiles": smiles,
        "rank_score": rank_score,
        "prob": prob,
        "total_score": total_score,
        "scaffold_smiles": scaffold_smiles,
        "family_size": family_size,
        "confidence": conf,
        "cliff_partners": cliff_partners[:3],
        "max_phase": max_phase,
    }


# ============================================================
# Helper: max_phase fallback
# ============================================================
@lru_cache(maxsize=1)
def _load_max_phase_map() -> dict:
    """ChEMBL fetch 결과 — 없으면 빈 dict."""
    p = _DERIVED / "chembl_max_phase.csv"
    if not p.exists():
        logger.warning(f"max_phase data not yet available: {p}")
        return {}
    df = pd.read_csv(p)
    return dict(zip(df["compound_id"].astype(str), df["max_phase"]))


def _safe_lookup_max_phase(cid: str) -> Optional[int]:
    m = _load_max_phase_map()
    val = m.get(cid)
    if val is None or pd.isna(val):
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


# ============================================================
# Cache invalidation (UI 핫리로드용)
# ============================================================
def clear_caches():
    load_champion_metrics.cache_clear()
    load_shap_top.cache_clear()
    get_briefing_for_pathway.cache_clear()
    get_briefing_for_target.cache_clear()
    get_briefing_for_drug.cache_clear()
    _load_max_phase_map.cache_clear()
