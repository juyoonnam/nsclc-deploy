"""NSCLC Insight Engine — Strands Supervisor Agent (v4).

v4 변경 (2026-05-21 D-6):
- ★ Hybrid 라우팅: 단순 query=Haiku 4.5, 복잡 query=Sonnet 4.6
- _classify_query_complexity() 신설 — keyword/length/pattern 기반 분류
- SupervisorResponse.model_used, complexity 필드 추가
- CLI --haiku-only / --sonnet-only 옵션 (강제 모델 선택)

v3 기능 유지:
- SYSTEM_PROMPT 정책 7 (tool 호출 효율)
- ToolInvoker dedup
- Bedrock ConverseStream
- Bedrock Prompt Caching
- match_patient_drugs adapter (mutations / gene_mutations 변환)

Models:
- Sonnet: us.anthropic.claude-sonnet-4-6 (복잡 query)
- Haiku:  us.anthropic.claude-haiku-4-5-20251001-v1:0 (단순 query)
Guardrail: 19ys87squ5mz (Version 6)
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

AGENTCORE_DIR = Path(__file__).parent.parent
LAMBDAS_DIR = AGENTCORE_DIR / "lambdas"
sys.path.insert(0, str(LAMBDAS_DIR))

from tool_schemas import TOOL_REGISTRY, CATEGORIES, to_mcp_tool_list  # noqa: E402

try:
    from strands import tool as strands_tool
except ImportError:
    def strands_tool(fn):
        fn._is_tool = True
        return fn


VERBOSE = os.environ.get("NSCLC_VERBOSE", "0") == "1"
log = logging.getLogger("nsclc-supervisor")


def _log(msg: str):
    log.info(msg)
    if VERBOSE:
        print(f"[supervisor] {msg}", flush=True)


def _diag_timestamp() -> str:
    now = time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now)) + f".{int((now % 1) * 1000):03d}Z"


def _summarize_for_log(value: Any, max_chars: int = 1200) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        text = str(value)
    if len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return f"{text[:max_chars]}...[truncated {omitted} chars]"


# ═══════════════════════════════════════════════════════════════════
# Query Complexity Classifier (v4 신설)
# ═══════════════════════════════════════════════════════════════════

# Complex query 시그널 (keyword 기반)
_COMPLEX_KEYWORDS = [
    # 환자/Model B 매칭
    "환자", "patient", "tcga-",
    # 빈번한 mutation site (조합되면 multi-drug 비교 필요)
    "l858r", "t790m", "g12c", "v600e", "g719", "c797s", "exon",
    # Multi-drug 비교
    " vs ", "비교", "추천", "후보", "ranking", "rank",
    "여러", "몇 가지", "리스트", "1순위", "2순위", "top",
    # 외부 화합물 (Phase A)
    "외부", "in-library", "in_library", "tanimoto", "phase a", "scaffold",
    # Multi-step
    "그리고 ", "또한", "추가로",
    # Multi-drug 키워드
    "약물들", "drugs",
]

# Simple query 시그널 (보호: complex 키워드 있어도 이게 강하면 simple)
_SIMPLE_SHORT_KEYWORDS = [
    "shap", "metadata", "정보", "기전만", "mechanism only",
]


def _classify_query_complexity(query: str) -> str:
    """Query 복잡도 분류. Returns 'simple' or 'complex'.

    Simple 조건:
    - 단일 약물 SHAP/metadata 조회
    - 단일 mutation 빈도 조회
    - 단일 cell line meta 조회
    - 짧은 질문 (< 50 chars)

    Complex 조건:
    - Multi-drug 비교 (약물 2개 이상)
    - Patient mutation matching
    - 외부 화합물 평가
    - Mutation 조합 (예: "L858R + T790M")
    - 길이 > 80 chars
    """
    if not query:
        return "simple"

    q = query.lower().strip()

    # Mutation 조합 패턴 (L858R + T790M, exon19 + T790M 등)
    mutation_combo = bool(re.search(
        r"(l858r|t790m|g12c|v600e|g719|c797s|exon\s*\d+|t790)\s*[+,&]\s*"
        r"(l858r|t790m|g12c|v600e|g719|c797s|exon\s*\d+)",
        q,
    ))
    if mutation_combo:
        return "complex"

    # Complex keyword 있으면 complex
    for kw in _COMPLEX_KEYWORDS:
        if kw in q:
            return "complex"

    # CHEMBL/InChIKey 형식의 약물 ID 2개 이상 → complex
    chembl_ids = re.findall(r"chembl\d+", q)
    if len(set(chembl_ids)) >= 2:
        return "complex"

    # 영문 약물 이름 추정 (대문자로 시작 + tinib/mab/parib 접미사) 2개 이상
    drug_names = re.findall(
        r"\b[A-Z][a-zA-Z]*(?:tinib|mab|parib|cic|nib)\b", query
    )
    if len(set(drug_names)) >= 2:
        return "complex"

    # 긴 질문은 복잡
    if len(query) > 80:
        return "complex"

    return "simple"


# ═══════════════════════════════════════════════════════════════════
# System Prompt v3
# ═══════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """당신은 NSCLC(비소세포폐암) 약물 재창출 AI supervisor입니다.
22개 MCP tool을 통해서만 정량 근거에 접근할 수 있습니다.
응답은 한국어로, 호출한 tool의 실제 반환값만을 근거로 작성합니다.

═══ 절대 준수 정책 (8개) ═══

【정책 1: Zero-Tool 수치 생성 금지】★ 최우선
Tool을 호출하지 않은 상태에서 다음을 절대 생성하지 않습니다:
- Ensemble Score, OOF score, PR-AUC, AUROC 등 모델 지표
- SHAP feature 이름과 SHAP 값
- IC50, LFC, viability 등 약리 수치
- 환자 빈도(%), mutation count 등 통계 수치
- PMID 번호

【정책 2: 외부 화합물 champion 금지 (Phase A)】
in_library 판단은 반드시 check_in_library tool을 호출해서 받은 결과만 사용합니다.

check_in_library → in_library=False인 화합물에 대해:
- get_ensemble_probability를 절대 호출하지 않습니다.
- 대신 compute_tanimoto → check_scope 경로를 사용합니다.

【정책 3: Placeholder 변수 노출 금지】
{AGE}, {VAR}, TODO, TBD 같은 변수/placeholder를 응답에 노출하지 않습니다.

【정책 4: 용어 통일】
금지: "예측", "치료한다", "효과적이다", "완치한다", "처방"
사용: "mechanism hypothesis", "근거가 시사함", "가능성을 탐색"

【정책 5: Hedge 표현 필수】
모든 응답 끝에 hedge 표현 (computational evidence, 임상 검증 필요 등) 포함.

【정책 6: Provenance Footer 강제】
---
🔧 via {호출된 tool 이름들}
📊 {정량 근거 요약} · Source: {데이터 출처}
---

【정책 7: Tool 호출 효율】★ v3
(a) **중복 호출 금지**: 같은 tool에 동일한 params를 두 번 이상 호출하지 않습니다.
(b) **병렬 호출 활용**: 한 turn에서 여러 tool_use 블록을 동시에 발행합니다.
(c) **필요 최소 호출**: 한 약물당 보통 5개 tool로 충분:
    check_in_library → get_drug_metadata → get_oof_prediction → get_shap_explanation → get_drug_response
(d) **search_drugs 1회**: 카테고리당 1번만 호출.
(e) **최대 12 turn**: 12 turn 안에 응답 완성.

【정책 8: 임상 단정 grounding】★ D-5 신설
FDA approval, dosing, contraindication, efficacy 수치(ORR/PFS/HR/CI),
가이드라인 권고 강도(ESMO I-A/I-B, NCCN category) 등 임상 단정을 응답에 포함하기 직전엔
반드시 search_clinical_knowledge_base를 먼저 호출하여 Bedrock KB(FDA + ESMO + FLAURA2) 근거를 확보합니다.

- 응답에는 source_uri와 page를 citation으로 표기합니다.
- 근거를 찾지 못하면 "검증된 임상 근거를 찾지 못함"으로 응답하고 단정하지 않습니다.
- search_pubmed(논문)와는 별개로, 가이드라인/허가사항 단정에는 KB가 우선입니다.

═══ Tool 사용 가이드 ═══

22개 tool, 7개 카테고리:
1. schema_discovery (3): list_data_sources, get_table_schema, count_records
2. drug_library (4): search_drugs, get_drug_metadata, check_in_library, compute_tanimoto
3. model_inference (4): get_oof_prediction, get_shap_explanation, get_ensemble_probability, predict_cell_response
4. patient (3): get_patient_mutation, match_patient_drugs, list_actionable_genes
5. drug_cell_response (3): get_drug_response, get_cell_line_meta, cross_source_lookup
6. knowledge_base (3): search_pubmed, extract_paper_evidence, search_clinical_knowledge_base
7. guardrail (2): check_scope, validate_clinical_claim

═══ 응답 포맷 ═══

1. 분석 결과 (한국어, tool 반환값 기반의 정량 데이터)
2. 근거 요약
3. Hedge 문장
4. Provenance footer

⚠️ 메타 정보(PR-AUC, feature 개수, 환자 수 등)는 반드시 tool 호출로 가져옵니다.
"""


HAIKU_EXTRA_INSTRUCTIONS = """

★ HAIKU 모델 추가 강제 규칙 ★

정책 4 강화 — 절대 금지 단어:
- "예측" → 반드시 "mechanism hypothesis" 또는 "근거가 시사함"으로 대체
- "치료한다" → "근거가 시사함"
- "효과적이다" → "데이터가 지지함"

정책 5 강화 — 응답 끝에 반드시 다음 형식의 Hedge 1줄 추가:
"⚠️ Hedge: 본 분석은 computational evidence 기반이며, 임상 적용을 위해서는 추가 실험적 검증이 필요합니다."

이 규칙들을 위반하면 응답이 거부됩니다.
"""


# ═══════════════════════════════════════════════════════════════════
# Data Classes (v4: model_used, complexity 추가)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class SupervisorResponse:
    text: str
    tools_called: list[str] = field(default_factory=list)
    latency_sec: float = 0.0
    provenance: list[dict] = field(default_factory=list)
    policy_violations: list[str] = field(default_factory=list)
    call_log: list[dict] = field(default_factory=list)
    backend: str = "bedrock_converse"
    n_turns: int = 0
    n_dedup_hits: int = 0
    model_used: str = ""  # ★ v4
    complexity: str = ""  # ★ v4


# ═══════════════════════════════════════════════════════════════════
# Lambda Invokers
# ═══════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════
# Hybrid invoke routing (Phase AP — drug_library_lambda local fallback)
# ═══════════════════════════════════════════════════════════════════
# rdkit 의존 lambda는 Lambda 환경 unzipped 250MB 한도 초과로 AWS 배포 보류.
# supervisor에서 local invoke로 처리 (rdkit이 supervisor 환경에 있어야 함).
# 환경변수로 override 가능: LOCAL_ONLY_LAMBDAS=drug_library_lambda,foo_lambda

import os as _os_hybrid
_LOCAL_ONLY_LAMBDAS: set[str] = set(
    s.strip()
    for s in _os_hybrid.environ.get("LOCAL_ONLY_LAMBDAS", "drug_library_lambda").split(",")
    if s.strip()
)

# schema.lambda_name (Python module name) → AWS Lambda function 이름
_LAMBDA_NAME_TO_AWS: dict[str, str] = {
    "drug_cell_response_lambda": "nsclc-drug-cell-response",
    "drug_library_lambda":       "nsclc-drug-library",        # AWS엔 배포 안 됨 (local 전용)
    "guardrail_lambda":          "nsclc-guardrail",
    "knowledge_base_lambda":     "nsclc-knowledge-base",
    "model_inference_lambda":    "nsclc-model-inference",
    "patient_lambda":            "nsclc-patient",
    "schema_discovery_lambda":   "nsclc-schema-discovery",
}

_LAMBDA_MODULES: dict[str, Any] = {}


def _get_lambda_module(lambda_name: str):
    if lambda_name not in _LAMBDA_MODULES:
        import importlib
        _LAMBDA_MODULES[lambda_name] = importlib.import_module(lambda_name)
    return _LAMBDA_MODULES[lambda_name]


def _invoke_local(lambda_name: str, tool_name: str, params: dict) -> dict:
    module = _get_lambda_module(lambda_name)
    return module.lambda_handler({"tool": tool_name, "params": params}, None)


def _invoke_remote(lambda_name: str, tool_name: str, params: dict, region: str = "us-east-1") -> dict:
    import boto3
    client = boto3.client("lambda", region_name=region)
    response = client.invoke(
        FunctionName=lambda_name,
        InvocationType="RequestResponse",
        Payload=json.dumps({"tool": tool_name, "params": params}),
    )
    return json.loads(response["Payload"].read())


# ═══════════════════════════════════════════════════════════════════
# match_patient_drugs adapter (v3.1)
# ═══════════════════════════════════════════════════════════════════

def _adapt_match_patient_drugs_params(params: dict) -> dict:
    """LLM이 mutations / gene_mutations 등 잘못된 키로 호출 시 mutation_profile로 변환."""
    if "mutations" in params and "mutation_profile" not in params:
        muts = params.pop("mutations")
        gene_muts: dict[str, list] = {}
        for m in muts:
            m_str = str(m).strip()
            if "_" in m_str:
                g, x = m_str.split("_", 1)
                gene_muts.setdefault(g.upper(), []).append(x)
            else:
                gene_muts.setdefault(m_str.upper(), []).append("any")
        params["mutation_profile"] = {g: "+".join(v) for g, v in gene_muts.items()}
    if "gene_mutations" in params and "mutation_profile" not in params:
        params["mutation_profile"] = params.pop("gene_mutations")
    return params


# ═══════════════════════════════════════════════════════════════════
# Tool Wrappers (Phase A + Dedup)
# ═══════════════════════════════════════════════════════════════════


def _truncate_tool_result(result: dict, max_chars: int = 50000, max_list_items: int = 20) -> dict:
    """Tool result 크기 제한. 거대 list/string을 잘라 messages 폭증 방지.

    Bedrock 모델 input limit (Sonnet 4.6: 1M tokens) 초과를 막기 위함.
    """
    import json as _json
    s_full = _json.dumps(result, ensure_ascii=False, default=str)
    if len(s_full) <= max_chars:
        return result

    # result["result"] 안의 거대 컬렉션을 잘라냄
    if isinstance(result, dict) and "result" in result:
        r = result["result"]
        if isinstance(r, dict):
            for k, v in list(r.items()):
                if isinstance(v, list) and len(v) > max_list_items:
                    r[k] = v[:max_list_items] + [
                        {"_truncated": f"...추가 {len(v) - max_list_items}개 결과 생략 (size cap)"}
                    ]
                elif isinstance(v, str) and len(v) > 8000:
                    r[k] = v[:8000] + "... [truncated]"
                elif isinstance(v, dict):
                    for kk, vv in list(v.items()):
                        if isinstance(vv, list) and len(vv) > max_list_items:
                            v[kk] = vv[:max_list_items] + [
                                {"_truncated": f"...{len(vv) - max_list_items}개 생략"}
                            ]
        elif isinstance(r, list) and len(r) > max_list_items:
            result["result"] = r[:max_list_items] + [
                {"_truncated": f"...추가 {len(r) - max_list_items}개 결과 생략"}
            ]

    # 다시 체크 — 여전히 크면 강제 압축
    s_after = _json.dumps(result, ensure_ascii=False, default=str)
    if len(s_after) > max_chars:
        return {
            "result": {
                "_truncated": "Tool result exceeded size cap (50KB)",
                "preview_first_2k": s_after[:2000],
                "original_size_chars": len(s_after),
            },
            "provenance": result.get("provenance", {"tool": "?", "source": "truncated"}),
        }
    return result


class ToolInvoker:
    def __init__(self, local_mode: bool = True, region: str = "us-east-1"):
        self.local_mode = local_mode
        self.region = region
        self.call_log: list[dict] = []
        self._in_library_cache: dict[str, bool] = {}
        self._dedup_cache: dict[str, dict] = {}
        self.n_dedup_hits = 0

    def _dedup_key(self, tool_name: str, params: dict) -> str:
        return tool_name + "::" + json.dumps(params, sort_keys=True, ensure_ascii=False)

    def invoke(self, tool_name: str, params: dict) -> dict:
        # ★ match_patient_drugs 어댑터
        if tool_name == "match_patient_drugs":
            params = _adapt_match_patient_drugs_params(params)

        call_start = time.time()
        started_at = _diag_timestamp()
        log.info(
            "tool_call start tool=%s started_at=%s params=%s",
            tool_name,
            started_at,
            _summarize_for_log(params),
        )

        # dedup
        cache_key = self._dedup_key(tool_name, params)
        if cache_key in self._dedup_cache:
            self.n_dedup_hits += 1
            _log(f"DEDUP HIT: {tool_name}")
            cached = self._dedup_cache[cache_key]
            log.info(
                "tool_call end tool=%s started_at=%s ended_at=%s elapsed_sec=%.3f "
                "success=%s dedup_hit=True error=%s",
                tool_name,
                started_at,
                _diag_timestamp(),
                time.time() - call_start,
                "error" not in cached if isinstance(cached, dict) else True,
                _summarize_for_log(cached.get("error", "")) if isinstance(cached, dict) else "",
            )
            self.call_log.append({
                "tool": tool_name, "lambda": "dedup_cache",
                "params": params, "elapsed_sec": 0.0,
                "success": "error" not in cached, "dedup_hit": True,
            })
            return cached

        # Phase A
        if tool_name == "get_ensemble_probability":
            in_library = params.get("in_library")
            if in_library is False:
                err = {
                    "error": {
                        "code": "POLICY_REJECT_EXTERNAL",
                        "message": (
                            "Phase A 정책: 외부 화합물에 대한 champion 확률 표시 금지. "
                            "compute_tanimoto + check_scope 경로를 사용하세요."
                        ),
                        "tool": "get_ensemble_probability",
                    },
                    "provenance": {"tool": "get_ensemble_probability", "source": "policy_enforcement"},
                }
                self.call_log.append({
                    "tool": tool_name, "lambda": "policy", "params": params,
                    "elapsed_sec": 0.0, "success": False,
                    "policy_rejected": "POLICY_REJECT_EXTERNAL",
                })
                self._dedup_cache[cache_key] = err
                log.info(
                    "tool_call end tool=%s lambda=policy started_at=%s ended_at=%s "
                    "elapsed_sec=%.3f success=False dedup_hit=False error=%s",
                    tool_name,
                    started_at,
                    _diag_timestamp(),
                    time.time() - call_start,
                    _summarize_for_log(err["error"]),
                )
                return err

        schema = TOOL_REGISTRY.get(tool_name)
        if not schema:
            log.info(
                "tool_call end tool=%s started_at=%s ended_at=%s elapsed_sec=%.3f "
                "success=False dedup_hit=False error=%s",
                tool_name,
                started_at,
                _diag_timestamp(),
                time.time() - call_start,
                _summarize_for_log({"code": "UNKNOWN_TOOL", "message": f"Unknown tool: {tool_name}"}),
            )
            return {"error": {"code": "UNKNOWN_TOOL", "message": f"Unknown tool: {tool_name}"}}

        lambda_name = schema.lambda_name
        # Hybrid routing: local_mode=True면 전부 local. False여도 _LOCAL_ONLY_LAMBDAS에 있으면 local.
        use_local = self.local_mode or (lambda_name in _LOCAL_ONLY_LAMBDAS)
        start = time.time()
        try:
            if use_local:
                result = _invoke_local(lambda_name, tool_name, params)
            else:
                aws_function_name = _LAMBDA_NAME_TO_AWS.get(lambda_name, lambda_name)
                result = _invoke_remote(aws_function_name, tool_name, params, self.region)
        except Exception as e:
            result = {"error": {"code": "LAMBDA_EXCEPTION",
                                "message": f"{type(e).__name__}: {e}", "tool": tool_name}}
        elapsed = time.time() - start

        # ★ v4.2: tool result truncate (messages 폭증 방지)
        result_size = len(json.dumps(result, ensure_ascii=False, default=str))
        if result_size > 50000:
            _log(f"TRUNCATE: {tool_name} result {result_size} chars → 50000 cap")
            result = _truncate_tool_result(result, max_chars=50000, max_list_items=20)

        self.call_log.append({
            "tool": tool_name, "lambda": lambda_name, "params": params,
            "elapsed_sec": round(elapsed, 3),
            "success": "error" not in result,
            "result_size_chars": result_size,
        })
        self._dedup_cache[cache_key] = result

        if tool_name == "check_in_library" and "result" in result:
            self._in_library_cache[cache_key] = result["result"].get("in_library", False)

        log.info(
            "tool_call end tool=%s lambda=%s mode=%s started_at=%s ended_at=%s "
            "elapsed_sec=%.3f success=%s dedup_hit=False result_size_chars=%d error=%s",
            tool_name,
            lambda_name,
            "local" if use_local else "remote",
            started_at,
            _diag_timestamp(),
            elapsed,
            "error" not in result,
            result_size,
            _summarize_for_log(result.get("error", "")) if isinstance(result, dict) else "",
        )
        _log(f"TOOL: {tool_name} → {'OK' if 'error' not in result else 'ERR'} in {elapsed:.2f}s")
        return result

    def get_call_log(self) -> list[dict]:
        return self.call_log

    def get_tools_called(self) -> list[str]:
        return [e["tool"] for e in self.call_log if not e.get("dedup_hit")]

    def reset(self):
        self.call_log = []
        self._in_library_cache = {}
        self._dedup_cache = {}
        self.n_dedup_hits = 0


_TOOL_INVOKER: ContextVar[ToolInvoker | None] = ContextVar(
    "_TOOL_INVOKER",
    default=None,
)


def _build_strands_tools():
    tools = []
    for tool_name, schema in TOOL_REGISTRY.items():
        def make_tool(tn=tool_name, desc=schema.description):
            @strands_tool
            def _wrapped(**params):
                tool_invoker = _TOOL_INVOKER.get()
                if tool_invoker is None:
                    return {"error": "ToolInvoker not initialized"}
                return tool_invoker.invoke(tn, params)
            _wrapped.__name__ = tn
            _wrapped.__doc__ = desc
            return _wrapped
        tools.append(make_tool())
    return tools


ALL_TOOLS = _build_strands_tools()


# ═══════════════════════════════════════════════════════════════════
# Supervisor Main Class
# ═══════════════════════════════════════════════════════════════════


def _post_process_haiku_response(text: str) -> str:
    """Haiku 응답에서 금지 용어 치환 + Hedge 자동 추가."""
    if not text:
        return text
    # 금지 용어 치환
    replacements = [
        (r"\b예측합니다\b", "mechanism hypothesis를 시사합니다"),
        (r"\b예측한다\b", "근거가 시사한다"),
        (r"\b예측\b", "mechanism hypothesis"),
        (r"치료한다", "근거가 시사함"),
        (r"효과적이다", "데이터가 지지함"),
    ]
    for pat, repl in replacements:
        text = re.sub(pat, repl, text)
    # Hedge 부재 시 자동 추가
    hedge_indicators = [
        "mechanism hypothesis", "기전 가설", "근거가 시사",
        "임상 검증", "추가 검증", "실험적 검증",
        "가능성을 탐색", "데이터가 지지",
    ]
    if not any(h in text for h in hedge_indicators):
        text += ("\n\n⚠️ **Hedge**: 본 분석은 computational evidence 기반이며, "
                 "실제 임상 적용을 위해서는 추가 실험적 검증이 필요합니다.")
    return text


class NSCLCSupervisor:
    def __init__(
        self,
        local_mode: bool = True,
        region: str = "us-east-1",
        model_id: str = "us.anthropic.claude-sonnet-4-6",  # 호환: default model
        sonnet_model_id: str = "us.anthropic.claude-sonnet-4-6",
        haiku_model_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        enable_hybrid_routing: bool = True,
        force_model: str = "",  # "", "sonnet", "haiku" 강제 선택
        guardrail_id: str = "19ys87squ5mz",
        guardrail_version: str = "9",
        system_prompt: str | None = None,
        enable_prompt_caching: bool = True,
        max_turns: int = 12,
    ):
        self.local_mode = local_mode
        self.region = region
        self.model_id = model_id
        self.sonnet_model_id = sonnet_model_id
        self.haiku_model_id = haiku_model_id
        self.enable_hybrid_routing = enable_hybrid_routing
        self.force_model = force_model
        self.guardrail_id = guardrail_id
        self.guardrail_version = guardrail_version
        self.system_prompt = system_prompt or SYSTEM_PROMPT
        self.enable_prompt_caching = enable_prompt_caching
        self.max_turns = max_turns

    def _select_model_for_query(self, query: str) -> tuple[str, str]:
        """Returns (model_id, complexity_label).

        complexity: 'simple' | 'complex' | 'forced'
        """
        if self.force_model == "sonnet":
            return self.sonnet_model_id, "forced_sonnet"
        if self.force_model == "haiku":
            return self.haiku_model_id, "forced_haiku"
        if not self.enable_hybrid_routing:
            return self.model_id, "default"

        complexity = _classify_query_complexity(query)
        if complexity == "simple":
            return self.haiku_model_id, "simple"
        return self.sonnet_model_id, "complex"

    def _frame_query_for_guardrails(self, query: str) -> str:
        """Add a runtime-only safety frame for clinical evidence questions."""
        query = (query or "").strip()
        lower = query.lower()
        clinical_terms = (
            "nsclc", "환자", "patient", "변이", "mutation", "약물", "drug",
            "치료", "therapy", "권고", "recommend", "egfr", "kras", "alk",
        )
        if not any(term in lower for term in clinical_terms):
            return query
        return (
            f"{query}\n\n"
            "[Response framing]\n"
            "- 한국어로 답하되, 연구 참고용 evidence summary로만 작성한다.\n"
            "- 처방/치료 지시형 문장 대신 '근거상 후보', '임상적으로 검토되는 옵션', "
            "'전문의 판단 필요' 표현을 사용한다.\n"
            "- 도구에서 얻은 수치, provenance, PMID/FDA/ESMO citation, 모델 지표는 보존한다.\n"
            "- FDA label dose 같은 허가사항은 지시가 아니라 문헌/라벨 사실로만 표시한다.\n"
            "- 표와 섹션을 끝까지 완성하고, guardrail/policy 문구를 본문에 쓰지 않는다."
        )

    def invoke(self, query: str) -> SupervisorResponse:
        tool_invoker = ToolInvoker(local_mode=self.local_mode, region=self.region)
        start_time = time.time()

        # ★ v4: hybrid 모델 선택
        selected_model, complexity = self._select_model_for_query(query)
        model_query = self._frame_query_for_guardrails(query)
        _log(f"ROUTING: query → {complexity} → {selected_model}")
        log.info(
            "supervisor_invoke start started_at=%s query_len=%d model_query_len=%d model=%s complexity=%s",
            _diag_timestamp(),
            len(query),
            len(model_query),
            selected_model,
            complexity,
        )

        token = _TOOL_INVOKER.set(tool_invoker)

        backend = "bedrock_converse"
        n_turns = 0
        try:
            try:
                if os.environ.get("NSCLC_USE_STRANDS", "0") == "1":
                    response_text = self._invoke_with_strands(model_query, selected_model)
                    backend = "strands"
                else:
                    response_text, n_turns = self._invoke_with_bedrock_converse(
                        model_query, tool_invoker, selected_model
                    )
            except Exception as e:
                _log(f"Primary backend failed: {type(e).__name__}: {e}")
                try:
                    response_text, n_turns = self._invoke_with_bedrock_converse(
                        model_query, tool_invoker, selected_model
                    )
                    backend = "bedrock_converse_fallback"
                except Exception as e2:
                    response_text = f"❌ Supervisor 호출 실패: {type(e2).__name__}: {e2}"
                    backend = "error"

            latency = time.time() - start_time
            tools_called = tool_invoker.get_tools_called()
            call_log = tool_invoker.get_call_log()
            log.info(
                "supervisor_invoke complete ended_at=%s elapsed_sec=%.3f backend=%s "
                "turns=%d tools=%d dedup_hits=%d",
                _diag_timestamp(),
                latency,
                backend,
                n_turns,
                len(tools_called),
                tool_invoker.n_dedup_hits,
            )

            # ★ v4.1: Haiku 응답 후처리
            if "haiku" in selected_model.lower():
                response_text = _post_process_haiku_response(response_text)

            if "🔧" not in response_text:
                footer = self._build_provenance_footer(call_log)
                response_text = f"{response_text}\n\n{footer}"

            violations = self._check_policy_violations(response_text, tools_called)

            return SupervisorResponse(
                text=response_text,
                tools_called=tools_called,
                latency_sec=round(latency, 2),
                provenance=[e for e in call_log if e["success"]],
                policy_violations=violations,
                call_log=call_log,
                backend=backend,
                n_turns=n_turns,
                n_dedup_hits=tool_invoker.n_dedup_hits,
                model_used=selected_model,
                complexity=complexity,
            )
        finally:
            _TOOL_INVOKER.reset(token)

    def invoke_stream(self, query: str) -> Iterator[dict]:
        tool_invoker = ToolInvoker(local_mode=self.local_mode, region=self.region)
        start_time = time.time()

        # ★ v4: hybrid 모델 선택
        selected_model, complexity = self._select_model_for_query(query)
        model_query = self._frame_query_for_guardrails(query)
        _log(f"ROUTING: query → {complexity} → {selected_model}")

        token = _TOOL_INVOKER.set(tool_invoker)

        try:
            # 라우팅 정보를 첫 chunk로 yield
            log.info(
                "supervisor_stream start started_at=%s query_len=%d model_query_len=%d model=%s complexity=%s",
                _diag_timestamp(),
                len(query),
                len(model_query),
                selected_model,
                complexity,
            )
            yield {"type": "routing", "model": selected_model, "complexity": complexity}
            log.info("supervisor_stream routing_emitted model=%s complexity=%s", selected_model, complexity)

            accumulated_text = ""
            n_turns = 0
            for chunk in self._invoke_with_bedrock_converse_stream(
                model_query, tool_invoker, selected_model
            ):
                if chunk.get("type") == "replace_text":
                    accumulated_text = chunk.get("text", "")
                elif chunk.get("type") == "text_chunk":
                    accumulated_text += chunk["text"]
                if chunk.get("type") == "turn_end":
                    n_turns = chunk.get("turn", n_turns)
                yield chunk

            latency = time.time() - start_time
            tools_called = tool_invoker.get_tools_called()
            call_log = tool_invoker.get_call_log()
            log.info(
                "supervisor_stream generation_complete ended_at=%s elapsed_sec=%.3f "
                "accumulated_chars=%d turns=%d tools=%d dedup_hits=%d",
                _diag_timestamp(),
                latency,
                len(accumulated_text),
                n_turns,
                len(tools_called),
                tool_invoker.n_dedup_hits,
            )

            # ★ v4.1: Haiku 응답 후처리
            if "haiku" in selected_model.lower():
                accumulated_text = _post_process_haiku_response(accumulated_text)

            if "🔧" not in accumulated_text:
                footer = self._build_provenance_footer(call_log)
                accumulated_text = f"{accumulated_text}\n\n{footer}"

            violations = self._check_policy_violations(accumulated_text, tools_called)

            log.info(
                "supervisor_stream done_event_emit ended_at=%s elapsed_sec=%.3f response_chars=%d",
                _diag_timestamp(),
                latency,
                len(accumulated_text),
            )
            yield {
                "type": "done",
                "response": {
                    "text": accumulated_text,
                    "tools_called": tools_called,
                    "latency_sec": round(latency, 2),
                    "call_log": call_log,
                    "policy_violations": violations,
                    "backend": "bedrock_converse_stream",
                    "n_turns": n_turns,
                    "n_dedup_hits": tool_invoker.n_dedup_hits,
                    "model_used": selected_model,
                    "complexity": complexity,
                },
            }
            log.info("supervisor_stream done_event_emitted elapsed_sec=%.3f", time.time() - start_time)
        except Exception as e:
            log.exception("supervisor_stream error_event_emit")
            yield {"type": "error", "message": f"{type(e).__name__}: {e}"}
        finally:
            log.info("supervisor_stream exit elapsed_sec=%.3f", time.time() - start_time)
            _TOOL_INVOKER.reset(token)

    def _invoke_with_strands(self, query: str, selected_model: str) -> str:
        from strands import Agent
        from strands.models.bedrock import BedrockModel

        model = BedrockModel(model_id=selected_model, region_name=self.region)
        agent = Agent(model=model, system_prompt=self.system_prompt, tools=ALL_TOOLS)
        return str(agent(query))

    def _build_converse_request(
        self,
        messages: list,
        selected_model: str,
        *,
        include_tools: bool = True,
    ) -> dict:
        # ★ v4.1: Haiku 전용 prompt augmentation
        active_prompt = self.system_prompt
        if "haiku" in (selected_model or "").lower():
            active_prompt = self.system_prompt + HAIKU_EXTRA_INSTRUCTIONS

        if self.enable_prompt_caching:
            system_blocks = [
                {"text": active_prompt},
                {"cachePoint": {"type": "default"}},
            ]
        else:
            system_blocks = [{"text": active_prompt}]

        request = {
            "modelId": selected_model or self.model_id,  # ★ v4
            "system": system_blocks,
            "messages": messages,
            "inferenceConfig": {"maxTokens": 6144, "temperature": 0.2},
        }
        if include_tools:
            tool_specs = [
                {"toolSpec": {
                    "name": schema.name,
                    "description": schema.description,
                    "inputSchema": {"json": schema.input_schema},
                }}
                for schema in TOOL_REGISTRY.values()
            ]
            if self.enable_prompt_caching:
                request["toolConfig"] = {"tools": tool_specs + [{"cachePoint": {"type": "default"}}]}
            else:
                request["toolConfig"] = {"tools": tool_specs}
        if self.guardrail_id:
            request["guardrailConfig"] = {
                "guardrailIdentifier": self.guardrail_id,
                "guardrailVersion": self.guardrail_version,
                "trace": "enabled",
            }
        return request

    def _rewrite_guardrail_intervention(
        self,
        client,
        messages: list,
        selected_model: str,
        draft_text: str,
    ) -> str:
        rewrite_prompt = (
            "이전 초안은 임상 지시처럼 보이는 표현 때문에 중단되었다. "
            "이미 수집된 도구 결과와 인용만 사용해 한국어 연구용 근거 요약으로 다시 작성한다.\n"
            "요구사항:\n"
            "- 처방, 투여 지시, 환자별 치료 결정 문장을 쓰지 않는다.\n"
            "- '권고한다' 대신 '근거상 옵션', '임상적으로 검토되는 후보'라고 쓴다.\n"
            "- 용량/복용법/부작용 관리 섹션은 사용자가 직접 묻지 않았으면 생략한다.\n"
            "- 수치, 모델 지표, PRISM/OOF, PMID/FDA/ESMO 출처는 보존한다.\n"
            "- 1) 핵심 결론 2) 문헌/가이드라인 근거 3) 모델/세포주 근거 4) 한계 순서로 1400자 이내."
        )
        original_question = ""
        if messages and messages[0].get("content"):
            original_question = messages[0]["content"][0].get("text", "")
        rewrite_messages = [{
            "role": "user",
            "content": [{
                "text": (
                    f"{rewrite_prompt}\n\n"
                    f"[Original question]\n{original_question[:1200]}\n\n"
                    f"[Interrupted draft]\n{(draft_text or '')[:6000]}"
                )
            }],
        }]
        try:
            request = self._build_converse_request(
                rewrite_messages,
                selected_model,
                include_tools=False,
            )
            response = client.converse(**request)
            content = response.get("output", {}).get("message", {}).get("content", [])
            text = "".join(block.get("text", "") for block in content if "text" in block).strip()
            stop_reason = response.get("stopReason", "")
            log.info(
                "bedrock_stream guardrail_rewrite_complete stop_reason=%s text_chars=%d",
                stop_reason,
                len(text),
            )
            if text and stop_reason != "guardrail_intervened":
                return text
        except Exception:
            log.exception("bedrock_stream guardrail_rewrite_failed")

        fallback = (draft_text or "").replace("[Guardrail Intervened]", "").strip()
        marker = "NSCLC Insight Engine은"
        if marker in fallback:
            fallback = fallback.split(marker, 1)[0].strip()
        if fallback:
            return (
                f"{fallback}\n\n"
                "본 내용은 연구 참고용 근거 요약이며, 실제 임상 판단은 전문 의료인의 검토가 필요합니다."
            )
        return (
            "연구 참고용 근거 요약을 생성하는 중 일부 임상 지시성 표현이 제한되었습니다. "
            "수집된 도구 결과는 우측 Evidence / Tool Trace에서 확인할 수 있으며, "
            "실제 임상 판단은 전문 의료인의 검토가 필요합니다."
        )

    def _invoke_with_bedrock_converse(
        self,
        query: str,
        tool_invoker: ToolInvoker,
        selected_model: str,
    ) -> tuple[str, int]:
        import boto3
        client = boto3.client("bedrock-runtime", region_name=self.region)
        messages = [{"role": "user", "content": [{"text": query}]}]

        for turn in range(self.max_turns):
            turn_no = turn + 1
            turn_start = time.time()
            turn_started_at = _diag_timestamp()
            request = self._build_converse_request(messages, selected_model)
            log.info(
                "bedrock_converse turn_start turn=%d started_at=%s model=%s messages=%d",
                turn_no,
                turn_started_at,
                selected_model,
                len(messages),
            )
            try:
                response = client.converse(**request)
            except Exception as e:
                if "cachePoint" in str(e) and self.enable_prompt_caching:
                    _log("Prompt caching unsupported — disabling")
                    log.info(
                        "bedrock_converse cache_retry turn=%d error=%s",
                        turn_no,
                        f"{type(e).__name__}: {e}",
                    )
                    self.enable_prompt_caching = False
                    request = self._build_converse_request(messages, selected_model)
                    response = client.converse(**request)
                else:
                    log.exception("bedrock_converse turn_error turn=%d", turn_no)
                    raise

            output = response["output"]["message"]
            messages.append(output)
            stop_reason = response.get("stopReason", "end_turn")

            n_tool_use = len([b for b in output["content"] if "toolUse" in b])
            text_parts = [b["text"] for b in output["content"] if "text" in b]
            text_chars = sum(len(t) for t in text_parts)
            log.info(
                "bedrock_converse turn_response turn=%d ended_at=%s elapsed_sec=%.3f "
                "stop_reason=%s tool_use_count=%d text_blocks=%d text_chars=%d",
                turn_no,
                _diag_timestamp(),
                time.time() - turn_start,
                stop_reason,
                n_tool_use,
                len(text_parts),
                text_chars,
            )
            _log(f"TURN {turn_no}: stop_reason={stop_reason}, tool_uses={n_tool_use}")

            if stop_reason == "end_turn":
                log.info(
                    "bedrock_converse text_generation_complete turn=%d started_at=%s "
                    "ended_at=%s text_chars=%d",
                    turn_no,
                    turn_started_at,
                    _diag_timestamp(),
                    text_chars,
                )
                return "\n".join(text_parts), turn + 1

            elif stop_reason == "tool_use":
                tool_results = []
                for block in output["content"]:
                    if "toolUse" in block:
                        tu = block["toolUse"]
                        log.info(
                            "bedrock_converse tool_use_received turn=%d tool_use_id=%s "
                            "tool=%s input=%s",
                            turn_no,
                            tu.get("toolUseId", ""),
                            tu.get("name", ""),
                            _summarize_for_log(tu.get("input", {})),
                        )
                        result = tool_invoker.invoke(tu["name"], tu.get("input", {}))
                        tool_results.append({
                            "toolResult": {
                                "toolUseId": tu["toolUseId"],
                                "content": [{"json": result}],
                            }
                        })
                messages.append({"role": "user", "content": tool_results})

            elif stop_reason == "guardrail_intervened":
                blocked = "\n".join(text_parts) if text_parts else "안전 정책 차단"
                log.info(
                    "bedrock_converse guardrail_intervened turn=%d text_chars=%d",
                    turn_no,
                    len(blocked),
                )
                return f"[Guardrail Intervened]\n{blocked}", turn + 1

            else:
                log.info(
                    "bedrock_converse stop_other turn=%d stop_reason=%s text_chars=%d",
                    turn_no,
                    stop_reason,
                    text_chars,
                )
                return ("\n".join(text_parts) if text_parts else "(응답 없음)", turn + 1)

        log.info("bedrock_converse max_turns_exceeded max_turns=%d", self.max_turns)
        return "(최대 턴 수 초과)", self.max_turns

    def _invoke_with_bedrock_converse_stream(
        self,
        query: str,
        tool_invoker: ToolInvoker,
        selected_model: str,
    ) -> Iterator[dict]:
        import boto3
        client = boto3.client("bedrock-runtime", region_name=self.region)
        messages = [{"role": "user", "content": [{"text": query}]}]

        for turn in range(self.max_turns):
            turn_no = turn + 1
            turn_start = time.time()
            turn_started_at = _diag_timestamp()
            request = self._build_converse_request(messages, selected_model)
            log.info(
                "bedrock_stream turn_start turn=%d started_at=%s model=%s messages=%d",
                turn_no,
                turn_started_at,
                selected_model,
                len(messages),
            )
            try:
                stream_response = client.converse_stream(**request)
            except Exception as e:
                if "cachePoint" in str(e) and self.enable_prompt_caching:
                    log.info(
                        "bedrock_stream cache_retry turn=%d error=%s",
                        turn_no,
                        f"{type(e).__name__}: {e}",
                    )
                    self.enable_prompt_caching = False
                    request = self._build_converse_request(messages, selected_model)
                    stream_response = client.converse_stream(**request)
                else:
                    log.exception("bedrock_stream turn_error turn=%d", turn_no)
                    raise

            assistant_content: list = []
            current_text = ""
            current_tool_use: dict | None = None
            current_tool_input_json = ""
            stop_reason = "end_turn"
            event_count = 0
            text_started_at = ""
            text_chars = 0
            text_delta_count = 0
            tool_use_count = 0

            for event in stream_response.get("stream", []):
                event_count += 1
                if "messageStart" in event:
                    log.info(
                        "bedrock_stream message_start turn=%d role=%s timestamp=%s",
                        turn_no,
                        event["messageStart"].get("role", ""),
                        _diag_timestamp(),
                    )
                    continue
                elif "contentBlockStart" in event:
                    start = event["contentBlockStart"]["start"]
                    if "toolUse" in start:
                        tool_use_count += 1
                        current_tool_use = {
                            "toolUseId": start["toolUse"]["toolUseId"],
                            "name": start["toolUse"]["name"],
                        }
                        current_tool_input_json = ""
                        log.info(
                            "bedrock_stream tool_use_start turn=%d index=%d tool_use_id=%s tool=%s",
                            turn_no,
                            tool_use_count,
                            current_tool_use["toolUseId"],
                            current_tool_use["name"],
                        )
                        yield {"type": "tool_start",
                               "tool": current_tool_use["name"], "params": {}}
                elif "contentBlockDelta" in event:
                    delta = event["contentBlockDelta"]["delta"]
                    if "text" in delta:
                        if not text_started_at:
                            text_started_at = _diag_timestamp()
                            log.info(
                                "bedrock_stream text_start turn=%d started_at=%s",
                                turn_no,
                                text_started_at,
                            )
                        text_delta_count += 1
                        text_chars += len(delta["text"])
                        current_text += delta["text"]
                        yield {"type": "text_chunk", "text": delta["text"]}
                    elif "toolUse" in delta and current_tool_use is not None:
                        current_tool_input_json += delta["toolUse"].get("input", "")
                elif "contentBlockStop" in event:
                    if current_tool_use is not None:
                        try:
                            tool_input = json.loads(current_tool_input_json) if current_tool_input_json else {}
                        except json.JSONDecodeError:
                            tool_input = {}
                        current_tool_use["input"] = tool_input
                        assistant_content.append({"toolUse": current_tool_use})
                        log.info(
                            "bedrock_stream tool_use_received turn=%d tool_use_id=%s "
                            "tool=%s input=%s",
                            turn_no,
                            current_tool_use["toolUseId"],
                            current_tool_use["name"],
                            _summarize_for_log(tool_input),
                        )
                        current_tool_use = None
                        current_tool_input_json = ""
                    elif current_text:
                        log.info(
                            "bedrock_stream text_block_stop turn=%d block_chars=%d",
                            turn_no,
                            len(current_text),
                        )
                        assistant_content.append({"text": current_text})
                        current_text = ""
                elif "messageStop" in event:
                    stop_reason = event["messageStop"].get("stopReason", "end_turn")
                    log.info(
                        "bedrock_stream message_stop turn=%d stop_reason=%s timestamp=%s",
                        turn_no,
                        stop_reason,
                        _diag_timestamp(),
                    )
                elif "metadata" in event:
                    log.info(
                        "bedrock_stream metadata turn=%d data=%s",
                        turn_no,
                        _summarize_for_log(event["metadata"]),
                    )

            messages.append({"role": "assistant", "content": assistant_content})
            if text_started_at:
                log.info(
                    "bedrock_stream text_end turn=%d started_at=%s ended_at=%s "
                    "text_chars=%d text_delta_count=%d",
                    turn_no,
                    text_started_at,
                    _diag_timestamp(),
                    text_chars,
                    text_delta_count,
                )
            log.info(
                "bedrock_stream turn_end turn=%d ended_at=%s elapsed_sec=%.3f "
                "stop_reason=%s tool_use_count=%d text_chars=%d events=%d assistant_blocks=%d",
                turn_no,
                _diag_timestamp(),
                time.time() - turn_start,
                stop_reason,
                tool_use_count,
                text_chars,
                event_count,
                len(assistant_content),
            )
            _log(f"STREAM TURN {turn_no}: stop_reason={stop_reason}")

            yield {"type": "turn_end", "turn": turn_no, "stop_reason": stop_reason}

            if stop_reason == "end_turn":
                log.info("bedrock_stream generation_complete turn=%d stop_reason=end_turn", turn_no)
                return
            elif stop_reason == "tool_use":
                tool_results = []
                for block in assistant_content:
                    if "toolUse" in block:
                        tu = block["toolUse"]
                        start = time.time()
                        result = tool_invoker.invoke(tu["name"], tu.get("input", {}))
                        elapsed = time.time() - start
                        yield {
                            "type": "tool_result",
                            "tool": tu["name"],
                            "success": "error" not in result,
                            "elapsed": elapsed,
                        }
                        tool_results.append({
                            "toolResult": {
                                "toolUseId": tu["toolUseId"],
                                "content": [{"json": result}],
                            }
                        })
                messages.append({"role": "user", "content": tool_results})
            elif stop_reason == "guardrail_intervened":
                draft_text = "".join(
                    block.get("text", "") for block in assistant_content if "text" in block
                )
                rewrite_text = self._rewrite_guardrail_intervention(
                    client,
                    messages,
                    selected_model,
                    draft_text,
                )
                yield {"type": "replace_text", "text": ""}
                yield {"type": "text_chunk", "text": rewrite_text}
                return
            else:
                log.info("bedrock_stream stop_other turn=%d stop_reason=%s", turn_no, stop_reason)
                return

        log.info("bedrock_stream max_turns_exceeded max_turns=%d", self.max_turns)

    def _build_provenance_footer(self, call_log: list[dict]) -> str:
        successful = [e for e in call_log if e["success"] and not e.get("dedup_hit")]
        tool_names = [e["tool"] for e in successful]
        if not tool_names:
            return "---\n🔧 via (no tools called)\n---"
        lines = ["---", f"🔧 via {' + '.join(tool_names)}"]
        sources = set()
        for e in successful:
            schema = TOOL_REGISTRY.get(e["tool"])
            if schema:
                sources.add(schema.lambda_name)
        if sources:
            lines.append(f"📊 Source: {', '.join(sorted(sources))}")
        lines.append("---")
        return "\n".join(lines)

    def _check_policy_violations(self, text: str, tools_called: list[str]) -> list[str]:
        v = []
        ph = re.findall(r"\{([A-Z_][A-Z0-9_]*)\}", text)
        if ph:
            v.append(f"Placeholder 변수 노출: {set(ph)}")
        if re.search(r"\b(TODO|TBD|XXX|FIXME)\b", text):
            v.append("Placeholder 텍스트")
        banned = ["예측", "치료한다", "치료할 수 있다", "효과적이다",
                  "효과가 있다", "완치한다", "완치됩니다"]
        for t in banned:
            if t in text:
                v.append(f"금지 용어: '{t}'")
        if re.search(r"권장합니다|복용하세요|처방받으세요|매일\s*\d+\s*mg", text):
            v.append("처방/용량 단정")
        hedge = ["mechanism hypothesis", "기전 가설", "근거가 시사",
                 "임상 검증", "추가 검증", "실험적 검증",
                 "가능성을 탐색", "데이터가 지지"]
        if not any(h in text for h in hedge) and len(text) > 200:
            v.append("Hedge 표현 부재")
        if "🔧" not in text:
            v.append("Provenance footer 부재")
        if not tools_called:
            fab = [
                (r"Ensemble Score\s*:\s*\d", "Ensemble"),
                (r"PR-AUC\s*[:_]?w?\s*[:=]?\s*0\.\d", "PR-AUC"),
                (r"SHAP\s*값?\s*[:=]?\s*[+-]?0\.\d", "SHAP"),
                (r"IC50\s*[:=]?\s*\d+\s*nM", "IC50"),
                (r"LFC\s*[:=]?\s*[+-]?\d", "LFC"),
                (r"PMID\s*[:=]?\s*\d{7,9}", "PMID"),
            ]
            for pat, desc in fab:
                if re.search(pat, text):
                    v.append(f"Zero-Tool fab: {desc}")
        if "check_in_library" not in tools_called:
            if re.search(r"in[_\s-]?library\s*[:=]?\s*(TRUE|True|true|✅)", text):
                v.append("Phase A 우회")
        return v


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="NSCLC Supervisor Agent v4 (Hybrid)")
    parser.add_argument("query", nargs="?", default="Imatinib이 NSCLC 후보로 뽑힌 SHAP 근거는?")
    parser.add_argument("--remote", action="store_true")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--guardrail-version", default="6")
    parser.add_argument("--use-strands", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--no-hybrid", action="store_true",
                        help="Hybrid 라우팅 비활성 (model_id 사용)")
    parser.add_argument("--haiku-only", action="store_true",
                        help="모든 query를 Haiku로 강제")
    parser.add_argument("--sonnet-only", action="store_true",
                        help="모든 query를 Sonnet로 강제")
    parser.add_argument("--classify-only", action="store_true",
                        help="복잡도 분류만 출력 후 종료 (LLM 호출 X)")
    parser.add_argument("--max-turns", type=int, default=12)
    parser.add_argument("--stream", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        os.environ["NSCLC_VERBOSE"] = "1"
        VERBOSE = True

    if args.use_strands:
        os.environ["NSCLC_USE_STRANDS"] = "1"

    force_model = ""
    if args.haiku_only:
        force_model = "haiku"
    elif args.sonnet_only:
        force_model = "sonnet"

    if args.classify_only:
        complexity = _classify_query_complexity(args.query)
        print(f"Query: {args.query}")
        print(f"Complexity: {complexity}")
        print(f"Model: {'Haiku' if complexity == 'simple' else 'Sonnet'}")
        sys.exit(0)

    supervisor = NSCLCSupervisor(
        local_mode=not args.remote,
        region=args.region,
        guardrail_version=args.guardrail_version,
        enable_prompt_caching=not args.no_cache,
        enable_hybrid_routing=not args.no_hybrid,
        force_model=force_model,
        max_turns=args.max_turns,
    )

    print(f"{'='*60}")
    print(f"Query: {args.query}")
    print(f"Mode: {'remote' if args.remote else 'local'} / "
          f"{'stream' if args.stream else 'sync'}")
    print(f"Hybrid routing: {supervisor.enable_hybrid_routing} "
          f"(force={force_model or 'none'})")
    print(f"Guardrail: {supervisor.guardrail_id} v{supervisor.guardrail_version}")
    print(f"Prompt caching: {supervisor.enable_prompt_caching}")
    print(f"{'='*60}\n")

    if args.stream:
        for chunk in supervisor.invoke_stream(args.query):
            ctype = chunk.get("type")
            if ctype == "routing":
                print(f"[ROUTING] {chunk['complexity']} → {chunk['model']}", flush=True)
            elif ctype == "text_chunk":
                print(chunk["text"], end="", flush=True)
            elif ctype == "tool_start":
                print(f"\n[→ {chunk['tool']}]", end=" ", flush=True)
            elif ctype == "tool_result":
                print(f"({'OK' if chunk['success'] else 'ERR'} {chunk['elapsed']:.2f}s)",
                      flush=True)
            elif ctype == "done":
                r = chunk["response"]
                print(f"\n\n{'='*60}")
                print(f"Model: {r['model_used']} ({r['complexity']})")
                print(f"Backend: {r['backend']}")
                print(f"Tools ({len(r['tools_called'])}): {r['tools_called']}")
                print(f"Latency: {r['latency_sec']}s, Turns: {r['n_turns']}, "
                      f"Dedup hits: {r['n_dedup_hits']}")
                if r['policy_violations']:
                    print(f"⚠️ Violations: {r['policy_violations']}")
                print(f"{'='*60}")
            elif ctype == "error":
                print(f"\nERROR: {chunk['message']}")
    else:
        response = supervisor.invoke(args.query)
        print(response.text)
        print(f"\n{'='*60}")
        print(f"Model: {response.model_used} ({response.complexity})")
        print(f"Backend: {response.backend}")
        print(f"Tools ({len(response.tools_called)}): {response.tools_called}")
        print(f"Latency: {response.latency_sec}s, Turns: {response.n_turns}, "
              f"Dedup hits: {response.n_dedup_hits}")
        if response.policy_violations:
            print(f"⚠️ Violations: {response.policy_violations}")
        print(f"{'='*60}")
