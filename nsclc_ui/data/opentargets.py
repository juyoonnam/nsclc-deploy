"""
Open Targets Platform GraphQL — NSCLC 임상 증거 외부 source.

실제 스키마 검증 완료 (2026-05-04 introspect):
  Target.drugAndClinicalCandidates: clinicalTargets {
    count
    rows: [ClinicalTargetFromTarget!]! {
      id
      maxClinicalStage         # 문자열: "Approved" / "Phase IV" / "Phase III" / ...
      drug: Drug { id, name, drugType, maximumClinicalStage }
      diseases: [ClinicalDiseaseListItem!]! {
        diseaseFromSource
        disease: Disease { id, name }
      }
    }
  }

폐기 메모:
  - Target.knownDrugs / Disease.knownDrugs → API에서 제거됨, 400 에러
  - Drug.maximumClinicalTrialPhase / isApproved → 제거됨
  - 새 필드: Drug.maximumClinicalStage (문자열), Target.drugAndClinicalCandidates

전략:
  - 2단계: search(queryString) → ensembl ID, target(ensemblId).drugAndClinicalCandidates
  - gene 단위 in-memory 캐시
"""

import json
import time
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

OT_API = "https://api.platform.opentargets.org/api/v4/graphql"
HTTP_TIMEOUT = 30
NSCLC_EFO = "EFO_0003060"

_GENE_CACHE: dict = {}


def _gql_post(query: str, variables: dict, timeout: int = HTTP_TIMEOUT) -> dict:
    """GraphQL POST → JSON dict. 실패 시 빈 dict.
    400/500 시 응답 body 첫 300자 로그."""
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = Request(
        OT_API,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        try:
            err_body = e.read().decode("utf-8")[:300]
        except Exception:
            err_body = ""
        print(f"[opentargets] HTTP {e.code}: {err_body}", flush=True)
        return {}
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        print(f"[opentargets] error: {type(e).__name__}: {e}", flush=True)
        return {}


SEARCH_QUERY = """
query Search($q: String!) {
  search(queryString: $q, entityNames: ["target"]) {
    hits {
      id
      name
      object {
        ... on Target { id approvedSymbol approvedName }
      }
    }
  }
}
"""

TARGET_DRUGS_QUERY = """
query TargetDrugs($ensemblId: String!) {
  target(ensemblId: $ensemblId) {
    id
    approvedSymbol
    drugAndClinicalCandidates {
      count
      rows {
        id
        maxClinicalStage
        drug {
          id
          name
          drugType
          maximumClinicalStage
        }
        diseases {
          diseaseFromSource
          disease {
            id
            name
          }
        }
      }
    }
  }
}
"""


def _is_nsclc_disease(disease_id, disease_name) -> bool:
    if (disease_id or "") == NSCLC_EFO:
        return True
    name = (disease_name or "").lower()
    return ("non-small cell lung" in name
            or "non small cell lung" in name
            or "non-small-cell lung" in name
            or "nsclc" in name)


def _is_sclc_disease(disease_id, disease_name) -> bool:
    name = (disease_name or "").lower()
    return ("small cell lung" in name and "non-small" not in name
            and "non small" not in name) or name.strip() == "sclc"


def _is_lung_ambig(disease_id, disease_name) -> bool:
    if _is_nsclc_disease(disease_id, disease_name):
        return False
    if _is_sclc_disease(disease_id, disease_name):
        return False
    name = (disease_name or "").lower()
    return ("lung" in name
            and ("carcinoma" in name or "cancer" in name or "neoplasm" in name))


def _stage_to_phase_int(stage) -> int:
    """maxClinicalStage 문자열 → phase 숫자 (정렬·UI 호환).

    OT 실제 값 패턴 (introspect로 확인되지 않아 실제 응답 기준):
      "Approval" / "Approved" → 4
      "PHASE_4" / "Phase IV" / "Phase 4" → 4
      "PHASE_3" / "Phase III" / "Phase 3" → 3
      "PHASE_2" / "Phase II" / "Phase 2" → 2
      "PHASE_1" / "Phase I" / "Phase 1" → 1
      "Preclinical" / 빈값 → 0
    """
    if not stage:
        return 0
    s = str(stage).strip().lower().replace("_", " ").replace("-", " ")
    if "approv" in s:                   # approval, approved
        return 4
    if "phase iv" in s or "phase 4" in s:
        return 4
    if "phase iii" in s or "phase 3" in s:
        return 3
    if "phase ii" in s or "phase 2" in s:
        return 2
    if "phase i" in s or "phase 1" in s:
        return 1
    return 0


def _format_stage_label(stage) -> str:
    """원본 stage 문자열을 보기 좋은 라벨로.
    "PHASE_3" → "Phase 3", "Approval" → "Approved", 빈값 → "Preclinical"."""
    if not stage:
        return "Preclinical"
    s = str(stage).strip()
    s_norm = s.lower().replace("_", " ")
    if "approv" in s_norm:
        return "Approved"
    if "phase iv" in s_norm or "phase 4" in s_norm:
        return "Phase 4"
    if "phase iii" in s_norm or "phase 3" in s_norm:
        return "Phase 3"
    if "phase ii" in s_norm or "phase 2" in s_norm:
        return "Phase 2"
    if "phase i" in s_norm or "phase 1" in s_norm:
        return "Phase 1"
    return s.title() if s else "Preclinical"


def _pick_ensembl_id(hits: list, gene_symbol: str) -> str:
    gene_upper = gene_symbol.upper()
    for h in hits:
        obj = h.get("object") or {}
        if (obj.get("approvedSymbol") or "").upper() == gene_upper:
            return obj.get("id") or h.get("id") or ""
    for h in hits:
        if (h.get("name") or "").upper() == gene_upper:
            return h.get("id") or ""
    if hits:
        return hits[0].get("id") or ""
    return ""


def fetch_opentargets_drugs(gene_symbol: str) -> dict:
    """gene → Target.drugAndClinicalCandidates.

    반환:
      drugs: list[dict]      — 정렬 (NSCLC > lung_ambig > 기타, max_stage 내림차순)
      total: int             — drugAndClinicalCandidates.count
      drugs_unique: int
      nsclc_count: int
      lung_ambig_count: int
      target_id: str         — ensembl ID
      fetched_at, elapsed_ms, from_cache
    """
    gene_key = gene_symbol.strip().upper()
    if not gene_key:
        return _empty_ot_result()

    if gene_key in _GENE_CACHE:
        cached = dict(_GENE_CACHE[gene_key])
        cached["from_cache"] = True
        return cached

    t0 = time.time()
    print(f"[opentargets] POST gene={gene_key}", flush=True)

    # 1단계: search
    search_resp = _gql_post(SEARCH_QUERY, {"q": gene_key})
    if not search_resp or "data" not in search_resp:
        if search_resp and "errors" in search_resp:
            print(f"[opentargets] search errors: {str(search_resp['errors'])[:200]}",
                  flush=True)
        result = _empty_ot_result()
        result["elapsed_ms"] = int((time.time() - t0) * 1000)
        _GENE_CACHE[gene_key] = result
        return result

    hits = (search_resp.get("data") or {}).get("search", {}).get("hits", []) or []
    ensembl_id = _pick_ensembl_id(hits, gene_key)
    if not ensembl_id:
        print(f"[opentargets] target={gene_key} no ensembl ID", flush=True)
        result = _empty_ot_result()
        result["elapsed_ms"] = int((time.time() - t0) * 1000)
        _GENE_CACHE[gene_key] = result
        return result

    # 2단계: drugAndClinicalCandidates
    drugs_resp = _gql_post(TARGET_DRUGS_QUERY, {"ensemblId": ensembl_id})
    if not drugs_resp or "data" not in drugs_resp:
        if drugs_resp and "errors" in drugs_resp:
            print(f"[opentargets] drugs errors: {str(drugs_resp['errors'])[:200]}",
                  flush=True)
        result = _empty_ot_result()
        result["target_id"] = ensembl_id
        result["elapsed_ms"] = int((time.time() - t0) * 1000)
        _GENE_CACHE[gene_key] = result
        return result

    target_obj = (drugs_resp.get("data") or {}).get("target") or {}
    dac = target_obj.get("drugAndClinicalCandidates") or {}
    rows = dac.get("rows") or []
    total_count = dac.get("count", 0) or 0

    seen: dict = {}
    drugs: list = []

    for row in rows:
        drug = row.get("drug") or {}
        drug_id = drug.get("id") or ""
        if not drug_id:
            continue

        row_diseases = row.get("diseases") or []
        ind_entries = []
        row_has_nsclc = False
        row_has_lung_ambig = False
        for cd in row_diseases:
            disease_obj = cd.get("disease") or {}
            d_id = disease_obj.get("id")
            d_name = disease_obj.get("name") or cd.get("diseaseFromSource") or ""
            is_nsclc = _is_nsclc_disease(d_id, d_name)
            is_lung_a = _is_lung_ambig(d_id, d_name)
            if is_nsclc:
                row_has_nsclc = True
            if is_lung_a:
                row_has_lung_ambig = True
            ind_entries.append({
                "disease_id": d_id,
                "disease_name": d_name,
                "is_nsclc": is_nsclc,
                "is_lung_ambig": is_lung_a,
            })

        max_stage = (row.get("maxClinicalStage")
                     or drug.get("maximumClinicalStage") or "")

        if drug_id in seen:
            d = drugs[seen[drug_id]]
            d["indications"].extend(ind_entries)
            if row_has_nsclc:
                d["nsclc"] = True
            if row_has_lung_ambig and not d.get("nsclc"):
                d["lung_ambig"] = True
            if _stage_to_phase_int(max_stage) > _stage_to_phase_int(d["max_stage"]):
                d["max_stage"] = max_stage
                d["max_phase"] = _stage_to_phase_int(max_stage)
        else:
            d = {
                "drug_id": drug_id,
                "drug_name": drug.get("name") or "",
                "drug_type": drug.get("drugType") or "",
                "max_stage": max_stage,
                "max_phase": _stage_to_phase_int(max_stage),
                "mechanism": "",  # OT 새 스키마엔 row 단위 mechanism 없음
                "nsclc": row_has_nsclc,
                "lung_ambig": row_has_lung_ambig and not row_has_nsclc,
                "indications": list(ind_entries),
            }
            seen[drug_id] = len(drugs)
            drugs.append(d)

    def _sort_key(d):
        priority = 0 if d.get("nsclc") else (1 if d.get("lung_ambig") else 2)
        return (priority, -_stage_to_phase_int(d.get("max_stage", "")))

    drugs.sort(key=_sort_key)

    nsclc_count = sum(1 for d in drugs if d.get("nsclc"))
    lung_count = sum(1 for d in drugs if d.get("lung_ambig"))
    elapsed = int((time.time() - t0) * 1000)

    print(
        f"[opentargets] target={gene_key} ensembl={ensembl_id} "
        f"total_rows={total_count} drugs_unique={len(drugs)} "
        f"nsclc={nsclc_count} lung_ambig={lung_count} elapsed={elapsed}ms",
        flush=True
    )
    if drugs:
        top3 = ", ".join(f"{d['drug_name']}({d['max_stage']})"
                         for d in drugs[:3])
        print(f"  → top 3: {top3}", flush=True)

    result = {
        "drugs": drugs,
        "total": total_count,
        "drugs_unique": len(drugs),
        "nsclc_count": nsclc_count,
        "lung_ambig_count": lung_count,
        "target_id": ensembl_id,
        "fetched_at": datetime.now().strftime("%H:%M:%S"),
        "elapsed_ms": elapsed,
        "from_cache": False,
    }
    _GENE_CACHE[gene_key] = result
    return result


def _empty_ot_result() -> dict:
    return {
        "drugs": [],
        "total": 0,
        "drugs_unique": 0,
        "nsclc_count": 0,
        "lung_ambig_count": 0,
        "target_id": "",
        "fetched_at": datetime.now().strftime("%H:%M:%S"),
        "elapsed_ms": 0,
        "from_cache": False,
    }


def cache_stats() -> dict:
    return {
        "cached_genes": list(_GENE_CACHE.keys()),
        "count": len(_GENE_CACHE),
    }


def clear_cache() -> None:
    _GENE_CACHE.clear()
