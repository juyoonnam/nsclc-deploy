"""
nsclc_ui/data/pubmed.py

PMID/DOI → 논문 메타데이터 + 초록 + PMC OA 본문(가능 시).

NCBI E-utilities API 사용:
- esearch: DOI → PMID 변환
- efetch (db=pubmed): PMID → 메타+초록 (XML)
- efetch (db=pmc): PMCID → 본문 (XML, OA만 접근 가능)
- elink: PMID → PMCID

참고
----
- E-utilities는 인증 없이 3 req/sec 제한. NCBI API key 있으면 10 req/sec.
- PMC OA: 본문 자유 접근. 비OA 논문은 권한 에러 (E_BAD_REQUEST).
- 본문 추출 실패 시 graceful fallback (초록만 반환).

사용
----
>>> from nsclc_ui.data.pubmed import fetch_paper, PaperContent
>>> paper = fetch_paper("38468124")  # PMID
>>> paper.title, len(paper.abstract or ""), paper.has_full_text
>>> paper = fetch_paper("10.1038/s41586-023-XXXXX")  # DOI도 OK
"""
from __future__ import annotations

import logging
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DEFAULT_TIMEOUT = 10.0
MAX_FULLTEXT_CHARS = 60_000  # Bedrock context 보호 (Haiku 200k지만 비용 cap)

_PMID_PATTERN = re.compile(r"^\d{1,9}$")
_DOI_PATTERN = re.compile(r"^10\.\d{4,9}/[-._;()/:A-Z0-9]+$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# 데이터 구조
# ---------------------------------------------------------------------------
@dataclass
class PaperContent:
    """논문 메타데이터 + 본문."""
    pmid: str                                     # 항상 있음 (DOI 입력 시 변환됨)
    pmcid: Optional[str] = None                   # PMC OA에 있으면
    doi: Optional[str] = None
    title: str = ""
    journal: Optional[str] = None
    year: Optional[int] = None
    authors: list[str] = field(default_factory=list)
    abstract: Optional[str] = None
    full_text: Optional[str] = None               # PMC OA에서 추출 (실패 시 None)
    full_text_source: Optional[str] = None        # "pmc_oa" / None

    @property
    def has_full_text(self) -> bool:
        return bool(self.full_text and len(self.full_text) > 200)

    @property
    def text_for_extraction(self) -> str:
        """LLM 추출용 텍스트 — 본문 있으면 본문, 없으면 초록.

        길이 cap 적용 (MAX_FULLTEXT_CHARS).
        """
        body = self.full_text if self.has_full_text else (self.abstract or "")
        if len(body) > MAX_FULLTEXT_CHARS:
            return body[:MAX_FULLTEXT_CHARS] + "\n[... 길이 cap으로 절단 ...]"
        return body

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["has_full_text"] = self.has_full_text
        return d


@dataclass
class FetchError(Exception):
    """fetch 실패 marker — UI에서 사용자 친화 메시지로 변환용."""
    reason: str
    detail: Optional[str] = None

    def __str__(self) -> str:
        return f"{self.reason}" + (f" ({self.detail})" if self.detail else "")


# ---------------------------------------------------------------------------
# 입력 정규화 — PMID / DOI / PMC ID 자동 감지
# ---------------------------------------------------------------------------
def _normalize_identifier(raw: str) -> tuple[str, str]:
    """입력 문자열 → (id_type, normalized_value).

    id_type: "pmid" | "doi" | "pmcid"
    """
    s = raw.strip()
    s = re.sub(r"^(https?://)?(www\.)?", "", s)  # URL prefix 제거

    # PMC ID (PMC1234567 또는 PMCID:1234567)
    m = re.match(r"^(?:pmcid:?\s*)?(?:pmc)?(\d{4,8})$", s, re.IGNORECASE)
    if m and "PMC" in s.upper():
        return "pmcid", "PMC" + m.group(1)

    # DOI
    if _DOI_PATTERN.match(s):
        return "doi", s
    # DOI URL 형태 (doi.org/10....)
    m = re.match(r"^(?:dx\.)?doi\.org/(.+)$", s, re.IGNORECASE)
    if m:
        return "doi", m.group(1)

    # PubMed URL → PMID 추출
    m = re.match(r"^(?:pubmed\.ncbi\.nlm\.nih\.gov/)(\d+)/?$", s, re.IGNORECASE)
    if m:
        return "pmid", m.group(1)

    # 순수 숫자 → PMID
    if _PMID_PATTERN.match(s):
        return "pmid", s

    raise FetchError(
        reason="식별자 형식을 인식할 수 없음",
        detail=f"PMID(숫자), DOI(10.xxxx/xxxx), PMC ID 형식이어야 합니다. 입력: {raw[:50]}",
    )


# ---------------------------------------------------------------------------
# E-utilities HTTP 호출 (인증 없는 단순 GET)
# ---------------------------------------------------------------------------
def _http_get(url: str, timeout: float = DEFAULT_TIMEOUT) -> bytes:
    """E-utilities GET. 단일 호출, retry 없음 (시연 hang 방지)."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "nsclc-insight-engine/1.0 (research demo)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise FetchError(
            reason=f"NCBI HTTP {e.code}",
            detail=str(e.reason)[:200],
        )
    except urllib.error.URLError as e:
        raise FetchError(reason="네트워크 오류", detail=str(e.reason)[:200])
    except TimeoutError:
        raise FetchError(reason="NCBI timeout", detail=f"{timeout}s 초과")


# ---------------------------------------------------------------------------
# 1단계: DOI → PMID
# ---------------------------------------------------------------------------
def _doi_to_pmid(doi: str) -> str:
    url = (
        f"{EUTILS_BASE}/esearch.fcgi?db=pubmed&retmode=json"
        f"&term={urllib.parse.quote(doi)}[doi]"
    )
    raw = _http_get(url)
    import json
    try:
        data = json.loads(raw)
        ids = data.get("esearchresult", {}).get("idlist", [])
    except (ValueError, KeyError) as e:
        raise FetchError(reason="DOI 검색 응답 파싱 실패", detail=str(e))
    if not ids:
        raise FetchError(reason="DOI에 해당하는 PMID 없음", detail=f"DOI: {doi}")
    return ids[0]


# ---------------------------------------------------------------------------
# 2단계: PMID → 메타+초록 (PubMed XML)
# ---------------------------------------------------------------------------
def _fetch_pubmed_metadata(pmid: str) -> PaperContent:
    url = (
        f"{EUTILS_BASE}/efetch.fcgi?db=pubmed&id={pmid}"
        f"&rettype=abstract&retmode=xml"
    )
    raw = _http_get(url)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        raise FetchError(reason="PubMed XML 파싱 실패", detail=str(e))

    article = root.find(".//PubmedArticle")
    if article is None:
        raise FetchError(reason="PMID에 대한 논문 정보 없음", detail=f"PMID: {pmid}")

    # title
    title_node = article.find(".//ArticleTitle")
    title = _xml_text(title_node) if title_node is not None else ""

    # journal — Element는 truthy 평가 deprecated, 명시적 체크
    journal_node = article.find(".//Journal/Title")
    if journal_node is None:
        journal_node = article.find(".//ISOAbbreviation")
    journal = _xml_text(journal_node) if journal_node is not None else None

    # year
    year_node = article.find(".//PubDate/Year")
    if year_node is None:
        year_node = article.find(".//PubDate/MedlineDate")
    year = None
    if year_node is not None and year_node.text:
        m = re.search(r"\b(19|20)\d{2}\b", year_node.text)
        if m:
            year = int(m.group(0))

    # authors
    authors = []
    for au in article.findall(".//AuthorList/Author"):
        last = au.find("LastName")
        init = au.find("Initials")
        if last is not None and last.text:
            name = last.text + (" " + init.text if init is not None and init.text else "")
            authors.append(name)

    # abstract — 여러 AbstractText 노드를 합침 (구조화 초록 대응)
    abstract_parts = []
    for at in article.findall(".//Abstract/AbstractText"):
        label = at.attrib.get("Label", "")
        text = _xml_text(at)
        if not text:
            continue
        if label:
            abstract_parts.append(f"{label}: {text}")
        else:
            abstract_parts.append(text)
    abstract = "\n\n".join(abstract_parts) if abstract_parts else None

    # DOI / PMCID (ArticleIdList에서)
    doi = None
    pmcid = None
    for aid in article.findall(".//ArticleIdList/ArticleId"):
        idtype = aid.attrib.get("IdType", "").lower()
        if idtype == "doi" and aid.text:
            doi = aid.text.strip()
        elif idtype == "pmc" and aid.text:
            pmcid = aid.text.strip()
            if not pmcid.upper().startswith("PMC"):
                pmcid = "PMC" + pmcid

    return PaperContent(
        pmid=pmid,
        pmcid=pmcid,
        doi=doi,
        title=title,
        journal=journal,
        year=year,
        authors=authors,
        abstract=abstract,
    )


def _xml_text(node) -> str:
    """node 안의 텍스트 + 자식 텍스트 모두 합쳐서 반환 (sub/sup 등 inline 태그 대응)."""
    if node is None:
        return ""
    return "".join(node.itertext()).strip()


# ---------------------------------------------------------------------------
# 3단계: PMC OA 본문 (선택적)
# ---------------------------------------------------------------------------
def _fetch_pmc_fulltext(pmcid: str) -> Optional[str]:
    """PMC OA 본문 추출. OA 아니면 None 반환 (예외 던지지 않음).

    PMC API는 비OA에 대해 ERROR 응답을 XML 안에 담아 보냄.
    """
    pmc_num = pmcid.upper().replace("PMC", "")
    url = (
        f"{EUTILS_BASE}/efetch.fcgi?db=pmc&id={pmc_num}&retmode=xml"
    )
    try:
        raw = _http_get(url, timeout=DEFAULT_TIMEOUT * 1.5)  # 본문은 더 큼
    except FetchError as e:
        logger.warning("[pubmed] PMC fetch 실패: %s", e)
        return None

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None

    # 비-OA 표시: <pmc-articleset><error>...
    err = root.find(".//error")
    if err is not None:
        logger.info("[pubmed] PMC %s 비-OA: %s", pmcid, _xml_text(err)[:100])
        return None

    # body 추출 — JATS XML 구조
    body = root.find(".//body")
    if body is None:
        return None

    text_parts = []
    for sec in body.findall(".//sec"):
        # section title
        title_node = sec.find("title")
        if title_node is not None:
            t = _xml_text(title_node)
            if t:
                text_parts.append(f"\n## {t}\n")
        # paragraphs
        for p in sec.findall("p"):
            text = _xml_text(p)
            if text:
                text_parts.append(text)
    # body 직하 p (sec 밖)
    for p in body.findall("./p"):
        text = _xml_text(p)
        if text:
            text_parts.append(text)

    full = "\n\n".join(text_parts).strip()
    return full if len(full) > 200 else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def fetch_paper(identifier: str, fetch_fulltext: bool = True) -> PaperContent:
    """PMID/DOI/PMC ID → PaperContent.

    Args:
        identifier: PMID(숫자) / DOI(10.xxxx/...) / PMC ID(PMC1234567)
        fetch_fulltext: True면 PMCID 발견 시 본문도 가져옴 (실패 시 graceful)

    Raises:
        FetchError: 식별자 인식 실패, NCBI 호출 실패, 논문 없음
    """
    id_type, value = _normalize_identifier(identifier)
    logger.info("[pubmed] fetch %s=%s", id_type, value)

    if id_type == "pmid":
        pmid = value
    elif id_type == "doi":
        pmid = _doi_to_pmid(value)
    elif id_type == "pmcid":
        # PMCID → PMID 매핑은 별도 호출 필요. 단순화: efetch pmc로 본문만 받고
        # 메타는 PMC XML에서 추출. 시연용 PMID 입력 권장이라 깊게 안 함.
        raise FetchError(
            reason="PMC ID 입력은 현재 미지원",
            detail="PMID 또는 DOI를 입력하세요.",
        )
    else:
        raise FetchError(reason=f"알 수 없는 id_type: {id_type}")

    paper = _fetch_pubmed_metadata(pmid)

    if fetch_fulltext and paper.pmcid:
        full = _fetch_pmc_fulltext(paper.pmcid)
        if full:
            paper.full_text = full
            paper.full_text_source = "pmc_oa"
            logger.info("[pubmed] PMC OA full text %d chars", len(full))

    return paper
