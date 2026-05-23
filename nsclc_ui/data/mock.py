"""
NSCLC Insight Engine — Dashboard data (E1_tuned champion).
Values are from actual experiment results unless noted.
"""

# ---------------------------------------------------------------------------
# 1. KPI cards  (Overview tab)
# ---------------------------------------------------------------------------
KPI_CARDS = [
    {
        "label": "Champion model",
        "value": "E6",
        "sublabel": "scaffold PR-AUC 0.1253 · +37.3% vs Pre",
        "sublabel_color": "success",
    },
    {
        "label": "Compounds ranked",
        "value": "33,057",
        "sublabel": "948 features · 16 targets · labels_v3 · 5-Modality",
        "sublabel_color": "tertiary",
    },
    {
        "label": "Positives",
        "value": "115",
        "sublabel": "+1 lit-mined (Envonalkib) · UPGRADE_GOLD=0",
        "sublabel_color": "success",
    },
    {
        "label": "Validation",
        "value": "G1+G2",
        "sublabel": "Temporal 15.8% · LODO 29.6% recovery",
        "sublabel_color": "tertiary",
    },
]

# ---------------------------------------------------------------------------
# 2. Ranking table  (Ranking tab – top 20, from ranking_scaffold.csv)
# ---------------------------------------------------------------------------
RANKING_TABLE = [
    {"rank": 1,  "name": "Osimertinib",    "chembl_id": "CHEMBL3353410", "score": 0.832, "std": 0.051, "phase": "IV",  "label": "Positive",  "evidence": "CT·PM"},
    {"rank": 2,  "name": "Bosutinib",      "chembl_id": "CHEMBL288441",  "score": 0.832, "std": 0.060, "phase": "I",   "label": "Positive",  "evidence": "CT·PM"},
    {"rank": 3,  "name": "CHEMBL1173655",  "chembl_id": "CHEMBL1173655", "score": 0.819, "std": 0.064, "phase": "IV",  "label": "Positive",  "evidence": "CT·PM"},
    {"rank": 4,  "name": "CHEMBL4846921",  "chembl_id": "CHEMBL4846921", "score": 0.809, "std": 0.045, "phase": "—",   "label": "Unlabeled", "evidence": "—"},
    {"rank": 5,  "name": "Entrectinib",    "chembl_id": "CHEMBL1983268", "score": 0.796, "std": 0.028, "phase": "IV",  "label": "Positive",  "evidence": "CT·PM"},
    {"rank": 6,  "name": "CHEMBL4448494",  "chembl_id": "CHEMBL4448494", "score": 0.768, "std": 0.110, "phase": "—",   "label": "Unlabeled", "evidence": "—"},
    {"rank": 7,  "name": "Vemurafenib",    "chembl_id": "CHEMBL1229517", "score": 0.761, "std": 0.051, "phase": "III", "label": "Positive",  "evidence": "CT·PM"},
    {"rank": 8,  "name": "CHEMBL3735648",  "chembl_id": "CHEMBL3735648", "score": 0.754, "std": 0.011, "phase": "—",   "label": "Unlabeled", "evidence": "—"},
    {"rank": 9,  "name": "CHEMBL2105717",  "chembl_id": "CHEMBL2105717", "score": 0.741, "std": 0.145, "phase": "III", "label": "Positive",  "evidence": "CT·PM"},
    {"rank": 10, "name": "Brigatinib",     "chembl_id": "CHEMBL3545311", "score": 0.721, "std": 0.021, "phase": "IV",  "label": "Positive",  "evidence": "CT·PM"},
    {"rank": 11, "name": "Crizotinib",     "chembl_id": "CHEMBL601719",  "score": 0.718, "std": 0.086, "phase": "IV",  "label": "Positive",  "evidence": "CT·PM"},
    {"rank": 12, "name": "CHEMBL3116050",  "chembl_id": "CHEMBL3116050", "score": 0.679, "std": 0.080, "phase": "—",   "label": "Unlabeled", "evidence": "—"},
    {"rank": 13, "name": "CHEMBL489058",   "chembl_id": "CHEMBL489058",  "score": 0.649, "std": 0.086, "phase": "—",   "label": "Unlabeled", "evidence": "—"},
    {"rank": 14, "name": "Milciclib",      "chembl_id": "CHEMBL564829",  "score": 0.630, "std": 0.068, "phase": "—",   "label": "Unlabeled", "evidence": "—"},
    {"rank": 15, "name": "CHEMBL3671320",  "chembl_id": "CHEMBL3671320", "score": 0.624, "std": 0.089, "phase": "—",   "label": "Unlabeled", "evidence": "—"},
    {"rank": 16, "name": "CHEMBL5870500",  "chembl_id": "CHEMBL5870500", "score": 0.607, "std": 0.128, "phase": "—",   "label": "Unlabeled", "evidence": "—"},
    {"rank": 17, "name": "Lorlatinib",     "chembl_id": "CHEMBL3286830", "score": 0.583, "std": 0.136, "phase": "IV",  "label": "Positive",  "evidence": "CT·PM"},
    {"rank": 18, "name": "CHEMBL4068839",  "chembl_id": "CHEMBL4068839", "score": 0.582, "std": 0.198, "phase": "—",   "label": "Unlabeled", "evidence": "—"},
    {"rank": 19, "name": "AEE-788",        "chembl_id": "CHEMBL587723",  "score": 0.577, "std": 0.195, "phase": "—",   "label": "Unlabeled", "evidence": "—"},
    {"rank": 20, "name": "CEP-11981",      "chembl_id": "CHEMBL2010872", "score": 0.560, "std": 0.065, "phase": "—",   "label": "Unlabeled", "evidence": "—"},
]

# ---------------------------------------------------------------------------
# 3. Score distribution  (Drug Ranking tab — histogram)
# ---------------------------------------------------------------------------
SCORE_DISTRIBUTION = [31673, 869, 223, 86, 60, 37, 34, 29, 10, 9, 6, 5, 4, 1, 3, 4, 4, 0, 0, 0]

# ---------------------------------------------------------------------------
# 4. SHAP top-5 features for Osimertinib (rank #1)
# ---------------------------------------------------------------------------
SHAP_TOP5 = [
    {"feature": "pic50_mean",        "contribution": 0.737},
    {"feature": "pic50_std",         "contribution": 0.431},
    {"feature": "pic50_egfr_erbb2",  "contribution": 0.212},
    {"feature": "phys_tpsa",         "contribution": 0.192},
    {"feature": "pic50_max",         "contribution": 0.168},
]

# ---------------------------------------------------------------------------
# 5. Scaffold clusters  (Chemistry tab)
# ---------------------------------------------------------------------------
SCAFFOLD_CLUSTERS = [
    {"name": "Pyrimidine-amine", "hits": 14, "total": 89},
    {"name": "Quinazoline",      "hits": 11, "total": 67},
    {"name": "Pyridine-amide",   "hits": 9,  "total": 54},
    {"name": "Indazole",         "hits": 7,  "total": 41},
    {"name": "Benzimidazole",    "hits": 5,  "total": 38},
    {"name": "Macrocycle",       "hits": 3,  "total": 22},
]

# ---------------------------------------------------------------------------
# 6. Predict tab data
# ---------------------------------------------------------------------------
PREDICT_INPUT_EXAMPLE = "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1"

PREDICT_QUICK_EXAMPLES = [
    {"name": "Gefitinib",    "smiles": "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1", "tag": "IN_DOMAIN"},
    {"name": "Osimertinib",  "smiles": "C=CC(=O)Nc1cc(OC)c(Nc2nccc(-c3cn(C)c4ccccc34)n2)cc1N(C)CCN(C)C", "tag": "IN_DOMAIN"},
    {"name": "Aspirin",      "smiles": "CC(=O)Oc1ccccc1C(=O)O",                            "tag": "BORDERLINE"},
    {"name": "Glucose",      "smiles": "OCC1OC(O)C(O)C(O)C1O",                             "tag": "OUT_OF_DOMAIN"},
]

TRIAGE_MOCK_RESPONSE = {
    "decision": "REVIEW_REQUIRED",
    "confidence": 0.62,
    "metrics": {
        "score": 0.724,
        "rank_estimate": 412,
        "rank_total": 33057,
        "ensemble_std": 0.031,
        "xgb_score": 0.741,
        "lgbm_score": 0.707,
        "max_tanimoto": 0.41,
        "ood_status": "BORDERLINE",
        "evidence_ct": 0,
        "evidence_pm": 0,
        "evidence_dc": None,
    },
    "reasons": [
        "score=0.724≥0.70",
        "no_nsclc_evidence",
        "tanimoto_borderline=0.41",
    ],
    "shap": [
        {"feature": "MolWt",   "contribution":  0.18},
        {"feature": "LogP",    "contribution":  0.13},
        {"feature": "NumArom", "contribution":  0.09},
        {"feature": "FracCSP3","contribution": -0.06},
        {"feature": "TPSA",    "contribution": -0.03},
    ],
    "neighbors": [
        {"name": "Gefitinib",  "chembl": "CHEMBL939",     "tanimoto": 0.41, "label": "Positive"},
        {"name": "Erlotinib",  "chembl": "CHEMBL553",     "tanimoto": 0.38, "label": "Positive"},
        {"name": "Lapatinib",  "chembl": "CHEMBL554",     "tanimoto": 0.34, "label": "Unlabeled"},
        {"name": "Vandetanib", "chembl": "CHEMBL24828",   "tanimoto": 0.31, "label": "Positive"},
        {"name": "Icotinib",   "chembl": "CHEMBL1241995", "tanimoto": 0.29, "label": "Positive"},
    ],
    "interpretation": (
        "Input compound matches known EGFR inhibitor scaffold (quinazoline). "
        "4 of 5 nearest neighbors are NSCLC-positive."
    ),
    "inchikey": "XGALLCVXEZPNRQ-UHFFFAOYSA-N",
}

TRIAGE_DECISION_COLORS = {
    "LIKELY_ACTIVE":           "success",
    "REVIEW_REQUIRED":         "warning",
    "OUT_OF_DOMAIN":           "danger",
    "NO_EVIDENCE_FOR_UPGRADE": "secondary",
}

# ---------------------------------------------------------------------------
# 7. Candidate Explorer — Adjudication log
# ---------------------------------------------------------------------------
ADJUDICATION_LOG = [
    {"timestamp": "2026-04-22 18:42", "compound": "Envonalkib",    "chembl": "CHEMBL5095063", "decision": "Confirm", "reason": "Phase III NSCLC, NCT04009317 확인",       "user": "YJ"},
    {"timestamp": "2026-04-22 18:30", "compound": "Tepotinib",     "chembl": "CHEMBL3989908", "decision": "Defer",   "reason": "MET 데이터 추가 검토 필요",               "user": "YJ"},
    {"timestamp": "2026-04-22 17:55", "compound": "Adagrasib",     "chembl": "CHEMBL4594356", "decision": "Confirm", "reason": "KRAS G12C 2L NSCLC 승인",                "user": "YJ"},
    {"timestamp": "2026-04-22 17:12", "compound": "Staurosporine", "chembl": "CHEMBL47",      "decision": "Block",   "reason": "범용 kinase 시약, 임상 부적합",           "user": "YJ"},
    {"timestamp": "2026-04-22 16:48", "compound": "Lapatinib",     "chembl": "CHEMBL554",     "decision": "Defer",   "reason": "EGFR/HER2 — NSCLC 적응증 추가검증",       "user": "YJ"},
    {"timestamp": "2026-04-22 16:20", "compound": "Vandetanib",    "chembl": "CHEMBL24828",   "decision": "Confirm", "reason": "RET inhibitor, NSCLC label 부합",         "user": "YJ"},
    {"timestamp": "2026-04-22 15:58", "compound": "Icotinib",      "chembl": "CHEMBL1241995", "decision": "Confirm", "reason": "EGFR, China-approved NSCLC",               "user": "YJ"},
]

ADJUDICATION_DECISION_COLORS = {
    "Confirm": "success",
    "Defer":   "warning",
    "Block":   "danger",
    "Reject":  "danger",
}

# ---------------------------------------------------------------------------
# 8. Model Card  (E1_tuned)
# ---------------------------------------------------------------------------
MODEL_CARD = {
    "overview": {
        "name": "E6",
        "algo": "XGBoost + LightGBM ensemble (alpha=0.6)",
        "n_features": 948,
        "n_train": 33057,
        "n_positive": 115,
        "label_version": "labels_v3",
        "targets": "16 (KEGG hsa05223 pathway, 9→16 expansion)",
    },
    "performance": [
        {"metric": "scaffold PR-AUC",   "pre": 0.1007, "final": 0.1161, "delta": "+14.6%"},
        {"metric": "stratified PR-AUC", "pre": 0.1413, "final": 0.1501, "delta": "+6.2%"},
        {"metric": "AUROC (scaffold)",  "pre": 0.7865, "final": 0.7936, "delta": "+0.9%"},
        {"metric": "NDCG@20",           "pre": 0.2194, "final": 0.2409, "delta": "+9.8%"},
    ],
    "experiments": [
        {"name": "E-1 Target expansion (9→16)",   "result": "Positive", "delta": "+14.6%", "summary": "KEGG pathway 분석 → druggable 타겟 확장. Champion 교체."},
        {"name": "E-3 Selectivity index",          "result": "Absorbed", "delta": "—",      "summary": "E-1에 non-orthogonal로 흡수."},
        {"name": "E-4 Mordred descriptors",        "result": "Negative", "delta": "−21.9%", "summary": "681개 2D descriptor 추가 → information dilution."},
        {"name": "G-3 STRING PPI features",        "result": "Neutral",  "delta": "+0.17%", "summary": "18개 PPI 피처 추가 → 노이즈 수준 변동."},
        {"name": "F-1 Literature mining",          "result": "Confirmed","delta": "0",      "summary": "82개 검색, UPGRADE_GOLD=0. Phase3+ 커버리지 확인."},
        {"name": "G-1 Temporal validation",        "result": "Positive", "delta": "—",      "summary": "recall@top1% 15.8% (3/19). Scaffold leakage 13/19 공시."},
        {"name": "G-2 LODO validation",            "result": "Positive", "delta": "—",      "summary": "recovery@top1% 29.6%. ρ(rank, pic50_mean)=−0.867."},
    ],
    "axes": [
        {"name": "Target expansion (KEGG)",        "result": "Positive", "summary": "9→16 타겟. pIC50 파생 피처 강화. +14.6%."},
        {"name": "Label expansion (Silver)",       "result": "Negative", "summary": "Silver-C(DepMap) 주범. Viability ≠ IC50 feature space."},
        {"name": "Learning method (PU/Focal)",     "result": "Negative", "summary": "Bagging PU −66.6%, Focal −21.2%. 오염률 <0.1%."},
        {"name": "Descriptor expansion (Mordred)", "result": "Negative", "summary": "681 descriptors → dilution. Gate3 FAIL."},
        {"name": "Literature mining",              "result": "Positive", "summary": "Envonalkib 1건 + Phase3+ 커버리지 확인."},
        {"name": "HPO retune",                     "result": "Positive", "summary": "E0→E0_tuned +13.1%, E0_tuned→E1_tuned +14.6%."},
    ],
    "hpo_diff": [
        {"param": "max_depth (XGB)",        "baseline": 9,    "tuned": 4},
        {"param": "scale_pos_weight (XGB)", "baseline": 178,  "tuned": 26.16},
        {"param": "num_leaves (LGBM)",      "baseline": 61,   "tuned": 14},
        {"param": "learning_rate (XGB)",    "baseline": 0.1,  "tuned": 0.0144},
        {"param": "n_estimators (XGB)",     "baseline": 500,  "tuned": 250},
        {"param": "n_estimators (LGBM)",    "baseline": 500,  "tuned": 1050},
    ],
    "protocol": {
        "splits": "Scaffold CV (5-fold) + Stratified eval",
        "seed": "42, 123, 7 (3-seed)",
        "metric": "pr_auc (unweighted) — sample_weight 비균일로 가중 비교 무효",
        "n_seeds": 3,
    },
    "negative_results": [
        {"name": "Silver-C (DepMap)",   "reason": "Viability 측정 ≠ ChEMBL IC50 feature space"},
        {"name": "PU Learning",         "reason": "오염률 <0.1%로 baseline이 이미 처리 중"},
        {"name": "Focal Loss",          "reason": "쉬운 샘플 과적합, scaffold 일반화 실패 (−21.2%)"},
        {"name": "Mordred descriptors", "reason": "939→1620 피처 확장 → information dilution (−21.9%)"},
        {"name": "STRING PPI",          "reason": "18 피처 추가, +0.17% (노이즈 수준)"},
    ],
    "validation": {
        "temporal": {
            "description": "2018년 이전 데이터로 학습 → 2019+ 승인약 예측",
            "recall_top1pct": "15.8% (3/19)",
            "top3": ["Mirdametinib (rank 16)", "Avutometinib (rank 73)", "Repotrectinib (rank 98)"],
            "scaffold_leakage": "13/19 — 발표에서 명시",
        },
        "lodo": {
            "description": "115 positive 하나씩 빼고 재발견 검증",
            "recovery_top1pct": "29.6% (34/115)",
            "enrichment": "~30× vs random",
            "rho_pic50_mean": -0.867,
            "rho_rank_std": 0.918,
            "key_insight": "pIC50 신호 강도가 재발견 성공의 핵심 변수",
        },
    },
}

# ---------------------------------------------------------------------------
# 9. About page
# ---------------------------------------------------------------------------
KNOWN_LIMITATIONS = [
    "PR-AUC 0.1161 < 목표 0.30 — 피처 확장만으로 구조적 한계. 다중 소스 통합으로 +14.6% 달성.",
    "SHAP 해석은 XGBoost 단독 기준. 성능 보고는 앙상블 기준 (proxy 공시).",
    "라벨 커버리지 갭: CT.gov 미등록 약물(예: 중국 임상)은 원리적으로 포착 불가.",
    "Scaffold split은 RDKit Murcko 기반. Pre와 fold 배정이 다를 수 있음.",
    "Silver-C (DepMap) 통합 실패 — viability와 IC50 feature space 불일치.",
    "PU Learning 무효 확인 — 오염률 <0.1%에서 추가 이득 없음.",
    "Focal Loss 무효 확인 — scaffold 일반화 실패.",
    "Mordred descriptors 추가 실패 — information dilution (−21.9%).",
    "LODO 재발견 성능은 pIC50 신호 강도에 의존 (ρ=−0.87). 일반화 아닌 재발견으로 해석.",
    "G-1 scaffold leakage 13/19 — Temporal validation 결과 해석 시 필수 공시.",
    '32,942 Negative는 "확정 Negative"가 아니라 "근거 미확인 Unlabeled" (post-hoc 발견).',
]

DATA_SOURCES = [
    {"name": "ChEMBL",             "version": "v34",      "license": "CC BY-SA 3.0",  "use": "활성 데이터 + 화합물 구조 (16 targets)"},
    {"name": "ClinicalTrials.gov", "version": "v2 API",   "license": "Public domain", "use": "임상시험 라벨 (Gold Positive)"},
    {"name": "KEGG",               "version": "hsa05223", "license": "Academic",      "use": "NSCLC pathway → 타겟 확장 (9→16)"},
    {"name": "PubMed",             "version": "E-utils",  "license": "Public",        "use": "문헌 마이닝 (라벨 보강 + F-1 검증)"},
    {"name": "STRING",             "version": "v12",      "license": "CC BY 4.0",     "use": "PPI 네트워크 (G-3, 중립 결과)"},
    {"name": "DrugCentral",        "version": "2023",     "license": "CC BY-SA 4.0",  "use": "약물명 ↔ ChEMBL crosswalk"},
    {"name": "OpenTargets",        "version": "v23.12",   "license": "CC0 1.0",       "use": "Silver-B 라벨 (시도 → drop)"},
    {"name": "DepMap PRISM",       "version": "23Q4",     "license": "CC BY 4.0",     "use": "Silver-C 라벨 (시도 → drop)"},
]

VERSION_HISTORY = [
    {"version": "Pre v3",       "date": "2026-04-16", "summary": "Chemistry-only baseline. PR-AUC 0.10. Top-5 4/5 NSCLC 근거."},
    {"version": "Final E0",     "date": "2026-04-17", "summary": "Pre 재현 + 평가 프로토콜 freeze (scaffold+stratified, 3-seed)."},
    {"version": "E0+Silver",    "date": "2026-04-18", "summary": "Silver-B/C 통합 시도. Multi-seed 후 Negative 확인."},
    {"version": "E0+PU/Focal",  "date": "2026-04-19", "summary": "Bagging PU/Weighted PU/Focal 시도. 전부 Negative."},
    {"version": "E0+Lit",       "date": "2026-04-20", "summary": "PubMed 마이닝 → Envonalkib 1건 승격 (114→115)."},
    {"version": "E0_tuned",     "date": "2026-04-21", "summary": "HPO 재튜닝. scaffold +13.1%. 1차 Champion."},
    {"version": "E1_tuned",     "date": "2026-04-22", "summary": "KEGG 9→16 타겟 확장 + HPO. +14.6%. Final Champion."},
    {"version": "E4_mordred",   "date": "2026-04-23", "summary": "Mordred 681 descriptor. −21.9%. 미채택."},
    {"version": "G-1 Temporal", "date": "2026-04-22", "summary": "recall@top1% 15.8%. Leakage 13/19 공시."},
    {"version": "G-2 LODO",     "date": "2026-04-23", "summary": "recovery@top1% 29.6%. ρ(pic50_mean)=−0.867."},
    {"version": "F-1 LitMining","date": "2026-04-23", "summary": "82개 검색, UPGRADE_GOLD=0. 커버리지 확인."},
    {"version": "G-3 PPI",      "date": "2026-04-24", "summary": "+0.17% (중립). 미채택."},
]

# ---------------------------------------------------------------------------
# 10. Experiment comparison table + Model Card limitations
# ---------------------------------------------------------------------------
EXPERIMENT_TABLE = [
    {"exp": "E0 (Pre 재현)",          "pr_auc": "0.0896",         "delta": "—",       "verdict": "baseline"},
    {"exp": "E0_tuned (HPO)",         "pr_auc": "0.1013±0.0121",  "delta": "+13.1%",  "verdict": "✅"},
    {"exp": "E1_tuned (Champion)",    "pr_auc": "0.1161±0.0123",  "delta": "+14.6%",  "verdict": "✅ Champion"},
    {"exp": "E4 Mordred",             "pr_auc": "—",              "delta": "−21.9%",  "verdict": "❌"},
    {"exp": "G-3 PPI",                "pr_auc": "—",              "delta": "+0.17%",  "verdict": "중립"},
    {"exp": "Silver-C (DepMap)",      "pr_auc": "—",              "delta": "−18.1%",  "verdict": "❌"},
    {"exp": "Bagging PU",             "pr_auc": "0.0325",         "delta": "−66.6%",  "verdict": "❌"},
]

MODEL_CARD_LIMITATIONS = [
    "PR-AUC 0.1161은 절대값으로 낮음. 극심한 불균형(0.34% Positive) 하에서의 상대적 개선에 의미.",
    "SHAP은 XGB seed=42 단독 proxy. 앙상블 전체 SHAP이 아님.",
    "Temporal validation scaffold leakage 13/19 — 순수 예측력은 3/19에 근거.",
    "새 분자 예측 시 pIC50 피처 미사용 → 구조 피처만으로 예측.",
    "NSCLC ≠ SCLC. 본 모델은 NSCLC 타겟만 학습.",
]


# ---------------------------------------------------------------------------
# 11. Variant-aware Evidence (representative cases)
# ---------------------------------------------------------------------------
VARIANT_EVIDENCE = {
    "CHEMBL3353410": {
        "variant": "EGFR T790M",
        "response": "강한 반응 (ORR 71%)",
        "source": "AURA3 trial, NEJM 2017",
    },
    "CHEMBL939": {
        "variant": "EGFR del19/L858R",
        "response": "1차 TKI 표준치료",
        "source": "IPASS trial, NEJM 2009",
    },
    "CHEMBL1229517": {
        "variant": "BRAF V600E",
        "response": "ORR 42% (NSCLC)",
        "source": "VE-BASKET, Lancet Oncol 2015",
    },
    "CHEMBL4535757": {
        "variant": "KRAS G12C",
        "response": "ORR 37.1%",
        "source": "CodeBreaK 100, NEJM 2021",
    },
    "CHEMBL3286830": {
        "variant": "ALK/ROS1 fusion",
        "response": "ORR 90% (1L ALK+)",
        "source": "CROWN trial, NEJM 2020",
    },
}

# Variant evidence by gene (for target-based lookup)
VARIANT_EVIDENCE_BY_GENE = [
    {"gene": "EGFR", "variant": "L858R", "frequency": "39% of EGFR-mutant NSCLC",
     "drugs": ["Osimertinib", "Erlotinib", "Gefitinib"], "evidence_level": "A",
     "source": "CIViC EID:883, OncoKB Level 1"},
    {"gene": "EGFR", "variant": "Exon 19 deletion", "frequency": "45% of EGFR-mutant NSCLC",
     "drugs": ["Osimertinib", "Afatinib"], "evidence_level": "A",
     "source": "CIViC EID:879, OncoKB Level 1"},
    {"gene": "KRAS", "variant": "G12C", "frequency": "13% of NSCLC",
     "drugs": ["Sotorasib", "Adagrasib"], "evidence_level": "A",
     "source": "CIViC EID:7765, OncoKB Level 1"},
    {"gene": "ALK", "variant": "EML4-ALK fusion", "frequency": "3-7% of NSCLC",
     "drugs": ["Alectinib", "Lorlatinib", "Crizotinib"], "evidence_level": "A",
     "source": "CIViC EID:550, OncoKB Level 1"},
    {"gene": "BRAF", "variant": "V600E", "frequency": "1-2% of NSCLC",
     "drugs": ["Dabrafenib + Trametinib"], "evidence_level": "A",
     "source": "CIViC EID:6955, OncoKB Level 1"},
]

# D2: Cell line map (expanded)
CELL_LINE_MAP_V2 = {
    "EGFR": {"lines": ["PC-9", "HCC827", "H1975"], "note": "PC-9: del19 sensitive, H1975: T790M resistant"},
    "KRAS": {"lines": ["A549", "H358", "SW1573"], "note": "A549: G12S, H358: G12C"},
    "ALK": {"lines": ["H3122", "SNU-2535"], "note": "H3122: EML4-ALK v1 fusion"},
    "ROS1": {"lines": ["HCC78"], "note": "HCC78: SLC34A2-ROS1 fusion"},
    "MET": {"lines": ["EBC-1", "H1993"], "note": "EBC-1: MET amplified"},
    "BRAF": {"lines": ["HCC364", "CALU-6"], "note": "HCC364: V600E"},
    "RET": {"lines": ["LC-2/ad", "TT"], "note": "LC-2/ad: CCDC6-RET fusion"},
    "NTRK1": {"lines": ["KM-12"], "note": "KM-12: TPM3-NTRK1 (CRC, NSCLC proxy)"},
    "ERBB2": {"lines": ["NCI-H2170", "Calu-3"], "note": "H2170: HER2 amplified"},
    "PIK3CA": {"lines": ["H1047", "MCF7"], "note": "Downstream PI3K pathway"},
    "CDK4": {"lines": ["A549", "H460"], "note": "CDK4/6 inhibitor sensitive"},
    "CDK6": {"lines": ["A549", "H460"], "note": "CDK4/6 inhibitor sensitive"},
}
