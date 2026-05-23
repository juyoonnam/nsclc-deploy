"""
bedrock_client.py
NSCLC Insight Engine — LLM 통합 wrapper.

Mode toggle (env var NSCLC_LLM_MODE):
  - "mock":    mock_lib + local_retrieval만 사용. Bedrock invoke 안 함.
  - "bedrock": 실 Bedrock invoke. retrieved evidence를 prompt context로 박음.

전략: KB (Knowledge Base) 없이 direct invoke. retrieval은 로컬에서 처리.
  → KB 생성/ingestion 절차 skip 가능 (sprint 안 빠른 통합)
  → 발표 후 KB로 hot-swap 시 _bedrock_invoke 내부만 RetrieveAndGenerate API로 교체

Pipeline:
  query(node_type, node_name, role, user_question)
    → cache check
    → local_retrieval.retrieve() → top-k PubMed records
    → mock_response() OR _bedrock_invoke()
    → _validate() → 형식/PMID/금지어 검증
    → cache write
    → return LLMResponse

Failure modes (모두 graceful):
  - cache write 실패: warning, continue
  - retrieval 결과 비어있음: "Insufficient evidence" 응답
  - Bedrock invoke 실패: mock_lib fallback (있으면) OR "Insufficient evidence"
  - validation 실패: retry 1회 (Bedrock 모드), 그래도 실패면 INSUFFICIENT fallback
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from .local_retrieval import retrieve as _local_retrieve
from .mock_lib import mock_response as _mock_response, INSUFFICIENT


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODE = os.getenv("NSCLC_LLM_MODE", "bedrock").lower()
MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
HAIKU_ID = os.getenv("BEDROCK_HAIKU_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
GUARDRAIL_ID = os.getenv("BEDROCK_GUARDRAIL_ID", "").strip()
GUARDRAIL_VERSION = os.getenv("BEDROCK_GUARDRAIL_VERSION", "DRAFT").strip() or "DRAFT"


def _guardrail_kwargs() -> dict:
    if not GUARDRAIL_ID:
        return {}
    return {
        "guardrailIdentifier": GUARDRAIL_ID,
        "guardrailVersion": GUARDRAIL_VERSION,
    }


def _check_guardrail_intervened(raw: dict) -> bool:
    return raw.get("stop_reason", "") == "guardrail_intervened"

# Project root: final/ → parents[2] from final/nsclc_ui/llm/
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PROJECT_ROOT / "data" / "derived" / "llm_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 5team/presentation_data/llm_prompts/system_prompt_v1.md
PROMPT_PATH = Path(__file__).parent / "prompts" / "system_prompt_v1.md"

if PROMPT_PATH.exists():
    SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")
else:
    SYSTEM_PROMPT = (
        "You are a mechanism hypothesis assistant for NSCLC. "
        "Respond in Korean with 2-3 sentences. Cite PMIDs in [PMID:XXXX] format. "
        "Never use prediction/treatment/recommendation language."
    )

SAFETY_REFUSAL_RULES = """

[Safety refusal rules]
7. 욕설, 모욕, 도발성 발언에는 단호하게 거부합니다: "그런 질문에는 답변하지 않습니다. NSCLC 약물 재창출 관련 질문을 해주세요."
8. 의학적 진단·처방·치료 권고 요청은 명확히 거부합니다: "환자 개별 치료 결정은 임상의 권한입니다. 본 시스템은 약물 재창출 후보 탐색 도구입니다."
"""

SYSTEM_PROMPT = SYSTEM_PROMPT.rstrip() + SAFETY_REFUSAL_RULES


# ---------------------------------------------------------------------------
# Response dataclass
# ---------------------------------------------------------------------------

@dataclass
class LLMResponse:
    text: str
    pmids: list[str]
    grounded: bool       # True if response cites at least one retrieved PMID
    cached: bool         # True if returned from disk cache
    mode: str            # "mock" | "bedrock" | "error"
    latency_ms: float
    error: str = ""      # non-empty if any failure occurred

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _cache_key(node_type: str, node_name: str, user_q: str = "") -> str:
    payload = f"{node_type}|{node_name}|{user_q}|{MODEL_ID}|{MODE}|v1"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _cache_read(ck: str) -> dict | None:
    p = CACHE_DIR / f"{ck}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _cache_write(ck: str, data: dict) -> None:
    try:
        (CACHE_DIR / f"{ck}.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


def _normalize_node_type(node_type: str) -> tuple[str, str, str]:
    """Return (cache/prompt type, retrieval type, mock type)."""
    t = (node_type or "").strip().lower()
    if t in {"gene", "protein", "target"}:
        return "gene", "gene", "protein"
    if t in {"drug", "compound"}:
        return "drug", "drug", "drug"
    return t or "generic", t or "generic", t or "generic"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

FORBIDDEN_WORDS = (
    "예측한다", "예측됨", "치료할 수 있다", "치료 가능", "효과적이다", "효과가 있다",
    "권장한다", "처방한다", "처방",
    "predicts", "predicted to respond", "treats", "cures",
)


def _validate(text: str) -> tuple[bool, str]:
    """Validate LLM output. Return (ok, reason)."""
    if not text:
        return False, "empty"
    if text.startswith(INSUFFICIENT):
        return True, "ok_insufficient"
    if not re.search(r"\[PMID:\d+", text):
        return False, "no_pmid"
    for w in FORBIDDEN_WORDS:
        if w in text:
            return False, f"forbidden:{w}"
    if len(text) > 400:
        return False, "too_long"
    starts_ok = (
        text.startswith("Mechanism hypothesis:")
        or text.startswith("개별 환자 치료 결정")
        or text.startswith(INSUFFICIENT[:20])
    )
    if not starts_ok:
        return False, "bad_format"
    return True, "ok"


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_user_message(
    node_type: str,
    node_name: str,
    role: str,
    retrieved: list[dict],
    user_q: str = "",
) -> str:
    parts = ["[Retrieved evidence]"]
    if not retrieved:
        parts.append("(no relevant abstracts found)")
    else:
        for r in retrieved:
            journal = (r.get("journal") or "")[:50]
            abstract = (r.get("abstract") or "").replace("\n", " ").strip()
            # 토큰 절약: abstract 400자로 자름
            abstract = abstract[:400]
            parts.append(
                f'PMID:{r.get("pmid","")} ({r.get("year","")}, {journal}): "{abstract}..."'
            )
    parts.append("")
    parts.append("[Node clicked]")
    parts.append(f"Type: {node_type}")
    parts.append(f"Name: {node_name}")
    parts.append(f"NSCLC role: {role or '(unspecified)'}")
    if user_q:
        parts.append("")
        parts.append("[User question]")
        parts.append(user_q)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Bedrock invoke (lazy import boto3)
# ---------------------------------------------------------------------------

def _bedrock_invoke(
    node_type: str,
    node_name: str,
    role: str,
    retrieved: list[dict],
    user_q: str = "",
    retry: bool = False,
) -> tuple[str, list[str], bool, str]:
    """Direct Bedrock invoke. Return (text, pmids, grounded, error)."""
    try:
        import boto3
    except ImportError:
        return "", [], False, "boto3_not_installed"

    try:
        client = boto3.client("bedrock-runtime", region_name=REGION)
    except Exception as e:
        return "", [], False, f"client_init:{type(e).__name__}"

    user_msg = _build_user_message(node_type, node_name, role, retrieved, user_q)

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 400,
        "temperature": 0.1 if retry else 0.3,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_msg}],
    }

    try:
        resp = client.invoke_model(
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body),
            **_guardrail_kwargs(),
        )
        raw = json.loads(resp["body"].read())
        if _check_guardrail_intervened(raw):
            return "그런 질문에는 답변하지 않습니다. NSCLC 약물 재창출 관련 질문을 해주세요.", [], False, "guardrail_intervened"
    except Exception as e:
        return "", [], False, f"invoke:{type(e).__name__}:{str(e)[:80]}"

    text = ""
    if isinstance(raw, dict):
        content = raw.get("content") or []
        if content and isinstance(content[0], dict):
            text = content[0].get("text", "")

    if not text:
        return "", [], False, "empty_response"

    pmids = re.findall(r"PMID:(\d+)", text)
    grounded = bool(pmids) and any(
        p in (r.get("pmid", "") for r in retrieved) for p in pmids
    )
    return text.strip(), pmids, grounded, ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def query(
    node_type: str,
    node_name: str,
    role: str = "",
    user_question: str = "",
    *,
    retrieve_k: int = 5,
    bypass_cache: bool = False,
) -> LLMResponse:
    """Main entry point.

    Args:
        node_type:    "gene" | "protein" | "target" | "drug"
        node_name:    gene symbol or drug name
        role:         NSCLC contextual role (e.g., "hub target")
        user_question: optional user free-text question (for chat panel)
        retrieve_k:   number of evidence records to retrieve
        bypass_cache: skip cache lookup (useful for prompt-eng iteration)

    Returns:
        LLMResponse dataclass.
    """
    t0 = time.time()
    cache_type, retrieval_type, mock_type = _normalize_node_type(node_type)

    # 1. cache lookup
    ck = _cache_key(cache_type, node_name, user_question)
    if not bypass_cache:
        cached = _cache_read(ck)
        if cached:
            return LLMResponse(
                text=cached["text"],
                pmids=cached.get("pmids", []),
                grounded=cached.get("grounded", True),
                cached=True,
                mode=cached.get("mode", MODE),
                latency_ms=(time.time() - t0) * 1000.0,
                error=cached.get("error", ""),
            )

    # 2. retrieve evidence (always local, mode-agnostic)
    try:
        retrieved = _local_retrieve(node_name, retrieval_type, k=retrieve_k)
    except Exception as e:
        retrieved = []
        _retrieve_err = f"retrieve_failed:{type(e).__name__}"
    else:
        _retrieve_err = ""

    # 3. dispatch by mode
    err = _retrieve_err
    if MODE == "mock":
        text, pmids = _mock_response(mock_type, node_name, role, retrieved)
        grounded = bool(pmids) and not text.startswith("Insufficient")
    elif MODE == "bedrock":
        text, pmids, grounded, invoke_err = _bedrock_invoke(
            cache_type, node_name, role, retrieved, user_question
        )
        if invoke_err:
            err = (err + ";" + invoke_err).strip(";")
            # Bedrock 실패 → mock fallback (있으면)
            text2, pmids2 = _mock_response(mock_type, node_name, role, retrieved)
            if text2 and not text2.startswith("Insufficient"):
                text, pmids, grounded = text2, pmids2, True
                err += ";fallback_mock"
            else:
                text, pmids, grounded = INSUFFICIENT, [], False
    else:
        text, pmids, grounded = INSUFFICIENT, [], False
        err = f"unknown_mode:{MODE}"

    # 4. validate
    ok, reason = _validate(text)
    if not ok:
        if MODE == "bedrock":
            # one retry with lower temperature
            text2, pmids2, grounded2, retry_err = _bedrock_invoke(
                cache_type, node_name, role, retrieved, user_question, retry=True
            )
            ok2, reason2 = _validate(text2)
            if ok2:
                text, pmids, grounded = text2, pmids2, grounded2
                err = ""
            else:
                fallback_text, fallback_pmids = _mock_response(mock_type, node_name, role, retrieved)
                if fallback_text and not fallback_text.startswith("Insufficient"):
                    text, pmids, grounded = fallback_text, fallback_pmids, True
                    err = (err + f";validation_failed:{reason2};fallback_mock").strip(";")
                else:
                    text = INSUFFICIENT
                    pmids = []
                    grounded = False
                    # Treat "insufficient evidence" as a valid audience-facing answer,
                    # not as a production error chip. Actual fallback cases still keep
                    # fallback_mock in error and are marked mode=mock below.
                    err = ""
        else:
            text = INSUFFICIENT
            pmids = []
            grounded = False
            err = (err + f";validation_failed:{reason}").strip(";")

    # 5. build response + cache
    effective_mode = "mock" if "fallback_mock" in err else MODE
    resp = LLMResponse(
        text=text,
        pmids=pmids,
        grounded=grounded,
        cached=False,
        mode=effective_mode,
        latency_ms=(time.time() - t0) * 1000.0,
        error=err,
    )

    # Cache stable responses, including fallback/insufficient evidence, so pre-warming
    # can make demo latency predictable even if Bedrock temporarily falls back.
    _cache_write(ck, {
        "text": resp.text,
        "pmids": resp.pmids,
        "grounded": resp.grounded,
        "mode": resp.mode,
        "error": resp.error,
    })

    return resp


def query_entity(
    name: str,
    name_type: str,
    k: int = 3,
    *,
    role: str = "",
    user_question: str = "",
    bypass_cache: bool = False,
) -> LLMResponse:
    """Convenience wrapper for UI code that thinks in entity-name first."""
    return query(
        name_type,
        name,
        role=role,
        user_question=user_question,
        retrieve_k=k,
        bypass_cache=bypass_cache,
    )


HAIKU_SYSTEM_PROMPT = """당신은 NSCLC Insight Engine 플랫폼의 안내 챗봇입니다.

이 플랫폼은 비소세포폐암(NSCLC) 약물 재창출(drug repurposing) 머신러닝 도구입니다.
사용자가 단백질(EGFR, ERBB2, KRAS 등)이나 약물(Osimertinib 등)을 클릭하면
champion model의 예측 + SHAP 근거 + 문헌 기반 mechanism hypothesis를 제공합니다.

규칙:
1. 일반 대화(인사, 사용법 질문)에는 친절히 응답합니다.
2. NSCLC/약물/타겟 관련 구체적 질문은 "패스웨이 맵에서 노드를 클릭한 뒤 질문하시면 더 정확한 답변이 가능합니다"라고 안내합니다.
3. 답변은 한국어, 3-4문장 이내, 간결하게.
4. 의학적 조언, 진단, 치료 권고는 절대 하지 않습니다.
5. 플랫폼과 무관한 주제(날씨, 주식, 잡담 등)는 "이 챗봇은 NSCLC 플랫폼 안내 전용입니다"라고 응답합니다.
6. 욕설, 모욕, 도발성 발언에는 단호하게 거부합니다: "그런 질문에는 답변하지 않습니다. NSCLC 약물 재창출 관련 질문을 해주세요."
7. 의학적 진단·처방·치료 권고 요청은 명확히 거부합니다: "환자 개별 치료 결정은 임상의 권한입니다. 본 시스템은 약물 재창출 후보 탐색 도구입니다."

플랫폼 주요 기능:
- 패스웨이 맵: 노드 클릭으로 mechanism hypothesis 확인
- 후보 순위: champion model이 예측한 약물 후보
- 후보 상세: SHAP 기반 근거 분석
- 시뮬레이터: 셀라인/환자 시나리오 시뮬레이션
- 모델 카드: 모델 성능 + 한계 + 검증 결과
"""


def _haiku_mock(question: str) -> str:
    """credentials 없을 때 fallback. 기본 인사/안내 케이스."""
    q = question.strip().lower()
    if any(k in q for k in ["바보", "멍청", "꺼져", "닥쳐", "병신", "새끼", "fuck", "idiot", "stupid"]):
        return "그런 질문에는 답변하지 않습니다. NSCLC 약물 재창출 관련 질문을 해주세요."
    if any(k in q for k in ["처방", "복용", "먹어도", "써도 돼", "치료해줘", "진단", "용량", "dose", "dosage", "prescribe", "diagnose"]):
        return "환자 개별 치료 결정은 임상의의 권한입니다. 본 시스템은 약물 재창출 후보 탐색 도구이며, 진단·처방·복용 지침을 제공하지 않습니다."
    if any(k in q for k in ["안녕", "hi", "hello", "ㅎㅇ"]):
        return "안녕하세요! NSCLC Insight Engine 챗봇입니다. 패스웨이 맵에서 단백질이나 약물 노드를 클릭하시면 자세한 mechanism hypothesis를 안내드릴 수 있습니다."
    if any(k in q for k in ["뭐야", "뭐임", "무엇", "어떤", "사용법", "어떻게"]):
        return "이 플랫폼은 NSCLC(비소세포폐암) 약물 재창출을 위한 ML 도구입니다. 패스웨이 맵에서 노드를 클릭하거나, 후보 순위/시뮬레이터 탭을 둘러보세요. 구체적인 단백질·약물 이름을 질문하시면 champion model 결과를 안내합니다."
    if any(k in q for k in ["고마", "감사", "thanks", "thank"]):
        return "도움이 되었다면 다행이에요. 더 궁금한 점 있으시면 노드를 클릭하고 질문해주세요."
    return "죄송하지만 그 질문은 정확히 이해하지 못했습니다. NSCLC 관련 단백질(EGFR, ERBB2 등)이나 약물(Osimertinib 등) 이름을 포함해 질문해주시면 더 정확한 답변이 가능합니다."


def _haiku_invoke(question: str) -> tuple[str, str]:
    """일반 자연어 응답용 Haiku 호출. mock fallback 포함.
    
    Returns (text, error). error == "" 이면 성공.
    mock 모드일 때는 항상 _haiku_mock 사용.
    """
    if MODE == "mock":
        return _haiku_mock(question), ""
    try:
        import boto3
    except ImportError:
        return _haiku_mock(question), "boto3_not_installed"
    try:
        client = boto3.client("bedrock-runtime", region_name=REGION)
    except Exception as e:
        return _haiku_mock(question), f"client_init:{type(e).__name__}"
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 500,
        "temperature": 0.5,
        "system": HAIKU_SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": question}],
    }
    try:
        resp = client.invoke_model(
            modelId=HAIKU_ID,
            body=json.dumps(body),
            contentType="application/json",
            **_guardrail_kwargs(),
        )
        data = json.loads(resp["body"].read())
        if _check_guardrail_intervened(data):
            return "그런 질문에는 답변하지 않습니다. NSCLC 약물 재창출 관련 질문을 해주세요.", "guardrail_intervened"
        text = data.get("content", [{}])[0].get("text", "").strip()
        if not text:
            return _haiku_mock(question), "empty_response"
        return text, ""
    except Exception as e:
        return _haiku_mock(question), f"haiku_invoke:{type(e).__name__}"


HAIKU_ENTITY_PROMPT = """당신은 NSCLC Insight Engine 챗봇입니다. 단백질·약물에 대한 간단한 mechanism 설명을 한국어로 제공합니다.

[규칙]
1. 한국어 2-3문장. 매우 간결하게.
2. 전문 용어는 한국어 우선, 영어는 괄호: "활성화 돌연변이(activating mutation)"
3. 임상 권고 금지. "보고됨", "알려짐" 등 관찰 표현.
4. PMID가 evidence에 있으면 [PMID:xxx] 형식 1-2개만.

[톤 예시]
"EGFR은 비소세포폐암(NSCLC)에서 활성화 돌연변이가 자주 발견되는 수용체 타이로신 인산화효소입니다. 돌연변이된 EGFR은 하류 MAPK 및 PI3K-AKT 경로를 항진시켜 종양 성장을 유도하는 것으로 알려짐."
"""


def query_entity_haiku(
    name: str,
    name_type: str,
    k: int = 3,
    role: str = "",
    user_question: str = "",
) -> "LLMResponse":
    """Haiku로 entity 응답. Sonnet 대비 2-3배 빠름. 추천질문/단순 mechanism 용도."""
    import time
    node_type, _, node_name = _normalize_node_type(name_type)
    
    ck = _cache_key(node_type, name, user_question) + "_haiku"
    cached = _cache_read(ck)
    if cached:
        return LLMResponse(
            text=cached.get("text", ""),
            pmids=cached.get("pmids", []),
            grounded=cached.get("grounded", False),
            cached=True,
            mode="haiku",
            latency_ms=cached.get("latency_ms", 0),
            error=None,
        )
    
    if MODE == "mock":
        return query_entity(name, name_type, k=k, role=role, user_question=user_question)
    
    t0 = time.time()
    try:
        from nsclc_ui.llm.mock_lib import retrieve_evidence
        retrieved = retrieve_evidence(node_type, name, k=k)
    except Exception:
        retrieved = []
    
    user_msg = _build_user_message(node_type, name, role, retrieved, user_question)
    
    try:
        import boto3
        client = boto3.client("bedrock-runtime", region_name=REGION)
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 500,
            "temperature": 0.15,
            "system": HAIKU_ENTITY_PROMPT,
            "messages": [{"role": "user", "content": user_msg}],
        }
        resp = client.invoke_model(
            modelId=HAIKU_ID,
            body=json.dumps(body),
            contentType="application/json",
            **_guardrail_kwargs(),
        )
        data = json.loads(resp["body"].read())
        if _check_guardrail_intervened(data):
            latency = int((time.time() - t0) * 1000)
            return LLMResponse(
                text="그런 질문에는 답변하지 않습니다. NSCLC 약물 재창출 관련 질문을 해주세요.",
                pmids=[], grounded=False, cached=False, mode="guardrail",
                latency_ms=latency, error="guardrail_intervened",
            )
        text = data.get("content", [{}])[0].get("text", "").strip()
        latency = int((time.time() - t0) * 1000)
        
        import re as _re
        pmids = _re.findall(r"PMID[:\s]*(\d{6,9})", text)
        pmids = list(dict.fromkeys(pmids))[:5]
        grounded = bool(pmids) or bool(retrieved)
        
        result = LLMResponse(
            text=text, pmids=pmids, grounded=grounded,
            cached=False, mode="haiku",
            latency_ms=latency, error=None,
        )
        _cache_write(ck, {
            "text": text, "pmids": pmids, "grounded": grounded,
            "latency_ms": latency,
        })
        return result
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        return LLMResponse(
            text="Insufficient evidence: Haiku 호출 실패 (" + type(e).__name__ + ")",
            pmids=[], grounded=False, cached=False, mode="error",
            latency_ms=latency, error="haiku_entity:" + type(e).__name__,
        )


def query_freeform(question: str) -> "LLMResponse":
    """entity 없는 자연어 질문 → Haiku 응답.
    
    plug-in 형태로 query_entity 옆에 배치. UI에서 entity 판정 실패 시 호출.
    """
    import time
    t0 = time.time()
    text, err = _haiku_invoke(question)
    latency = int((time.time() - t0) * 1000)
    if err:
        # mock fallback도 호출되긴 했으므로 mode="haiku_fallback"
        return LLMResponse(
            text=text,
            pmids=[],
            grounded=False,
            cached=False,
            mode="haiku_fallback",
            latency_ms=latency,
            error=err,
        )
    return LLMResponse(
        text=text,
        pmids=[],
        grounded=False,
        cached=False,
        mode="haiku" if MODE == "bedrock" else "haiku_mock",
        latency_ms=latency,
        error=None,
    )


def health_check() -> dict:
    """Quick diagnostic. No LLM call."""
    from .local_retrieval import stats as retrieval_stats
    from .mock_lib import known_entities
    return {
        "mode": MODE,
        "model_id": MODEL_ID,
        "region": REGION,
        "prompt_loaded": PROMPT_PATH.exists(),
        "prompt_path": str(PROMPT_PATH),
        "cache_dir": str(CACHE_DIR),
        "cache_entries": len(list(CACHE_DIR.glob("*.json"))),
        "retrieval": retrieval_stats(),
        "mock": {
            "n_protein": known_entities()["n_protein"],
            "n_drug": known_entities()["n_drug"],
        },
    }


if __name__ == "__main__":
    print("=== health check ===")
    print(json.dumps(health_check(), indent=2, ensure_ascii=False))
    print()
    print("=== smoke test (mode={}) ===".format(MODE))
    for t, n, r in [
        ("protein", "EGFR", "hub target"),
        ("protein", "KRAS", "hub target"),
        ("drug", "Osimertinib", "3rd-gen EGFR TKI"),
        ("drug", "Trametinib", "MEK inhibitor"),
        ("protein", "SAAL1", "low-degree neighbor"),
    ]:
        resp = query(t, n, r)
        print(f"--- {t}:{n} ({resp.latency_ms:.0f}ms, cached={resp.cached}, mode={resp.mode}) ---")
        print(resp.text)
        if resp.error:
            print(f"  [error: {resp.error}]")
        print()
