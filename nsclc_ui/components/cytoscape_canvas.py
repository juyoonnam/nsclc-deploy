"""
cytoscape_canvas.py
Pathway Map cytoscape 요소 빌더 + 범례.

pathway_map.py에서 분리. KEGG pathway_data.json → cytoscape elements 변환.
"""
from __future__ import annotations
import json
import logging
from pathlib import Path
import dash_mantine_components as dmc
from dash import html

from nsclc_ui.components.cytoscape_styles import COLORS_CYTO

logger = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parents[2]  # final/
_PATHWAY_JSON = _BASE / "data" / "derived" / "pathway_data.json"

_LONG_LABEL_ALIASES = {
    "P3R3URF-PIK3R3": "P3R3URF\nPIK3R3",
}

_OVERLAP_COMPACT_IDS = {"167"}

_DRUG_CAPSULES = [
    {
        "id": "drug_osimertinib",
        "compound_id": "CHEMBL3353410",
        "label": "Osimertinib\n★ rank2",
        "target": "EGFR",
        "offset": (132, 10),
        "class": "drug-green",
    },
    {
        "id": "drug_alectinib",
        "compound_id": "CHEMBL1738797",
        "label": "Alectinib\n★ rank1",
        "target": "ALK",
        "offset": (126, 18),
        "class": "drug-purple",
    },
    {
        "id": "drug_trametinib",
        "compound_id": "CHEMBL507361",
        "label": "Trametinib",
        "target": "MAP2K1",
        "offset": (132, 44),
        "class": "drug-amber",
    },
]


def _load_pathway_data() -> dict:
    """pathway_data.json 로드. 캐시 안 함 (briefing.py에서 lru_cache로 처리)."""
    if not _PATHWAY_JSON.exists():
        logger.warning(f"pathway_data.json not found: {_PATHWAY_JSON}")
        return {}
    try:
        return json.load(open(_PATHWAY_JSON))
    except Exception as e:
        logger.error(f"failed to load pathway_data: {e}")
        return {}


def _display_label_for_node(node: dict) -> str:
    """KEGG 원본 좌표/alias는 보존하고 화면 라벨만 정리."""
    node_type = node.get("type", "gene")
    gene_syms = node.get("gene_symbols") or []
    if node_type == "compound":
        kegg_ids = node.get("kegg_ids") or []
        return kegg_ids[0].replace("cpd:", "") if kegg_ids else ""
    if gene_syms:
        first = str(gene_syms[0])
        return _LONG_LABEL_ALIASES.get(first, first)

    raw = (node.get("label") or "").strip()
    tokens = raw.split(",")[0].split() if raw else []
    return tokens[0].strip() if tokens else f"node_{node.get('entry_id', '?')}"


def _classes_for_node(node: dict, base_class: str, display_label: str) -> str:
    classes = [base_class]
    if str(node.get("entry_id")) in _OVERLAP_COMPACT_IDS:
        classes.append("overlap-compact")
    if "\n" in display_label or len(display_label) > 8:
        classes.append("long-label")
    return " ".join(classes)


def _first_node_for_gene(nodes: list[dict], gene: str) -> dict | None:
    for node in nodes:
        gene_syms = node.get("gene_symbols") or []
        if gene in gene_syms:
            return node
    return None


def _append_drug_capsules(elements: list[dict], nodes: list[dict]) -> None:
    """표적 좌표 기준 offset으로 drug capsule synthetic node 추가."""
    for capsule in _DRUG_CAPSULES:
        target_node = _first_node_for_gene(nodes, capsule["target"])
        if not target_node:
            continue
        target_id = str(target_node.get("entry_id"))
        x = int(target_node.get("x", 0)) + capsule["offset"][0]
        y = int(target_node.get("y", 0)) + capsule["offset"][1]

        elements.append({
            "data": {
                "id": capsule["id"],
                "label": capsule["label"],
                "node_type": "drug",
                "compound_id": capsule["compound_id"],
                "target_gene": capsule["target"],
            },
            "position": {"x": x, "y": y},
            "classes": f"drug-capsule {capsule['class']}",
        })
        elements.append({
            "data": {
                "id": f"e_{capsule['id']}_{target_id}",
                "source": capsule["id"],
                "target": target_id,
                "relation_type": "candidate-drug-target",
            },
            "classes": "drug-link",
        })


def build_elements(pathway_id: str) -> list:
    """pathway JSON → Cytoscape elements 변환.

    KEGG 노드 구조:
      entry_id (str), type ('gene'|'compound'|'group'),
      gene_symbols (list[str]), kegg_ids (list[str]),
      label (str, alias 콤마 결합), x, y, width, height,
      is_project_target (bool), has_compounds (bool, gene만), top_compounds, total_compound_count
    """
    data = _load_pathway_data()
    pw = data.get("pathways", {}).get(pathway_id)
    if not pw:
        return []

    elements = []
    for node in pw.get("nodes", []):
        node_type = node.get("type", "gene")
        is_project = node.get("is_project_target", False)
        has_compounds = node.get("has_compounds", False)

        # class 결정
        if node_type == "compound":
            cls = "kegg-compound"
        elif has_compounds:
            cls = "has-compounds"
        elif is_project:
            cls = "project-target"
        else:
            cls = "gene-default"

        gene_syms = node.get("gene_symbols") or []
        display_label = _display_label_for_node(node)

        elements.append({
            "data": {
                "id": str(node.get("entry_id")),
                "label": display_label,
                "node_type": node_type,
                "is_project_target": is_project,
                "has_compounds": has_compounds,
                "gene_symbols": gene_syms,            # 전체 alias 보존 (클릭 시 사용)
                "kegg_ids": node.get("kegg_ids") or [],
                "compound_count": node.get("total_compound_count", 0),
            },
            "position": {"x": int(node.get("x", 0)), "y": int(node.get("y", 0))},
            "classes": _classes_for_node(node, cls, display_label),
        })

    for edge in pw.get("edges", []):
        subtypes = edge.get("subtypes") or []
        subtypes_lower = [s.lower() for s in subtypes]
        if any("activat" in s or "expression" in s for s in subtypes_lower):
            cls = "activation"
        elif any("inhibit" in s or "repression" in s for s in subtypes_lower):
            cls = "inhibition"
        else:
            cls = ""

        src_id = str(edge.get("source"))
        tgt_id = str(edge.get("target"))
        elements.append({
            "data": {
                "id": f"e_{src_id}_{tgt_id}",
                "source": src_id,
                "target": tgt_id,
                "relation_type": edge.get("relation_type", ""),
                "subtypes": subtypes,
            },
            "classes": cls,
        })

    _append_drug_capsules(elements, pw.get("nodes", []))

    return elements


def legend() -> dmc.Group:
    """Cytoscape 범례 (좌측 하단)."""
    return dmc.Group([
        dmc.Group([
            dmc.Box(w=12, h=12, style={"background": COLORS_CYTO["node_target_active"], "borderRadius": "3px"}),
            dmc.Text("약물 있는 표적", size="xs", c="dimmed"),
        ], gap=4),
        dmc.Group([
            dmc.Box(w=12, h=12, style={"background": COLORS_CYTO["node_target"], "borderRadius": "3px"}),
            dmc.Text("프로젝트 타겟", size="xs", c="dimmed"),
        ], gap=4),
        dmc.Group([
            dmc.Box(w=12, h=12, style={"background": COLORS_CYTO["node_default"], "borderRadius": "3px"}),
            dmc.Text("기타 유전자", size="xs", c="dimmed"),
        ], gap=4),
        dmc.Group([
            dmc.Box(w=10, h=10, style={"background": COLORS_CYTO["kegg_compound"], "borderRadius": "50%"}),
            dmc.Text("KEGG compound", size="xs", c="dimmed"),
        ], gap=4),
        dmc.Group([
            dmc.Box(w=18, h=2, style={"background": COLORS_CYTO["edge_activate"]}),
            dmc.Text("활성화", size="xs", c="dimmed"),
        ], gap=4),
        dmc.Group([
            dmc.Box(w=18, h=2, style={"background": COLORS_CYTO["edge_inhibit"]}),
            dmc.Text("억제", size="xs", c="dimmed"),
        ], gap=4),
    ], gap="md", justify="center")


def pathway_options() -> tuple[list, str]:
    """Dash Select용 (옵션 리스트, 기본값) 반환."""
    data = _load_pathway_data()
    pws = data.get("pathways", {})
    if not pws:
        return [], None
    options = [
        {"value": pid, "label": f"{info.get('pathway_name', pid)} ({pid})"}
        for pid, info in pws.items()
    ]
    default = "hsa05223" if "hsa05223" in pws else next(iter(pws.keys()))
    return options, default
