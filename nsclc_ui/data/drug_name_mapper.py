"""Map SIGNOR drug/entity names to local ChEMBL IDs for briefing cards."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from nsclc_ui.data.loaders import normalize_compound_id

_BASE = Path(__file__).resolve().parents[2]  # final/
_NAME_PATH = _BASE / "data" / "kegg" / "drug_name_lookup.csv"

_SALT_WORDS = {
    "hydrochloride",
    "dihydrochloride",
    "ditosylate",
    "dimaleate",
    "mesylate",
    "tosylate",
    "phosphate",
    "sulfate",
    "sulphate",
    "sodium",
    "potassium",
    "maleate",
    "succinate",
}

_CURATED_SIGNOR_TO_CHEMBL = {
    "afatinib": "CHEMBL1173655",
    "alectinib": "CHEMBL1738797",
    "brigatinib": "CHEMBL3545311",
    "ceritinib": "CHEMBL2403108",
    "crizotinib": "CHEMBL601719",
    "dabrafenib": "CHEMBL2028663",
    "dacomitinib": "CHEMBL2110732",
    "entrectinib": "CHEMBL1983268",
    "erlotinib": "CHEMBL553",
    "gefitinib": "CHEMBL939",
    "lapatinib": "CHEMBL1201179",
    "lorlatinib": "CHEMBL3286830",
    "neratinib": "CHEMBL180022",
    "osimertinib": "CHEMBL3353410",
    "selumetinib": "CHEMBL1614701",
    "sotorasib": "CHEMBL4535757",
    "tepotinib": "CHEMBL3402762",
    "trametinib": "CHEMBL507361",
    "vemurafenib": "CHEMBL1229517",
}


def normalize_drug_name(name: str | None) -> str:
    """Normalize SIGNOR/free-text drug names for exact-ish lookup."""
    if not name:
        return ""
    text = str(name).strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    parts = [part for part in text.split() if part not in _SALT_WORDS]
    return " ".join(parts)


@lru_cache(maxsize=1)
def _load_name_index() -> dict[str, str]:
    """Load local ChEMBL preferred-name index."""
    if not _NAME_PATH.exists():
        return {}

    import pandas as pd

    df = pd.read_csv(_NAME_PATH, usecols=["molecule_chembl_id", "pref_name"])
    index: dict[str, str] = {}
    for _, row in df.dropna(subset=["molecule_chembl_id", "pref_name"]).iterrows():
        cid = normalize_compound_id(row["molecule_chembl_id"])
        key = normalize_drug_name(row["pref_name"])
        if key:
            index.setdefault(key, cid)
        first_token = key.split()[0] if key else ""
        if first_token and len(first_token) >= 5:
            index.setdefault(first_token, cid)
    return index


def map_signor_drug_name(name: str | None) -> str | None:
    """Return a local ChEMBL ID for a SIGNOR entity name, if available."""
    key = normalize_drug_name(name)
    if not key:
        return None
    if key in _CURATED_SIGNOR_TO_CHEMBL:
        return _CURATED_SIGNOR_TO_CHEMBL[key]
    first_token = key.split()[0] if key else ""
    if first_token in _CURATED_SIGNOR_TO_CHEMBL:
        return _CURATED_SIGNOR_TO_CHEMBL[first_token]

    index = _load_name_index()
    return index.get(key) or index.get(first_token)
