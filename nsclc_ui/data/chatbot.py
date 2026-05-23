"""
nsclc_ui/data/chatbot.py

Pathway 컨텍스트 기반 챗봇 — AWS Bedrock (Claude Haiku) + rule-based fallback.

핵심 설계
---------
1. **컨텍스트 강제**: gene + 해당 노드의 compound/외부/임상 정보만 LLM에 전달.
   off-topic 질문은 거부. 환각 차단.
2. **fallback 4트리거**:
   - boto3 미설치/import 실패
   - Bedrock 인증·권한 실패
   - HTTP timeout (5초)
   - 응답 파싱 실패
3. **출력 스키마 freeze**:
   {type, text, evidence_refs, confidence, fallback_reason}
   type ∈ {"answer", "no_info", "off_topic", "fallback_rule"}
4. **비용 cap**: max_tokens=500, 입력 system prompt + user 합쳐 ~4k chars.

사용 예시
---------
>>> from nsclc_ui.data.chatbot import ChatbotContext, answer_question
>>> ctx = ChatbotContext(
...     gene_symbol="EGFR",
...     pathway_id="hsa05223",
...     pathway_name="NSCLC",
...     internal_compounds=[{"compound_id": "CHEMBL103667", "rank_score": 0.85}],
...     external_chembl=[{"chembl_id": "CHEMBL5805801", "pchembl": 10.43}],
...     clinical_drugs=[{"name": "AFATINIB", "max_phase": 4, "nsclc": True}],
... )
>>> resp = answer_question("EGFR 억제제 중 NSCLC Phase 3 이상은?", ctx)
>>> resp.type, resp.fallback_reason
('answer', None)  # Bedrock 성공 시 / fallback 시 ('fallback_rule', '...')

NOTE: 컨테이너에서 Bedrock 호출 불가 → 단위 테스트는 mock 기반.
       실제 응답 호환성은 사용자 로컬 검증 필요 (S 시리즈 동일 패턴).
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Literal, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------
DEFAULT_MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"
DEFAULT_REGION = "ap-northeast-2"
DEFAULT_TIMEOUT_SEC = 5.0
DEFAULT_MAX_TOKENS = 500
MAX_USER_QUESTION_CHARS = 1000
MAX_CONTEXT_CHARS = 3500  # system prompt 안 컨텍스트 부분 cap

ResponseType = Literal["answer", "no_info", "off_topic", "fallback_rule"]


# ---------------------------------------------------------------------------
# 데이터 구조
# ---------------------------------------------------------------------------
@dataclass
class ChatbotContext:
    """노드 클릭 시점의 패스웨이 컨텍스트.

    pathway_map.py에서 cytoscape 노드 클릭 → 해당 gene + ChEMBL/OT 호출 결과를
    이 dataclass로 묶어서 챗봇에 전달.
    """
    gene_symbol: str
    pathway_id: str = "hsa05223"
    pathway_name: str = "NSCLC"
    gene_name: Optional[str] = None  # 예: "Epidermal growth factor receptor"
    modality: Optional[str] = None   # 5-modality 중 가장 가까운 것 (옵션)
    # 우리 33,057개 중 이 gene 타겟팅 + rank_score 상위
    internal_compounds: list[dict[str, Any]] = field(default_factory=list)
    # ChEMBL 외부 (학습에 안 들어간 화합물)
    external_chembl: list[dict[str, Any]] = field(default_factory=list)
    # OpenTargets 임상 약물 (NSCLC 적응증 우선)
    clinical_drugs: list[dict[str, Any]] = field(default_factory=list)
    # ChEMBL alone 흡수율 (정직성 메시지용, 옵션)
    chembl_coverage_pct: Optional[float] = None


@dataclass
class BedrockConfig:
    model_id: str = DEFAULT_MODEL_ID
    region: str = DEFAULT_REGION
    timeout_sec: float = DEFAULT_TIMEOUT_SEC
    max_tokens: int = DEFAULT_MAX_TOKENS


@dataclass
class ChatbotResponse:
    type: ResponseType
    text: str
    evidence_refs: list[dict[str, Any]]  # [{"source": "internal", "id": "CHEMBL...", ...}, ...]
    confidence: float                    # 0.0~1.0 (rule-based는 0.4 고정)
    fallback_reason: Optional[str] = None  # Bedrock 성공 시 None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def answer_question(
    user_question: str,
    context: ChatbotContext,
    bedrock_config: Optional[BedrockConfig] = None,
) -> ChatbotResponse:
    """챗봇 메인 엔트리.

    1. 입력 검증 (길이, off-topic 빠른 차단)
    2. Bedrock 시도
    3. 실패 시 rule-based fallback
    """
    # ---- 입력 검증 ----
    if not user_question or not user_question.strip():
        return ChatbotResponse(
            type="off_topic",
            text="질문을 입력해주세요.",
            evidence_refs=[],
            confidence=1.0,
        )

    user_question = user_question.strip()[:MAX_USER_QUESTION_CHARS]

    # 빠른 off-topic 차단: gene/compound/pathway/약물/임상 키워드 없으면 거부
    # (LLM 호출 비용 아끼기 + 환각 방지 1차 방어)
    if _is_off_topic(user_question, context):
        return _off_topic_response(context)

    # ---- Bedrock 시도 ----
    cfg = bedrock_config or BedrockConfig()
    try:
        return _call_bedrock(user_question, context, cfg)
    except _BedrockUnavailable as e:
        # fallback 직전 strict guard — LLM 못 거르므로 여기서 한번 더.
        if _is_off_topic_strict(user_question, context):
            return _off_topic_response(context)
        logger.warning("[chatbot] Bedrock unavailable: %s — fallback", e)
        return _rule_based_fallback(user_question, context, reason=str(e))
    except Exception as e:  # noqa: BLE001 — 마지막 안전망
        logger.exception("[chatbot] unexpected error: %s — fallback", e)
        if _is_off_topic_strict(user_question, context):
            return _off_topic_response(context)
        return _rule_based_fallback(
            user_question, context, reason=f"unexpected: {type(e).__name__}"
        )


# ---------------------------------------------------------------------------
# Off-topic 차단
# ---------------------------------------------------------------------------
_DOMAIN_KEYWORDS = {
    # 약물·활성 (의문사·"추천" 같은 일반어 제거 — false negative 차단)
    "약물", "drug", "compound", "화합물", "억제", "inhibitor", "agonist",
    "antagonist", "ic50", "pic50", "활성", "potency", "binding",
    # 임상
    "임상", "phase", "승인", "approval", "approved", "trial", "fda", "치료",
    # 타겟·생물
    "타겟", "target", "gene", "유전자", "단백질", "protein", "kinase",
    "변이", "mutation", "resistance", "내성",
    # 패스웨이·질환
    "패스웨이", "pathway", "nsclc", "암", "cancer", "tumor", "lung",
    # 우리 시스템
    "rank", "modality", "score", "후보", "candidate",
}

# strict 모드용 — Bedrock 죽은 fallback 경로에서 "domain + anchor" 둘 다 요구.
# anchor는 도메인 정체성을 강하게 박는 단어들.
_ANCHOR_KEYWORDS = {
    "nsclc", "비소세포폐암", "pathway", "패스웨이", "chembl", "opentarget",
    "임상", "phase", "target", "타겟", "gene", "유전자", "drug", "약물",
    "compound", "화합물",
}

# 명백한 일상어 BLOCKLIST — 컨텍스트 있어도 이건 명백히 off-topic.
# 짧게 유지 (false positive 방지). substring 매치이므로 한국어는 어절 단위로.
_BLOCKLIST_KEYWORDS = {
    "점심", "저녁", "아침", "식사", "메뉴", "맛집",
    "날씨", "기온", "비와", "눈와",
    "주식", "코인", "비트코인", "환율", "부동산",
    "여행", "항공권", "호텔", "관광",
    "영화", "드라마", "게임", "음악", "노래", "아이돌",
    "축구", "야구", "농구",
    "lunch", "dinner", "breakfast", "weather", "stock", "movie", "music", "travel",
}


def _extract_context_terms(context: ChatbotContext) -> set[str]:
    """컨텍스트의 고유명사(gene/compound/drug 이름)를 추출.

    질문에 컨텍스트 안 항목명이 들어가 있으면 1차/strict 모두 통과시켜
    "AFATINIB 부작용은?" 같은 정상 질문 차단을 방지.
    """
    terms: set[str] = {
        str(context.gene_symbol or "").lower(),
        str(context.pathway_id or "").lower(),
        str(context.pathway_name or "").lower(),
    }
    for c in context.internal_compounds[:10]:
        cid = str(c.get("compound_id", "")).lower()
        if cid:
            terms.add(cid)
    for c in context.external_chembl[:10]:
        cid = str(c.get("chembl_id", "")).lower()
        if cid:
            terms.add(cid)
    for d in context.clinical_drugs[:10]:
        name = str(d.get("name", "")).lower()
        if name:
            terms.add(name)
    return {t for t in terms if len(t) >= 3}


def _has_meaningful_context(context: ChatbotContext) -> bool:
    """노드 클릭으로 internal/external/clinical 중 하나라도 데이터가 채워졌나."""
    return bool(
        context.internal_compounds
        or context.external_chembl
        or context.clinical_drugs
    )


def _is_off_topic(question: str, context: ChatbotContext) -> bool:
    """1차 필터 — 관대 정책 (컨텍스트 있으면 기본 통과).

    정책:
    1. BLOCKLIST 매치 (점심/날씨/주식 등) → 차단 (컨텍스트 무관)
    2. gene_symbol/context terms 매치 → 통과 (fast path)
    3. 컨텍스트가 의미 있으면 (노드 클릭됨) → 통과 (LLM이 모호 질문도 노드 기준 해석)
    4. else → 차단 (컨텍스트 없으면 도메인 키워드만으로는 불충분)

    Bedrock 정상 경로에서 LLM이 시스템 프롬프트로 2차 거름.
    """
    q_lower = question.lower()

    # 1. BLOCKLIST 우선 (컨텍스트 무관 강한 차단)
    if any(kw in q_lower for kw in _BLOCKLIST_KEYWORDS):
        return True

    # 2. fast path
    if context.gene_symbol.lower() in q_lower:
        return False
    if any(t in q_lower for t in _extract_context_terms(context)):
        return False

    # 3. 컨텍스트 있으면 모호 질문도 통과 (LLM에 위임)
    if _has_meaningful_context(context):
        return False

    # 4. 컨텍스트 없으면 차단 (도메인 키워드만으로는 불충분)
    return True


def _is_off_topic_strict(question: str, context: ChatbotContext) -> bool:
    """fallback 경로용 — 1차와 동일 정책.

    fallback rule-based가 컨텍스트 데이터 dump로 모호 질문에도 답함.
    예: "이건 뭐냐" + EGFR 컨텍스트 → "EGFR 관련 정보 (규칙 기반): 내부 후보..."
    별도 strict 가드 불필요. BLOCKLIST만 통과시키지 않음.
    """
    return _is_off_topic(question, context)


def _off_topic_response(context: ChatbotContext) -> ChatbotResponse:
    """off-topic 거부 응답 (코드 중복 제거용 헬퍼).

    원본 1차 필터 + Bedrock 실패 시 strict 가드 + generic Exception 가드,
    총 3곳에서 동일 응답 반환하므로 헬퍼로 추출.
    """
    return ChatbotResponse(
        type="off_topic",
        text=(
            f"이 챗봇은 {context.gene_symbol} 노드와 관련된 약물/타겟/임상 "
            "정보만 답변합니다. 다른 주제는 답변할 수 없습니다."
        ),
        evidence_refs=[],
        confidence=1.0,
    )


# ---------------------------------------------------------------------------
# Bedrock 호출
# ---------------------------------------------------------------------------
class _BedrockUnavailable(Exception):
    """boto3/credential/timeout/parse 실패의 공통 마커."""


def _call_bedrock(
    user_question: str,
    context: ChatbotContext,
    cfg: BedrockConfig,
) -> ChatbotResponse:
    # boto3 import — 실패 시 fallback
    try:
        import boto3
        from botocore.config import Config as BotoConfig
        from botocore.exceptions import (
            BotoCoreError,
            ClientError,
            EndpointConnectionError,
            ReadTimeoutError,
        )
    except ImportError as e:
        raise _BedrockUnavailable(f"boto3 미설치: {e}")

    # 환경변수 override 허용 (배포 시 region 변경 등)
    region = os.environ.get("BEDROCK_REGION", cfg.region)
    model_id = os.environ.get("BEDROCK_MODEL_ID", cfg.model_id)

    boto_config = BotoConfig(
        read_timeout=cfg.timeout_sec,
        connect_timeout=cfg.timeout_sec,
        retries={"max_attempts": 1},  # 발표 중 hang 방지
    )

    try:
        client = boto3.client("bedrock-runtime", region_name=region, config=boto_config)
    except Exception as e:  # NoRegionError 등
        raise _BedrockUnavailable(f"boto3 client 생성 실패: {e}")

    system_prompt, evidence_refs = _build_system_prompt(context)

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": cfg.max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_question}],
        "temperature": 0.2,  # 환각 억제
    }

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
        # AccessDenied / ValidationException / ThrottlingException 등
        code = e.response.get("Error", {}).get("Code", "Unknown")
        raise _BedrockUnavailable(f"Bedrock ClientError({code}): {e}")
    except BotoCoreError as e:
        raise _BedrockUnavailable(f"Bedrock BotoCoreError: {e}")

    # 응답 파싱
    try:
        payload = json.loads(resp["body"].read())
        # Anthropic Messages API 응답: {"content": [{"type": "text", "text": "..."}], ...}
        text_blocks = [
            b.get("text", "")
            for b in payload.get("content", [])
            if b.get("type") == "text"
        ]
        text = "\n".join(t for t in text_blocks if t).strip()
        if not text:
            raise _BedrockUnavailable("Bedrock 응답에 text 없음")
    except (KeyError, ValueError, TypeError, AttributeError) as e:
        raise _BedrockUnavailable(f"응답 파싱 실패: {e}")

    # type 추정: 응답에 "정보 없음"/"모름" 신호 있으면 no_info
    response_type: ResponseType = "answer"
    if _looks_like_no_info(text):
        response_type = "no_info"

    return ChatbotResponse(
        type=response_type,
        text=text,
        evidence_refs=evidence_refs,
        confidence=0.7,  # Bedrock 성공 시 기본 신뢰도
        fallback_reason=None,
    )


def _looks_like_no_info(text: str) -> bool:
    markers = [
        "정보가 없",
        "정보는 없",
        "알 수 없",
        "주어진 컨텍스트에",
        "제공된 정보",
        "no information",
        "not available",
    ]
    t = text.lower()
    return any(m.lower() in t for m in markers)


# ---------------------------------------------------------------------------
# System prompt 조립
# ---------------------------------------------------------------------------
def _build_system_prompt(context: ChatbotContext) -> tuple[str, list[dict[str, Any]]]:
    """LLM에 전달할 system prompt + 답변 끝에 첨부할 evidence_refs."""
    refs: list[dict[str, Any]] = []

    lines: list[str] = [
        "당신은 NSCLC(비소세포폐암) 약물 재창출 시스템의 패스웨이 분석 어시스턴트입니다.",
        "다음 규칙을 엄격히 따르세요:",
        "1. 아래 [컨텍스트]에 명시된 정보만 사용해서 답변하세요.",
        "2. 컨텍스트에 없는 사실은 추측하지 말고 '제공된 컨텍스트에 정보 없음'이라 답하세요.",
        "3. 약물명·ChEMBL ID·임상 단계는 컨텍스트에 적힌 그대로 인용하세요.",
        "4. 한국어로 3~5문장 이내 간결하게 답하세요.",
        "5. NSCLC와 무관한 일반 의학 상담·진단·복약 지도는 거부하세요.",
        "6. 사용자 질문이 모호하거나 '이것/이거/뭐' 같은 지시어를 쓰면, "
        "[컨텍스트]의 선택된 유전자를 기준으로 해석해서 답하세요.",
        "",
        "[컨텍스트]",
        f"- 패스웨이: KEGG {context.pathway_id} ({context.pathway_name})",
        f"- 선택된 유전자: {context.gene_symbol}"
        + (f" ({context.gene_name})" if context.gene_name else ""),
    ]

    if context.modality:
        lines.append(f"- 가장 가까운 modality: {context.modality}")

    # Internal compounds (우리 학습 데이터 + rank)
    if context.internal_compounds:
        lines.append("")
        lines.append(f"- 내부 후보 (우리 33,057개 중 {context.gene_symbol} 타겟팅, rank 상위):")
        for c in context.internal_compounds[:5]:
            cid = c.get("compound_id", "?")
            rank = c.get("rank_score")
            modality = c.get("modality", "")
            rank_str = f"rank={rank:.3f}" if isinstance(rank, (int, float)) else "rank=?"
            extra = f", modality={modality}" if modality else ""
            lines.append(f"    · {cid} ({rank_str}{extra})")
            refs.append({"source": "internal", "id": cid, "rank_score": rank})

    # External ChEMBL (학습에 없던 화합물)
    if context.external_chembl:
        lines.append("")
        lines.append(f"- 외부 ChEMBL 활성 화합물 (학습 데이터 외, pIC50 상위):")
        for c in context.external_chembl[:5]:
            cid = c.get("chembl_id", "?")
            pic50 = c.get("pchembl")
            pic50_str = f"pIC50={pic50:.2f}" if isinstance(pic50, (int, float)) else "pIC50=?"
            lines.append(f"    · {cid} ({pic50_str})")
            refs.append({"source": "external_chembl", "id": cid, "pchembl": pic50})

    # 흡수율 정직성 메시지
    if context.chembl_coverage_pct is not None:
        if context.chembl_coverage_pct >= 90:
            lines.append(
                f"- 주의: ChEMBL 흡수율 {context.chembl_coverage_pct:.1f}% — "
                "우리 학습 source = ChEMBL이므로 외부 검증 한계 (Open Targets로 보완)."
            )

    # OpenTargets 임상 약물
    if context.clinical_drugs:
        lines.append("")
        lines.append("- OpenTargets 임상 약물 (NSCLC 적응증 우선):")
        for d in context.clinical_drugs[:5]:
            name = d.get("name", "?")
            phase = d.get("max_phase", "?")
            is_nsclc = d.get("nsclc", False)
            tag = " [NSCLC]" if is_nsclc else ""
            lines.append(f"    · {name} (phase={phase}{tag})")
            refs.append({
                "source": "opentargets",
                "name": name,
                "max_phase": phase,
                "nsclc": is_nsclc,
            })

    if not (context.internal_compounds or context.external_chembl or context.clinical_drugs):
        lines.append("")
        lines.append("- (이 노드에 연결된 약물 정보 없음 — 사용자가 다른 노드를 선택하도록 안내)")

    prompt = "\n".join(lines)
    # 길이 cap (안전망)
    if len(prompt) > MAX_CONTEXT_CHARS:
        prompt = prompt[:MAX_CONTEXT_CHARS] + "\n[... 컨텍스트 길이 초과로 절단됨 ...]"
    return prompt, refs


# ---------------------------------------------------------------------------
# Rule-based fallback
# ---------------------------------------------------------------------------
def _rule_based_fallback(
    user_question: str,
    context: ChatbotContext,
    reason: str,
) -> ChatbotResponse:
    """Bedrock 실패 시 컨텍스트 기반 정형 응답.

    LLM 없이도 발표 시연이 깨지지 않도록 함. 답변 품질은 낮지만
    "처리 중 → 무응답"보다 훨씬 낫다.
    """
    refs: list[dict[str, Any]] = []
    parts: list[str] = []

    g = context.gene_symbol
    parts.append(f"**{g}** 관련 정보 (규칙 기반 응답):")

    # Internal
    if context.internal_compounds:
        top = context.internal_compounds[:3]
        items = []
        for c in top:
            cid = c.get("compound_id", "?")
            rank = c.get("rank_score")
            rank_str = f"{rank:.3f}" if isinstance(rank, (int, float)) else "?"
            items.append(f"{cid}(rank={rank_str})")
            refs.append({"source": "internal", "id": cid, "rank_score": rank})
        parts.append(f"- 내부 후보 Top3: {', '.join(items)}")

    # External
    if context.external_chembl:
        top = context.external_chembl[:3]
        items = []
        for c in top:
            cid = c.get("chembl_id", "?")
            pic = c.get("pchembl")
            pic_str = f"{pic:.2f}" if isinstance(pic, (int, float)) else "?"
            items.append(f"{cid}(pIC50={pic_str})")
            refs.append({"source": "external_chembl", "id": cid, "pchembl": c.get("pchembl")})
        parts.append(f"- 외부 ChEMBL 활성 Top3: {', '.join(items)}")

    # Clinical
    if context.clinical_drugs:
        nsclc_drugs = [d for d in context.clinical_drugs if d.get("nsclc")]
        if nsclc_drugs:
            top = nsclc_drugs[:3]
            items = []
            for d in top:
                name = d.get("name", "?")
                phase = d.get("max_phase", "?")
                items.append(f"{name}(phase={phase})")
                refs.append({
                    "source": "opentargets", "name": name,
                    "max_phase": phase, "nsclc": True,
                })
            parts.append(f"- NSCLC 적응증 임상 약물 Top3: {', '.join(items)}")

    if context.chembl_coverage_pct is not None and context.chembl_coverage_pct >= 90:
        parts.append(
            f"- 주의: ChEMBL 흡수율 {context.chembl_coverage_pct:.1f}% — "
            "우리 source와 동일하므로 외부 검증 한계."
        )

    if len(parts) == 1:  # 헤더만
        parts.append(f"- 이 노드({g})에 연결된 약물 정보가 없습니다.")

    parts.append("")
    parts.append("(LLM 응답이 일시 불가하여 정형 데이터로 답변했습니다.)")

    return ChatbotResponse(
        type="fallback_rule",
        text="\n".join(parts),
        evidence_refs=refs,
        confidence=0.4,
        fallback_reason=reason,
    )


# ---------------------------------------------------------------------------
# Helper: pathway_map.py 콜백에서 호출 편하게
# ---------------------------------------------------------------------------
def build_context_from_node(
    gene_symbol: str,
    *,
    gene_name: Optional[str] = None,
    internal_df_records: Optional[list[dict]] = None,
    external_chembl_records: Optional[list[dict]] = None,
    ot_drug_records: Optional[list[dict]] = None,
    chembl_coverage_pct: Optional[float] = None,
) -> ChatbotContext:
    """pathway_map.py에서 노드 클릭 콜백 결과를 그대로 넣어 ChatbotContext 생성.

    인자 이름은 pathway_map.py 변수명에 맞게 추후 조정.
    """
    return ChatbotContext(
        gene_symbol=gene_symbol,
        gene_name=gene_name,
        internal_compounds=internal_df_records or [],
        external_chembl=external_chembl_records or [],
        clinical_drugs=ot_drug_records or [],
        chembl_coverage_pct=chembl_coverage_pct,
    )
