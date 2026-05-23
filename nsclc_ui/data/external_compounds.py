"""
ChEMBL 실시간 외부 화합물 fetcher.

설계 원칙
─────────
• 사전 수집 데이터 일체 사용 안 함. 모든 외부 화합물은 노드 클릭 시점에 ChEMBL API로 호출.
• 동일 gene 재클릭 시 in-memory 캐시 hit (앱 재시작 시 캐시 소실 = 매번 최신).
• 라벨은 데이터 출처/시점을 정직하게 표시. "사전 수집"이라는 표현 금지.
• 우리 DB(33,057) compound_id는 결과에서 제외 — "외부"라는 라벨의 정직성 유지.

ChEMBL REST API 요점
─────────────────────
• base: https://www.ebi.ac.uk/chembl/api/data
• limit max = 1000 (default 20). pagination = limit/offset.
• Django-style filter: __gte, __lte, __in, __istartswith 등.
• molecule batch: ?molecule_chembl_id__in=ID1,ID2,... (URL 길이 안전 위해 분할).
• 라이선스 CC BY-SA 3.0 — 출처 표기 필수.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

# ── 상수 ──────────────────────────────────────────────────────
CHEMBL_API = "https://www.ebi.ac.uk/chembl/api/data"
PCHEMBL_MIN = 7.0           # pIC50 ≥ 7  (= IC50 ≤ 100 nM)
ACTIVITY_LIMIT = 1000       # ChEMBL API max. EGFR/CDK4 같은 대형 타겟 안전.
TOP_N = 20                  # UI 표시 + molecule 상세 enrichment 대상
MOL_BATCH = 25              # molecule batch 호출 청크 크기 (URL 길이 안전)
IND_BATCH = 25              # drug_indication batch 청크
ASSAY_TYPE = "B"            # binding assay만
HTTP_TIMEOUT = 20           # API timeout (초). limit=1000 응답 대비 여유.

# NSCLC 적응증 판정 키워드 (도메인 룰: NSCLC ≠ SCLC)
# 명시적 NSCLC 표현만 인정. "lung carcinoma" 단독은 SCLC 포함 가능 → 별도 처리.
_NSCLC_PATTERNS = [
    "non-small cell lung",
    "non small cell lung",
    "non-small-cell lung",
    "nsclc",
]
_LUNG_BUT_AMBIG = ["lung carcinoma", "lung neoplasm", "lung cancer"]
_SCLC_MARKERS = ["small cell lung", "small-cell lung", "sclc"]

_BASE = Path(__file__).resolve().parents[2]  # final/

# ── 모듈 상태 ─────────────────────────────────────────────────
_TARGET_GENE_LOOKUP = None   # pd.DataFrame (lazy)
_OUR_COMPOUND_IDS = None     # set[str]    (lazy)
_GENE_CACHE: dict = {}       # in-memory: {gene: result_dict}


# ── HTTP ──────────────────────────────────────────────────────
def _http_get(url: str, timeout: int = HTTP_TIMEOUT) -> dict:
    """HTTP GET → JSON dict. 실패 시 빈 dict (조용히)."""
    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
        return {}


# ── lazy loaders ──────────────────────────────────────────────
def _load_target_gene_lookup():
    """target_gene_lookup.csv lazy 로드 (gene → ChEMBL target ID 매핑)."""
    global _TARGET_GENE_LOOKUP
    if _TARGET_GENE_LOOKUP is not None:
        return _TARGET_GENE_LOOKUP

    import pandas as pd
    path = _BASE / "data" / "derived" / "target_gene_lookup.csv"
    if path.exists():
        df = pd.read_csv(path)
        df["gene_symbol"] = df["gene_symbol"].astype(str).str.strip().str.upper()
        _TARGET_GENE_LOOKUP = df
    else:
        _TARGET_GENE_LOOKUP = pd.DataFrame()
    return _TARGET_GENE_LOOKUP


def _load_our_compound_ids():
    """compound_target_map.csv lazy 로드. 우리 DB 33,057 compound_id set."""
    global _OUR_COMPOUND_IDS
    if _OUR_COMPOUND_IDS is not None:
        return _OUR_COMPOUND_IDS

    import pandas as pd
    path = _BASE / "data" / "derived" / "compound_target_map.csv"
    if path.exists():
        ids = pd.read_csv(path)["compound_id"].astype(str).str.strip().str.upper()
        _OUR_COMPOUND_IDS = set(ids)
    else:
        _OUR_COMPOUND_IDS = set()
    return _OUR_COMPOUND_IDS


# ── ChEMBL API helpers ────────────────────────────────────────
def _resolve_target_id(gene_symbol: str) -> str:
    """gene symbol → ChEMBL target ID (Homo sapiens, SINGLE PROTEIN).
    target_gene_lookup 우선, 없으면 ChEMBL search API fallback."""
    df = _load_target_gene_lookup()
    if not df.empty:
        match = df[
            (df["gene_symbol"] == gene_symbol.upper()) &
            (df["organism"] == "Homo sapiens") &
            (df["target_type"] == "SINGLE PROTEIN")
        ]
        if not match.empty:
            return match.iloc[0]["target_chembl_id"]

    # API fallback
    data = _http_get(f"{CHEMBL_API}/target/search.json?q={gene_symbol}&limit=5")
    for t in data.get("targets", []):
        if (t.get("organism") == "Homo sapiens"
                and t.get("target_type") == "SINGLE PROTEIN"):
            return t.get("target_chembl_id", "")
    return ""


def _fetch_activities(target_id: str) -> tuple:
    """ChEMBL activity 호출.

    핵심:
      - order_by=-pchembl_value 로 강력 활성부터 받음
      - page_meta.total_count로 ChEMBL 풀 전체 크기 파악
      - 우리 DB 제외 후 external만 반환

    반환:
      (mol_map, stats)
        mol_map: {compound_id: max_pchembl} (우리 DB 제외)
        stats: {
          chembl_pool_total: int,    # ChEMBL pchembl≥7.0 binding 활성 총 건수
          analyzed: int,              # 우리가 본 raw activity 건수 (≤ limit)
          dedup_total: int,           # 중복 제거 후 unique compound 수
          our_overlap: int,           # 그 중 우리 DB와 겹친 수
          external: int,              # 외부 발견 수
          coverage_rate: float,       # our_overlap / dedup_total
          cutoff_pchembl: float|None, # limit cap 시 잘린 지점 (pchembl_min)
          analyzed_pchembl_max: float|None,
        }
    """
    params = {
        "target_chembl_id": target_id,
        "pchembl_value__gte": PCHEMBL_MIN,
        "assay_type": ASSAY_TYPE,
        "limit": ACTIVITY_LIMIT,
        "order_by": "-pchembl_value",
        "format": "json",
    }
    url = f"{CHEMBL_API}/activity.json?{urlencode(params)}"
    print(f"[chembl] GET {url}", flush=True)
    data = _http_get(url)

    empty_stats = {
        "chembl_pool_total": 0, "analyzed": 0, "dedup_total": 0,
        "our_overlap": 0, "external": 0, "coverage_rate": 0.0,
        "cutoff_pchembl": None, "analyzed_pchembl_max": None,
    }
    if not data:
        print(f"[chembl] target={target_id} EMPTY API response", flush=True)
        return {}, empty_stats

    raw_n = len(data.get("activities", []))
    pool_total = (data.get("page_meta") or {}).get("total_count", 0) or 0

    # 1단계: dedup
    mol_map_all: dict = {}
    for act in data.get("activities", []):
        mid = (act.get("molecule_chembl_id") or "").strip().upper()
        pval = act.get("pchembl_value")
        if not mid or pval is None:
            continue
        try:
            pv = float(pval)
        except (ValueError, TypeError):
            continue
        if mid not in mol_map_all or pv > mol_map_all[mid]:
            mol_map_all[mid] = pv

    # 2단계: 우리 DB 제외
    our_ids = _load_our_compound_ids()
    overlap = sum(1 for mid in mol_map_all if mid in our_ids)
    mol_map = {mid: pv for mid, pv in mol_map_all.items() if mid not in our_ids}

    pvals = list(mol_map_all.values())
    pchembl_max = max(pvals) if pvals else None
    # cap에 걸린 경우 (raw가 limit과 같으면 더 있는 거): 가장 낮은 pchembl이 cutoff
    cutoff = (min(pvals) if pvals else None) if raw_n >= ACTIVITY_LIMIT else None

    coverage = (overlap / len(mol_map_all)) if mol_map_all else 0.0

    stats = {
        "chembl_pool_total": pool_total,
        "analyzed": raw_n,
        "dedup_total": len(mol_map_all),
        "our_overlap": overlap,
        "external": len(mol_map),
        "coverage_rate": coverage,
        "cutoff_pchembl": cutoff,
        "analyzed_pchembl_max": pchembl_max,
    }

    # 진단 로그
    cap_note = f" CAP(cutoff={cutoff:.2f})" if cutoff is not None else ""
    print(
        f"[chembl] target={target_id} "
        f"pool={pool_total} analyzed={raw_n}{cap_note} "
        f"dedup={len(mol_map_all)} overlap={overlap} "
        f"external={len(mol_map)} coverage={coverage*100:.1f}%",
        flush=True
    )
    if mol_map:
        sorted_ext = sorted(mol_map.items(), key=lambda x: -x[1])[:3]
        ext_preview = ", ".join(f"{mid}({pv:.2f})" for mid, pv in sorted_ext)
        print(f"  → external top 3: {ext_preview}", flush=True)

    return mol_map, stats


def _fetch_molecule_details(compound_ids: list) -> dict:
    """molecule batch fetch.
    반환: {compound_id: {pref_name, max_phase, molecule_type, mw, alogp, smiles}}.
    배치 크기 MOL_BATCH로 분할해 URL 길이 안전 확보."""
    if not compound_ids:
        return {}

    out: dict = {}
    for i in range(0, len(compound_ids), MOL_BATCH):
        chunk = compound_ids[i:i + MOL_BATCH]
        ids_param = ",".join(chunk)
        url = (
            f"{CHEMBL_API}/molecule.json"
            f"?molecule_chembl_id__in={ids_param}"
            f"&limit={len(chunk)}"
        )
        data = _http_get(url)
        for mol in data.get("molecules", []):
            mid = (mol.get("molecule_chembl_id") or "").strip().upper()
            if not mid:
                continue
            props = mol.get("molecule_properties") or {}
            structures = mol.get("molecule_structures") or {}
            out[mid] = {
                "pref_name": mol.get("pref_name") or "",
                "max_phase": mol.get("max_phase"),
                "molecule_type": mol.get("molecule_type"),
                "mw": props.get("full_mwt"),
                "alogp": props.get("alogp"),
                "smiles": structures.get("canonical_smiles") or "",
            }
    return out


def _phase_badge(max_phase) -> str:
    """phase 숫자 → 텍스트 배지."""
    try:
        p = float(max_phase) if max_phase is not None else 0
    except (ValueError, TypeError):
        p = 0
    if p >= 4: return "Approved"
    if p >= 3: return "Phase 3"
    if p >= 2: return "Phase 2"
    if p >= 1: return "Phase 1"
    return "Preclinical"


def _classify_indication(efo_term: str, mesh_heading: str) -> str:
    """적응증 텍스트 → 카테고리.
    반환: "nsclc" | "lung_ambig" | "sclc" | "other"

    NSCLC ≠ SCLC. NSCLC 명시된 것만 NSCLC. lung 단독은 별도 분류.
    """
    txt = f"{efo_term or ''} {mesh_heading or ''}".lower()
    if not txt.strip():
        return "other"

    for pat in _NSCLC_PATTERNS:
        if pat in txt:
            return "nsclc"
    for pat in _SCLC_MARKERS:
        if pat in txt:
            return "sclc"
    for pat in _LUNG_BUT_AMBIG:
        if pat in txt:
            return "lung_ambig"
    return "other"


def _fetch_drug_indications(compound_ids: list) -> dict:
    """drug_indication batch fetch.
    반환: {compound_id: [{efo_term, mesh_heading, max_phase_for_ind, category}, ...]}

    category: "nsclc" | "lung_ambig" | "sclc" | "other"
    응답에 indication 없는 화합물은 dict에 키 자체가 없음 (preclinical 등).
    """
    if not compound_ids:
        return {}

    out: dict = {}
    for i in range(0, len(compound_ids), IND_BATCH):
        chunk = compound_ids[i:i + IND_BATCH]
        ids_param = ",".join(chunk)
        # limit 크게 (한 화합물당 indication 여러개 가능, 25*10 = 250 안전)
        url = (
            f"{CHEMBL_API}/drug_indication.json"
            f"?molecule_chembl_id__in={ids_param}"
            f"&limit=1000"
        )
        data = _http_get(url)
        for ind in data.get("drug_indications", []):
            mid = (ind.get("molecule_chembl_id") or "").strip().upper()
            if not mid:
                continue
            efo = ind.get("efo_term") or ""
            mesh = ind.get("mesh_heading") or ""
            entry = {
                "efo_term": efo,
                "mesh_heading": mesh,
                "max_phase_for_ind": ind.get("max_phase_for_ind"),
                "category": _classify_indication(efo, mesh),
            }
            out.setdefault(mid, []).append(entry)

    # 각 화합물별 indication 정렬: phase 내림차순
    for mid in out:
        out[mid].sort(
            key=lambda x: float(x.get("max_phase_for_ind") or 0), reverse=True
        )
    return out


def _summarize_indications(inds: list) -> dict:
    """compound의 indication 리스트 → UI 요약.
    반환: {nsclc: bool, lung_ambig: bool, top_label: str, all_count: int}
    """
    if not inds:
        return {"nsclc": False, "lung_ambig": False,
                "top_label": "", "all_count": 0}

    has_nsclc = any(i["category"] == "nsclc" for i in inds)
    has_lung_ambig = any(i["category"] == "lung_ambig" for i in inds)

    # 표시 우선순위: NSCLC > lung_ambig > 첫 indication (= 가장 phase 높은 것)
    label = ""
    if has_nsclc:
        nsclc_inds = [i for i in inds if i["category"] == "nsclc"]
        label = nsclc_inds[0]["efo_term"] or nsclc_inds[0]["mesh_heading"]
    elif has_lung_ambig:
        lung_inds = [i for i in inds if i["category"] == "lung_ambig"]
        label = lung_inds[0]["efo_term"] or lung_inds[0]["mesh_heading"]
    else:
        label = inds[0]["efo_term"] or inds[0]["mesh_heading"] or "?"

    return {
        "nsclc": has_nsclc,
        "lung_ambig": has_lung_ambig,
        "top_label": label,
        "all_count": len(inds),
    }


# ── public API ────────────────────────────────────────────────
def fetch_external_compounds(gene_symbol: str, top_n: int = TOP_N) -> dict:
    """gene → 외부 화합물 top-N (실시간 ChEMBL).

    반환 dict
      compounds: list[dict]    enrichment 완료 (pref_name, max_phase, mw, smiles 포함)
      total: int               dedup·우리DB제외 후 전체 활성 후보 수
      fetched_at: "HH:MM:SS"   최초 호출 시각
      elapsed_ms: int          최초 호출 소요 (ms)
      from_cache: bool         in-memory 캐시 hit 여부
      target_id: str           사용된 ChEMBL target ID (없으면 "")
    """
    gene_key = gene_symbol.strip().upper()
    if not gene_key:
        return _empty_result("")

    # 캐시 hit
    if gene_key in _GENE_CACHE:
        cached = dict(_GENE_CACHE[gene_key])
        cached["from_cache"] = True
        return cached

    t0 = time.time()
    target_id = _resolve_target_id(gene_key)

    if not target_id:
        result = _empty_result("")
        result["fetched_at"] = datetime.now().strftime("%H:%M:%S")
        result["elapsed_ms"] = int((time.time() - t0) * 1000)
        _GENE_CACHE[gene_key] = result
        return result

    # 1. activity 풀
    mol_map, stats = _fetch_activities(target_id)
    total = len(mol_map)

    # 2. pchembl 내림차순 top-N
    sorted_mols = sorted(mol_map.items(), key=lambda x: -x[1])[:top_n]
    top_ids = [mid for mid, _ in sorted_mols]

    # 3. molecule 상세 enrichment
    details = _fetch_molecule_details(top_ids)

    # 4. indication enrichment (phase ≥ 1 화합물에만 — preclinical엔 indication 없음)
    def _phase_num(d):
        try:
            return float(d.get("max_phase") or 0)
        except (ValueError, TypeError):
            return 0
    ind_target_ids = [mid for mid in top_ids if _phase_num(details.get(mid, {})) >= 1]
    indications = _fetch_drug_indications(ind_target_ids)

    compounds = []
    for mid, pchembl in sorted_mols:
        det = details.get(mid, {})
        inds = indications.get(mid, [])
        ind_summary = _summarize_indications(inds)
        compounds.append({
            "compound_id": mid,
            "max_pchembl": round(pchembl, 2),
            "pref_name": det.get("pref_name", ""),
            "max_phase": det.get("max_phase"),
            "badge": _phase_badge(det.get("max_phase")),
            "molecule_type": det.get("molecule_type"),
            "mw": det.get("mw"),
            "alogp": det.get("alogp"),
            "smiles": det.get("smiles", ""),
            "source": "ChEMBL API",
            # 적응증
            "indications": inds,                       # raw list
            "nsclc_indication": ind_summary["nsclc"],  # NSCLC 명시 적응증 보유
            "lung_ambig_indication": ind_summary["lung_ambig"],
            "top_indication": ind_summary["top_label"],
            "indication_count": ind_summary["all_count"],
        })

    result = {
        "compounds": compounds,
        "total": total,
        "fetched_at": datetime.now().strftime("%H:%M:%S"),
        "elapsed_ms": int((time.time() - t0) * 1000),
        "from_cache": False,
        "target_id": target_id,
        "stats": stats,
    }
    _GENE_CACHE[gene_key] = result
    return result


def _empty_result(target_id: str) -> dict:
    return {
        "compounds": [],
        "total": 0,
        "fetched_at": datetime.now().strftime("%H:%M:%S"),
        "elapsed_ms": 0,
        "from_cache": False,
        "target_id": target_id,
        "stats": {
            "chembl_pool_total": 0, "analyzed": 0, "dedup_total": 0,
            "our_overlap": 0, "external": 0, "coverage_rate": 0.0,
            "cutoff_pchembl": None, "analyzed_pchembl_max": None,
        },
    }


# ── 운영 헬퍼 ─────────────────────────────────────────────────
def warm_cache(gene_symbols: list, verbose: bool = True) -> dict:
    """발표 전 워밍업. 모든 gene 미리 호출 → 캐시 채움.
    반환: {gene: {ok, total, top, ms}} 요약."""
    summary = {}
    for i, gene in enumerate(gene_symbols, 1):
        result = fetch_external_compounds(gene)
        summary[gene] = {
            "ok": bool(result["target_id"]),
            "total": result["total"],
            "top": len(result["compounds"]),
            "ms": result["elapsed_ms"],
        }
        if verbose:
            tag = "HIT" if result["from_cache"] else "MISS"
            print(
                f"[{i}/{len(gene_symbols)}] {gene}: {tag} "
                f"target={result['target_id'] or 'NONE'} "
                f"total={result['total']} top={len(result['compounds'])} "
                f"{result['elapsed_ms']}ms"
            )
    return summary


def cache_stats() -> dict:
    """현재 in-memory 캐시 상태."""
    return {
        "cached_genes": list(_GENE_CACHE.keys()),
        "count": len(_GENE_CACHE),
    }


def clear_cache() -> None:
    """in-memory 캐시 초기화 (테스트/재호출용)."""
    _GENE_CACHE.clear()
