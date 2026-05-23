"""
nsclc_ui/data/library/discovery.py

Discovery 4룰 정의 및 카드별 type/reason 계산.

룰:
1. Surprising      = pubmed_hits ≤ 3 AND rank_score 상위 5%
2. Scaffold-novel  = family_size ≤ 5 AND rank_score ≥ 0.5
3. Target-rare     = primary_target 풀 ≤ 5 AND rank_score ≥ 0.5
4. Repurpose-ready = chembl_max_phase_any ≥ 3 AND has_nsclc_trial = False

우선순위: Repurpose-ready > Surprising > Scaffold-novel > Target-rare

v2 변경: NaN 안전 처리 (_safe_int 헬퍼), int() 폭발 방지
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

# 룰 파라미터
SURPRISING_PUBMED_MAX = 3
SURPRISING_RANK_QUANTILE = 0.95

SCAFFOLD_NOVEL_FAMILY_MAX = 5
SCAFFOLD_NOVEL_RANK_MIN = 0.5

TARGET_RARE_POOL_MAX = 5
TARGET_RARE_RANK_MIN = 0.5

REPURPOSE_READY_PHASE_MIN = 3

DISCOVERY_COLOR = {
    "surprising": "violet",
    "scaffold_novel": "teal",
    "target_rare": "orange",
    "repurpose_ready": "blue",
}

DISCOVERY_LABEL_KO = {
    "surprising": "Surprising",
    "scaffold_novel": "Scaffold-novel",
    "target_rare": "Target-rare",
    "repurpose_ready": "Repurpose-ready",
}


# ---- NaN 안전 헬퍼 ----


def _safe_int(value: Any, default: int = 0) -> int:
    """NaN/None/문자열 모두 안전. pd.NA는 pd.isna로 잡힘."""
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class RuleAvailability:
    surprising: bool
    scaffold_novel: bool
    target_rare: bool
    repurpose_ready: bool


def check_rule_availability(df: pd.DataFrame) -> RuleAvailability:
    surprising = (
        "pubmed_hits" in df.columns and df["pubmed_hits"].notna().sum() >= 50
    )
    repurpose = (
        "chembl_max_phase_any" in df.columns
        and "has_nsclc_trial" in df.columns
        and df["chembl_max_phase_any"].notna().sum() >= 100
        and df["has_nsclc_trial"].notna().sum() >= 1000
    )
    return RuleAvailability(
        surprising=surprising,
        scaffold_novel=True,
        target_rare=True,
        repurpose_ready=repurpose,
    )


# ---- 개별 룰 flag (벡터화) ----


def _flag_surprising(df: pd.DataFrame) -> pd.Series:
    if "pubmed_hits" not in df.columns or df["pubmed_hits"].notna().sum() < 50:
        return pd.Series(False, index=df.index)
    rank_threshold = df["rank_score"].quantile(SURPRISING_RANK_QUANTILE)
    # pubmed_hits NaN (no_pref_name) 케이스는 unknown — surprising 판정 제외
    return (
        df["pubmed_hits"].notna()
        & (df["rank_score"] >= rank_threshold)
        & (df["pubmed_hits"].fillna(99999) <= SURPRISING_PUBMED_MAX)
    )


def _flag_scaffold_novel(df: pd.DataFrame) -> pd.Series:
    return (
        (df["family_size"].fillna(99999) <= SCAFFOLD_NOVEL_FAMILY_MAX)
        & (df["rank_score"] >= SCAFFOLD_NOVEL_RANK_MIN)
    )


def _flag_target_rare(df: pd.DataFrame) -> pd.Series:
    target_counts = df["primary_target"].value_counts()
    rare_targets = set(target_counts[target_counts <= TARGET_RARE_POOL_MAX].index)
    return (
        df["primary_target"].isin(rare_targets)
        & (df["rank_score"] >= TARGET_RARE_RANK_MIN)
    )


def _flag_repurpose_ready(df: pd.DataFrame) -> pd.Series:
    has_chembl = "chembl_max_phase_any" in df.columns
    has_ct = "has_nsclc_trial" in df.columns
    if not (has_chembl and has_ct):
        return pd.Series(False, index=df.index)
    return (
        (df["chembl_max_phase_any"].fillna(0) >= REPURPOSE_READY_PHASE_MIN)
        & (df["has_nsclc_trial"].fillna(True) == False)
    )


PRIORITY_ORDER = ["repurpose_ready", "surprising", "scaffold_novel", "target_rare"]


def compute_discovery(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    flags = {
        "surprising": _flag_surprising(df),
        "scaffold_novel": _flag_scaffold_novel(df),
        "target_rare": _flag_target_rare(df),
        "repurpose_ready": _flag_repurpose_ready(df),
    }
    for name, s in flags.items():
        df[f"flag_{name}"] = s

    def pick(row):
        for t in PRIORITY_ORDER:
            if row[f"flag_{t}"]:
                return t
        return None

    df["discovery_type"] = df.apply(pick, axis=1)
    df["discovery_reason"] = df.apply(_make_reason, axis=1)
    return df


def _make_reason(row) -> str:
    """카드 한 줄 reason. NaN 안전."""
    t = row.get("discovery_type")
    if t is None:
        return ""

    if t == "surprising":
        hits = _safe_int(row.get("pubmed_hits"))
        return f"NSCLC 문헌 {hits}건 — prob 상위 5%"

    if t == "scaffold_novel":
        fs = _safe_int(row.get("family_size"))
        return f"단독 scaffold (family_size {fs}) — 신규 화학공간"

    if t == "target_rare":
        target = row.get("primary_target") or "?"
        return f"{target} 타겟 — NSCLC 후보 희소"

    if t == "repurpose_ready":
        phase = _safe_int(row.get("chembl_max_phase_any"))
        return f"다른 적응증 Phase {phase} — NSCLC 임상 미보고"

    return ""


def diagnose(df: pd.DataFrame) -> dict:
    dft = compute_discovery(df)
    avail = check_rule_availability(df)
    return {
        "total_rows": len(dft),
        "rule_availability": {
            "surprising": avail.surprising,
            "scaffold_novel": avail.scaffold_novel,
            "target_rare": avail.target_rare,
            "repurpose_ready": avail.repurpose_ready,
        },
        "flag_counts": {
            "surprising": int(dft["flag_surprising"].sum()),
            "scaffold_novel": int(dft["flag_scaffold_novel"].sum()),
            "target_rare": int(dft["flag_target_rare"].sum()),
            "repurpose_ready": int(dft["flag_repurpose_ready"].sum()),
        },
        "discovery_type_distribution": dft["discovery_type"].value_counts(dropna=False).to_dict(),
    }


if __name__ == "__main__":
    import json
    from nsclc_ui.data.library.loader import load_library_full
    df = load_library_full()
    print(json.dumps(diagnose(df), indent=2, ensure_ascii=False, default=str))
