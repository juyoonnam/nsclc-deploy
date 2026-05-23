"""Knowledge Base Lambda — 3 tools (v2 / 2026-05-22 D-5).

- search_pubmed                   : PubMed E-utilities (esearch + esummary) — 최근 논문 검색
- extract_paper_evidence          : efetch abstract + question 기반 hit 문장 추출
- search_clinical_knowledge_base  : Bedrock KB retrieve (FDA + ESMO + FLAURA2, Titan v2)
                                    임상 단정 응답 전 grounding 강제 (정책 8)

PubMed: 발표 데모용 E-utilities 직접 호출 (urllib, 의존성 없음).
Bedrock KB: PHZTHHSMZC (us-east-1, S3 Vectors, 5 PDFs, Titan v2 1024 dim).

NCBI E-utilities:
- esearch.fcgi: query → PMID list (relevance sort)
- esummary.fcgi: PMID list → title/authors/year/journal/doi
- efetch.fcgi: PMID → abstract text
Rate limit: 3 req/sec (no API key). AWS Lambda는 외부 인터넷 접근 가능 (VPC 안 쓸 때).

Bedrock KB:
- bedrock-agent-runtime.retrieve API
- KB 내용: FDA label (gefitinib/osimertinib/sotorasib) + ESMO PAGA 2024 + PMC FLAURA2
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _common import (  # noqa: E402
    KNOWLEDGE_BASE_ID, BEDROCK_REGION,
    mcp_response, mcp_error, route_tool,
)

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
USER_AGENT = "NSCLC-Insight-Engine/1.0"
HTTP_TIMEOUT = 10


def _http_get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read())


def _http_get_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _esearch_pubmed(term: str, retmax: int = 10, year_min: int | None = 2020) -> list[str]:
    full_term = f"{term} AND {year_min}:3000[pdat]" if year_min else term
    params = {
        "db": "pubmed",
        "term": full_term,
        "retmax": retmax,
        "retmode": "json",
        "sort": "relevance",
    }
    url = f"{EUTILS_BASE}/esearch.fcgi?{urllib.parse.urlencode(params)}"
    data = _http_get_json(url)
    return data.get("esearchresult", {}).get("idlist", [])


def _esummary_pubmed(pmids: list[str]) -> dict:
    if not pmids:
        return {}
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "json",
    }
    url = f"{EUTILS_BASE}/esummary.fcgi?{urllib.parse.urlencode(params)}"
    data = _http_get_json(url)
    return data.get("result", {})


def _efetch_abstract(pmid: str) -> str:
    params = {
        "db": "pubmed",
        "id": pmid,
        "rettype": "abstract",
        "retmode": "text",
    }
    url = f"{EUTILS_BASE}/efetch.fcgi?{urllib.parse.urlencode(params)}"
    return _http_get_text(url)


# ===== Bedrock client (lazy init) =====
_BEDROCK_CLIENT = None


def _get_bedrock_client():
    """boto3 bedrock-agent-runtime client. Lambda cold start 시 1회 init."""
    global _BEDROCK_CLIENT
    if _BEDROCK_CLIENT is None:
        import boto3
        _BEDROCK_CLIENT = boto3.client(
            "bedrock-agent-runtime", region_name=BEDROCK_REGION
        )
    return _BEDROCK_CLIENT


# ===== Tools =====

def search_pubmed(
    query: str,
    top_k: int = 5,
    year_min: int | None = 2020,
) -> dict:
    """PubMed search (relevance sort, 최신 N년 필터).

    LLM이 hallucination 없이 임상 근거 인용할 때 사용.
    """
    if not query or not query.strip():
        return mcp_error(
            "query 비어있음. 예: 'NSCLC EGFR T790M osimertinib resistance'",
            "search_pubmed", code="EMPTY_QUERY",
        )

    try:
        pmids = _esearch_pubmed(query, retmax=top_k, year_min=year_min)
    except Exception as e:
        return mcp_error(
            f"PubMed esearch failed: {type(e).__name__}: {e}",
            "search_pubmed", code="ESEARCH_FAILED",
        )

    if not pmids:
        return mcp_response(
            result={
                "query": query, "top_k": top_k, "year_min": year_min,
                "papers": [], "count": 0,
                "note": "검색 결과 없음. query 단순화 또는 year_min 완화 시도.",
            },
            tool_name="search_pubmed",
            source="PubMed E-utilities",
        )

    try:
        summary = _esummary_pubmed(pmids)
    except Exception as e:
        return mcp_error(
            f"PubMed esummary failed: {type(e).__name__}: {e}",
            "search_pubmed", code="ESUMMARY_FAILED",
        )

    papers = []
    for pmid in pmids:
        p = summary.get(pmid, {})
        if not p:
            continue
        authors = [a.get("name") for a in p.get("authors", [])][:3]
        doi = next(
            (aid.get("value") for aid in p.get("articleids", [])
             if aid.get("idtype") == "doi"),
            None,
        )
        papers.append({
            "pmid": pmid,
            "title": p.get("title"),
            "authors_first3": authors,
            "year": (p.get("pubdate") or "")[:4],
            "journal": p.get("source"),
            "doi": doi,
            "pubtype": p.get("pubtype"),
            "citation_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        })

    return mcp_response(
        result={
            "query": query,
            "top_k": top_k,
            "year_min": year_min,
            "papers": papers,
            "count": len(papers),
        },
        tool_name="search_pubmed",
        source="PubMed E-utilities (esearch + esummary)",
    )


def extract_paper_evidence(pmid: str, question: str | None = None) -> dict:
    """PMID → abstract + question 기반 hit 문장 (keyword overlap).

    extract_paper_evidence가 LLM의 hedging 답변에 인용 근거로 사용.
    """
    if not pmid:
        return mcp_error("pmid 비어있음", "extract_paper_evidence", code="EMPTY_PMID")

    pmid = str(pmid).strip()
    try:
        abstract = _efetch_abstract(pmid)
    except Exception as e:
        return mcp_error(
            f"PubMed efetch failed: {type(e).__name__}: {e}",
            "extract_paper_evidence", code="EFETCH_FAILED",
        )

    if not abstract:
        return mcp_response(
            result={
                "pmid": pmid, "abstract": None, "matched_sentences": [],
                "note": "abstract not retrieved",
            },
            tool_name="extract_paper_evidence",
            source="PubMed E-utilities (efetch)",
        )

    # question 기반 sentence ranking (keyword overlap)
    matched_sentences = []
    if question:
        q_words = {w.lower() for w in question.split() if len(w) > 3}
        clean_abstract = abstract.replace("\n", " ")
        sentences = [s.strip() for s in clean_abstract.split(". ") if s.strip()]
        for sent in sentences:
            sent_words = {w.lower().strip(",.()[]") for w in sent.split() if len(w) > 3}
            overlap = len(q_words & sent_words)
            if overlap >= 2:
                matched_sentences.append({
                    "sentence": sent,
                    "keyword_overlap": overlap,
                })
        matched_sentences.sort(key=lambda x: x["keyword_overlap"], reverse=True)

    return mcp_response(
        result={
            "pmid": pmid,
            "question": question,
            "abstract_length": len(abstract),
            "abstract_preview": abstract[:600],
            "matched_sentences": matched_sentences[:5],
            "citation_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        },
        tool_name="extract_paper_evidence",
        source="PubMed E-utilities (efetch)",
    )


def search_clinical_knowledge_base(
    query: str,
    max_results: int = 5,
) -> dict:
    """Bedrock KB retrieve — 임상 grounding용 chunks 검색 (정책 8).

    KB 내용 (5 PDFs, Titan v2 1024 dim, S3 Vectors):
    - FDA labels: osimertinib (Tagrisso), gefitinib (Iressa), sotorasib (Lumakras)
    - ESMO PAGA NSCLC 2024 (Pan-Asian consensus)
    - PMC FLAURA2 (osimertinib + chemo phase III)

    임상 단정 직전엔 반드시 호출:
    - FDA approval / dosing / contraindication
    - efficacy 수치 (ORR / PFS / HR / CI)
    - guideline strength (ESMO I-A / I-B, NCCN category)

    응답에 source_uri + page citation 표기 필수.
    근거를 찾지 못하면 "검증된 임상 근거를 찾지 못함"으로 응답하고 단정하지 말 것.
    """
    if not query or not str(query).strip():
        return mcp_error(
            "query 비어있음. 예: 'osimertinib EGFR T790M dosing'",
            "search_clinical_knowledge_base", code="EMPTY_QUERY",
        )

    # max_results sanity (토큰 비용 cap: 1-10)
    try:
        max_results = int(max_results)
    except (TypeError, ValueError):
        max_results = 5
    max_results = max(1, min(max_results, 10))

    client = _get_bedrock_client()

    try:
        response = client.retrieve(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            retrievalQuery={"text": str(query).strip()},
            retrievalConfiguration={
                "vectorSearchConfiguration": {"numberOfResults": max_results}
            },
        )
    except Exception as e:
        return mcp_error(
            f"Bedrock KB retrieve failed: {type(e).__name__}: {e}",
            "search_clinical_knowledge_base", code="KB_RETRIEVE_FAILED",
        )

    results = response.get("retrievalResults", []) or []

    if not results:
        return mcp_response(
            result={
                "query": query,
                "chunks": [],
                "count": 0,
                "note": (
                    "임상 KB에서 매칭 chunk 없음. "
                    "query 단순화 또는 약물명/유전자명 단독으로 재시도 권장."
                ),
            },
            tool_name="search_clinical_knowledge_base",
            source=f"Bedrock KB {KNOWLEDGE_BASE_ID} (FDA + ESMO + FLAURA2)",
            kb_id=KNOWLEDGE_BASE_ID,
        )

    chunks = []
    for r in results:
        loc = r.get("location") or {}
        s3 = loc.get("s3Location") or {}
        s3_uri = s3.get("uri")
        meta = r.get("metadata") or {}
        content = r.get("content") or {}
        chunks.append({
            "text": content.get("text", ""),
            "source_uri": s3_uri,
            "source_filename": s3_uri.rsplit("/", 1)[-1] if s3_uri else None,
            "page": meta.get("x-amz-bedrock-kb-document-page-number"),
            "score": r.get("score"),
            "chunk_id": meta.get("x-amz-bedrock-kb-chunk-id"),
        })

    return mcp_response(
        result={
            "query": query,
            "max_results": max_results,
            "chunks": chunks,
            "count": len(chunks),
            "top_score": chunks[0]["score"] if chunks else None,
        },
        tool_name="search_clinical_knowledge_base",
        source=f"Bedrock KB {KNOWLEDGE_BASE_ID} (FDA labels + ESMO PAGA 2024 + PMC FLAURA2)",
        kb_id=KNOWLEDGE_BASE_ID,
        embedding_model="amazon.titan-embed-text-v2:0 (1024 dim)",
        vector_store="Amazon S3 Vectors",
    )


# ===== Lambda entry =====
TOOL_REGISTRY = {
    "search_pubmed": search_pubmed,
    "extract_paper_evidence": extract_paper_evidence,
    "search_clinical_knowledge_base": search_clinical_knowledge_base,
}


def lambda_handler(event, context):  # noqa: ARG001
    return route_tool(event, TOOL_REGISTRY)


if __name__ == "__main__":
    tests = [
        {"tool": "search_pubmed", "params": {
            "query": "NSCLC EGFR T790M osimertinib resistance",
            "top_k": 3,
        }},
        {"tool": "search_clinical_knowledge_base", "params": {
            "query": "osimertinib EGFR T790M dosing",
            "max_results": 3,
        }},
        {"tool": "search_clinical_knowledge_base", "params": {
            "query": "sotorasib KRAS G12C contraindication",
            "max_results": 3,
        }},
    ]
    for e in tests:
        print(f">>> {e['tool']}({e['params']})")
        print(json.dumps(lambda_handler(e, None), indent=2, ensure_ascii=False)[:2000])
        print()
