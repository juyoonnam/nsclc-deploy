"""22 MCP Tool Schema Registry.

모든 tool의 JSON Schema 정의. AgentCore Gateway 등록 및 Strands Supervisor tool binding에 공용.
7개 Lambda 카테고리 × 22 tools (D-5 update: knowledge_base 2→3, Bedrock KB 추가).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolSchema:
    """MCP tool 스키마 정의."""

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] = field(default_factory=dict)
    lambda_name: str = ""
    category: str = ""


# ═══════════════════════════════════════════════════════════════════
# 1. schema_discovery_lambda (3 tools)
# ═══════════════════════════════════════════════════════════════════

list_data_sources = ToolSchema(
    name="list_data_sources",
    description="전체 데이터 소스 카탈로그 요약. 사용 가능한 데이터셋 목록과 메타데이터를 반환한다.",
    input_schema={
        "type": "object",
        "properties": {},
        "required": [],
    },
    output_schema={
        "type": "object",
        "properties": {
            "data_sources": {"type": "array", "items": {"type": "object"}},
            "count": {"type": "integer"},
        },
    },
    lambda_name="schema_discovery_lambda",
    category="schema_discovery",
)

get_table_schema = ToolSchema(
    name="get_table_schema",
    description="특정 데이터 소스의 전체 스키마 및 메타데이터를 반환한다.",
    input_schema={
        "type": "object",
        "properties": {
            "source_id": {
                "type": "string",
                "description": "데이터 소스 ID (list_data_sources에서 확인)",
            },
        },
        "required": ["source_id"],
    },
    lambda_name="schema_discovery_lambda",
    category="schema_discovery",
)

count_records = ToolSchema(
    name="count_records",
    description="특정 데이터 소스의 레코드 수를 반환한다. 선택적 필터 적용 가능.",
    input_schema={
        "type": "object",
        "properties": {
            "source_id": {
                "type": "string",
                "description": "데이터 소스 ID",
            },
            "filter_": {
                "type": "object",
                "description": "선택적 필터 조건 (key-value)",
                "default": None,
            },
        },
        "required": ["source_id"],
    },
    lambda_name="schema_discovery_lambda",
    category="schema_discovery",
)

# ═══════════════════════════════════════════════════════════════════
# 2. drug_library_lambda (4 tools)
# ═══════════════════════════════════════════════════════════════════

search_drugs = ToolSchema(
    name="search_drugs",
    description="약물 라이브러리 검색. 이름, 타겟 유전자, 카테고리(A~X)로 필터링한다. 33,057개 약물 풀.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "검색어 (약물 이름 또는 SMILES)",
            },
            "target": {
                "type": "string",
                "description": "타겟 유전자명 (예: EGFR, KRAS)",
            },
            "category": {
                "type": "string",
                "description": "카테고리 필터 (A=NSCLC승인, B=임상진행, C=재창출후보, D=Tier1비항암, E=ATC없음, X=전임상)",
                "enum": ["A", "B", "C", "D", "E", "X"],
            },
            "limit": {
                "type": "integer",
                "description": "최대 반환 수",
                "default": 20,
            },
        },
        "required": [],
    },
    lambda_name="drug_library_lambda",
    category="drug_library",
)

get_drug_metadata = ToolSchema(
    name="get_drug_metadata",
    description="약물 상세 메타데이터 조회. drug_id, InChIKey, 또는 이름으로 검색. 타겟 정보 포함.",
    input_schema={
        "type": "object",
        "properties": {
            "drug_id": {
                "type": "string",
                "description": "약물 compound ID",
            },
            "inchikey": {
                "type": "string",
                "description": "InChIKey (14자 prefix 매칭)",
            },
            "name": {
                "type": "string",
                "description": "약물 이름 (fuzzy match)",
            },
        },
        "required": [],
    },
    lambda_name="drug_library_lambda",
    category="drug_library",
)

check_in_library = ToolSchema(
    name="check_in_library",
    description="Phase A 정책 핵심: 화합물이 라이브러리에 존재하는지 판단. in_library=False면 champion 모델 사용 금지.",
    input_schema={
        "type": "object",
        "properties": {
            "inchikey": {
                "type": "string",
                "description": "InChIKey (14자 prefix 매칭)",
            },
            "smiles": {
                "type": "string",
                "description": "SMILES 문자열 (RDKit으로 InChIKey 변환)",
            },
            "name": {
                "type": "string",
                "description": "약물 이름 (fuzzy match fallback)",
            },
        },
        "required": [],
    },
    lambda_name="drug_library_lambda",
    category="drug_library",
)

compute_tanimoto = ToolSchema(
    name="compute_tanimoto",
    description="외부 SMILES와 라이브러리 약물 간 Morgan FP Tanimoto 유사도 top-K 계산. max < 0.3이면 거부 권고.",
    input_schema={
        "type": "object",
        "properties": {
            "smiles_query": {
                "type": "string",
                "description": "비교할 SMILES 문자열",
            },
            "top_k": {
                "type": "integer",
                "description": "반환할 유사 약물 수",
                "default": 5,
            },
        },
        "required": ["smiles_query"],
    },
    lambda_name="drug_library_lambda",
    category="drug_library",
)

# ═══════════════════════════════════════════════════════════════════
# 3. model_inference_lambda (4 tools)
# ═══════════════════════════════════════════════════════════════════

get_oof_prediction = ToolSchema(
    name="get_oof_prediction",
    description="Champion E6 모델의 OOF(Out-of-Fold) prediction 조회. 198,342 rows frozen 데이터.",
    input_schema={
        "type": "object",
        "properties": {
            "drug_id": {
                "type": "string",
                "description": "약물 compound ID",
            },
        },
        "required": ["drug_id"],
    },
    lambda_name="model_inference_lambda",
    category="model_inference",
)

get_shap_explanation = ToolSchema(
    name="get_shap_explanation",
    description="SHAP top-K 피처 기여도 (XGB seed42 proxy). 약물이 후보로 선정된 근거를 설명한다.",
    input_schema={
        "type": "object",
        "properties": {
            "drug_id": {
                "type": "string",
                "description": "약물 compound ID",
            },
            "top_k": {
                "type": "integer",
                "description": "반환할 상위 피처 수",
                "default": 10,
            },
        },
        "required": ["drug_id"],
    },
    lambda_name="model_inference_lambda",
    category="model_inference",
)

get_ensemble_probability = ToolSchema(
    name="get_ensemble_probability",
    description="E6 ensemble 30 model 가중 평균 확률. ⚠️ in_library=True일 때만 허용. 외부 화합물은 POLICY_REJECT_EXTERNAL 에러.",
    input_schema={
        "type": "object",
        "properties": {
            "drug_id": {
                "type": "string",
                "description": "약물 compound ID",
            },
            "in_library": {
                "type": "boolean",
                "description": "라이브러리 포함 여부 (check_in_library 결과). False면 정책 거부.",
            },
        },
        "required": ["drug_id", "in_library"],
    },
    lambda_name="model_inference_lambda",
    category="model_inference",
)

predict_cell_response = ToolSchema(
    name="predict_cell_response",
    description="Model A v3 세포주 반응 예측 (lfc regression). CCLE PCA96 + 2695 features.",
    input_schema={
        "type": "object",
        "properties": {
            "drug_id": {
                "type": "string",
                "description": "약물 compound ID",
            },
            "cell_line": {
                "type": "string",
                "description": "세포주 이름 (예: H1975, A549)",
            },
        },
        "required": ["drug_id", "cell_line"],
    },
    lambda_name="model_inference_lambda",
    category="model_inference",
)

# ═══════════════════════════════════════════════════════════════════
# 4. patient_lambda (3 tools)
# ═══════════════════════════════════════════════════════════════════

get_patient_mutation = ToolSchema(
    name="get_patient_mutation",
    description="TCGA 환자 mutation 조회. 환자별/유전자별/전체 집계. 942명 × 20 actionable genes.",
    input_schema={
        "type": "object",
        "properties": {
            "patient_id": {
                "type": "string",
                "description": "환자 ID (TCGA barcode)",
            },
            "gene": {
                "type": "string",
                "description": "유전자명 (예: EGFR, KRAS)",
            },
        },
        "required": [],
    },
    lambda_name="patient_lambda",
    category="patient",
)

match_patient_drugs = ToolSchema(
    name="match_patient_drugs",
    description="환자 mutation profile → 라이브러리 약물 매칭. patient_id 또는 mutation_profile 중 하나 필수.",
    input_schema={
        "type": "object",
        "properties": {
            "patient_id": {
                "type": "string",
                "description": "환자 ID (TCGA barcode)",
            },
            "mutation_profile": {
                "type": "object",
                "description": "mutation profile dict (예: {\"EGFR\": \"L858R+T790M\"})",
            },
        },
        "required": [],
    },
    lambda_name="patient_lambda",
    category="patient",
)

list_actionable_genes = ToolSchema(
    name="list_actionable_genes",
    description="NSCLC 임상 가이드라인 기준 20개 actionable gene 리스트 반환.",
    input_schema={
        "type": "object",
        "properties": {},
        "required": [],
    },
    lambda_name="patient_lambda",
    category="patient",
)

# ═══════════════════════════════════════════════════════════════════
# 5. drug_cell_response_lambda (3 tools)
# ═══════════════════════════════════════════════════════════════════

get_drug_response = ToolSchema(
    name="get_drug_response",
    description="약물-세포주 반응(lfc) 조회. 현재 PRISM NSCLC 세포주 반응만 지원. lfc < 0 = viability 감소.",
    input_schema={
        "type": "object",
        "properties": {
            "drug_id": {
                "type": "string",
                "description": "약물 compound ID 또는 이름",
            },
            "cell_line": {
                "type": "string",
                "description": "세포주 이름 (미지정 시 모든 NSCLC 세포주)",
            },
            "source": {
                "type": "string",
                "description": "데이터 소스. 현재 prism만 지원.",
                "enum": ["prism"],
                "default": "prism",
            },
        },
        "required": ["drug_id"],
    },
    lambda_name="drug_cell_response_lambda",
    category="drug_cell_response",
)

get_cell_line_meta = ToolSchema(
    name="get_cell_line_meta",
    description="세포주 메타데이터 조회. mutation profile, tissue, subtype 정보.",
    input_schema={
        "type": "object",
        "properties": {
            "cell_line": {
                "type": "string",
                "description": "세포주 이름 (예: H1975, HCC827, A549)",
            },
        },
        "required": ["cell_line"],
    },
    lambda_name="drug_cell_response_lambda",
    category="drug_cell_response",
)

cross_source_lookup = ToolSchema(
    name="cross_source_lookup",
    description="PRISM ∩ GDSC2 28개 cross-source 약물의 일치도 비교.",
    input_schema={
        "type": "object",
        "properties": {
            "drug_id": {
                "type": "string",
                "description": "특정 약물 ID (미지정 시 전체 28개 요약)",
            },
        },
        "required": [],
    },
    lambda_name="drug_cell_response_lambda",
    category="drug_cell_response",
)

# ═══════════════════════════════════════════════════════════════════
# 6. knowledge_base_lambda (3 tools — D-5 update: Bedrock KB 추가)
# ═══════════════════════════════════════════════════════════════════

search_pubmed = ToolSchema(
    name="search_pubmed",
    description="PubMed E-utilities 기반 논문 검색 (esearch + esummary). NSCLC 관련 최신 논문을 relevance 순으로 반환.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "검색 쿼리 (자연어)",
            },
            "top_k": {
                "type": "integer",
                "description": "반환할 논문 수",
                "default": 5,
            },
            "year_min": {
                "type": "integer",
                "description": "최소 출판 연도",
                "default": 2020,
            },
        },
        "required": ["query"],
    },
    lambda_name="knowledge_base_lambda",
    category="knowledge_base",
)

extract_paper_evidence = ToolSchema(
    name="extract_paper_evidence",
    description="특정 PMID 논문에서 질문 관련 근거 문장을 추출한다. PubMed efetch abstract + keyword overlap 기반.",
    input_schema={
        "type": "object",
        "properties": {
            "pmid": {
                "type": "string",
                "description": "PubMed ID",
            },
            "question": {
                "type": "string",
                "description": "추출할 근거의 맥락 질문 (선택)",
            },
        },
        "required": ["pmid"],
    },
    lambda_name="knowledge_base_lambda",
    category="knowledge_base",
)

search_clinical_knowledge_base = ToolSchema(
    name="search_clinical_knowledge_base",
    description=(
        "Bedrock KB retrieve — 임상 grounding chunks 검색 (정책 8). "
        "FDA labels(osimertinib/gefitinib/sotorasib) + ESMO PAGA 2024 + PMC FLAURA2. "
        "임상 단정(FDA approval, dosing, contraindication, efficacy 수치 ORR/PFS/HR/CI, "
        "guideline strength I-A/I-B) 직전엔 반드시 호출. 응답에 source_uri + page citation 표기 필수."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "임상 검색 쿼리 (예: 'osimertinib EGFR T790M dosing', 'sotorasib KRAS G12C contraindication')",
            },
            "max_results": {
                "type": "integer",
                "description": "반환할 chunk 수 (1-10)",
                "default": 5,
            },
        },
        "required": ["query"],
    },
    lambda_name="knowledge_base_lambda",
    category="knowledge_base",
)

# ═══════════════════════════════════════════════════════════════════
# 7. guardrail_lambda (2 tools)
# ═══════════════════════════════════════════════════════════════════

check_scope = ToolSchema(
    name="check_scope",
    description="Phase A scope check. in-library + Tanimoto → champion/analog_only/reject 모드 결정.",
    input_schema={
        "type": "object",
        "properties": {
            "in_library": {
                "type": "boolean",
                "description": "라이브러리 포함 여부 (check_in_library 결과)",
            },
            "max_tanimoto": {
                "type": "number",
                "description": "최대 Tanimoto 유사도 (외부 화합물일 때 필수)",
            },
        },
        "required": ["in_library"],
    },
    lambda_name="guardrail_lambda",
    category="guardrail",
)

validate_clinical_claim = ToolSchema(
    name="validate_clinical_claim",
    description="LLM 응답의 단정/처방 단어 검증. 금지 용어 탐지 및 hedge term 존재 확인.",
    input_schema={
        "type": "object",
        "properties": {
            "claim": {
                "type": "string",
                "description": "검증할 텍스트 (LLM 응답 전문 또는 일부)",
            },
        },
        "required": ["claim"],
    },
    lambda_name="guardrail_lambda",
    category="guardrail",
)


# ═══════════════════════════════════════════════════════════════════
# Registry & Helpers
# ═══════════════════════════════════════════════════════════════════

TOOL_REGISTRY: dict[str, ToolSchema] = {
    # schema_discovery (3)
    "list_data_sources": list_data_sources,
    "get_table_schema": get_table_schema,
    "count_records": count_records,
    # drug_library (4)
    "search_drugs": search_drugs,
    "get_drug_metadata": get_drug_metadata,
    "check_in_library": check_in_library,
    "compute_tanimoto": compute_tanimoto,
    # model_inference (4)
    "get_oof_prediction": get_oof_prediction,
    "get_shap_explanation": get_shap_explanation,
    "get_ensemble_probability": get_ensemble_probability,
    "predict_cell_response": predict_cell_response,
    # patient (3)
    "get_patient_mutation": get_patient_mutation,
    "match_patient_drugs": match_patient_drugs,
    "list_actionable_genes": list_actionable_genes,
    # drug_cell_response (3)
    "get_drug_response": get_drug_response,
    "get_cell_line_meta": get_cell_line_meta,
    "cross_source_lookup": cross_source_lookup,
    # knowledge_base (3)  ← D-5 update
    "search_pubmed": search_pubmed,
    "extract_paper_evidence": extract_paper_evidence,
    "search_clinical_knowledge_base": search_clinical_knowledge_base,
    # guardrail (2)
    "check_scope": check_scope,
    "validate_clinical_claim": validate_clinical_claim,
}

CATEGORIES = {
    "schema_discovery": {
        "lambda_name": "schema_discovery_lambda",
        "description": "데이터 카탈로그 및 스키마 탐색",
        "tools": ["list_data_sources", "get_table_schema", "count_records"],
    },
    "drug_library": {
        "lambda_name": "drug_library_lambda",
        "description": "약물 라이브러리 검색 및 Phase A 정책 (33,057개)",
        "tools": ["search_drugs", "get_drug_metadata", "check_in_library", "compute_tanimoto"],
    },
    "model_inference": {
        "lambda_name": "model_inference_lambda",
        "description": "Champion E6 모델 추론 및 SHAP 해석",
        "tools": ["get_oof_prediction", "get_shap_explanation", "get_ensemble_probability", "predict_cell_response"],
    },
    "patient": {
        "lambda_name": "patient_lambda",
        "description": "TCGA 환자 mutation 및 약물 매칭 (942명 × 20 genes)",
        "tools": ["get_patient_mutation", "match_patient_drugs", "list_actionable_genes"],
    },
    "drug_cell_response": {
        "lambda_name": "drug_cell_response_lambda",
        "description": "세포주 약물 반응 (PRISM/GDSC2 lfc)",
        "tools": ["get_drug_response", "get_cell_line_meta", "cross_source_lookup"],
    },
    "knowledge_base": {
        "lambda_name": "knowledge_base_lambda",
        "description": "PubMed 논문 검색 + Bedrock KB 임상 grounding (FDA + ESMO + FLAURA2)",
        "tools": ["search_pubmed", "extract_paper_evidence", "search_clinical_knowledge_base"],
    },
    "guardrail": {
        "lambda_name": "guardrail_lambda",
        "description": "Phase A 정책 enforcement 및 임상 언어 검증",
        "tools": ["check_scope", "validate_clinical_claim"],
    },
}


def get_tools_by_category(category: str | None = None) -> dict[str, list[ToolSchema]]:
    """카테고리별 tool 그룹핑 반환.

    category 미지정 시 전체 7개 카테고리 반환.
    """
    if category:
        if category not in CATEGORIES:
            raise ValueError(f"Unknown category: {category}. Available: {list(CATEGORIES.keys())}")
        tool_names = CATEGORIES[category]["tools"]
        return {category: [TOOL_REGISTRY[t] for t in tool_names]}

    result = {}
    for cat, meta in CATEGORIES.items():
        result[cat] = [TOOL_REGISTRY[t] for t in meta["tools"]]
    return result


def get_tool_count() -> int:
    """전체 tool 수 반환 (22이어야 함)."""
    return len(TOOL_REGISTRY)


def to_mcp_tool_list() -> list[dict]:
    """MCP 규격 tool list 변환 (Strands Agent SDK 호환)."""
    tools = []
    for schema in TOOL_REGISTRY.values():
        tools.append({
            "name": schema.name,
            "description": schema.description,
            "inputSchema": schema.input_schema,
        })
    return tools
