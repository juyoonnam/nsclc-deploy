"""V4-2/V4-3: SIGNOR graph → dash-cytoscape elements + stylesheet.

Builds cytoscape elements from SIGNOR NSCLC graph (364 nodes, 531 edges)
with sign-based edge coloring and NSCLC target highlighting.
"""
from __future__ import annotations
import hashlib
import pickle
import re
from functools import lru_cache
from pathlib import Path
import networkx as nx

from nsclc_ui.components.cytoscape_styles import COLORS_CYTO
from nsclc_ui.data.drug_name_mapper import map_signor_drug_name

_BASE = Path(__file__).resolve().parents[2]  # final/
_GRAPH_PATH = _BASE / "data" / "derived" / "signor_nsclc_graph.gpickle"
_DRUG_PATH = _BASE / "data" / "derived" / "signor_nsclc_drug.parquet"

_graph_cache = None


def load_signor_graph() -> nx.DiGraph:
    """Load SIGNOR NSCLC graph (cached)."""
    global _graph_cache
    if _graph_cache is None:
        with open(_GRAPH_PATH, "rb") as f:
            _graph_cache = pickle.load(f)
    return _graph_cache


def _nsclc_targets(G: nx.DiGraph) -> set[str]:
    return {n for n in G.nodes() if G.nodes[n].get("is_nsclc_target", 0) == 1}


@lru_cache(maxsize=1)
def load_signor_drug_edges() -> list[dict]:
    """Load SIGNOR drug/entity → NSCLC target edges (cached)."""
    if not _DRUG_PATH.exists():
        return []

    import pandas as pd

    df = pd.read_parquet(_DRUG_PATH)
    if "ENTITYA" not in df.columns or "ENTITYB" not in df.columns:
        return []

    targets = _nsclc_targets(load_signor_graph())
    df = df[df["ENTITYB"].astype(str).str.upper().isin(targets)]
    return df.to_dict("records")


def _text(record: dict, key: str, default: str = "") -> str:
    value = record.get(key)
    if value is None:
        return default
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return default
    return text


def _drug_node_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:36]
    digest = hashlib.sha1(name.lower().encode("utf-8")).hexdigest()[:8]
    return f"drug::{slug or 'entity'}::{digest}"


def _drug_type_class(type_a: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", type_a.lower()).strip("-")
    return f"signor-drug-{slug or 'entity'}"


def _drug_edge_classes(effect: str, mechanism: str) -> str:
    text = f"{effect} {mechanism}".lower()
    classes = ["signor-drug-edge"]
    if "up-regulates" in text or "activation" in text:
        classes.append("signor-drug-edge-up")
    elif "down-regulates" in text or "inhibition" in text or "repression" in text:
        classes.append("signor-drug-edge-down")
    else:
        classes.append("signor-drug-edge-neutral")
    return " ".join(classes)


def _append_unique(items: list, value: str, limit: int = 8) -> None:
    if value and value not in items and len(items) < limit:
        items.append(value)


def _clean_ref(value: str) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none", "t", "f", "true", "false"}:
        return ""
    return text


def _safe_float(value) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _build_drug_elements(visible_nodes: set[str]) -> list[dict]:
    drug_nodes: dict[str, dict] = {}
    drug_edges: list[dict] = []

    for idx, row in enumerate(load_signor_drug_edges()):
        target = _text(row, "ENTITYB").upper()
        name = _text(row, "ENTITYA")
        if not target or target not in visible_nodes or not name:
            continue

        type_a = _text(row, "TYPEA", "entity")
        effect = _text(row, "EFFECT")
        mechanism = _text(row, "MECHANISM")
        compound_id = map_signor_drug_name(name) or ""
        node_id = _drug_node_id(name)

        if node_id not in drug_nodes:
            drug_nodes[node_id] = {
                "data": {
                    "id": node_id,
                    "label": name,
                    "node_type": "drug",
                    "drug_name": name,
                    "compound_id": compound_id,
                    "signor_type": type_a,
                    "signor_types": [],
                    "targets": [],
                    "mechanisms": [],
                    "effects": [],
                    "pmids": [],
                },
                "classes": " ".join([
                    "signor-node",
                    "signor-drug-node",
                    _drug_type_class(type_a),
                ]),
            }

        data = drug_nodes[node_id]["data"]
        if compound_id and not data.get("compound_id"):
            data["compound_id"] = compound_id
        _append_unique(data["signor_types"], type_a)
        _append_unique(data["targets"], target)
        _append_unique(data["mechanisms"], mechanism)
        _append_unique(data["effects"], effect)
        for key in ("PMID", "SENTENCE"):
            _append_unique(data["pmids"], _clean_ref(row.get(key)), limit=5)

        drug_edges.append({
            "data": {
                "id": f"{node_id}__{target}__drug__{idx}",
                "source": node_id,
                "target": target,
                "effect": effect,
                "mechanism": mechanism,
                "score": _safe_float(row.get("SCORE")),
                "node_type": "drug_edge",
            },
            "classes": _drug_edge_classes(effect, mechanism),
        })

    return list(drug_nodes.values()) + drug_edges


def build_signor_elements(
    influenced: dict | None = None,
    seeds: list[str] | None = None,
    min_degree: int = 0,
    include_drugs: bool = False,
) -> list[dict]:
    """Build cytoscape elements from SIGNOR graph.

    Args:
        influenced: optional {gene: influence_score} from RWR for heat overlay
        seeds: optional list of seed genes (highlighted differently)
        min_degree: hide protein nodes with total degree below this value
        include_drugs: add SIGNOR drug/entity edges into NSCLC target nodes
    """
    G = load_signor_graph()
    seeds = set(seeds or [])
    influenced = influenced or {}
    min_degree = max(0, int(min_degree or 0))
    targets = _nsclc_targets(G)
    visible_nodes = {
        node for node in G.nodes()
        if node in seeds or node in targets or G.degree(node) >= min_degree
    }
    
    # Influence percentile thresholds for heat coloring
    if influenced:
        scores = sorted([v for k, v in influenced.items() if k not in seeds], reverse=True)
        thresholds = {
            "high": scores[len(scores) // 10] if len(scores) > 10 else 0,
            "mid": scores[len(scores) // 3] if len(scores) > 3 else 0,
        }
    else:
        thresholds = {"high": 0, "mid": 0}

    elements = []
    for node in G.nodes():
        if node not in visible_nodes:
            continue
        is_target = bool(G.nodes[node].get("is_nsclc_target", 0))
        is_seed = node in seeds
        score = influenced.get(node, 0.0)

        classes = ["signor-node"]
        if is_seed:
            classes.append("signor-seed")
        elif is_target:
            classes.append("signor-target")
        if not is_seed and score > 0:
            if score >= thresholds["high"]:
                classes.append("signor-heat-high")
            elif score >= thresholds["mid"]:
                classes.append("signor-heat-mid")
            else:
                classes.append("signor-heat-low")

        elements.append({
            "data": {
                "id": node,
                "label": node,
                "score": round(score, 4),
                "is_target": is_target,
                "node_type": "protein",
                "degree": int(G.degree(node)),
            },
            "classes": " ".join(classes),
        })

    for src, tgt, attrs in G.edges(data=True):
        if src not in visible_nodes or tgt not in visible_nodes:
            continue
        sign = attrs.get("sign", 0)
        if sign > 0:
            edge_class = "signor-edge-up"
        elif sign < 0:
            edge_class = "signor-edge-down"
        else:
            edge_class = "signor-edge-neutral"
        elements.append({
            "data": {
                "id": f"{src}__{tgt}",
                "source": src,
                "target": tgt,
                "effect": attrs.get("effect") or "",
                "mechanism": attrs.get("mechanism") or "",
                "score": float(attrs.get("score") or 0),
            },
            "classes": edge_class,
        })
    if include_drugs:
        elements.extend(_build_drug_elements(visible_nodes))
    return elements


SIGNOR_STYLESHEET = [
    {
        "selector": "node.signor-node",
        "style": {
            "background-color": "#0B1629",
            "label": "data(label)",
            "color": COLORS_CYTO["text_dim"],
            "text-valign": "center",
            "text-halign": "center",
            "font-size": "9px",
            "font-weight": "600",
            "border-width": 1,
            "border-color": "#334155",
            "shape": "ellipse",
            "width": 22,
            "height": 22,
            "z-index": 4,
        },
    },
    {
        "selector": "node.signor-target",
        "style": {
            "background-color": "#10243B",
            "border-color": COLORS_CYTO["node_pathway"],
            "border-width": 2,
            "color": "#FFFFFF",
            "width": 38,
            "height": 38,
            "font-size": "11px",
            "font-weight": "700",
            "z-index": 6,
        },
    },
    {
        "selector": "node.signor-drug-node",
        "style": {
            "background-color": "#9775FA",
            "border-color": "#C4B5FD",
            "border-width": 2,
            "color": "#FFFFFF",
            "shape": "diamond",
            "width": 24,
            "height": 24,
            "font-size": "8px",
            "font-weight": "700",
            "text-wrap": "wrap",
            "text-max-width": "58px",
            "z-index": 8,
        },
    },
    {
        "selector": "node.signor-drug-antibody",
        "style": {
            "background-color": "#22D3EE",
            "border-color": "#BAE6FD",
            "color": "#06101F",
        },
    },
    {
        "selector": "node.signor-drug-proteinfamily, node.signor-drug-complex",
        "style": {
            "background-color": "#51CF66",
            "border-color": "#B2F2BB",
            "color": "#06101F",
        },
    },
    {
        "selector": "node.signor-seed",
        "style": {
            "background-color": "#FF5B5B",
            "border-color": "#FFD43B",
            "border-width": 3,
            "color": "#FFFFFF",
            "width": 44,
            "height": 44,
            "font-size": "12px",
            "font-weight": "800",
            "shadow-blur": 16,
            "shadow-color": "#FFD43B",
            "shadow-opacity": 0.7,
            "z-index": 9,
        },
    },
    {
        "selector": "node.signor-heat-high",
        "style": {
            "background-color": "#F59F00",
            "color": "#06101F",
            "border-color": "#F59F00",
            "border-width": 2,
            "width": 32,
            "height": 32,
            "font-size": "10px",
            "font-weight": "800",
            "z-index": 7,
        },
    },
    {
        "selector": "node.signor-heat-mid",
        "style": {
            "background-color": "#7A5A1F",
            "border-color": "#F59F00",
            "color": "#FFE5A4",
            "width": 26,
            "height": 26,
            "z-index": 5,
        },
    },
    {
        "selector": "node.signor-heat-low",
        "style": {
            "background-color": "#3A3220",
            "border-color": "#7A5A1F",
            "color": "#94A3B8",
            "z-index": 4,
        },
    },
    {
        "selector": "edge",
        "style": {
            "curve-style": "bezier",
            "width": 1,
            "opacity": 0.5,
            "target-arrow-shape": "triangle",
            "arrow-scale": 0.7,
            "z-index": 1,
        },
    },
    {
        "selector": "edge.signor-edge-up",
        "style": {
            "line-color": COLORS_CYTO["edge_activate"],
            "target-arrow-color": COLORS_CYTO["edge_activate"],
        },
    },
    {
        "selector": "edge.signor-edge-down",
        "style": {
            "line-color": COLORS_CYTO["edge_inhibit"],
            "target-arrow-color": COLORS_CYTO["edge_inhibit"],
        },
    },
    {
        "selector": "edge.signor-edge-neutral",
        "style": {
            "line-color": "#475569",
            "target-arrow-color": "#475569",
        },
    },
    {
        "selector": "edge.signor-drug-edge",
        "style": {
            "line-style": "dashed",
            "width": 1.4,
            "opacity": 0.75,
            "line-color": "#FF5B5B",
            "target-arrow-color": "#FF5B5B",
            "z-index": 2,
        },
    },
    {
        "selector": "edge.signor-drug-edge-up",
        "style": {
            "line-color": COLORS_CYTO["edge_activate"],
            "target-arrow-color": COLORS_CYTO["edge_activate"],
        },
    },
    {
        "selector": "edge.signor-drug-edge-neutral",
        "style": {
            "line-color": "#9775FA",
            "target-arrow-color": "#9775FA",
        },
    },
]
