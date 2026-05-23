"""Guardrail Lambda.

Tools (2):
- check_scope               : in-library + Tanimoto 임계값 → champion/analog_only/reject 모드 결정
- validate_clinical_claim   : LLM 출력의 단정/처방 단어 차단

Bedrock Guardrail 19ys87squ5mz (Version 1)와 협동.
Phase A 정책 enforcement layer.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _common import (  # noqa: E402
    TANIMOTO_REJECT_THRESHOLD,
    GUARDRAIL_ID,
    GUARDRAIL_VERSION,
    mcp_response,
    mcp_error,
    route_tool,
)

# ===== 정책 패턴 =====
BANNED_TERMS = [
    "치료한다", "치료할 수 있다",
    "효과적이다", "효과가 있다",
    "예측한다", "예측됨", "예측됩니다",
    "처방", "권장합니다",
    "확실히", "분명히",
    "cures", "treats", "predicts",
]

REQUIRED_HEDGE_TERMS = [
    "mechanism hypothesis",
    "may suggest",
    "evidence indicates",
    "기전 가설",
    "근거가 시사함",
]


# ===== Tool Handlers =====
def check_scope(
    in_library: bool,
    max_tanimoto: float | None = None,
) -> dict:
    """Scope check: in-library 여부 + Tanimoto 임계값.

    Returns:
      mode = "champion"     → in-library. champion ensemble 사용 가능.
      mode = "analog_only"  → external but T >= 0.3. analog evidence only. 확률 표시 금지.
      mode = "reject"       → external + T < 0.3. mechanism hypothesis도 거부.
    """
    if in_library:
        return mcp_response(
            result={
                "allow": True,
                "mode": "champion",
                "rationale": "in-library 매칭. champion ensemble(E6, PR-AUC_w 0.1383) 사용 가능.",
                "next_tools": ["get_ensemble_probability", "get_shap_explanation"],
            },
            tool_name="check_scope",
            source="Phase A policy",
            guardrail_id=GUARDRAIL_ID,
            guardrail_version=GUARDRAIL_VERSION,
        )

    if max_tanimoto is None:
        return mcp_error(
            "external compound인데 max_tanimoto 미제공. compute_tanimoto 먼저 호출.",
            "check_scope",
            code="MISSING_TANIMOTO",
        )

    if max_tanimoto < TANIMOTO_REJECT_THRESHOLD:
        return mcp_response(
            result={
                "allow": False,
                "mode": "reject",
                "rationale": (
                    f"Tanimoto {max_tanimoto:.3f} < {TANIMOTO_REJECT_THRESHOLD} 임계값. "
                    "구조적 유사 라이브러리 약물 부재로 mechanism hypothesis 불가."
                ),
                "next_action": "사용자에게 거부 안내. champion/analog 모두 차단.",
            },
            tool_name="check_scope",
            source="Phase A policy + LLM output policy #4",
            guardrail_id=GUARDRAIL_ID,
            guardrail_version=GUARDRAIL_VERSION,
        )

    # external but close analog (T >= 0.3)
    return mcp_response(
        result={
            "allow": True,
            "mode": "analog_only",
            "rationale": (
                f"external compound (T={max_tanimoto:.3f} ≥ {TANIMOTO_REJECT_THRESHOLD}). "
                "analog evidence only. champion 확률 표시 금지."
            ),
            "policy_evidence": "Phase A: 외부 화합물 PR-AUC 보존 5.8% (0.1162 → 0.0067)",
            "next_tools": ["search_pubmed", "extract_paper_evidence"],
            "forbidden_tools": ["get_ensemble_probability"],
        },
        tool_name="check_scope",
        source="Phase A policy",
        guardrail_id=GUARDRAIL_ID,
        guardrail_version=GUARDRAIL_VERSION,
    )


def validate_clinical_claim(claim: str) -> dict:
    """LLM 응답 텍스트의 단정/처방 단언 검증.

    - BANNED_TERMS 포함 → violations 반환
    - REQUIRED_HEDGE_TERMS 부재 시 경고

    실 운영 시 Bedrock Guardrail invoke와 결합 (현재는 로컬 패턴 매칭만).
    """
    if not claim:
        return mcp_error("claim is empty", "validate_clinical_claim", code="EMPTY_CLAIM")

    text = str(claim)
    violations = [t for t in BANNED_TERMS if t in text]
    hedges_present = [t for t in REQUIRED_HEDGE_TERMS if t in text]
    has_hedge = len(hedges_present) > 0

    valid = len(violations) == 0 and (has_hedge or len(text) < 100)
    # 짧은 텍스트(<100자)는 hedge 부재해도 통과 (단일 fact 응답)

    return mcp_response(
        result={
            "claim": text[:200] + ("..." if len(text) > 200 else ""),
            "valid": valid,
            "violations": violations,
            "hedge_terms_present": hedges_present,
            "required_terms_examples": REQUIRED_HEDGE_TERMS[:3],
            "recommendation": (
                "응답을 'mechanism hypothesis' 프레이밍으로 재작성"
                if not valid
                else "OK"
            ),
        },
        tool_name="validate_clinical_claim",
        source="local policy + Bedrock Guardrail",
        guardrail_id=GUARDRAIL_ID,
        guardrail_version=GUARDRAIL_VERSION,
    )


# ===== Lambda entry =====
TOOL_REGISTRY = {
    "check_scope": check_scope,
    "validate_clinical_claim": validate_clinical_claim,
}


def lambda_handler(event, context):  # noqa: ARG001
    return route_tool(event, TOOL_REGISTRY)


if __name__ == "__main__":
    import json
    tests = [
        {"tool": "check_scope", "params": {"in_library": True}},
        {"tool": "check_scope", "params": {"in_library": False, "max_tanimoto": 0.494}},
        {"tool": "check_scope", "params": {"in_library": False, "max_tanimoto": 0.15}},
        {"tool": "validate_clinical_claim", "params": {"claim": "Imatinib은 NSCLC를 치료한다."}},
        {"tool": "validate_clinical_claim", "params": {"claim": "Imatinib의 multi-kinase 타겟이 NSCLC mechanism hypothesis를 시사한다."}},
    ]
    for e in tests:
        print(f">>> {e}")
        print(json.dumps(lambda_handler(e, None), indent=2, ensure_ascii=False))
        print()
