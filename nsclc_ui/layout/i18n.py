"""
NSCLC Insight Engine — i18n (ko/en).
Technical terms stay English in both: SHAP, scaffold, pIC50, PR-AUC, rank_score, Tanimoto, Murcko, PAINS, Lipinski.
"""

T = {
    "ko": {
        "total_compounds": "전체 화합물",
        "multi_modality": "다중 모달리티 (≥2)",
        "positives": "양성",
        "pipeline": "파이프라인",
        "evidence": "근거",
        "experiment_plan": "실험 계획",
        "actionable_variants": "Actionable Variants",
        "essentiality": "Target Essentiality",
        "confirm": "✓ 확정",
        "review": "? 검토",
        "block": "✕ 차단",
        "decision_copilot": "Decision Copilot (auto-draft)",
        "risk_radar": "Risk Radar",
        "modality_comparison": "모달리티 비교",
        "model_summary": "Model Summary",
        "experiment_history": "Experiment History",
        "disclaimer": "연구용 후보 우선순위화 도구입니다. 임상 의사결정에 직접 사용할 수 없습니다.",
        "filter": "필터",
        "compounds": "화합물",
        "top_rank_score": "최고 rank_score",
        "scaffolds": "Scaffold 수",
        "search_placeholder": "ChEMBL ID 검색...",
    },
    "en": {
        "total_compounds": "Total Compounds",
        "multi_modality": "Multi-modality (≥2)",
        "positives": "Positives",
        "pipeline": "Pipeline",
        "evidence": "Evidence",
        "experiment_plan": "Experiment Plan",
        "actionable_variants": "Actionable Variants",
        "essentiality": "Target Essentiality",
        "confirm": "✓ Confirm",
        "review": "? Review",
        "block": "✕ Block",
        "decision_copilot": "Decision Copilot (auto-draft)",
        "risk_radar": "Risk Radar",
        "modality_comparison": "Modality Comparison",
        "model_summary": "Model Summary",
        "experiment_history": "Experiment History",
        "disclaimer": "Research prioritization tool. Not for clinical decision-making.",
        "filter": "Filter",
        "compounds": "Compounds",
        "top_rank_score": "Top rank_score",
        "scaffolds": "Scaffolds",
        "search_placeholder": "Search ChEMBL ID...",
    },
}

DEFAULT_LANG = "ko"


def t(key: str, lang: str = DEFAULT_LANG) -> str:
    """Translation helper. Falls back to en → key."""
    return T.get(lang, T["en"]).get(key, T["en"].get(key, key))
