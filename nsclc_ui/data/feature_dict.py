"""
feature_dict.py
SHAP feature 한국어 사전 (E6 챔피언 모델 기준).

Pathway Map / Drug Ranking / Model Card에서 import.
"""
from __future__ import annotations

FEATURE_DICT: dict[str, dict] = {
    # activity
    "pic50_mean": {"kr_label": "활성 강도 평균", "definition_1line": "분석 표적들에 대한 평균 약물 활성 강도", "category": "activity", "source": "ChEMBL pIC50"},
    "pic50_max": {"kr_label": "최고 활성 강도", "definition_1line": "이 약물이 가장 강하게 작용한 표적의 활성 강도", "category": "activity", "source": "ChEMBL pIC50"},
    "pic50_std": {"kr_label": "활성 강도 편차", "definition_1line": "표적별 약물 활성 차이가 얼마나 큰지", "category": "activity", "source": "ChEMBL pIC50"},
    "pic50_entropy": {"kr_label": "표적 다양성", "definition_1line": "여러 표적에 골고루 작용하는지 한 곳에 집중하는지", "category": "activity", "source": "ChEMBL pIC50"},
    "pic50_n_targets": {"kr_label": "실험된 표적 수", "definition_1line": "이 약물이 실제로 실험된 표적 개수", "category": "activity", "source": "ChEMBL pIC50"},
    # structure_fp
    "morgan_428": {"kr_label": "구조 패턴 #428", "definition_1line": "분자 안 특정 부분 구조의 존재 여부", "category": "structure_fp", "source": "RDKit Morgan FP"},
    "morgan_807": {"kr_label": "구조 패턴 #807", "definition_1line": "분자 안 특정 부분 구조의 존재 여부", "category": "structure_fp", "source": "RDKit Morgan FP"},
    "morgan_849": {"kr_label": "구조 패턴 #849", "definition_1line": "분자 안 특정 부분 구조의 존재 여부", "category": "structure_fp", "source": "RDKit Morgan FP"},
    # physchem
    "phys_tpsa": {"kr_label": "극성 표면적", "definition_1line": "분자 표면 중 극성 부분 넓이 (세포막 통과력 지표)", "category": "physchem", "source": "RDKit Descriptors"},
    "phys_mw": {"kr_label": "분자량", "definition_1line": "약물 분자의 무게 (경구 흡수성 지표)", "category": "physchem", "source": "RDKit Descriptors"},
    "phys_logp": {"kr_label": "지용성 (logP)", "definition_1line": "기름 vs 물 분배 비율 (지방·세포막 친화도)", "category": "physchem", "source": "RDKit Descriptors"},
    "phys_hbd": {"kr_label": "수소결합 공여자", "definition_1line": "분자가 수소결합을 줄 수 있는 부위 개수", "category": "physchem", "source": "RDKit Descriptors"},
    "phys_hba": {"kr_label": "수소결합 수용자", "definition_1line": "분자가 수소결합을 받을 수 있는 부위 개수", "category": "physchem", "source": "RDKit Descriptors"},
    "phys_rotatable_bonds": {"kr_label": "회전 가능 결합", "definition_1line": "분자가 얼마나 잘 휘어지는지 나타내는 지표", "category": "physchem", "source": "RDKit Descriptors"},
    "phys_aromatic_rings": {"kr_label": "방향족 고리 수", "definition_1line": "벤젠 같은 평평한 고리의 개수", "category": "physchem", "source": "RDKit Descriptors"},
    "phys_qed": {"kr_label": "약물성 점수 (QED)", "definition_1line": "전반적으로 약처럼 보이는지 0~1 점수", "category": "physchem", "source": "RDKit Descriptors"},
    # crispr
    "crispr_ess_min_active": {"kr_label": "최고 의존 표적", "definition_1line": "약물 표적 중 NSCLC 세포가 가장 의존하는 표적", "category": "crispr", "source": "DepMap 26Q1 NSCLC"},
    "crispr_ess_mean_active": {"kr_label": "표적 의존도 평균", "definition_1line": "약물 표적들에 대한 NSCLC 세포 의존도 평균", "category": "crispr", "source": "DepMap 26Q1 NSCLC"},
    "crispr_ess_n_essential": {"kr_label": "의존 표적 수", "definition_1line": "약물 표적 중 NSCLC 세포 생존에 중요한 표적 수", "category": "crispr", "source": "DepMap 26Q1 NSCLC"},
    # tcga
    "tcga_expr_max_active": {"kr_label": "최고 발현 표적", "definition_1line": "약물 표적 중 NSCLC 환자에서 가장 많이 발현된 표적", "category": "tcga", "source": "TCGA-LUAD/LUSC RNA-seq"},
    "tcga_expr_mean_active": {"kr_label": "표적 발현량 평균", "definition_1line": "이 약물 표적들의 NSCLC 환자 평균 발현량", "category": "tcga", "source": "TCGA-LUAD/LUSC RNA-seq"},
    "tcga_expr_std_active": {"kr_label": "환자별 발현 차이", "definition_1line": "환자마다 표적 발현량이 얼마나 다른지", "category": "tcga", "source": "TCGA-LUAD/LUSC RNA-seq"},
    # ambiguity
    "pic50_gap": {"kr_label": "표적 선택성 차이", "definition_1line": "1순위와 2순위 표적의 활성 강도 차이", "category": "ambiguity", "source": "ChEMBL pIC50"},
    "is_ambiguous": {"kr_label": "표적 모호성", "definition_1line": "주 표적이 명확한지 (gap < 0.5면 모호)", "category": "ambiguity", "source": "ChEMBL pIC50"},
}

CATEGORY_META: dict[str, dict] = {
    "activity": {"kr": "결합 활성", "color": "blue", "icon": "🔬"},
    "structure_fp": {"kr": "분자 구조", "color": "green", "icon": "⚛"},
    "physchem": {"kr": "물리화학 성질", "color": "orange", "icon": "💊"},
    "crispr": {"kr": "유전자 의존도", "color": "red", "icon": "🧬"},
    "tcga": {"kr": "환자 발현량", "color": "purple", "icon": "🏥"},
    "ambiguity": {"kr": "선택성·모호성", "color": "gray", "icon": "❓"},
}


def get_feature_label(feature_name: str) -> dict:
    if feature_name in FEATURE_DICT:
        return FEATURE_DICT[feature_name]
    if feature_name.startswith("morgan_"):
        try:
            bit = int(feature_name.split("_")[1])
            return {"kr_label": f"구조 패턴 #{bit}", "definition_1line": "분자 안 특정 부분 구조의 존재 여부", "category": "structure_fp", "source": "RDKit Morgan FP"}
        except (IndexError, ValueError):
            pass
    if feature_name.startswith("phys_"):
        return {"kr_label": feature_name.replace("phys_", ""), "definition_1line": "분자의 물리화학적 성질 (RDKit 계산)", "category": "physchem", "source": "RDKit Descriptors"}
    return {"kr_label": feature_name, "definition_1line": "(설명 미등록)", "category": "unknown", "source": ""}


def get_category_meta(category: str) -> dict:
    return CATEGORY_META.get(category, {"kr": category, "color": "gray", "icon": "•"})
