"""
local_retrieval.py
PubMed corpus 기반 lightweight retrieval. Bedrock Knowledge Base 대체.

Corpus location: final/data/external/pubmed_nsclc/<name_type>/<NAME>/PMID*.json
  - name_type: "gene" | "drug"
  - NAME: gene_symbol (16 NSCLC targets) or drug name (30 NSCLC drugs)
  - PMID*.json: {pmid, name, name_type, title, abstract, year, journal}

3-tier retrieval (사실상 keyword + folder match):
  Tier 1 (exact): name == query AND name_type == query_type → folder match
  Tier 2 (title): query name in abstract title (case-insensitive substring)
  Tier 3 (body):  query name in abstract body (case-insensitive substring)

Memory footprint: 약 351 records × ~2KB = 750KB. Negligible.
Load once via @lru_cache.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Iterable

CORPUS_DIR = (
    Path(__file__).resolve().parents[2]
    / "data" / "external" / "pubmed_nsclc"
)


@lru_cache(maxsize=1)
def _load_index() -> tuple[dict, ...]:
    """Load all PubMed JSON records into an immutable tuple (for lru_cache safety)."""
    records = []
    if not CORPUS_DIR.exists():
        return tuple()
    for p in CORPUS_DIR.rglob("PMID*.json"):
        if p.name.endswith(".metadata.json"):
            continue
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        # precompute lowercase composite text for fast keyword matching
        rec["_title_lower"] = (rec.get("title") or "").lower()
        rec["_abs_lower"] = (rec.get("abstract") or "").lower()
        rec["_name_lower"] = (rec.get("name") or "").lower()
        records.append(rec)
    return tuple(records)


def retrieve(
    name: str,
    name_type: str = "gene",
    k: int = 5,
    *,
    require_nsclc: bool = False,
) -> list[dict]:
    """Return top-k PubMed records matching the given entity.

    Args:
        name: gene symbol or drug name (case-insensitive).
        name_type: "gene" | "drug". Tier-1 only matches when this aligns with
            the corpus record's name_type.
        k: max records to return (default 5).
        require_nsclc: if True, filter results to those containing "nsclc" or
            "non-small cell lung" in title/abstract. Default False because the
            collector already filtered with the NSCLC clause; toggle for safety.

    Returns:
        List of dicts with fields: pmid, name, name_type, title, abstract,
        year, journal. Ordered by tier (1>2>3), then by year desc.
    """
    if not name:
        return []
    idx = _load_index()
    if not idx:
        return []

    q = name.lower().strip()
    q_type = (name_type or "").lower().strip()

    tier1, tier2, tier3 = [], [], []
    for r in idx:
        if r["_name_lower"] == q and (not q_type or r.get("name_type", "") == q_type):
            tier1.append(r)
        elif q in r["_title_lower"]:
            tier2.append(r)
        elif q in r["_abs_lower"]:
            tier3.append(r)

    if require_nsclc:
        def _has_nsclc(r):
            t = r["_title_lower"] + " " + r["_abs_lower"]
            return ("nsclc" in t) or ("non-small cell lung" in t) or ("non small cell lung" in t)
        tier1 = [r for r in tier1 if _has_nsclc(r)]
        tier2 = [r for r in tier2 if _has_nsclc(r)]
        tier3 = [r for r in tier3 if _has_nsclc(r)]

    def _sort_key(r):
        try:
            y = -int(r.get("year", "0") or 0)
        except Exception:
            y = 0
        return (y, r.get("pmid", ""))

    tier1.sort(key=_sort_key)
    tier2.sort(key=_sort_key)
    tier3.sort(key=_sort_key)

    combined = tier1 + tier2 + tier3
    # dedupe by pmid
    seen = set()
    out = []
    for r in combined:
        pmid = r.get("pmid", "")
        if pmid in seen:
            continue
        seen.add(pmid)
        out.append(_clean(r))
        if len(out) >= k:
            break
    return out


def retrieve_multi(
    names: Iterable[str],
    name_type: str = "gene",
    k_per_name: int = 3,
    k_total: int = 5,
) -> list[dict]:
    """Multi-seed retrieval: union of per-name retrieve, deduped, top-k_total."""
    seen = set()
    combined = []
    for n in names:
        for r in retrieve(n, name_type, k=k_per_name):
            if r["pmid"] in seen:
                continue
            seen.add(r["pmid"])
            combined.append(r)
    return combined[:k_total]


def _clean(rec: dict) -> dict:
    """Strip internal underscored fields before returning to caller."""
    return {k: v for k, v in rec.items() if not k.startswith("_")}


def stats() -> dict:
    """Diagnostic: corpus size + per-type counts. For unit tests / smoke checks."""
    idx = _load_index()
    by_type = {}
    by_name = {}
    for r in idx:
        t = r.get("name_type", "?")
        by_type[t] = by_type.get(t, 0) + 1
        n = r.get("name", "?")
        by_name[n] = by_name.get(n, 0) + 1
    return {
        "total": len(idx),
        "by_type": by_type,
        "unique_names": len(by_name),
        "corpus_dir": str(CORPUS_DIR),
        "corpus_exists": CORPUS_DIR.exists(),
    }


if __name__ == "__main__":
    print("=== local_retrieval stats ===")
    print(json.dumps(stats(), indent=2, ensure_ascii=False))
    print()
    for q, t in [("EGFR", "gene"), ("Osimertinib", "drug"), ("MAPK3", "gene"), ("SAAL1", "gene")]:
        results = retrieve(q, t, k=3)
        print(f"=== {t}: {q} ({len(results)} hits) ===")
        for r in results:
            print(f"  PMID:{r['pmid']} ({r['year']}) {r['title'][:80]}")
        print()
