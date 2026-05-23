"""
nsclc_ui/data/library/cards.py

Library mode UI contract.

Public API (키로 import 대상):
- load_library_cards()        -> list[dict]
- filter_cards(cards, state)  -> tuple[list[dict], int]
- paginate(cards, page, size) -> list[dict]
- compute_facet_counts(cards, state) -> dict

내부:
- loader + discovery 결과를 lru_cache로 1회 계산
- DataFrame → list[dict] 변환도 1회만 (process-level)

filter_state 키 (모두 optional):
- phase: list[str]              ["A", "B", "C", "D", "E", "X"]
- nsclc_status: list[str]       ["D", "E"]
- cross_source_only: bool
- target_query: str             substring (대소문자 무관)
- scaffold_max_family: int|None  family_size ≤ N
- discovery_types: list[str]    ["surprising", "scaffold_novel", "target_rare", "repurpose_ready"]
- sort_by: str                  "rank_score" | "confidence" | "novelty"

논리:
- 같은 그룹 옵션끼리 OR
- 그룹 간 AND
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import pandas as pd

from nsclc_ui.data.library.discovery import (
    DISCOVERY_COLOR,
    DISCOVERY_LABEL_KO,
    compute_discovery,
)
from nsclc_ui.data.library.loader import load_library_full

PAGE_SIZE_DEFAULT = 6

# Phase chip 라벨 (final_category prefix → 한글)
PHASE_LABEL = {
    "A": "A 승인",
    "B": "B 임상중",
    "C": "C 재창출",
    "D": "D 비항암",
    "E": "E 연구용",
    "X": "X 전임상",
}


# ---- 내부 (DataFrame 레벨) ----


@lru_cache(maxsize=1)
def _full_df() -> pd.DataFrame:
    """loader + discovery 1회 계산."""
    return compute_discovery(load_library_full())


def _confidence_dots(std: Any) -> int:
    """rank_score_std → 신뢰도 점 1-3."""
    if pd.isna(std):
        return 1
    if std <= 0.01:
        return 3
    if std <= 0.03:
        return 2
    return 1


def _row_to_card(row: pd.Series) -> dict[str, Any]:
    cid = str(row["compound_id"])
    cat = row.get("category") or "X"
    dt = row.get("discovery_type")

    discovery_chip = None
    if dt:
        discovery_chip = {
            "label": DISCOVERY_LABEL_KO.get(dt, dt),
            "color": DISCOVERY_COLOR.get(dt),
        }

    targets = row.get("targets_list") or []
    if not isinstance(targets, list):
        targets = []

    return {
        "compound_id": cid,
        "name": row.get("pref_name") or cid,
        "phase_chip": {
            "label": PHASE_LABEL.get(cat, cat),
            "category": cat,
        },
        "rank_score": float(row.get("rank_score") or 0.0),
        "rank_score_std": float(row.get("rank_score_std") or 0.0),
        "confidence_dots": _confidence_dots(row.get("rank_score_std")),
        "targets": targets[:5],
        "primary_target": row.get("primary_target"),
        "scaffold_smiles": row.get("scaffold_smiles"),
        "family_size": int(row.get("family_size") or 0),
        "smiles": row.get("canonical_smiles"),
        "x_s_verified": bool(row.get("x_s_verified") or False),
        "nsclc_status": cat if cat in ("D", "E") else None,
        "discovery_type": dt,
        "discovery_chip": discovery_chip,
        "reason": row.get("discovery_reason") or "",
        "actions": {
            "detail_href": f"/candidate-explorer?cid={cid}",
            "pathway_href": f"/pathway?cid={cid}",
            "cell_line_href": f"/simulator?cid={cid}&mode=cell-line",
        },
    }


# ---- Public API ----


@lru_cache(maxsize=1)
def load_library_cards() -> list[dict[str, Any]]:
    """33,057 카드 dict. 앱 시작 시 1회 변환, 이후 캐시."""
    df = _full_df()
    return [_row_to_card(r) for _, r in df.iterrows()]


def filter_cards(
    cards: list[dict[str, Any]],
    filter_state: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    """filter_state 적용 → (filtered, count)."""
    out = cards

    phases = filter_state.get("phase") or []
    if phases:
        out = [c for c in out if c["phase_chip"]["category"] in phases]

    statuses = filter_state.get("nsclc_status") or []
    if statuses:
        out = [c for c in out if c.get("nsclc_status") in statuses]

    if filter_state.get("cross_source_only"):
        out = [c for c in out if c["x_s_verified"]]

    q = (filter_state.get("target_query") or "").strip().upper()
    if q:
        out = [
            c for c in out
            if any(q in (t or "").upper() for t in c.get("targets", []))
        ]

    fmax = filter_state.get("scaffold_max_family")
    if fmax is not None:
        out = [c for c in out if 0 < c.get("family_size", 0) <= fmax]

    dtypes = filter_state.get("discovery_types") or []
    if dtypes:
        out = [c for c in out if c.get("discovery_type") in dtypes]

    sort_by = filter_state.get("sort_by") or "rank_score"
    if sort_by == "rank_score":
        out = sorted(out, key=lambda c: -c["rank_score"])
    elif sort_by == "confidence":
        out = sorted(out, key=lambda c: (-c["confidence_dots"], -c["rank_score"]))
    elif sort_by == "novelty":
        out = sorted(
            out,
            key=lambda c: (c.get("family_size") or 99999, -c["rank_score"]),
        )

    return out, len(out)


def paginate(
    cards: list[dict[str, Any]],
    page: int,
    page_size: int = PAGE_SIZE_DEFAULT,
) -> list[dict[str, Any]]:
    page = max(1, int(page or 1))
    start = (page - 1) * page_size
    return cards[start:start + page_size]


def compute_facet_counts(
    cards: list[dict[str, Any]],
    filter_state: dict[str, Any],
) -> dict[str, Any]:
    """
    Faceted standard:
    각 그룹의 카운트는 *그 그룹만 제외* 한 상태에서 다른 필터 적용 후 계산.
    같은 그룹 내 다른 옵션 선택 시 카운트 0 안 됨.
    """
    total = len(cards)
    _, filtered_n = filter_cards(cards, filter_state)

    def _without(group: str) -> list[dict]:
        partial = {k: v for k, v in filter_state.items() if k != group}
        sub, _ = filter_cards(cards, partial)
        return sub

    counts: dict[str, Any] = {
        "total": total,
        "filtered": filtered_n,
    }

    sub = _without("phase")
    counts["phase"] = {
        cat: sum(1 for c in sub if c["phase_chip"]["category"] == cat)
        for cat in ["A", "B", "C", "D", "E", "X"]
    }

    sub = _without("nsclc_status")
    counts["nsclc_status"] = {
        s: sum(1 for c in sub if c.get("nsclc_status") == s)
        for s in ["D", "E"]
    }

    sub = _without("cross_source_only")
    counts["cross_source"] = sum(1 for c in sub if c["x_s_verified"])

    sub = _without("discovery_types")
    counts["discovery_types"] = {
        t: sum(1 for c in sub if c.get("discovery_type") == t)
        for t in ["surprising", "scaffold_novel", "target_rare", "repurpose_ready"]
    }

    return counts


# ---- 진단 ----


def diagnose() -> dict[str, Any]:
    cards = load_library_cards()
    counts = compute_facet_counts(cards, {})
    sample = cards[0] if cards else {}
    return {
        "n_cards": len(cards),
        "facet_counts": counts,
        "sample_card_keys": list(sample.keys()),
        "sample_card": sample,
        "discovery_type_dist": {
            (t or "None"): sum(1 for c in cards if c.get("discovery_type") == t)
            for t in [
                "surprising", "scaffold_novel", "target_rare", "repurpose_ready", None
            ]
        },
    }


if __name__ == "__main__":
    import json
    print(json.dumps(diagnose(), indent=2, ensure_ascii=False, default=str))
