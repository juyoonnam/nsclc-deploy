"""
nsclc_ui/data/paper_extractor.py

논문 본문/초록 → Bedrock으로 4항목 추출:
- drugs: 약물명 리스트 (각각 ChEMBL/DrugBank ID 가능 시 동반)
- targets: 타겟 유전자/단백질 리스트
- clinical_phase: 임상 단계 (Preclinical / Phase 1~4 / Approved / Unknown)
- response_rate: 반응률·효과 metric (ORR, PFS, OS 등; 없으면 None)

설계
----
- chatbot.py와 동일한 Bedrock + fallback 패턴 재사용 (학습 비용 0)
- JSON schema 응답 강제 → Pydantic 같은 검증 없이 타입 체크
- 추출 실패 시 PaperExtraction.is_empty()로 UI 분기

NOTE: 컨테이너에서 Bedrock 호출 불가 → 단위 테스트는 mock 기반.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 상수 (chatbot.py와 동일 패턴 — env override 가능)
# ---------------------------------------------------------------------------
DEFAULT_MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"
DEFAULT_REGION = "ap-northeast-2"
DEFAULT_TIMEOUT_SEC = 15.0   # 본문은 chatbot보다 길어서 더 김
DEFAULT_MAX_TOKENS = 800

VALID_PHASES = {
    "Preclinical", "Phase 1", "Phase 2", "Phase 3", "Phase 4",
    "Approved", "Unknown",
}


# ---------------------------------------------------------------------------
# 데이터 구조
# ---------------------------------------------------------------------------
@dataclass
class ExtractedDrug:
    name: str
    chembl_id: Optional[str] = None     # 본문에 명시된 경우만
    role: Optional[str] = None          # "experimental" / "comparator" / "approved" 등


@dataclass
class ExtractedTarget:
    symbol: str                         # gene symbol (EGFR, KRAS 등)
    full_name: Optional[str] = None     # "Epidermal growth factor receptor"


@dataclass
class ExtractedResponseRate:
    metric: str                         # "ORR" / "PFS" / "OS" / "DCR" / 자유 텍스트
    value: str                          # "63%" / "9.2 months" / "HR 0.41"
    cohort: Optional[str] = None        # "first-line EGFR-mutant NSCLC" 등


@dataclass
class PaperExtraction:
    """4항목 추출 결과."""
    drugs: list[ExtractedDrug] = field(default_factory=list)
    targets: list[ExtractedTarget] = field(default_factory=list)
    clinical_phase: str = "Unknown"     # VALID_PHASES 중 하나
    response_rates: list[ExtractedResponseRate] = field(default_factory=list)
    raw_summary: Optional[str] = None   # LLM의 1-2문장 요약 (시연용)
    fallback_reason: Optional[str] = None
    confidence: float = 0.7

    def is_empty(self) -> bool:
        return not (self.drugs or self.targets or self.response_rates)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExtractorConfig:
    model_id: str = DEFAULT_MODEL_ID
    region: str = DEFAULT_REGION
    timeout_sec: float = DEFAULT_TIMEOUT_SEC
    max_tokens: int = DEFAULT_MAX_TOKENS


class _BedrockUnavailable(Exception):
    """fallback marker."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def extract_from_paper(
    title: str,
    text: str,
    config: Optional[ExtractorConfig] = None,
) -> PaperExtraction:
    """논문 텍스트 → 4항목 구조화 추출.

    Args:
        title: 논문 제목 (LLM 컨텍스트용)
        text: 본문 또는 초록 (이미 길이 cap 적용된 상태)
        config: Bedrock 설정. None이면 default.

    Returns:
        PaperExtraction. 실패 시 fallback_reason 채워진 빈 결과.
    """
    if not text or not text.strip():
        return PaperExtraction(
            fallback_reason="입력 텍스트 비어있음",
            confidence=0.0,
        )

    cfg = config or ExtractorConfig()
    try:
        return _call_bedrock_extractor(title, text, cfg)
    except _BedrockUnavailable as e:
        logger.warning("[extractor] Bedrock unavailable: %s — fallback", e)
        return PaperExtraction(
            fallback_reason=str(e),
            confidence=0.0,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("[extractor] unexpected: %s", e)
        return PaperExtraction(
            fallback_reason=f"unexpected: {type(e).__name__}",
            confidence=0.0,
        )


# ---------------------------------------------------------------------------
# Bedrock 호출
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """You are a biomedical paper analyst for an NSCLC drug repurposing system.

Read the [Paper] and extract EXACTLY these 4 fields. Output ONLY a JSON object,
no preamble, no markdown fences:

{
  "drugs": [{"name": "drug name", "chembl_id": "CHEMBL... or null", "role": "experimental|comparator|approved|null"}],
  "targets": [{"symbol": "GENE_SYMBOL", "full_name": "full name or null"}],
  "clinical_phase": "Preclinical|Phase 1|Phase 2|Phase 3|Phase 4|Approved|Unknown",
  "response_rates": [{"metric": "ORR|PFS|OS|DCR|...", "value": "63%|9.2 months|HR 0.41", "cohort": "context or null"}],
  "raw_summary": "1-2 sentence Korean summary"
}

Rules:
- Use ONLY information from the paper. Do not infer or guess.
- If a field has no info, use empty list [] or "Unknown".
- Gene symbols must be uppercase official symbols (EGFR not egfr).
- For clinical_phase, pick the SINGLE highest stage mentioned for the main drug.
- response_rates: extract ALL numeric efficacy metrics with their context.
- raw_summary in Korean, focus on what the paper proves about the drug-target.
- If the paper is unrelated to NSCLC/lung cancer, set all lists empty and put reason in raw_summary."""


def _call_bedrock_extractor(
    title: str,
    text: str,
    cfg: ExtractorConfig,
) -> PaperExtraction:
    try:
        import boto3
        from botocore.config import Config as BotoConfig
        from botocore.exceptions import (
            BotoCoreError, ClientError,
            EndpointConnectionError, ReadTimeoutError,
        )
    except ImportError as e:
        raise _BedrockUnavailable(f"boto3 미설치: {e}")

    region = os.environ.get("BEDROCK_REGION", cfg.region)
    model_id = os.environ.get("BEDROCK_MODEL_ID", cfg.model_id)

    boto_config = BotoConfig(
        read_timeout=cfg.timeout_sec,
        connect_timeout=cfg.timeout_sec,
        retries={"max_attempts": 1},
    )

    try:
        client = boto3.client("bedrock-runtime", region_name=region, config=boto_config)
    except Exception as e:
        raise _BedrockUnavailable(f"boto3 client 생성 실패: {e}")

    user_msg = f"[Paper Title]\n{title}\n\n[Paper]\n{text}"

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": cfg.max_tokens,
        "system": _SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_msg}],
        "temperature": 0.0,  # 추출은 deterministic
    }

    t0 = time.time()
    try:
        resp = client.invoke_model(
            modelId=model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
    except (EndpointConnectionError, ReadTimeoutError) as e:
        raise _BedrockUnavailable(f"Bedrock timeout: {e}")
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "Unknown")
        raise _BedrockUnavailable(f"Bedrock ClientError({code}): {e}")
    except BotoCoreError as e:
        raise _BedrockUnavailable(f"Bedrock BotoCoreError: {e}")

    elapsed_ms = int((time.time() - t0) * 1000)
    logger.info("[extractor] Bedrock %dms", elapsed_ms)

    # 응답 파싱
    try:
        payload = json.loads(resp["body"].read())
        text_blocks = [
            b.get("text", "") for b in payload.get("content", [])
            if b.get("type") == "text"
        ]
        full_text = "".join(text_blocks).strip()
    except (KeyError, ValueError, TypeError, AttributeError) as e:
        raise _BedrockUnavailable(f"응답 파싱 실패: {e}")

    if not full_text:
        raise _BedrockUnavailable("Bedrock 응답 비어있음")

    return _parse_json_to_extraction(full_text)


def _parse_json_to_extraction(llm_text: str) -> PaperExtraction:
    """LLM JSON 응답 → PaperExtraction. 강건한 파싱 + schema validation."""
    # 마크다운 fence 제거 (모델이 가끔 ```json 붙임)
    cleaned = llm_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise _BedrockUnavailable(f"JSON 파싱 실패: {e}")

    if not isinstance(data, dict):
        raise _BedrockUnavailable(f"응답이 dict 아님: {type(data).__name__}")

    # drugs
    drugs = []
    for d in (data.get("drugs") or []):
        if not isinstance(d, dict):
            continue
        name = d.get("name")
        if not name or not isinstance(name, str):
            continue
        drugs.append(ExtractedDrug(
            name=name.strip(),
            chembl_id=_safe_str(d.get("chembl_id")),
            role=_safe_str(d.get("role")),
        ))

    # targets
    targets = []
    for t in (data.get("targets") or []):
        if not isinstance(t, dict):
            continue
        symbol = t.get("symbol")
        if not symbol or not isinstance(symbol, str):
            continue
        targets.append(ExtractedTarget(
            symbol=symbol.strip().upper(),
            full_name=_safe_str(t.get("full_name")),
        ))

    # clinical_phase — None/비문자열 입력 가드
    phase_raw = data.get("clinical_phase", "Unknown")
    phase = phase_raw if isinstance(phase_raw, str) else "Unknown"
    if phase not in VALID_PHASES:
        normalized = phase.strip().title()
        phase_lower = phase.lower()
        # "Phase 3" / "PHASE 3" / "phase 3" 모두 매치되도록
        for valid in VALID_PHASES:
            if valid.lower() == phase_lower:
                phase = valid
                break
        else:
            phase = normalized if normalized in VALID_PHASES else "Unknown"

    # response_rates
    rates = []
    for r in (data.get("response_rates") or []):
        if not isinstance(r, dict):
            continue
        metric = r.get("metric")
        value = r.get("value")
        if not metric or not value:
            continue
        rates.append(ExtractedResponseRate(
            metric=str(metric).strip(),
            value=str(value).strip(),
            cohort=_safe_str(r.get("cohort")),
        ))

    return PaperExtraction(
        drugs=drugs,
        targets=targets,
        clinical_phase=phase,
        response_rates=rates,
        raw_summary=_safe_str(data.get("raw_summary")),
        fallback_reason=None,
        confidence=0.7,
    )


def _safe_str(v) -> Optional[str]:
    """LLM이 null/None/빈 문자열을 다양한 형태로 줄 때 normalize."""
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        if not s or s.lower() in ("null", "none", "n/a", "unknown"):
            return None
        return s
    return str(v)
