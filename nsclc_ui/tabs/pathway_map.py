"""
pathway_map.py
NSCLC Pathway Map — Living Atlas (Step 4-C: 우측 패널 + 콜백).

좌: cytoscape 캔버스 (SIGNOR NSCLC graph + RWR heat)
우: 자동완성 검색창 + 누적 브리핑 탭 + 카드 + LLM 영역 placeholder

분리된 모듈:
  - components/cytoscape_signor.py  SIGNOR_STYLESHEET, build_signor_elements
  - components/cytoscape_canvas.py  pathway_options
  - components/briefing_card.py     render_card (Step 4-C 신설)
  - data/briefing.py                get_briefing_for_pathway/target/drug
  - data/signal_propagation.py      RWR seed propagation

다음 단계 (Step 4-D): LLM Q&A 통합
다음 단계 (Step 4-E): SMILES/InChI 입력 모드 (v1.1.1 시안 7.1.3)
"""
from __future__ import annotations
from collections import defaultdict
from functools import lru_cache
import hashlib
import logging
import math
import re
from pathlib import Path

import dash
from dash import html, dcc, callback, Input, Output, State, no_update, ctx, ALL
import dash_cytoscape as cyto
import dash_mantine_components as dmc

from nsclc_ui.layout.theme import (
    CLUSTER_COLORS,
    SEED_COLOR,
    card_style,
)
import nsclc_ui.components.chatbot_panel as chatbot_panel_module
from nsclc_ui.components.cytoscape_signor import (
    SIGNOR_STYLESHEET,
    build_signor_elements,
    load_signor_drug_edges,
    load_signor_graph,
)
from nsclc_ui.components.cytoscape_canvas import pathway_options
from nsclc_ui.components.briefing_card import render_card
from nsclc_ui.data.loaders import get_top_compounds_for_target
from nsclc_ui.data.briefing import get_briefing_for_drug, get_briefing_for_target
from nsclc_ui.data.drug_name_mapper import map_signor_drug_name
from nsclc_ui.data.signal_propagation import rwr_from_seeds
from nsclc_ui.llm.bedrock_client import LLMResponse, query_entity
from nsclc_ui.components.chatbot_panel import (
    chatbot_panel,
    build_context_payload,
    CONTEXT_STORE_ID,
)
from nsclc_ui.components.chatbot_popup import (
    CHAT_POPUP_BACKDROP_ID,
    CHAT_POPUP_CLOSE_ID,
    CHAT_POPUP_ESCAPE_LISTENER_ID,
    CHAT_POPUP_FAB_ID,
    CHAT_POPUP_OPEN_STORE_ID,
    CHAT_POPUP_SHELL_ID,
    chatbot_popup,
)

logger = logging.getLogger(__name__)

dash.register_page(
    __name__,
    path="/pathway",
    name="Pathway Map",
    title="NSCLC Insight Engine",
    order=2,
)

_PATHWAY_OPTIONS, _DEFAULT_PW = pathway_options()
_BASE_DIR = Path(__file__).resolve().parents[2]
_CLUSTER_MAPPING_PATH = _BASE_DIR / "data" / "derived" / "nsclc_cluster_mapping.csv"
_SIGNOR_G = load_signor_graph()
_NSCLC_TARGETS = sorted([
    n for n in _SIGNOR_G.nodes()
    if _SIGNOR_G.nodes[n].get("is_nsclc_target", 0) == 1
])
_NSCLC_TARGET_SET = set(_NSCLC_TARGETS)
_SIGNOR_PROTEINS = sorted([
    n for n in _SIGNOR_G.nodes()
    if _SIGNOR_G.nodes[n].get("is_nsclc_target", 0) != 1
])
_SIGNOR_DRUG_EDGES = load_signor_drug_edges()
_SIGNOR_DRUG_EDGE_COUNT = len(_SIGNOR_DRUG_EDGES)

# ============================================================
# Autocomplete index
# ============================================================
_TYPE_EMOJI = {"protein": "□", "target": "🎯", "drug": "💊"}
_DISPLAY_ALIASES = {
    "CHEMBL1173655": "Afatinib",
    "CHEMBL3353410": "Osimertinib",
    "CHEMBL1738797": "Alectinib",
    "CHEMBL939": "Gefitinib",
    "CHEMBL507361": "Trametinib",
}
_SIGNOR_SEED_ID = "signor-seed-select-v1"
_SIGNOR_RESTART_ID = "signor-restart-prob-v1"
_SIGNOR_DEGREE_ID = "signor-degree-filter-v1"
_SIGNOR_SHOW_DRUGS_ID = "signor-show-drugs-v1"
_SIGNOR_RWR_STORE_ID = "signor-rwr-store-v1"
_SIGNOR_RESTART_WARNING_ID = "signor-restart-warning-v1"
_SIGNOR_RESTART_VALUE_ID = "signor-restart-current-value-v1"
_SIGNOR_TOP10_ID = "signor-top10-influenced-v1"
_ENTITY_TYPE_FILTER_STORE_ID = "entity-type-filter-store"
_ENTITY_TYPE_CHIP = "entity-type-chip"
_TOP_INFLUENCED_BTN_TYPE = "signor-top-influenced-node-v1"
_CYTO_NAV_RESULT_ID = "pathway-cyto-nav-result"
_CYTO_CONTROL_RESULT_ID = "pathway-cyto-control-result"
_MAP_ZOOM_IN_ID = "pathway-map-zoom-in"
_MAP_ZOOM_OUT_ID = "pathway-map-zoom-out"
_MAP_FIT_ID = "pathway-map-fit"
_OVERVIEW_SWITCH_ID = "pathway-overview-switch-v6"
_CLUSTER_HULL_SWITCH_ID = "pathway-cluster-hulls-switch-v6"
_MINIMAP_SWITCH_ID = "pathway-minimap-switch-v6"
_OVERVIEW_RESULT_ID = "pathway-overview-result-v6"
_MINIMAP_RESULT_ID = "pathway-minimap-result-v6"
_PATHWAY_BOTTOM_CARDS_ID = "pathway-bottom-cards-v6"
_CYTO_HOVER_RESULT_ID = "pathway-cyto-hover-result-v6"
_CLUSTER_OVERLAY_ID = "pathway-cluster-island-overlay-v6"
_CLUSTER_OVERLAY_RESULT_ID = "pathway-cluster-island-overlay-result-v6"
_DETAIL_DRAWER_OPEN_STORE_ID = "pathway-detail-drawer-open-store-v6"
_DETAIL_DRAWER_ID = "pathway-detail-drawer-v6"
_DETAIL_DRAWER_TOGGLE_ID = "pathway-detail-drawer-toggle-v6"
_DETAIL_DRAWER_CLOSE_ID = "pathway-detail-drawer-close-v6"
_DETAIL_DRAWER_RESULT_ID = "pathway-detail-drawer-result-v6"
_PATHWAY_MINIMAP_ID = "pathway-minimap-v6"
_PATHWAY_NEIGHBOR_BTN_TYPE = "pathway-bottom-neighbor-v6"
_PATHWAY_DRUG_CHIP_TYPE = "pathway-bottom-drug-v6"
_PATHWAY_DRUG_MORE_TYPE = "pathway-bottom-drug-more-v6"
_PATHWAY_DRUG_EXPANDED_STORE_ID = "pathway-drug-expanded-store-v6"
_VIEW_STATE_STORE_ID = "pathway-view-state-store-v6"
_VIEW_HISTORY_STORE_ID = "pathway-view-history-store-v6"
_VIEW_BACK_BUTTON_ID = "pathway-view-back-v6"
_NODE_SEARCH_BUTTON_ID = "node-search-button"
_RWR_COMPUTED_RESTART_PROB = 0.3
_CLUSTER_TOP_N = 10
_VIEW_HISTORY_MAX_DEPTH = 10

_CLUSTER_ORDER = ("RTK", "RAS_MAPK", "PI3K_AKT", "APOPTOSIS", "CELL_CYCLE", "TF")
_SEED_HUB_CLUSTER = "SEED_HUB"
_VISUAL_CLUSTER_ORDER = (_SEED_HUB_CLUSTER, *_CLUSTER_ORDER)
_CLUSTER_LABELS = {
    _SEED_HUB_CLUSTER: "EGFR Signaling Hub",
    "RTK": "RTK / Receptor Signaling",
    "RAS_MAPK": "RAS / MAPK Cascade",
    "PI3K_AKT": "PI3K / AKT Pathway",
    "APOPTOSIS": "Apoptosis & Stress Response",
    "CELL_CYCLE": "Cell Cycle & Proliferation",
    "TF": "Transcription & Gene Regulation",
}
_CLUSTER_SUBTITLES = {
    _SEED_HUB_CLUSTER: "Core EGFR network",
    "RTK": "Ligand-RTK interactions & early signaling",
    "RAS_MAPK": "RAS activation & MAPK signaling",
    "PI3K_AKT": "PI3K signaling & cell survival",
    "APOPTOSIS": "Apoptotic signaling & stress pathways",
    "CELL_CYCLE": "Cell cycle regulation & DNA replication",
    "TF": "Transcription factors & gene expression",
}
_CLUSTER_CENTERS = {
    _SEED_HUB_CLUSTER: (0.50, 0.50),
    "RTK": (0.34, 0.24),
    "RAS_MAPK": (0.66, 0.24),
    "PI3K_AKT": (0.25, 0.48),
    "APOPTOSIS": (0.75, 0.48),
    "CELL_CYCLE": (0.34, 0.74),
    "TF": (0.66, 0.74),
}
_VISUAL_CLUSTER_COLORS = {
    _SEED_HUB_CLUSTER: "#F59E0B",
    **CLUSTER_COLORS,
    "RAS_MAPK": "#60A5FA",
}
_CLUSTER_LAYOUT_WIDTH = 980
_CLUSTER_LAYOUT_HEIGHT = 680
_CLUSTER_TEMPLATE_RADII = {
    _SEED_HUB_CLUSTER: (175, 135),
    "RTK": (130, 92),
    "RAS_MAPK": (135, 96),
    "PI3K_AKT": (130, 105),
    "APOPTOSIS": (130, 105),
    "CELL_CYCLE": (125, 95),
    "TF": (130, 100),
}
_VISUAL_CLUSTER_TARGET_COUNTS = {
    _SEED_HUB_CLUSTER: 16,
    "RTK": 9,
    "RAS_MAPK": 9,
    "PI3K_AKT": 8,
    "APOPTOSIS": 8,
    "CELL_CYCLE": 7,
    "TF": 7,
}
_VISUAL_CLUSTER_TEMPLATE_GENES = {
    _SEED_HUB_CLUSTER: [
        "EGFR", "ERBB2", "ERBB3", "GRB2", "SOS1", "SHC1", "PLCG1", "PIK3CA",
        "PIK3R1", "AKT1", "MAPK1", "MAPK3", "SRC", "STAT3", "GAB1", "PTK2",
    ],
    "RTK": ["RET", "ROS1", "MET", "ALK", "NTRK1", "ERBB2", "AXL", "FGFR1", "PTPN11"],
    "RAS_MAPK": ["KRAS", "NRAS", "HRAS", "RAF1", "BRAF", "MAP2K1", "MAP2K2", "MAPK1", "MAPK3"],
    "PI3K_AKT": ["PIK3CA", "PIK3R1", "PTEN", "AKT1", "AKT2", "MTOR", "PDPK1", "GSK3B"],
    "APOPTOSIS": ["CASP9", "PARP1", "PRDX1", "ATM", "BAD", "BBC3", "TP53", "PELI1"],
    "CELL_CYCLE": ["CDK4", "CDK6", "CCND1", "RB1", "CDK1", "CDKN1A", "MYC"],
    "TF": ["STAT3", "JUN", "SP1", "RELA", "MYC", "CTNNB1", "PPARG"],
}
_HUB_SLOT_OFFSETS = [
    (0.00, 0.00),
    (-0.42, -0.36), (0.00, -0.45), (0.42, -0.36),
    (0.60, -0.06), (0.43, 0.32), (0.10, 0.46), (-0.34, 0.36), (-0.58, 0.06),
    (-0.27, -0.06), (0.27, -0.06), (0.00, 0.18),
    (-0.15, -0.28), (0.16, -0.28), (-0.18, 0.26), (0.22, 0.24),
    (-0.05, 0.60), (0.54, 0.42),
]
_CLUSTER_SLOT_OFFSETS = [
    (-0.46, -0.24), (-0.04, -0.38), (0.42, -0.22),
    (-0.54, 0.16), (-0.10, 0.02), (0.32, 0.10),
    (0.52, 0.30), (-0.28, 0.42), (0.18, 0.42),
    (0.02, 0.24), (-0.12, -0.16), (0.18, -0.12),
]
_CLUSTER_DRILLDOWN_STEPS = {
    "RTK": ["Ligand", "RTK", "GRB2/SOS", "RAS", "PI3K", "STAT", "Nuclear response"],
    "RAS_MAPK": ["RTK", "GRB2/SOS", "RAS", "RAF", "MEK", "ERK", "ELK1/FOS/MYC"],
    "PI3K_AKT": ["RTK", "PI3K", "PIP3", "AKT", "TSC", "MTOR", "Survival program"],
    "APOPTOSIS": ["Stress", "TP53", "BCL2 family", "Caspases", "PARP", "Cell fate"],
    "CELL_CYCLE": ["Cyclin D", "CDK4/6", "RB1", "E2F", "S phase", "DNA replication"],
    "TF": ["Signal input", "STAT/JUN/FOS", "MYC", "Chromatin", "Transcription output"],
}
_GENE_CHAIN_MAP = {
    "EGFR": [
        ["EGFR", "PI3K", "AKT", "MTOR"],
        ["EGFR", "RAS", "RAF", "MEK", "MAPK"],
        ["EGFR", "STAT3", "MYC"],
    ],
    "KRAS": [
        ["KRAS", "RAF", "MEK", "ERK", "FOS/MYC"],
        ["KRAS", "PI3K", "AKT", "MTOR"],
    ],
    "BRAF": [["BRAF", "MEK", "ERK", "ELK1/FOS"]],
    "MAP2K1": [["MEK1", "ERK", "ELK1", "FOS/MYC"]],
    "PIK3CA": [["PIK3CA", "AKT", "TSC", "MTOR"], ["PIK3CA", "PDK1", "AKT"]],
    "AKT1": [["AKT1", "TSC", "MTOR"], ["AKT1", "BAD", "Survival"]],
    "ERBB2": [["ERBB2", "PI3K", "AKT", "MTOR"], ["ERBB2", "RAS", "RAF", "MEK"]],
    "ALK": [["ALK", "RAS", "RAF", "MEK", "ERK"], ["ALK", "PI3K", "AKT"]],
    "MET": [["MET", "GRB2", "RAS", "MAPK"], ["MET", "PI3K", "AKT"]],
    "CDK4": [["Cyclin D", "CDK4", "RB1", "E2F", "S phase"]],
    "TP53": [["DNA damage", "TP53", "BAX/PUMA", "Caspases"]],
    "MYC": [["MAPK/PI3K input", "MYC", "Transcription", "Proliferation"]],
}

_SLIDER_MARK_STYLE = {"color": "#94A3B8", "fontSize": "10px"}
_RESTART_MARKS = {
    v: {"label": f"{v:.1f}", "style": _SLIDER_MARK_STYLE}
    for v in (0.1, 0.3, 0.5, 0.7, 0.9)
}
_DEGREE_MARKS = {
    v: {"label": str(v), "style": _SLIDER_MARK_STYLE}
    for v in (0, 3, 5, 10, 20)
}

_RIGHT_PANE_STYLE = {
    "width": "360px",
    "display": "flex",
    "flexDirection": "column",
    "overflowY": "auto",
    "overflowX": "hidden",
}

_CYTO_FRAME_STYLE = {
    "inset": "14px 18px 14px 18px",
    "border": "1px solid rgba(76, 103, 137, 0.35)",
    "borderRadius": "10px",
    "background": "radial-gradient(circle at 50% 45%, rgba(34, 211, 238, 0.075), transparent 34%), radial-gradient(circle at 50% 55%, rgba(245, 158, 11, 0.055), transparent 28%), linear-gradient(180deg, #07111f 0%, #050b14 100%)",
    "boxShadow": "inset 0 0 40px rgba(34, 211, 238, 0.035)",
    "overflow": "hidden",
}

_SMALL_MAP_BUTTON_STYLE = {
    "width": "32px",
    "height": "32px",
    "fontSize": "18px",
    "borderRadius": "7px",
}

_SEARCH_PANEL_STYLE = {
    "position": "static",
    "zIndex": 12,
    "width": "100%",
    "maxWidth": "none",
    "margin": 0,
}

_SEARCH_DROPDOWN_PROPS = {
    "withinPortal": True,
    "position": "bottom-start",
    "zIndex": 40,
}


def _clean_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}


def _row_text(record: dict, key: str, default: str = "") -> str:
    value = record.get(key)
    if value is None:
        return default
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return default
    return text


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


@lru_cache(maxsize=1)
def _load_cluster_mapping():
    import pandas as pd

    if not _CLUSTER_MAPPING_PATH.exists():
        logger.warning("Cluster mapping CSV missing: %s", _CLUSTER_MAPPING_PATH)
        return pd.DataFrame()

    df = pd.read_csv(_CLUSTER_MAPPING_PATH)
    if "gene" not in df.columns or "primary_cluster" not in df.columns:
        logger.warning("Cluster mapping CSV has invalid columns: %s", list(df.columns))
        return pd.DataFrame()

    df = df.copy()
    df["gene"] = df["gene"].astype(str).str.strip().str.upper()
    df["primary_cluster"] = df["primary_cluster"].astype(str).str.strip()
    for col in ("is_champion_target", "is_rwr_seed", "is_rwr_top10", "is_signor_drug_target"):
        if col not in df.columns:
            df[col] = False
        df[col] = df[col].map(_clean_bool)
    logger.info(
        "Loaded cluster mapping CSV: genes=%s clusters=%s path=%s",
        len(df),
        df["primary_cluster"].value_counts().to_dict(),
        _CLUSTER_MAPPING_PATH,
    )
    return df


@lru_cache(maxsize=1)
def _cluster_meta_by_gene() -> dict[str, dict]:
    df = _load_cluster_mapping()
    if df.empty:
        return {}
    return {str(row["gene"]): row for row in df.to_dict("records")}


def _build_cluster_groups(df=None) -> dict[str, list[str]]:
    df = _load_cluster_mapping() if df is None else df
    groups: dict[str, list[str]] = {cluster: [] for cluster in _CLUSTER_ORDER}
    if df.empty:
        return groups
    for row in df.to_dict("records"):
        cluster = str(row.get("primary_cluster") or "")
        gene = str(row.get("gene") or "").upper()
        if cluster in groups and gene:
            groups[cluster].append(gene)
    return groups


def _cluster_for_gene(gene: str | None) -> str | None:
    if not gene:
        return None
    meta = _cluster_meta_by_gene().get(str(gene).upper()) or {}
    cluster = meta.get("primary_cluster")
    return cluster if cluster in _CLUSTER_ORDER else None


def _gene_priority(gene: str, meta: dict, seed_set: set[str]) -> tuple:
    return (
        gene not in seed_set,
        not bool(meta.get("is_rwr_seed")),
        not bool(meta.get("is_rwr_top10")),
        not bool(meta.get("is_signor_drug_target")),
        -int(_SIGNOR_G.degree(gene)) if gene in _SIGNOR_G else 0,
        gene,
    )


def _visible_cluster_genes(seed: str | None = None, min_degree: int = 0) -> set[str]:
    df = _load_cluster_mapping()
    if df.empty:
        return set()

    min_degree = max(0, int(min_degree or 0))
    meta_by_gene = _cluster_meta_by_gene()
    visible: set[str] = set()
    mandatory_flags = ("is_rwr_seed", "is_rwr_top10", "is_signor_drug_target")
    cluster_groups = _build_cluster_groups(df)
    hub_template = set(_VISUAL_CLUSTER_TEMPLATE_GENES[_SEED_HUB_CLUSTER])

    for genes in _VISUAL_CLUSTER_TEMPLATE_GENES.values():
        visible.update(gene for gene in genes if gene in _SIGNOR_G)

    seed_gene = str(seed or "").upper()
    if seed_gene in _SIGNOR_G:
        visible.add(seed_gene)

    for cluster in _CLUSTER_ORDER:
        target_count = _VISUAL_CLUSTER_TARGET_COUNTS.get(cluster, _CLUSTER_TOP_N)
        current = [
            gene for gene in visible
            if meta_by_gene.get(gene, {}).get("primary_cluster") == cluster
            and gene not in hub_template
        ]
        in_graph = [gene for gene in cluster_groups.get(cluster, []) if gene in _SIGNOR_G]
        if min_degree:
            in_graph = [
                gene for gene in in_graph
                if _SIGNOR_G.degree(gene) >= min_degree or gene in visible
            ]
        for gene in sorted(in_graph, key=lambda item: (-int(_SIGNOR_G.degree(item)), item)):
            if len(current) >= target_count:
                break
            if gene in hub_template:
                continue
            if gene not in visible:
                visible.add(gene)
                current.append(gene)

    for gene, meta in meta_by_gene.items():
        cluster = meta.get("primary_cluster")
        if cluster not in _CLUSTER_ORDER or gene not in _SIGNOR_G:
            continue
        if any(bool(meta.get(flag)) for flag in mandatory_flags):
            cluster_count = sum(
                1 for item in visible
                if meta_by_gene.get(item, {}).get("primary_cluster") == cluster
            )
            if cluster_count < _VISUAL_CLUSTER_TARGET_COUNTS.get(cluster, _CLUSTER_TOP_N) + 2:
                visible.add(gene)
    return visible


def _cluster_counts_for_visible(visible: set[str], seed: str | None = None) -> dict[str, int]:
    counts = {cluster: 0 for cluster in _VISUAL_CLUSTER_ORDER}
    meta_by_gene = _cluster_meta_by_gene()
    visual_assignments = _visual_cluster_assignments(visible, seed)
    for gene in visible:
        cluster = visual_assignments.get(gene, meta_by_gene.get(gene, {}).get("primary_cluster"))
        if cluster in counts:
            counts[cluster] += 1
    return counts


def _cluster_center_xy(cluster: str) -> tuple[float, float]:
    x_ratio, y_ratio = _CLUSTER_CENTERS.get(cluster, _CLUSTER_CENTERS["RTK"])
    return (
        round((x_ratio - 0.5) * _CLUSTER_LAYOUT_WIDTH, 3),
        round((y_ratio - 0.5) * _CLUSTER_LAYOUT_HEIGHT, 3),
    )


def _seed_hub_label(seed: str | None) -> str:
    gene = str(seed or "EGFR").upper()
    return f"{gene} Signaling Hub"


def _seed_hub_subtitle(seed: str | None) -> str:
    gene = str(seed or "EGFR").upper()
    return f"Core {gene} network"


def _seed_hub_genes(seed: str | None, visible: set[str], limit: int = 16) -> set[str]:
    seed_gene = str(seed or "").upper()
    if not seed_gene or seed_gene not in _SIGNOR_G:
        return set()
    meta_by_gene = _cluster_meta_by_gene()
    hub: list[str] = []
    for gene in [seed_gene, *_VISUAL_CLUSTER_TEMPLATE_GENES[_SEED_HUB_CLUSTER]]:
        if gene in visible and gene in _SIGNOR_G and gene not in hub:
            hub.append(gene)
    neighbors = {
        node for node in (set(_SIGNOR_G.predecessors(seed_gene)) | set(_SIGNOR_G.successors(seed_gene)))
        if node in visible
    }
    ranked = sorted(
        neighbors,
        key=lambda gene: (
            not bool(meta_by_gene.get(gene, {}).get("is_rwr_top10")),
            not bool(meta_by_gene.get(gene, {}).get("is_champion_target")),
            -int(_SIGNOR_G.degree(gene)) if gene in _SIGNOR_G else 0,
            gene,
        ),
    )
    for gene in ranked:
        if len(hub) >= limit:
            break
        if gene not in hub:
            hub.append(gene)
    return set(hub[:limit])


def _visual_cluster_assignments(visible: set[str], seed: str | None = None) -> dict[str, str]:
    assignments: dict[str, str] = {}
    for cluster in _CLUSTER_ORDER:
        for gene in _VISUAL_CLUSTER_TEMPLATE_GENES.get(cluster, []):
            if gene in visible:
                assignments[gene] = cluster
    for gene in _seed_hub_genes(seed, visible):
        assignments[gene] = _SEED_HUB_CLUSTER
    return assignments


def _ordered_visual_cluster_genes(visible: set[str], seed: str | None = None) -> dict[str, list[str]]:
    meta_by_gene = _cluster_meta_by_gene()
    seed_set = {str(seed or "").upper()} if seed else set()
    visual_assignments = _visual_cluster_assignments(visible, seed)
    ordered: dict[str, list[str]] = {}

    for cluster in _VISUAL_CLUSTER_ORDER:
        genes = [
            gene for gene in visible
            if visual_assignments.get(gene, meta_by_gene.get(gene, {}).get("primary_cluster")) == cluster
            and gene in _SIGNOR_G
        ]
        if not genes:
            continue
        template = _VISUAL_CLUSTER_TEMPLATE_GENES.get(cluster, [])
        template_rank = {gene: idx for idx, gene in enumerate(template)}
        genes = sorted(
            genes,
            key=lambda gene: (
                gene not in seed_set,
                template_rank.get(gene, 10_000),
                *_gene_priority(gene, meta_by_gene.get(gene, {}), seed_set),
            ),
        )
        ordered[cluster] = genes
    return ordered


def _cluster_representatives(visible: set[str], seed: str | None = None) -> set[str]:
    reps: set[str] = set()
    TOP_N = 5  # cluster당 최소 노드 수 보장
    for cluster, genes in _ordered_visual_cluster_genes(visible, seed).items():
        if not genes:
            continue
        if cluster == _SEED_HUB_CLUSTER and seed:
            seed_gene = str(seed).upper()
            if seed_gene in genes:
                reps.add(seed_gene)
        for g in genes[:TOP_N]:
            reps.add(g)
    return reps


def _cluster_positions(visible: set[str], seed: str | None = None) -> dict[str, dict[str, float]]:
    positions: dict[str, dict[str, float]] = {}
    ordered = _ordered_visual_cluster_genes(visible, seed)

    for cluster, genes in ordered.items():
        if not genes:
            continue
        cx, cy = _cluster_center_xy(cluster)
        rx, ry = _CLUSTER_TEMPLATE_RADII.get(cluster, (120, 90))
        slots = _HUB_SLOT_OFFSETS if cluster == _SEED_HUB_CLUSTER else _CLUSTER_SLOT_OFFSETS
        for idx, gene in enumerate(genes):
            if idx < len(slots):
                ox, oy = slots[idx]
                positions[gene] = {
                    "x": round(cx + ox * rx, 3),
                    "y": round(cy + oy * ry, 3),
                }
                continue
            ring_idx = idx - len(slots)
            angle = (-math.pi / 2) + (2 * math.pi * ring_idx / max(1, len(genes) - len(slots)))
            radius_x = rx * (0.54 if cluster == _SEED_HUB_CLUSTER else 0.50)
            radius_y = ry * (0.56 if cluster == _SEED_HUB_CLUSTER else 0.52)
            positions[gene] = {
                "x": round(cx + math.cos(angle) * radius_x, 3),
                "y": round(cy + math.sin(angle) * radius_y, 3),
            }
    return positions


def _node_label(gene: str, meta: dict) -> str:
    return gene


def _append_visual_template_edges(
    elements: list[dict],
    visible: set[str],
    visual_assignments: dict[str, str],
    seed_gene: str | None,
) -> None:
    meta_by_gene = _cluster_meta_by_gene()
    ordered = _ordered_visual_cluster_genes(visible, seed_gene)
    seen_pairs: set[tuple[str, str]] = set()
    for element in elements:
        data = element.get("data") or {}
        source = data.get("source")
        target = data.get("target")
        if source and target:
            seen_pairs.add((str(source), str(target)))
            seen_pairs.add((str(target), str(source)))

    def add_edge(src: str, tgt: str, important: bool = False) -> None:
        if src == tgt or src not in visible or tgt not in visible or (src, tgt) in seen_pairs:
            return
        src_cluster = meta_by_gene.get(src, {}).get("primary_cluster")
        tgt_cluster = meta_by_gene.get(tgt, {}).get("primary_cluster")
        src_visual = visual_assignments.get(src, src_cluster)
        tgt_visual = visual_assignments.get(tgt, tgt_cluster)
        is_intra = bool(src_visual and src_visual == tgt_visual)
        edge_scope = "cluster-edge-intra" if is_intra else "cluster-edge-cross"
        if important:
            edge_scope += " cluster-edge-important"
        elements.append({
            "data": {
                "id": f"visual::{src}__{tgt}",
                "source": src,
                "target": tgt,
                "effect": "regulates",
                "mechanism": "visual template scaffold",
                "score": 0.0,
                "source_cluster": src_cluster or "",
                "target_cluster": tgt_cluster or "",
                "source_visual_cluster": src_visual or "",
                "target_visual_cluster": tgt_visual or "",
                "is_intra_cluster": is_intra,
                "is_important": important,
                "is_visual_template_edge": True,
            },
            "classes": f"signor-edge-neutral {edge_scope} cluster-edge-visual",
        })
        seen_pairs.add((src, tgt))
        seen_pairs.add((tgt, src))

    for cluster, genes in ordered.items():
        if len(genes) < 2:
            continue
        anchor = genes[0]
        for gene in genes[1:]:
            add_edge(anchor, gene, important=(cluster == _SEED_HUB_CLUSTER))
        ring = genes[1:] if cluster == _SEED_HUB_CLUSTER else genes
        for src, tgt in zip(ring, ring[1:] + ring[:1]):
            add_edge(src, tgt, important=False)
        if len(ring) >= 6:
            for idx in range(0, len(ring) - 3, 3):
                add_edge(ring[idx], ring[idx + 3], important=False)

    hub = ordered.get(_SEED_HUB_CLUSTER) or []
    hub_anchor = str(seed_gene or "").upper()
    if hub_anchor not in hub:
        hub_anchor = hub[0] if hub else ""
    if hub_anchor:
        for cluster in _CLUSTER_ORDER:
            for gene in (ordered.get(cluster) or [])[:2]:
                add_edge(hub_anchor, gene, important=True)


def _drug_node_id_v6(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")[:36]
    digest = hashlib.sha1(str(name).lower().encode("utf-8")).hexdigest()[:8]
    return f"drug::{slug or 'entity'}::{digest}"


def _drug_type_class_v6(type_a: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(type_a or "entity").lower()).strip("-")
    return f"signor-drug-{slug or 'entity'}"


def _drug_edge_classes_v6(effect: str, mechanism: str) -> str:
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


def _build_v6_drug_elements(visible_nodes: set[str], positions: dict[str, dict[str, float]]) -> list[dict]:
    drug_nodes: dict[str, dict] = {}
    drug_edges: list[dict] = []
    per_target_counts: dict[str, int] = defaultdict(int)

    for idx, row in enumerate(_SIGNOR_DRUG_EDGES):
        target = _row_text(row, "ENTITYB").upper()
        name = _row_text(row, "ENTITYA")
        if not target or target not in visible_nodes or not name:
            continue

        type_a = _row_text(row, "TYPEA", "entity")
        effect = _row_text(row, "EFFECT")
        mechanism = _row_text(row, "MECHANISM")
        compound_id = map_signor_drug_name(name) or ""
        node_id = _drug_node_id_v6(name)

        target_pos = positions.get(target, {"x": 0, "y": 0})
        drug_idx = per_target_counts[target]
        per_target_counts[target] += 1
        angle = -math.pi / 2 + (drug_idx % 10) * (2 * math.pi / 10)
        ring = drug_idx // 10
        radius = 92 + ring * 28
        node_pos = {
            "x": round(target_pos["x"] + math.cos(angle) * radius, 3),
            "y": round(target_pos["y"] + math.sin(angle) * radius, 3),
        }

        if node_id not in drug_nodes:
            drug_nodes[node_id] = {
                "data": {
                    "id": node_id,
                    "label": name,
                    "node_type": "drug",
                    "type": "drug",
                    "drug_name": name,
                    "compound_id": compound_id,
                    "signor_type": type_a,
                    "signor_types": [],
                    "targets": [],
                    "mechanisms": [],
                    "effects": [],
                    "pmids": [],
                },
                "position": node_pos,
                "classes": " ".join([
                    "signor-node",
                    "signor-drug-node",
                    _drug_type_class_v6(type_a),
                ]),
            }

        data = drug_nodes[node_id]["data"]
        if compound_id and not data.get("compound_id"):
            data["compound_id"] = compound_id
        _append_unique(data["signor_types"], type_a)
        _append_unique(data["targets"], target)
        _append_unique(data["mechanisms"], mechanism)
        _append_unique(data["effects"], effect)
        _append_unique(data["pmids"], _clean_ref(row.get("PMID")), limit=5)
        _append_unique(data["pmids"], _clean_ref(row.get("SENTENCE")), limit=5)

        drug_edges.append({
            "data": {
                "id": f"{node_id}__{target}__drug__{idx}",
                "source": node_id,
                "target": target,
                "effect": effect,
                "mechanism": mechanism,
                "score": _safe_float(row.get("SCORE")),
                "node_type": "drug_edge",
                "type": "drug_edge",
                "is_intra_cluster": False,
                "is_important": True,
            },
            "classes": _drug_edge_classes_v6(effect, mechanism),
        })

    return list(drug_nodes.values()) + drug_edges


def _build_cluster_island_elements(
    influenced: dict | None,
    seeds: list[str],
    min_degree: int,
    show_drugs: bool,
) -> tuple[list[dict], dict[str, int]]:
    influenced = influenced or {}
    seed_set = {str(seed).upper() for seed in seeds or []}
    visible = _visible_cluster_genes(seeds[0] if seeds else None, min_degree=min_degree)
    meta_by_gene = _cluster_meta_by_gene()
    seed_gene = seeds[0] if seeds else None
    positions = _cluster_positions(visible, seed_gene)
    cluster_reps = _cluster_representatives(visible, seed_gene)
    visual_assignments = _visual_cluster_assignments(visible, seed_gene)
    selected_cluster = _SEED_HUB_CLUSTER if visual_assignments else (_cluster_for_gene(seeds[0]) if seeds else None)
    elements: list[dict] = []

    for cluster in _VISUAL_CLUSTER_ORDER:
        cluster_genes = [
            gene for gene in visible
            if visual_assignments.get(gene, meta_by_gene.get(gene, {}).get("primary_cluster")) == cluster
        ]
        if cluster_genes:
            cluster_label = _seed_hub_label(seed_gene) if cluster == _SEED_HUB_CLUSTER else _CLUSTER_LABELS[cluster]
            cluster_subtitle = _seed_hub_subtitle(seed_gene) if cluster == _SEED_HUB_CLUSTER else _CLUSTER_SUBTITLES[cluster]
            classes = ["cluster-hull"]
            if cluster == _SEED_HUB_CLUSTER:
                classes.append("seed-hub-hull")
            if cluster == selected_cluster:
                classes.append("selected-cluster")
            elements.append({
                "data": {
                    "id": f"cluster::{cluster}",
                    "label": cluster_label,
                    "cluster_label": cluster_label,
                    "subtitle": cluster_subtitle,
                    "node_type": "cluster_hull",
                    "type": "cluster_hull",
                    "cluster": cluster,
                    "visual_cluster": cluster,
                    "cluster_color": _VISUAL_CLUSTER_COLORS.get(cluster, "#64748B"),
                    "gene_count": len(cluster_genes),
                },
                "classes": " ".join(classes),
                "selectable": False,
                "grabbable": False,
                "locked": True,
            })

    for gene in sorted(visible, key=lambda item: _gene_priority(item, meta_by_gene.get(item, {}), seed_set)):
        meta = meta_by_gene.get(gene, {})
        cluster = meta.get("primary_cluster")
        if cluster not in _CLUSTER_ORDER:
            continue
        visual_cluster = visual_assignments.get(gene, cluster)
        visual_color = _VISUAL_CLUSTER_COLORS.get(visual_cluster, CLUSTER_COLORS.get(cluster, "#64748B"))
        is_template_node = gene in set(_VISUAL_CLUSTER_TEMPLATE_GENES.get(visual_cluster, []))
        visual_cx, visual_cy = _cluster_center_xy(visual_cluster)
        visual_rx, visual_ry = _CLUSTER_TEMPLATE_RADII.get(visual_cluster, (120, 90))
        is_seed = gene in seed_set
        is_target = bool(_SIGNOR_G.nodes[gene].get("is_nsclc_target", 0)) if gene in _SIGNOR_G else False
        score = influenced.get(gene, 0.0)
        classes = ["signor-node", "cluster-node"]
        if visual_cluster == _SEED_HUB_CLUSTER:
            classes.append("seed-hub-node")
        if is_target:
            classes.append("signor-target")
        if meta.get("is_champion_target"):
            classes.append("signor-champion-target")
        if meta.get("is_rwr_top10"):
            classes.append("signor-rwr-top10")
        if meta.get("is_signor_drug_target"):
            classes.append("signor-drug-target")
        if is_seed:
            classes.append("signor-seed")
        if gene in cluster_reps:
            classes.append("show_label")

        node_data = {
            "id": gene,
            "label": _node_label(gene, meta),
            "label_with_star": gene,
            "gene": gene,
            "cluster": cluster,
            "cluster_label": _CLUSTER_LABELS.get(cluster, cluster),
            "visual_cluster": visual_cluster,
            "visual_cluster_label": _seed_hub_label(seed_gene) if visual_cluster == _SEED_HUB_CLUSTER else _CLUSTER_LABELS.get(visual_cluster, visual_cluster),
            "cluster_color": visual_color,
            "cluster_cx": visual_cx,
            "cluster_cy": visual_cy,
            "cluster_rx": visual_rx,
            "cluster_ry": visual_ry,
            "score": round(float(score or 0.0), 4),
            "is_target": is_target,
            "is_champion_target": bool(meta.get("is_champion_target")),
            "is_rwr_seed": bool(meta.get("is_rwr_seed")),
            "is_rwr_top10": bool(meta.get("is_rwr_top10")),
            "is_signor_drug_target": bool(meta.get("is_signor_drug_target")),
            "is_cluster_rep": gene in cluster_reps,
            "is_template_node": is_template_node,
            "is_high_degree_label": int(_SIGNOR_G.degree(gene)) >= 8 if gene in _SIGNOR_G else False,
            "node_type": "protein",
            "type": "protein",
            "role": "seed" if is_seed else "",
            "degree": int(_SIGNOR_G.degree(gene)) if gene in _SIGNOR_G else 0,
            "kegg_pathways": meta.get("kegg_pathways") or "",
            "parent": f"cluster::{visual_cluster}",
        }
        elements.append({
            "data": node_data,
            "position": positions.get(gene, {"x": 0, "y": 0}),
            "classes": " ".join(classes),
            "locked": False,
            "grabbable": True,
        })

    for src, tgt, attrs in _SIGNOR_G.edges(data=True):
        if src not in visible or tgt not in visible:
            continue
        sign = attrs.get("sign", 0)
        if sign > 0:
            edge_class = "signor-edge-up"
        elif sign < 0:
            edge_class = "signor-edge-down"
        else:
            edge_class = "signor-edge-neutral"
        src_cluster = meta_by_gene.get(src, {}).get("primary_cluster")
        tgt_cluster = meta_by_gene.get(tgt, {}).get("primary_cluster")
        src_visual_cluster = visual_assignments.get(src, src_cluster)
        tgt_visual_cluster = visual_assignments.get(tgt, tgt_cluster)
        is_intra = bool(src_visual_cluster and src_visual_cluster == tgt_visual_cluster)
        is_important = (
            src in seed_set
            or tgt in seed_set
            or bool(meta_by_gene.get(src, {}).get("is_rwr_top10"))
            or bool(meta_by_gene.get(tgt, {}).get("is_rwr_top10"))
        )
        if not is_intra and not is_important:
            continue
        edge_scope = "cluster-edge-intra" if is_intra else "cluster-edge-cross"
        if is_important and not is_intra:
            edge_scope += " cluster-edge-important"
        elements.append({
            "data": {
                "id": f"{src}__{tgt}",
                "source": src,
                "target": tgt,
                "effect": attrs.get("effect") or "",
                "mechanism": attrs.get("mechanism") or "",
                "score": float(attrs.get("score") or 0),
                "source_cluster": src_cluster or "",
                "target_cluster": tgt_cluster or "",
                "source_visual_cluster": src_visual_cluster or "",
                "target_visual_cluster": tgt_visual_cluster or "",
                "is_intra_cluster": is_intra,
                "is_important": is_important,
            },
            "classes": f"{edge_class} {edge_scope}",
        })

    _append_visual_template_edges(elements, visible, visual_assignments, seed_gene)

    if show_drugs:
        elements.extend(_build_v6_drug_elements(visible, positions))
    return elements, _cluster_counts_for_visible(visible, seed_gene)


def _view_state(mode: str = "cluster", focus_node: str | None = None, focus: dict | None = None) -> dict:
    return {
        "mode": mode if mode in {"cluster", "ego"} else "cluster",
        "focus_node": str(focus_node or "").upper() or None,
        "focus": focus or None,
    }


def _push_view_history(history: list | None, current_view: dict | None) -> list:
    cur = list(history or [])
    view = current_view or _view_state()
    cur.append(view)
    return cur[-_VIEW_HISTORY_MAX_DEPTH:]


def _ego_protein_id(gene: str) -> str:
    return f"ego::{str(gene or '').upper()}"


def _ego_cluster_id(cluster: str) -> str:
    return f"ego-cluster::{cluster}"


def _gene_from_node_data(node_data: dict | None) -> str:
    data = node_data or {}
    gene = data.get("gene") or data.get("id") or data.get("label") or ""
    gene = str(gene).replace("ego::", "", 1).upper()
    return gene


def _state_focus_or_default(view_state: dict | None) -> dict:
    focus = (view_state or {}).get("focus")
    if isinstance(focus, dict) and focus.get("id"):
        return focus
    node = (view_state or {}).get("focus_node")
    if node:
        return {"id": node, "type": "target" if node in _NSCLC_TARGET_SET else "protein", "_nav": True}
    return {"id": "EGFR", "type": "target", "_nav": True}


def _rank_neighbors(center: str, limit: int = 16) -> list[str]:
    if center not in _SIGNOR_G:
        return []
    meta_by_gene = _cluster_meta_by_gene()
    neighbors = set(_SIGNOR_G.predecessors(center)) | set(_SIGNOR_G.successors(center))
    ranked = sorted(
        [node for node in neighbors if node in _SIGNOR_G],
        key=lambda node: (
            not bool(meta_by_gene.get(node, {}).get("is_champion_target")),
            -int(_SIGNOR_G.degree(node)),
            node,
        ),
    )
    return ranked[:limit]


def _ego_drug_rows(center: str, limit: int = 8) -> list[dict]:
    rows, _ = _drug_connections_for_target(center, limit=None)
    return rows[:limit]


def _build_ego_elements(
    center: str | None,
    influenced: dict | None,
    show_drugs: bool,
) -> tuple[list[dict], dict[str, int]]:
    center = str(center or "EGFR").upper()
    if center not in _SIGNOR_G:
        center = "EGFR"
    influenced = influenced or {}
    meta_by_gene = _cluster_meta_by_gene()
    center_meta = meta_by_gene.get(center, {})

    neighbors = _rank_neighbors(center, limit=16)
    rwr_top = [
        gene for gene, _score in sorted(
            influenced.items(),
            key=lambda item: (-float(item[1] or 0), str(item[0])),
        )
        if gene != center and gene in _SIGNOR_G
    ][:5]

    protein_nodes = [center]
    for gene in [*neighbors, *rwr_top]:
        if gene not in protein_nodes:
            protein_nodes.append(gene)

    positions: dict[str, dict[str, float]] = {center: {"x": 0, "y": 0}}
    neighbor_set = set(neighbors)
    rwr_set = set(rwr_top)
    ring_nodes = [gene for gene in protein_nodes if gene != center]
    for idx, gene in enumerate(ring_nodes):
        radius = 155 if gene in neighbor_set else 235
        angle = (-math.pi / 2) + (2 * math.pi * idx / max(1, len(ring_nodes)))
        positions[gene] = {
            "x": round(math.cos(angle) * radius, 3),
            "y": round(math.sin(angle) * radius, 3),
        }

    elements: list[dict] = []
    ego_clusters = sorted({
        meta_by_gene.get(gene, {}).get("primary_cluster")
        for gene in protein_nodes
        if meta_by_gene.get(gene, {}).get("primary_cluster") in _CLUSTER_ORDER
    })
    for cluster in ego_clusters:
        elements.append({
            "data": {
                "id": _ego_cluster_id(cluster),
                "label": _CLUSTER_LABELS[cluster],
                "cluster_label": _CLUSTER_LABELS[cluster],
                "subtitle": _CLUSTER_SUBTITLES[cluster],
                "node_type": "cluster_hull",
                "type": "cluster_hull",
                "cluster": cluster,
                "cluster_color": CLUSTER_COLORS.get(cluster, "#64748B"),
            },
            "classes": "cluster-hull ego-hidden-hull",
            "selectable": False,
            "grabbable": False,
            "locked": True,
        })

    for gene in protein_nodes:
        meta = meta_by_gene.get(gene, {})
        cluster = meta.get("primary_cluster")
        score = influenced.get(gene, 0.0)
        is_center = gene == center
        is_target = bool(_SIGNOR_G.nodes[gene].get("is_nsclc_target", 0)) if gene in _SIGNOR_G else False
        classes = ["signor-node", "cluster-node", "ego-node"]
        if is_center:
            classes.append("ego-center")
        elif gene in rwr_set:
            classes.append("ego-rwr")
        else:
            classes.append("ego-neighbor")
        if is_target:
            classes.append("signor-target")
        if meta.get("is_champion_target"):
            classes.append("signor-champion-target")
        if meta.get("is_rwr_top10") or gene in rwr_set:
            classes.append("signor-rwr-top10")
        if meta.get("is_signor_drug_target"):
            classes.append("signor-drug-target")

        node_data = {
            "id": _ego_protein_id(gene),
            "label": _node_label(gene, meta),
            "label_with_star": gene,
            "gene": gene,
            "cluster": cluster if cluster in _CLUSTER_ORDER else "",
            "cluster_label": _CLUSTER_LABELS.get(cluster, cluster or ""),
            "cluster_color": CLUSTER_COLORS.get(cluster, "#64748B"),
            "score": round(float(score or 0.0), 4),
            "is_target": is_target,
            "is_champion_target": bool(meta.get("is_champion_target")),
            "is_rwr_seed": bool(meta.get("is_rwr_seed")) or is_center,
            "is_rwr_top10": bool(meta.get("is_rwr_top10")) or gene in rwr_set,
            "is_signor_drug_target": bool(meta.get("is_signor_drug_target")),
            "node_type": "protein",
            "type": "protein",
            "role": "seed" if is_center else "",
            "degree": int(_SIGNOR_G.degree(gene)) if gene in _SIGNOR_G else 0,
            "kegg_pathways": meta.get("kegg_pathways") or "",
        }
        if cluster in _CLUSTER_ORDER:
            node_data["parent"] = _ego_cluster_id(cluster)
        elements.append({
            "data": node_data,
            "position": positions.get(gene, {"x": 0, "y": 0}),
            "classes": " ".join(classes),
        })

    visible = set(protein_nodes)
    for src, tgt, attrs in _SIGNOR_G.edges(data=True):
        if src not in visible or tgt not in visible:
            continue
        sign = attrs.get("sign", 0)
        if sign > 0:
            edge_class = "signor-edge-up"
        elif sign < 0:
            edge_class = "signor-edge-down"
        else:
            edge_class = "signor-edge-neutral"
        classes = [edge_class, "ego-edge"]
        if src == center or tgt == center:
            classes.append("ego-center-edge")
        src_cluster = meta_by_gene.get(src, {}).get("primary_cluster")
        tgt_cluster = meta_by_gene.get(tgt, {}).get("primary_cluster")
        is_intra = bool(src_cluster and src_cluster == tgt_cluster)
        is_important = src == center or tgt == center or src in rwr_set or tgt in rwr_set
        elements.append({
            "data": {
                "id": f"ego::{src}__{tgt}",
                "source": _ego_protein_id(src),
                "target": _ego_protein_id(tgt),
                "effect": attrs.get("effect") or "",
                "mechanism": attrs.get("mechanism") or "",
                "score": float(attrs.get("score") or 0),
                "source_cluster": src_cluster or "",
                "target_cluster": tgt_cluster or "",
                "is_intra_cluster": is_intra,
                "is_important": is_important,
            },
            "classes": " ".join(classes),
        })

    if show_drugs or center_meta.get("is_signor_drug_target"):
        drug_rows = _ego_drug_rows(center, limit=8)
        for idx, row in enumerate(drug_rows):
            drug_name = _row_text(row, "ENTITYA")
            if not drug_name:
                continue
            compound_id = map_signor_drug_name(drug_name) or ""
            node_id = f"ego::{_drug_node_id_v6(drug_name)}"
            angle = (-math.pi / 2) + (2 * math.pi * idx / max(1, len(drug_rows)))
            positions[node_id] = {
                "x": round(math.cos(angle) * 285, 3),
                "y": round(math.sin(angle) * 285, 3),
            }
            elements.append({
                "data": {
                    "id": node_id,
                    "label": drug_name,
                    "node_type": "drug",
                    "type": "drug",
                    "drug_name": drug_name,
                    "compound_id": compound_id,
                    "signor_type": _row_text(row, "TYPEA", "entity"),
                    "targets": [center],
                    "mechanisms": [_row_text(row, "MECHANISM")] if _row_text(row, "MECHANISM") else [],
                    "effects": [_row_text(row, "EFFECT")] if _row_text(row, "EFFECT") else [],
                    "pmids": [_clean_ref(row.get("PMID"))] if _clean_ref(row.get("PMID")) else [],
                },
                "position": positions[node_id],
                "classes": "signor-node signor-drug-node ego-drug-node",
            })
            elements.append({
                "data": {
                    "id": f"{node_id}__{center}__ego_drug__{idx}",
                    "source": node_id,
                    "target": _ego_protein_id(center),
                    "effect": _row_text(row, "EFFECT"),
                    "mechanism": _row_text(row, "MECHANISM"),
                    "score": _safe_float(row.get("SCORE")),
                    "node_type": "drug_edge",
                    "type": "drug_edge",
                    "is_intra_cluster": False,
                    "is_important": True,
                },
                "classes": _drug_edge_classes_v6(_row_text(row, "EFFECT"), _row_text(row, "MECHANISM")),
            })

    return elements, _cluster_counts_for_visible({gene for gene in protein_nodes if gene in meta_by_gene})


def _build_ego_graph(center: str | None, restart_prob: float, show_drugs: bool):
    center = str(center or "EGFR").upper()
    if center not in _SIGNOR_G:
        center = "EGFR"
    requested_restart_prob = float(restart_prob or _RWR_COMPUTED_RESTART_PROB)
    res = rwr_from_seeds(
        [center],
        restart_prob=_RWR_COMPUTED_RESTART_PROB,
        top_n=None,
    )
    influenced = dict(zip(res["gene"], res["influence"]))
    elements, cluster_counts = _build_ego_elements(center, influenced, bool(show_drugs))
    rwr_data = {
        "seeds": [center],
        "restart_prob": _RWR_COMPUTED_RESTART_PROB,
        "requested_restart_prob": requested_restart_prob,
        "display_node_count": sum(
            1
            for ele in elements
            if (ele.get("data") or {}).get("node_type") == "protein"
        ),
        "cluster_counts": cluster_counts,
        "view_mode": "ego",
        "top10": [
            {
                "gene": row["gene"],
                "influence": round(float(row["influence"]), 4),
                "is_nsclc_target": bool(row["is_nsclc_target"]),
            }
            for _, row in res[~res["is_seed"]].head(10).iterrows()
        ],
        "n_iter": int(res.attrs.get("n_iter_converged", 0)),
    }
    return elements, rwr_data


def _build_pathway_stylesheet(show_hulls: bool = True) -> list[dict]:
    stylesheet = list(SIGNOR_STYLESHEET)
    stylesheet.extend([
        {
            "selector": "node.cluster-hull, $node > node",
            "style": {
                "shape": "round-rectangle",
                "label": "",
                "font-size": "13px",
                "font-weight": "bold",
                "text-valign": "top",
                "text-halign": "left",
                "text-margin-y": -8,
                "text-margin-x": 8,
                "padding": "40px",
                "background-opacity": 0,
                "border-width": 0,
                "border-opacity": 0,
                "corner-radius": 24,
                "color": "transparent",
                "text-opacity": 0,
                "shadow-blur": 18,
                "shadow-opacity": 0,
                "events": "no",
                "z-index": 0,
            },
        },
        {
            "selector": "node.cluster-hull.selected-cluster",
            "style": {
                "background-opacity": 0,
                "border-width": 0,
                "border-opacity": 0,
                "color": "transparent",
                "text-opacity": 0,
                "shadow-opacity": 0,
            },
        },
        {
            "selector": "node.cluster-node",
            "style": {
                "shape": "ellipse",
                "label": "",
                "background-color": "#475569",
                "border-color": "#64748B",
                "color": "#CBD5E1",
                "text-outline-color": "#050B14",
                "text-outline-width": 3,
                "text-outline-opacity": 0.85,
                "text-valign": "bottom",
                "text-margin-y": 4,
                "font-size": "11px",
                "font-weight": "600",
                "width": 16,
                "height": 16,
                "border-width": 2,
                "background-opacity": 0.01,
                "border-opacity": 0,
                "background-blacken": 0.14,
                "overlay-opacity": 0,
                "overlay-padding": 0,
                "shadow-blur": 8,
                "shadow-opacity": 0,
                "opacity": 0.015,
                "z-index": 12,
            },
        },
        {
            "selector": 'node[node_type = "protein"], node[type = "protein"]',
            "style": {
                "label": "",
            },
        },
        {
            "selector": 'node[role = "seed"], node[?is_rwr_top10], node[?is_champion_target], node[?is_cluster_rep], node[?is_high_degree_label], node.show_label, node.hover_label, node.highlighted',
            "style": {
                "label": "",
                "font-size": "11px",
                "font-weight": "600",
                "color": "#CBD5E1",
                "text-outline-width": 3,
                "text-outline-color": "#050B14",
                "text-outline-opacity": 0.85,
                "text-valign": "bottom",
                "text-margin-y": 4,
                "text-wrap": "none",
            },
        },
        {
            "selector": "node[?is_champion_target]",
            "style": {
                "label": "",
            },
        },
        {
            "selector": "edge",
            "style": {
                "width": 0.4,
                "opacity": 0.01,
                "curve-style": "bezier",
            },
        },
        {
            "selector": "edge[?is_intra_cluster], edge.cluster-edge-intra",
            "style": {
                "width": 1.1,
                "opacity": 0.01,
            },
        },
        {
            "selector": "edge[!is_intra_cluster], edge.cluster-edge-cross",
            "style": {
                "width": 0.8,
                "opacity": 0.01,
                "curve-style": "unbundled-bezier",
                "control-point-distances": -40,
                "control-point-weights": 0.5,
            },
        },
        {
            "selector": "edge[!is_intra_cluster][?is_important], edge.cluster-edge-important",
            "style": {
                "width": 1.4,
                "opacity": 0.01,
            },
        },
        {
            "selector": "edge.signor-drug-edge",
            "style": {
                "line-style": "dashed",
                "width": 1.4,
                "opacity": 0.01,
                "z-index": 2,
            },
        },
        {
            "selector": "node.seed-hub-node",
            "style": {
                "background-color": "#F59E0B",
                "border-color": "#FCD34D",
                "overlay-color": "#F59E0B",
                "overlay-opacity": 0.38,
                "overlay-padding": 10,
                "shadow-color": "#F59E0B",
                "shadow-blur": 14,
                "shadow-opacity": 0.34,
                "opacity": 0.98,
            },
        },
        {
            "selector": "node[?is_cluster_rep], node[?is_high_degree_label]",
            "style": {
                "width": 17,
                "height": 17,
                "border-width": 2,
                "opacity": 0.9,
            },
        },
        {
            "selector": "node.signor-target",
            "style": {
                "background-color": "#22C55E",
                "width": 18,
                "height": 18,
                "border-color": "#86EFAC",
                "border-width": 1.8,
                "overlay-color": "#22C55E",
                "overlay-opacity": 0.35,
                "overlay-padding": 10,
                "z-index": 18,
            },
        },
        {
            "selector": "node.signor-rwr-top10",
            "style": {
                "background-color": "#F59E0B",
                "border-color": "#FCD34D",
                "width": 22,
                "height": 22,
                "border-width": 2.5,
                "overlay-opacity": 0.45,
                "overlay-color": "#F59E0B",
                "overlay-padding": 12,
                "shadow-blur": 14,
                "shadow-color": "#F59E0B",
                "shadow-opacity": 0.35,
                "opacity": 1,
                "z-index": 22,
            },
        },
        {
            "selector": "node.signor-drug-target",
            "style": {
                "border-width": 3,
                "border-color": "#C084FC",
                "overlay-opacity": 0.4,
                "overlay-padding": 10,
                "shadow-blur": 12,
                "shadow-opacity": 0.34,
            },
        },
        {
            "selector": 'node.signor-seed, node[role = "seed"]',
            "style": {
                "background-color": SEED_COLOR,
                "border-color": "#FCA5A5",
                "border-width": 3,
                "color": "#FFFFFF",
                "width": 32,
                "height": 32,
                "font-size": "12px",
                "font-weight": "900",
                "background-blacken": 0.08,
                "overlay-color": SEED_COLOR,
                "overlay-opacity": 0.65,
                "overlay-padding": 18,
                "shadow-color": SEED_COLOR,
                "shadow-blur": 24,
                "shadow-opacity": 0.55,
                "shadow-offset-x": 0,
                "shadow-offset-y": 0,
                "opacity": 1,
                "z-index": 100,
            },
        },
        {
            "selector": "node.ego-center",
            "style": {
                "width": 36,
                "height": 36,
                "border-width": 4,
                "overlay-opacity": 0.64,
                "overlay-padding": 18,
                "shadow-blur": 38,
                "shadow-opacity": 0.95,
                "z-index": 110,
            },
        },
        {
            "selector": "node.ego-neighbor",
            "style": {
                "width": 18,
                "height": 18,
            },
        },
        {
            "selector": 'node.ego-drug-node, node[type = "drug"]',
            "style": {
                "shape": "diamond",
                "background-color": "#8B5CF6",
                "border-color": "#C4B5FD",
                "border-width": 1.5,
                "overlay-color": "#8B5CF6",
                "overlay-opacity": 0.35,
                "overlay-padding": 8,
                "shadow-color": "#8B5CF6",
                "shadow-blur": 14,
                "shadow-opacity": 0.45,
                "width": 16,
                "height": 16,
                "z-index": 24,
            },
        },
        {
            "selector": "edge.ego-center-edge",
            "style": {
                "width": 2,
                "opacity": 0.72,
            },
        },
        {
            "selector": ".faded",
            "style": {
                "opacity": 0.15,
            },
        },
        {
            "selector": "edge.faded",
            "style": {
                "opacity": 0.04,
            },
        },
        {
            "selector": ".highlighted",
            "style": {
                "opacity": 1,
                "z-index": 99,
            },
        },
        {
            "selector": "edge.highlighted",
            "style": {
                "opacity": 0.85,
                "width": 2.5,
                "z-index": 99,
            },
        },
        {
            "selector": 'node[node_type = "protein"], node[node_type = "drug"], node[type = "protein"], node[type = "drug"]',
            "style": {
                "label": "",
                "background-opacity": 0.01,
                "border-opacity": 0,
                "overlay-opacity": 0,
                "shadow-opacity": 0,
                "opacity": 0.015,
            },
        },
        {
            "selector": "edge",
            "style": {
                "opacity": 0.01,
                "width": 0.4,
                "target-arrow-shape": "none",
                "source-arrow-shape": "none",
            },
        },
    ])

    for cluster, color in CLUSTER_COLORS.items():
        stylesheet.extend([
            {
                "selector": f'node.cluster-node[cluster = "{cluster}"]',
                "style": {
                    "border-color": color,
                    "overlay-color": color,
                    "shadow-color": color,
                },
            },
            {
                "selector": f'node.cluster-hull[cluster = "{cluster}"]',
                "style": {
                    "background-color": color,
                    "border-color": color,
                    "shadow-color": color,
                },
            },
        ])
    return stylesheet


def _cluster_minimap():
    visible = _visible_cluster_genes("EGFR", min_degree=0)
    positions = _cluster_positions(visible, "EGFR")
    if not positions:
        return html.Div(id=_PATHWAY_MINIMAP_ID, className="pathway-minimap")

    xs = [pos["x"] for pos in positions.values()]
    ys = [pos["y"] for pos in positions.values()]
    x_min, x_max = min(xs) - 90, max(xs) + 90
    y_min, y_max = min(ys) - 90, max(ys) + 90
    width, height = 160, 90
    meta_by_gene = _cluster_meta_by_gene()

    def scale_x(value):
        return 10 + ((value - x_min) / max(1, x_max - x_min)) * (width - 20)

    def scale_y(value):
        return 10 + ((value - y_min) / max(1, y_max - y_min)) * (height - 20)

    dots = []
    for gene, pos in positions.items():
        cluster = meta_by_gene.get(gene, {}).get("primary_cluster")
        color = CLUSTER_COLORS.get(cluster, "#94A3B8")
        dots.append(html.Span(
            title=gene,
            className="pathway-minimap-dot",
            style={
                "left": f"{scale_x(pos['x']):.1f}px",
                "top": f"{scale_y(pos['y']):.1f}px",
                "background": color,
                "boxShadow": f"0 0 8px {color}",
            },
        ))

    return html.Div(
        [
            *dots,
            html.Span(className="pathway-minimap-viewport"),
        ],
        id=_PATHWAY_MINIMAP_ID,
        n_clicks=0,
        className="pathway-minimap",
        title="Overview minimap",
        **{
            "data-x-min": f"{x_min:.3f}",
            "data-x-max": f"{x_max:.3f}",
            "data-y-min": f"{y_min:.3f}",
            "data-y-max": f"{y_max:.3f}",
        },
    )


def _build_signor_autocomplete_index() -> list[dict]:
    drug_seen: dict[str, str] = {}
    for row in _SIGNOR_DRUG_EDGES:
        name = str(row.get("ENTITYA") or "").strip()
        if not name:
            continue
        cid = map_signor_drug_name(name)
        if cid:
            drug_seen.setdefault(cid, name)

    entries: list[dict] = []
    entries.extend({
        "id": gene,
        "label": gene,
        "type": "target",
        "rank": 0,
    } for gene in _NSCLC_TARGETS)
    entries.extend({
        "id": gene,
        "label": gene,
        "type": "protein",
        "rank": 2,
    } for gene in _SIGNOR_PROTEINS)
    entries.extend({
        "id": cid,
        "label": name,
        "type": "drug",
        "rank": 1,
    } for cid, name in sorted(drug_seen.items(), key=lambda item: item[1].lower()))
    return entries


_AC_INDEX: list[dict] = _build_signor_autocomplete_index()


def _build_autocomplete_data(type_filter: str | None = None) -> list[dict]:
    """Mantine Autocomplete data 형식: [{value, label}].
    value = 'type:id' (콜백에서 split으로 추출)."""
    items = sorted(_AC_INDEX, key=lambda e: (e.get("rank", 99), e.get("label", "")))
    if type_filter in {"drug", "protein", "target"}:
        items = [e for e in items if e.get("type") == type_filter]
    out = []
    for e in items:
        emoji = _TYPE_EMOJI.get(e.get("type"), "")
        label = f"{emoji} {e.get('label', '')}  [{e.get('type')}]"
        out.append({
            "value": f"{e.get('type')}:{e.get('id')}",
            "label": label,
        })
    return out


_AC_DATA = _build_autocomplete_data()


def _resolve_search_selection(value: str | None):
    """Resolve Mantine Autocomplete values and display labels to an index entry."""
    if not value:
        return None
    text = str(value).strip()
    if ":" in text:
        typ, _, eid = text.partition(":")
        if typ in {"target", "protein", "drug"} and eid:
            entry = next(
                (item for item in _AC_INDEX if item.get("type") == typ and item.get("id") == eid),
                None,
            )
            return (typ, eid, entry or {}) if entry is not None else None

    lower_text = text.lower()
    hinted_type = None
    for typ in ("target", "protein", "drug"):
        if f"[{typ}]" in lower_text:
            hinted_type = typ
            break

    cleaned = (
        text.replace("🎯", "")
        .replace("💊", "")
        .replace("□", "")
        .replace("[target]", "")
        .replace("[protein]", "")
        .replace("[drug]", "")
    )
    cleaned = " ".join(cleaned.split()).strip()
    cleaned_lower = cleaned.lower()
    if not cleaned_lower:
        return None

    for entry in _AC_INDEX:
        if hinted_type and entry.get("type") != hinted_type:
            continue
        if str(entry.get("id", "")).lower() == cleaned_lower:
            return entry.get("type"), entry.get("id"), entry
        if str(entry.get("label", "")).lower() == cleaned_lower:
            return entry.get("type"), entry.get("id"), entry
    return None


# ============================================================
# Layout
# ============================================================
def _tab_label(focus: dict) -> str:
    fid = str(focus.get("compound_id") or focus.get("id", ""))
    if _DISPLAY_ALIASES.get(fid.upper()):
        return _DISPLAY_ALIASES[fid.upper()]
    if focus.get("label"):
        return str(focus["label"])
    return _DISPLAY_ALIASES.get(fid, fid)


def _top_bar():
    return html.Div(
        [
            html.Div(
                [
                    html.Div("🧬", className="atlas-dna-mark", title="NSCLC Atlas"),
                    html.Div("Pathway Map — NSCLC Living Atlas", className="atlas-title"),
                ],
                className="atlas-topbar-left",
            ),
            html.Div(
                [
                    dmc.Select(
                        id="pathway-select",
                        data=_PATHWAY_OPTIONS,
                        value=_DEFAULT_PW,
                        size="xs",
                        className="atlas-pathway-select",
                        styles={
                            "input": {
                                "backgroundColor": "rgba(8, 17, 31, 0.72)",
                                "borderColor": "rgba(148, 163, 184, 0.22)",
                                "color": "#d7dee8",
                            }
                        },
                    ),
                ],
                className="atlas-topbar-right",
                style={"gap": "14px"},
            ),
        ],
        style={
            "height": "54px",
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "space-between",
            "gap": "16px",
            "padding": "0 22px",
            "borderBottom": "1px solid rgba(76, 103, 137, 0.22)",
            "background": "rgba(2, 8, 19, 0.42)",
        },
    )


def _search_panel():
    def control_label(text: str):
        return html.Div(
            text,
            style={
                "color": "#94A3B8",
                "fontSize": "10px",
                "fontWeight": 700,
                "letterSpacing": "0.02em",
                "marginBottom": "2px",
            },
        )

    return html.Div(
        [
            html.Div(
                [
                    dmc.Autocomplete(
                        id="entity-search",
                        placeholder="검색: erlotinib, EGFR, KRAS...",
                        data=_AC_DATA,
                        limit=4,
                        size="md",
                        clearable=True,
                        className="atlas-search-input",
                        comboboxProps=_SEARCH_DROPDOWN_PROPS,
                        styles={
                            "input": {
                                "paddingLeft": "14px",
                                "paddingRight": "14px",
                            }
                        },
                    ),
                    dmc.Tooltip(
                        html.Button(
                            html.Span("🔍", className="node-search-icon", **{"aria-hidden": "true"}),
                            id=_NODE_SEARCH_BUTTON_ID,
                            n_clicks=0,
                            type="button",
                            className="node-search-button",
                            title="검색 (Enter)",
                            **{"aria-label": "검색 (Enter)"},
                        ),
                        label="검색 (Enter)",
                        position="bottom",
                        withArrow=True,
                    ),
                ],
                className="atlas-search-bar",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            control_label("Seed"),
                            dmc.Select(
                                id=_SIGNOR_SEED_ID,
                                data=[{"label": g, "value": g} for g in _NSCLC_TARGETS],
                                value="EGFR",
                                size="xs",
                                clearable=False,
                                styles={
                                    "input": {
                                        "minHeight": "26px",
                                        "height": "26px",
                                        "backgroundColor": "rgba(8, 17, 31, 0.74)",
                                        "borderColor": "rgba(148, 163, 184, 0.22)",
                                        "color": "#E2E8F0",
                                        "fontSize": "11px",
                                    }
                                },
                            ),
                        ],
                        style={"minWidth": "82px"},
                    ),
                    html.Div(
                        [
                            html.Div(
                                [
                                    control_label("Restart"),
                                    html.Span(
                                        "사전계산: 0.3 (live re-compute은 v2 백로그)",
                                        className="atlas-restart-badge",
                                    ),
                                    html.Span(
                                        "현재: 0.30",
                                        id=_SIGNOR_RESTART_VALUE_ID,
                                        className="atlas-restart-current-value",
                                    ),
                                ],
                                className="atlas-restart-label-row",
                            ),
                            dcc.Slider(
                                id=_SIGNOR_RESTART_ID,
                                min=0.1,
                                max=0.9,
                                step=0.2,
                                value=_RWR_COMPUTED_RESTART_PROB,
                                marks=_RESTART_MARKS,
                                updatemode="drag",
                            ),
                            html.Div(id=_SIGNOR_RESTART_WARNING_ID, className="atlas-restart-warning"),
                        ],
                        style={"minWidth": 0},
                    ),
                    html.Div(
                        [
                            control_label("Degree"),
                            dcc.Slider(
                                id=_SIGNOR_DEGREE_ID,
                                min=0,
                                max=20,
                                step=None,
                                value=0,
                                marks=_DEGREE_MARKS,
                                tooltip={"placement": "bottom", "always_visible": False},
                            ),
                        ],
                        style={"minWidth": 0},
                    ),
                    html.Div(
                        [
                            control_label("Layer"),
                            dmc.Switch(
                                id=_SIGNOR_SHOW_DRUGS_ID,
                                label=f"Show drugs ({_SIGNOR_DRUG_EDGE_COUNT} edges)",
                                checked=False,
                                color="violet",
                                size="xs",
                                styles={
                                    "label": {
                                        "color": "#CBD5E1",
                                        "fontSize": "10px",
                                        "fontWeight": 700,
                                    }
                                },
                            ),
                        ],
                        style={"minWidth": "118px"},
                    ),
                ],
                style={
                    "display": "grid",
                    "gridTemplateColumns": "repeat(auto-fit, minmax(148px, 1fr))",
                    "gap": "10px",
                    "alignItems": "start",
                    "marginTop": "8px",
                    "padding": "6px 10px 2px",
                    "border": "1px solid rgba(148, 163, 184, 0.14)",
                    "borderRadius": "8px",
                    "background": "rgba(6, 16, 31, 0.42)",
                },
            ),
            html.Div(
                "선택하면 SIGNOR seed·카드 컨텍스트가 갱신됩니다.",
                className="atlas-search-hint",
            ),
        ],
        className="atlas-search-panel",
        style=_SEARCH_PANEL_STYLE,
    )


def _map_legend():
    rows = [
        ("●", "Seed (selected)", "#FF5B5B"),
        ("●", "NSCLC target", "#51CF66"),
        ("●", "RWR top 10% (heat)", "#F59F00"),
        ("◆", "Drug/entity hit", "#9775FA"),
        ("→", "up-regulates", "#22D3EE"),
        ("→", "down-regulates", "#FF5B5B"),
    ]
    return html.Div(
        [
            html.Div(
                [
                    html.Span(
                        icon,
                        style={"fontSize": "12px", "lineHeight": 1, "color": color},
                    ),
                    html.Span(label),
                ],
                className="atlas-legend-row",
                style={
                    "fontSize": "11px",
                    "gridTemplateColumns": "16px minmax(0, 1fr)",
                    "gap": "5px",
                    "lineHeight": 1.25,
                },
            )
            for icon, label, color in rows
        ],
        className="atlas-map-legend",
        style={
            "left": "auto",
            "bottom": "auto",
            "right": "14px",
            "top": "14px",
            "padding": "8px 10px",
            "minWidth": "118px",
            "background": "rgba(6, 16, 31, 0.66)",
            "borderColor": "rgba(148, 163, 184, 0.26)",
            "backdropFilter": "blur(10px)",
        },
    )


def _map_controls():
    def control_button(label: str, button_id: str, tooltip: str):
        return dmc.Tooltip(
            html.Button(
                label,
                id=button_id,
                n_clicks=0,
                type="button",
                className="atlas-map-button",
                title=tooltip,
                style=_SMALL_MAP_BUTTON_STYLE,
                **{"aria-label": tooltip},
            ),
            label=tooltip,
            position="top",
            withArrow=True,
        )

    return html.Div(
        [
            html.Div(
                [
                    control_button("+", _MAP_ZOOM_IN_ID, "확대"),
                    control_button("−", _MAP_ZOOM_OUT_ID, "축소"),
                    control_button("◎", _MAP_FIT_ID, "전체 보기 (reset)"),
                ],
                className="atlas-map-buttons",
                style={"gap": "7px"},
            ),
            html.Div(
                [
                    html.Span([html.Span("[휠]", className="interaction-guide-key"), "확대/축소"], className="interaction-guide-item"),
                    html.Span([html.Span("[드래그]", className="interaction-guide-key"), "이동"], className="interaction-guide-item"),
                    html.Span([html.Span("[클릭]", className="interaction-guide-key"), "노드 선택"], className="interaction-guide-item"),
                ],
                className="atlas-map-help interaction-guide-box",
            ),
        ],
        className="atlas-map-control-panel",
        style={"left": "14px", "bottom": "14px"},
    )


def _ego_back_button():
    return dmc.Tooltip(
        html.Button(
            "←",
            id=_VIEW_BACK_BUTTON_ID,
            n_clicks=0,
            type="button",
            className="pathway-view-back is-disabled",
            disabled=True,
            title="이전 pathway view",
            **{"aria-label": "이전 pathway view"},
        ),
        label="이전 pathway view",
        position="right",
        withArrow=True,
    )


def _map_view_toggles():
    switch_styles = {
        "label": {
            "color": "#CBD5E1",
            "fontSize": "11px",
            "fontWeight": 700,
        }
    }
    return html.Div(
        [
            dmc.Switch(
                id=_OVERVIEW_SWITCH_ID,
                label="Overview",
                checked=True,
                color="violet",
                size="xs",
                styles=switch_styles,
            ),
            dmc.Switch(
                id=_CLUSTER_HULL_SWITCH_ID,
                label="Cluster hulls",
                checked=True,
                color="violet",
                size="xs",
                styles=switch_styles,
            ),
            dmc.Switch(
                id=_MINIMAP_SWITCH_ID,
                label="Mini-map",
                checked=True,
                color="violet",
                size="xs",
                styles=switch_styles,
            ),
        ],
        className="pathway-map-view-toggles",
    )


def _map_drug_pills():
    return html.Div(className="atlas-drug-pills", style={"display": "none"})


def _chat_header():
    return html.Div(
        [
            html.Div(
                [
                    html.Span("●●"),
                    html.Span(
                        "Ask anything",
                        style={"fontSize": "17px", "fontWeight": 600},
                    ),
                ],
                className="atlas-chat-title",
                style={"fontSize": "17px", "fontWeight": 600},
            ),
            dmc.Tooltip(
                dmc.ActionIcon(
                    "⌫",
                    id="atlas-thread-clear",
                    variant="subtle",
                    color="gray",
                    size=30,
                    radius=7,
                    className="atlas-thread-clear",
                    style={"fontSize": "15px"},
                ),
                label="스레드 지우기",
                position="left",
            ),
        ],
        className="atlas-chat-header",
    )


def _build_pathway_suggested_questions(payload: dict | None) -> list[dict]:
    if not payload:
        return [
            {"color": "indigo", "question": "EGFR이(가) NSCLC에서 어떤 역할을 해?"},
            {"color": "grape", "question": "ERBB2(HER2)는 왜 champion target이야?"},
            {"color": "cyan", "question": "Osimertinib은 어떻게 작용해?"},
            {"color": "orange", "question": "이 모델의 한계는 뭐야?"},
            {"color": "pink", "question": "champion model이 뭔지 알려줘"},
            {"color": "blue", "question": "패스웨이 맵 어떻게 봐?"},
            {"color": "teal", "question": "이 결과 다음에 어떤 노드·탭을 보면 좋아?"},
        ]

    label = payload.get("display_label") or payload.get("gene_symbol") or "이 노드"
    return [
        {"color": "indigo", "question": f"{label}이(가) NSCLC에서 어떤 역할을 해?"},
        {"color": "grape", "question": f"{label} 관련 약물 후보가 뭐야?"},
        {"color": "cyan", "question": f"{label}의 mechanism hypothesis는?"},
        {"color": "orange", "question": f"{label}의 SHAP 기여도는?"},
        {"color": "teal", "question": "이 결과 다음에 어떤 노드·탭을 보면 좋아?"},
        {"color": "pink", "question": "champion model 결과랑 비교하면?"},
    ]


chatbot_panel_module._build_suggested_questions = _build_pathway_suggested_questions


def _build_signor_graph(seed: str | None, restart_prob: float, min_degree: int, show_drugs: bool):
    seeds = [seed] if seed in _NSCLC_TARGET_SET else ["EGFR"]
    requested_restart_prob = float(restart_prob or _RWR_COMPUTED_RESTART_PROB)
    res = rwr_from_seeds(
        seeds,
        restart_prob=_RWR_COMPUTED_RESTART_PROB,
        top_n=None,
    )
    influenced = dict(zip(res["gene"], res["influence"]))
    elements, cluster_counts = _build_cluster_island_elements(
        influenced=influenced,
        seeds=seeds,
        min_degree=int(min_degree or 0),
        show_drugs=bool(show_drugs),
    )
    if not elements:
        elements = build_signor_elements(
            influenced=influenced,
            seeds=seeds,
            min_degree=int(min_degree or 0),
            include_drugs=bool(show_drugs),
        )
        cluster_counts = {}
    rwr_data = {
        "seeds": seeds,
        "restart_prob": _RWR_COMPUTED_RESTART_PROB,
        "requested_restart_prob": requested_restart_prob,
        "display_node_count": sum(
            1
            for ele in elements
            if (ele.get("data") or {}).get("node_type") == "protein"
        ),
        "cluster_counts": cluster_counts,
        "view_mode": "cluster",
        "top10": [
            {
                "gene": row["gene"],
                "influence": round(float(row["influence"]), 4),
                "is_nsclc_target": bool(row["is_nsclc_target"]),
            }
            for _, row in res[~res["is_seed"]].head(10).iterrows()
        ],
        "n_iter": int(res.attrs.get("n_iter_converged", 0)),
    }
    return elements, rwr_data


def _render_top10_influenced(rwr_data: dict | None, focus: dict | None = None):
    top10 = (rwr_data or {}).get("top10") or []
    focus_id = str((focus or {}).get("id") or "")
    rows = []
    for row in top10[:10]:
        gene = str(row.get("gene") or "")
        if not gene:
            continue
        score = float(row.get("influence") or 0.0)
        is_target = bool(row.get("is_nsclc_target")) or gene in _NSCLC_TARGET_SET
        row_class = "atlas-top10-row"
        if gene == focus_id:
            row_class += " is-active"
        rows.append(
            html.Button(
                [
                    html.Span(
                        [
                            html.Span(gene, className="atlas-top10-gene"),
                        ],
                        className="atlas-top10-name",
                    ),
                    html.Span(f"{score:.4f}", className="atlas-top10-score"),
                ],
                id={"type": _TOP_INFLUENCED_BTN_TYPE, "gene": gene},
                n_clicks=0,
                type="button",
                className=row_class,
                title=f"{gene} RWR score {score:.4f}",
            )
        )

    if not rows:
        rows = [
            html.Div(
                "Seed를 선택하면 RWR 상위 노드가 표시됩니다.",
                className="atlas-top10-empty",
            )
        ]

    return html.Div(
        [
            html.Div("TOP 10 INFLUENCED (NON-SEED)", className="atlas-top10-title"),
            html.Div(rows, className="atlas-top10-list"),
        ],
        className="atlas-top10-content",
    )


def _make_layout():
    if not _PATHWAY_OPTIONS:
        return dmc.Container([
            dmc.Space(h=32),
            dmc.Alert(
                "pathway_data.json이 없습니다. scripts/29_collect_pathway_data.py 실행 필요.",
                title="데이터 미준비", color="red", variant="light",
            ),
        ], fluid=True)

    initial_focus = {"id": "EGFR", "type": "target"}
    initial_stack = [
        initial_focus,
    ]
    initial_elements, initial_rwr = _build_signor_graph("EGFR", _RWR_COMPUTED_RESTART_PROB, 0, False)

    return html.Div([
        # --- dcc.Stores ---
        dcc.Store(id="focus-store", data=initial_focus),
        dcc.Store(id="briefing-stack-store", data=initial_stack),
        dcc.Store(id="llm-thread-store", data=[]),
        dcc.Store(id="llm-fallback-store", data={"available": True, "reason": None}),
        dcc.Store(id=_SIGNOR_RWR_STORE_ID, data=initial_rwr),
        dcc.Store(id=_ENTITY_TYPE_FILTER_STORE_ID, data=None),
        dcc.Store(id=_PATHWAY_DRUG_EXPANDED_STORE_ID, data={}),
        dcc.Store(id=_VIEW_STATE_STORE_ID, data=_view_state("cluster", None, initial_focus)),
        dcc.Store(id=_VIEW_HISTORY_STORE_ID, data=[]),
        dcc.Store(id=_DETAIL_DRAWER_OPEN_STORE_ID, data=False),
        html.Div(id=_CYTO_NAV_RESULT_ID, style={"display": "none"}),
        html.Div(id=_CYTO_CONTROL_RESULT_ID, style={"display": "none"}),
        html.Div(id=_CYTO_HOVER_RESULT_ID, style={"display": "none"}),
        html.Div(id=_CLUSTER_OVERLAY_RESULT_ID, style={"display": "none"}),
        html.Div(id=_DETAIL_DRAWER_RESULT_ID, style={"display": "none"}),
        html.Div(id=_OVERVIEW_RESULT_ID, style={"display": "none"}),
        html.Div(id=_MINIMAP_RESULT_ID, style={"display": "none"}),

        _top_bar(),
        html.Div(
            [
                html.Div(
                    [
                        _search_panel(),
                        html.Div(id=_SIGNOR_TOP10_ID, className="atlas-top10-panel"),
                    ],
                    className="atlas-controls-pane left-controls",
                    style={"height": "calc(100vh - 98px)", "maxHeight": "calc(100vh - 120px)"},
                ),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(id=_CLUSTER_OVERLAY_ID, className="pathway-cluster-svg-layer"),
                                cyto.Cytoscape(
                                    id="pathway-cytoscape",
                                    elements=initial_elements,
                                    stylesheet=_build_pathway_stylesheet(True),
                                    layout={
                                        "name": "preset",
                                        "fit": True,
                                        "padding": 44,
                                        "animate": False,
                                    },
                                    style={
                                        "width": "100%",
                                        "height": "100%",
                                        "position": "absolute",
                                        "inset": 0,
                                        "zIndex": 2,
                                        "backgroundColor": "transparent",
                                    },
                                    minZoom=0.25,
                                    maxZoom=3.5,
                                    userZoomingEnabled=True,
                                    userPanningEnabled=True,
                                    boxSelectionEnabled=False,
                                ),
                                _ego_back_button(),
                                _map_legend(),
                                _map_controls(),
                                _cluster_minimap(),
                                _map_view_toggles(),
                            ],
                            className="atlas-cyto-frame",
                            style=_CYTO_FRAME_STYLE,
                        ),
                        _map_drug_pills(),
                    ],
                    className="atlas-left-pane atlas-canvas-pane center-cytoscape",
                    style={"height": "calc(100vh - 98px)"},
                ),
                html.Div(
                    [
                        html.Button(
                            "Details",
                            id=_DETAIL_DRAWER_TOGGLE_ID,
                            n_clicks=0,
                            type="button",
                            className="pathway-detail-drawer-tab",
                            title="Open target details",
                        ),
                        html.Button(
                            "×",
                            id=_DETAIL_DRAWER_CLOSE_ID,
                            n_clicks=0,
                            type="button",
                            className="pathway-detail-drawer-close",
                            title="Close details",
                        ),
                        html.Div(
                            id="briefing-tabs-container",
                            className="atlas-briefing-tabs",
                            style={
                                "height": "auto",
                                "minHeight": "40px",
                                "maxHeight": "84px",
                                "overflow": "visible",
                                "paddingRight": "8px",
                                "boxSizing": "border-box",
                                "flexShrink": 0,
                            },
                        ),
                        dcc.Loading(
                            type="dot",
                            color="#22D3EE",
                            style={
                                "flex": "0 0 auto",
                                "minHeight": 0,
                                "display": "flex",
                                "flexDirection": "column",
                            },
                            children=html.Div(
                                id="briefing-card-container",
                                className="atlas-briefing-card card-scrollable-body",
                                style={
                                    "paddingRight": "8px",
                                    "boxSizing": "border-box",
                                    "flex": "0 0 auto",
                                    "minHeight": 0,
                                    "overflowY": "visible",
                                },
                            ),
                        ),
                        html.Div(id=_PATHWAY_BOTTOM_CARDS_ID, className="pathway-right-cards"),
                    ],
                    id=_DETAIL_DRAWER_ID,
                    className="atlas-right-pane right-card-panel pathway-detail-drawer is-collapsed",
                    style=_RIGHT_PANE_STYLE,
                ),
            ],
            className="atlas-main",
            style={"height": "calc(100vh - 98px)", "columnGap": "18px"},
        ),
        chatbot_popup(chatbot_panel()),
    ], className="pathway-atlas-shell", style={"height": "calc(100vh - 44px)"})


layout = _make_layout()


# ============================================================
# Helpers (콜백 공통)
# ============================================================
def _push_to_stack(stack: list, focus: dict, max_size: int = 5) -> list:
    """stack에 focus를 push. 동일 entity 있으면 제거 후 끝에 추가. 최대 max_size."""
    cur = stack or []
    new_stack = [s for s in cur
                 if not (s.get("id") == focus.get("id")
                         and s.get("type") == focus.get("type"))]
    new_stack.append(focus)
    return new_stack[-max_size:]


def _as_items(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if v]
    text = str(value).strip()
    if not text:
        return []
    return [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]


def _fmt_items(value, limit: int = 5) -> str:
    items = _as_items(value)
    if not items:
        return "—"
    suffix = f" +{len(items) - limit} more" if len(items) > limit else ""
    return ", ".join(items[:limit]) + suffix


def _fmt_number(value, precision: int = 3, default: str = "—") -> str:
    if value is None or value == "":
        return default
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if numeric.is_integer():
        return f"{int(numeric):,}"
    return f"{numeric:.{precision}f}"


def _help_icon(text: str):
    return dmc.Tooltip(
        html.Span("?", className="atlas-label-help", **{"aria-label": text}),
        label=text,
        position="top",
        withArrow=True,
        multiline=True,
    )


def _protein_metric_row(label: str, value, tooltip: str | None = None, *, accent: bool = False):
    return html.Div(
        [
            html.Div(
                [html.Span(label), _help_icon(tooltip) if tooltip else None],
                className="atlas-protein-kv-label",
            ),
            html.Div(
                value,
                className="atlas-protein-kv-value" + (" is-accent" if accent else ""),
            ),
        ],
        className="atlas-protein-kv-row",
    )


def _direct_interactors(gene: str, *, downstream: bool = False, limit: int = 5) -> list[str]:
    if gene not in _SIGNOR_G:
        return []
    neighbors = list(_SIGNOR_G.successors(gene) if downstream else _SIGNOR_G.predecessors(gene))
    return sorted(
        neighbors,
        key=lambda node: (-(_SIGNOR_G.in_degree(node) + _SIGNOR_G.out_degree(node)), str(node)),
    )[:limit]


def _direct_neighbor_rows(gene: str, limit: int = 5) -> tuple[list[str], int]:
    if gene not in _SIGNOR_G:
        return [], 0
    neighbors = set(_SIGNOR_G.predecessors(gene)) | set(_SIGNOR_G.successors(gene))
    meta_by_gene = _cluster_meta_by_gene()
    ranked = sorted(
        [node for node in neighbors if node in _SIGNOR_G],
        key=lambda node: (
            not bool(meta_by_gene.get(node, {}).get("is_champion_target")),
            -int(_SIGNOR_G.degree(node)),
            node,
        ),
    )
    return ranked[:limit], max(0, len(ranked) - limit)


def _drug_connections_for_target(gene: str, limit: int | None = None) -> tuple[list[dict], int]:
    target = str(gene or "").upper()
    rows = []
    for row in _SIGNOR_DRUG_EDGES:
        if _row_text(row, "ENTITYB").upper() != target:
            continue
        effect = _row_text(row, "EFFECT").lower()
        if "down-regulates" not in effect:
            continue
        rows.append(row)
    rows = sorted(
        rows,
        key=lambda row: (-_safe_float(row.get("SCORE")), _row_text(row, "ENTITYA").lower()),
    )
    unique_rows: list[dict] = []
    seen_drugs: set[str] = set()
    for row in rows:
        drug_name = _row_text(row, "ENTITYA").lower()
        if not drug_name or drug_name in seen_drugs:
            continue
        seen_drugs.add(drug_name)
        unique_rows.append(row)
    rows = unique_rows
    if limit is None:
        return rows, 0
    return rows[:limit], max(0, len(rows) - limit)


def _drug_focus_payload(target: str, drug_name: str, compound_id: str | None = None) -> dict:
    matching_rows = [
        row for row in _SIGNOR_DRUG_EDGES
        if _row_text(row, "ENTITYB").upper() == str(target or "").upper()
        and _row_text(row, "ENTITYA") == drug_name
    ]
    focus = {
        "id": compound_id or drug_name,
        "type": "drug",
        "label": drug_name,
        "compound_id": compound_id or map_signor_drug_name(drug_name) or "",
        "targets": [target] if target else [],
        "_nav": True,
    }
    if matching_rows:
        mechanisms: list[str] = []
        effects: list[str] = []
        pmids: list[str] = []
        for row in matching_rows:
            _append_unique(mechanisms, _row_text(row, "MECHANISM"), limit=5)
            _append_unique(effects, _row_text(row, "EFFECT"), limit=5)
            _append_unique(pmids, _clean_ref(row.get("PMID")), limit=5)
        focus.update({
            "signor_type": _row_text(matching_rows[0], "TYPEA", "entity"),
            "mechanisms": mechanisms,
            "effects": effects,
            "pmids": pmids,
        })
    return {key: value for key, value in focus.items() if value not in (None, "", [])}


def _pathway_chains_for_gene(gene: str, cluster: str | None) -> list[list[str]]:
    gene = str(gene or "").upper()
    if gene in _GENE_CHAIN_MAP:
        return _GENE_CHAIN_MAP[gene]
    if cluster == "RTK":
        return [["RTK", "GRB2/SOS", "RAS", "RAF", "MEK", "MAPK"], ["RTK", "PI3K", "AKT", "MTOR"]]
    if cluster == "RAS_MAPK":
        return [["RAS", "RAF", "MEK", "ERK", "FOS/MYC"]]
    if cluster == "PI3K_AKT":
        return [["PI3K", "AKT", "TSC", "MTOR"], ["PI3K", "AKT", "BAD", "Survival"]]
    if cluster == "APOPTOSIS":
        return [["Stress", "TP53", "BCL2 family", "Caspases"]]
    if cluster == "CELL_CYCLE":
        return [["Cyclin", "CDK", "RB1", "E2F", "S phase"]]
    if cluster == "TF":
        return [["Signal input", gene or "TF", "Transcription output"]]
    return []


def _bottom_card(title: str, body, *, accent: str = "cyan"):
    return html.Div(
        [
            html.Div(title, className=f"pathway-bottom-card-title is-{accent}"),
            html.Div(body, className="pathway-bottom-card-body"),
        ],
        className="pathway-bottom-card",
    )


def _chip_button(label: str, button_id: dict, *, class_name: str = ""):
    return html.Button(
        label,
        id=button_id,
        n_clicks=0,
        type="button",
        className=f"pathway-chip-button {class_name}".strip(),
        title=str(label),
    )


def _render_neighbor_card(gene: str):
    neighbors, more = _direct_neighbor_rows(gene, limit=5)
    if not neighbors:
        return _bottom_card("🌐 핵심 이웃", html.Div("노드를 선택하세요", className="pathway-bottom-placeholder"))
    chips = []
    for neighbor in neighbors:
        label = neighbor
        chips.append(_chip_button(
            label,
            {"type": _PATHWAY_NEIGHBOR_BTN_TYPE, "gene": neighbor},
            class_name="is-neighbor",
        ))
    if more:
        chips.append(html.Span(f"... {more}개 더", className="pathway-chip-more"))
    return _bottom_card(
        "🌐 핵심 이웃",
        [
            html.Div(f"{gene} 주변의 고연결 핵심 단백질", className="pathway-bottom-caption"),
            html.Div(chips, className="pathway-chip-row"),
        ],
        accent="green",
    )


def _render_pathway_card(gene: str, cluster: str | None):
    chains = _pathway_chains_for_gene(gene, cluster)
    if not chains:
        return _bottom_card("🧬 주요 경로", html.Div("노드를 선택하세요", className="pathway-bottom-placeholder"))
    return _bottom_card(
        "🧬 주요 경로",
        [
            html.Div("KEGG hsa05223 중심 연결", className="pathway-bottom-caption"),
            html.Div(
                [
                    html.Div(" → ".join(chain), className="pathway-chain-row")
                    for chain in chains[:3]
                ],
                className="pathway-chain-list",
            ),
        ],
        accent="blue",
    )


def _render_drug_card(gene: str, expanded: dict | None = None):
    is_expanded = bool((expanded or {}).get(str(gene or "").upper()))
    rows, more = _drug_connections_for_target(gene, limit=None if is_expanded else 5)
    if not rows:
        return _bottom_card("💊 약물 연결", html.Div("연결된 down-regulating drug edge가 없습니다.", className="pathway-bottom-placeholder"))
    chips = []
    for row in rows:
        drug_name = _row_text(row, "ENTITYA")
        compound_id = map_signor_drug_name(drug_name) or ""
        chips.append(_chip_button(
            drug_name,
            {
                "type": _PATHWAY_DRUG_CHIP_TYPE,
                "target": gene,
                "drug": drug_name,
                "compound_id": compound_id,
            },
            class_name="is-drug",
        ))
    if more and not is_expanded:
        chips.append(html.Button(
            f"+{more} more",
            id={"type": _PATHWAY_DRUG_MORE_TYPE, "gene": gene},
            n_clicks=0,
            type="button",
            className="pathway-chip-more is-clickable",
            title="전체 약물 연결 보기",
        ))
    return _bottom_card(
        "💊 약물 연결",
        [
            html.Div(f"{gene}을 직접/간접 타깃하는 SIGNOR drug edge", className="pathway-bottom-caption"),
            html.Div(chips, className="pathway-chip-row"),
        ],
        accent="violet",
    )


def _render_drilldown_card(cluster: str | None):
    steps = _CLUSTER_DRILLDOWN_STEPS.get(cluster or "")
    if not steps:
        return _bottom_card("📊 경로 드릴다운", html.Div("노드를 선택하세요", className="pathway-bottom-placeholder"))
    return _bottom_card(
        "📊 경로 드릴다운",
        [
            html.Div(_CLUSTER_LABELS.get(cluster or "", cluster or ""), className="pathway-bottom-caption"),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(str(idx + 1), className="pathway-step-index"),
                            html.Span(step, className="pathway-step-label"),
                        ],
                        className="pathway-step",
                    )
                    for idx, step in enumerate(steps)
                ],
                className="pathway-stepper",
            ),
        ],
        accent="amber",
    )


def _render_bottom_cards(focus: dict | None, expanded: dict | None = None):
    def placeholder_cards():
        return [
            _bottom_card("🌐 핵심 이웃", html.Div("노드를 선택하세요", className="pathway-bottom-placeholder")),
            _bottom_card("🧬 주요 경로", html.Div("노드를 선택하세요", className="pathway-bottom-placeholder")),
            _bottom_card("💊 약물 연결", html.Div("노드를 선택하세요", className="pathway-bottom-placeholder")),
            _bottom_card("📊 경로 드릴다운", html.Div("노드를 선택하세요", className="pathway-bottom-placeholder")),
        ]

    if not focus:
        return placeholder_cards()
    typ = focus.get("type")
    gene = str(focus.get("id") or "").upper()
    if typ == "drug":
        targets = focus.get("targets") or []
        gene = str(targets[0]).upper() if targets else ""
    if not gene or gene not in _SIGNOR_G:
        return placeholder_cards()
    cluster = _cluster_for_gene(gene)
    return [
        _render_neighbor_card(gene),
        _render_pathway_card(gene, cluster),
        _render_drug_card(gene, expanded),
        _render_drilldown_card(cluster),
    ]


def _safe_panel_id(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", str(name or "entity")).strip("-") or "entity"


def _format_latency(ms: float | int | None) -> str:
    try:
        value = float(ms or 0)
    except (TypeError, ValueError):
        value = 0.0
    if value >= 1000:
        return f"{value / 1000:.1f}s"
    return f"{value:.0f}ms"


def _pmid_links(pmids: list[str] | tuple[str, ...], *, link_class: str):
    clean: list[str] = []
    for pmid in pmids or []:
        text = str(pmid).strip()
        if text.isdigit() and text not in clean:
            clean.append(text)
    if not clean:
        return [html.Span("—", className="mechanism-pmid-empty")]
    parts = []
    for idx, pmid in enumerate(clean[:5]):
        if idx:
            parts.append(html.Span(" · ", className="mechanism-pmid-separator"))
        parts.append(
            html.A(
                pmid,
                href=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                target="_blank",
                rel="noopener noreferrer",
                className=link_class,
            )
        )
    return parts


def _render_mechanism_panel(name: str, name_type: str, role: str = ""):
    try:
        resp = query_entity(name, name_type, k=3, role=role)
    except Exception as exc:
        logger.warning("LLM mechanism panel failed for %s:%s: %s", name_type, name, exc)
        resp = LLMResponse(
            text="Insufficient evidence: 근거 문헌을 안정적으로 불러오지 못했습니다.",
            pmids=[],
            grounded=False,
            cached=False,
            mode="error",
            latency_ms=0,
            error=f"ui_exception:{type(exc).__name__}",
        )

    status = [
        html.Span("cached" if resp.cached else "fresh", className="mechanism-status-chip"),
        html.Span(resp.mode or "unknown", className="mechanism-status-chip"),
        html.Span(_format_latency(resp.latency_ms), className="mechanism-status-chip"),
    ]
    if not resp.grounded:
        status.append(html.Span("insufficient", className="mechanism-status-chip is-muted"))

    return html.Div(
        [
            html.Div(status, className="mechanism-status-row"),
            html.Div(resp.text, className="mechanism-body"),
            html.Div(
                [html.Span("참고: ", className="mechanism-pmid-label"), *_pmid_links(resp.pmids, link_class="mechanism-pmid-link")],
                className="mechanism-pmids",
            ),
        ],
        id=f"mechanism-panel-{_safe_panel_id(name)}",
        className="mechanism-panel",
    )


def _drug_mechanism_name(focus: dict, compound_id: str | None = None) -> str:
    label = focus.get("label") if isinstance(focus, dict) else None
    node_id = focus.get("id") if isinstance(focus, dict) else None
    return label or _DISPLAY_ALIASES.get(str(compound_id or node_id or "").upper()) or str(compound_id or node_id or "drug")


def _pathway_target_card(gene_symbol: str):
    b = get_briefing_for_target(gene_symbol) or {}
    if not b or not b.get("available", True):
        return _signor_protein_card(gene_symbol)

    ess = b.get("essentiality") or {}
    mean_score = ess.get("mean_score")
    is_ess = ess.get("is_essential")
    ess_status = "필수" if is_ess is True else "비필수" if is_ess is False else "판정 보류"
    related_shap = b.get("related_shap") or []

    def shap_label(row: dict) -> str:
        rank = row.get("rank")
        category = str(row.get("category") or "").lower()
        kr_label = str(row.get("kr_label") or row.get("feature") or "핵심 feature")
        if category == "crispr":
            text = "최고 CRISPR 의존 셀라인"
        elif category == "tcga":
            text = "최고 TCGA 발현 표적"
        else:
            text = kr_label
        return f"SHAP #{rank}: {text}" if rank else f"SHAP: {text}"

    def shap_tooltip(row: dict) -> str:
        category = str(row.get("category") or "").lower()
        val = _fmt_number(row.get("mean_abs_shap"), precision=4)
        if category == "crispr":
            return f"champion 모델 예측에 사용된 핵심 feature, mean abs(SHAP) {val}"
        if category == "tcga":
            return "TCGA NSCLC bulk RNA-seq 발현 상위 셀라인 feature"
        definition = row.get("definition")
        return f"{definition} · mean abs(SHAP) {val}" if definition else f"mean abs(SHAP) {val}"

    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("표적", className="atlas-protein-eyebrow"),
                            html.H2(b.get("gene_symbol") or gene_symbol, className="atlas-protein-title"),
                        ],
                    ),
                    html.Div("Champion target", className="atlas-protein-badge"),
                ],
                className="atlas-protein-header",
            ),
            html.Div(
                [
                    _protein_metric_row(
                        "관련 약물 후보 수",
                        _fmt_number(b.get("n_drugs"), precision=0),
                        "champion 모델이 이 표적에 대해 평가한 약물 후보 개수 (rank_score 기준)",
                        accent=True,
                    ),
                    _protein_metric_row(
                        "CRISPR essentiality",
                        f"DepMap mean: {_fmt_number(mean_score)} · {ess_status}",
                        "DepMap 26Q1 NSCLC 셀라인 평균 CRISPR effect score. 음수일수록 의존성 큼",
                    ),
                    _protein_metric_row(
                        "DepMap NSCLC 셀라인",
                        f"n={_fmt_number(ess.get('n_cell_lines'), precision=0)}",
                        "이 표적에 대해 essentiality 데이터가 있는 NSCLC 셀라인 수",
                    ),
                ],
                className="atlas-protein-kv",
            ),
            html.Div(
                [
                    html.Div("관련 SHAP feature (top 5)", className="atlas-protein-section-title"),
                    html.Div(
                        [
                            _protein_metric_row(
                                shap_label(row),
                                _fmt_number(row.get("mean_abs_shap"), precision=4),
                                shap_tooltip(row),
                                accent=True,
                            )
                            for row in related_shap[:5]
                        ]
                        or [html.Div("표시할 SHAP feature가 없습니다.", className="atlas-protein-empty")],
                        className="atlas-protein-shap-list",
                    ),
                ],
                className="atlas-protein-section",
            ),
            _render_mechanism_panel(
                b.get("gene_symbol") or gene_symbol,
                "gene",
                role="champion NSCLC target",
            ),
        ],
        className="atlas-protein-card atlas-target-card",
    )


def _signor_protein_card(gene: str):
    in_deg = _SIGNOR_G.in_degree(gene) if gene in _SIGNOR_G else 0
    out_deg = _SIGNOR_G.out_degree(gene) if gene in _SIGNOR_G else 0
    is_target = bool(_SIGNOR_G.nodes[gene].get("is_nsclc_target", 0)) if gene in _SIGNOR_G else False
    upstream = _direct_interactors(gene)
    downstream = _direct_interactors(gene, downstream=True)
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("네트워크 단백질", className="atlas-protein-eyebrow"),
                            html.H2(gene, className="atlas-protein-title"),
                        ],
                    ),
                    html.Div("NSCLC 표적" if is_target else "연결 단백질", className="atlas-protein-badge"),
                ],
                className="atlas-protein-header",
            ),
            html.Div(
                (
                    "이 단백질은 NSCLC 신호 전달 네트워크에 등장하지만, 우리 모델의 학습 표적은 아닙니다. "
                    "그래서 약물 후보 예측 결과는 제공되지 않고, 네트워크 위치(상호작용)만 표시됩니다."
                ),
                className="signor-only-notice",
            ),
            html.Div(
                [
                    _protein_metric_row("In-degree", _fmt_number(in_deg, precision=0)),
                    _protein_metric_row("Out-degree", _fmt_number(out_deg, precision=0)),
                    _protein_metric_row("NSCLC target", "✓" if is_target else "—"),
                ],
                className="atlas-protein-kv",
            ),
            html.Div(
                [
                    html.Div("직접 연결된 단백질", className="atlas-protein-section-title"),
                    _protein_metric_row("들어오는 연결 Top 5", _fmt_items(upstream)),
                    _protein_metric_row("나가는 연결 Top 5", _fmt_items(downstream)),
                ],
                className="atlas-protein-section",
            ),
            html.Div(
                id=f"mechanism-panel-{_safe_panel_id(gene)}",
                className="mechanism-panel-placeholder",
                style={"display": "none"},
            ),
        ],
        className="atlas-protein-card atlas-signor-only-card",
    )


def _signor_drug_fallback_card(focus: dict):
    label = focus.get("label") or focus.get("id") or "SIGNOR drug"
    compound_id = focus.get("compound_id") or map_signor_drug_name(label)
    return html.Div(
        [
            html.Div(
                label,
                style={
                    "fontSize": "18px",
                    "fontWeight": 700,
                    "color": "#E8ECF1",
                    "marginBottom": "8px",
                },
            ),
            html.Div(
                "SIGNOR drug-target info",
                style={"fontSize": "11px", "color": "#8899AA", "marginBottom": "10px"},
            ),
            html.Div(
                [
                    html.Div(f"ChEMBL: {compound_id or '—'}"),
                    html.Div(f"Type: {focus.get('signor_type') or '—'}"),
                    html.Div(f"Targets: {_fmt_items(focus.get('targets'))}"),
                    html.Div(f"Mechanism: {_fmt_items(focus.get('mechanisms'), limit=3)}"),
                    html.Div(f"PMIDs/Refs: {_fmt_items(focus.get('pmids'), limit=3)}"),
                    html.Div("Champion OOF prob/rank: —"),
                ],
                style={"fontSize": "12px", "color": "#CBD5E1", "lineHeight": "1.7"},
            ),
        ],
        style=card_style(padding="12px", radius="8px"),
    )


# ============================================================
# 콜백
# ============================================================

# C-0: SIGNOR controls → cytoscape elements
@callback(
    Output("pathway-cytoscape", "elements"),
    Output(_SIGNOR_RWR_STORE_ID, "data"),
    Input(_SIGNOR_SEED_ID, "value"),
    Input(_SIGNOR_RESTART_ID, "value"),
    Input(_SIGNOR_DEGREE_ID, "value"),
    Input(_SIGNOR_SHOW_DRUGS_ID, "checked"),
    Input(_VIEW_STATE_STORE_ID, "data"),
)
def update_signor_graph(seed, restart_prob, min_degree, show_drugs, view_state):
    if (view_state or {}).get("mode") == "ego" and (view_state or {}).get("focus_node"):
        return _build_ego_graph(
            (view_state or {}).get("focus_node"),
            restart_prob or _RWR_COMPUTED_RESTART_PROB,
            True,
        )
    return _build_signor_graph(
        seed,
        restart_prob or _RWR_COMPUTED_RESTART_PROB,
        min_degree or 0,
        show_drugs,
    )


# C-0a: restart slider disclosure
@callback(
    Output(_SIGNOR_RESTART_WARNING_ID, "children"),
    Input(_SIGNOR_RESTART_ID, "value"),
)
def render_restart_warning(restart_prob):
    try:
        value = float(restart_prob)
    except (TypeError, ValueError):
        value = _RWR_COMPUTED_RESTART_PROB
    if abs(value - _RWR_COMPUTED_RESTART_PROB) < 1e-9:
        return ""
    return html.Span(
        (
            "현재 RWR은 restart=0.3 사전계산 결과입니다. "
            f"슬라이더 값 {value:.1f}은 시각적 표시일 뿐 RWR은 재계산되지 않습니다. "
            "(live re-compute은 v2 백로그)"
        ),
        className="atlas-restart-warning-active",
    )


@callback(
    Output(_SIGNOR_RESTART_VALUE_ID, "children"),
    Input(_SIGNOR_RESTART_ID, "value"),
)
def render_restart_value_label(restart_prob):
    try:
        value = float(restart_prob)
    except (TypeError, ValueError):
        value = _RWR_COMPUTED_RESTART_PROB
    return f"현재: {value:.2f}"


# C-0b: RWR store → top-10 influenced list
@callback(
    Output(_SIGNOR_TOP10_ID, "children"),
    Input(_SIGNOR_RWR_STORE_ID, "data"),
    Input("focus-store", "data"),
)
def render_top10_influenced(rwr_data, focus):
    return _render_top10_influenced(rwr_data, focus)


# C-0c: Cluster hull 토글 → Cytoscape stylesheet
@callback(
    Output("pathway-cytoscape", "stylesheet"),
    Input(_CLUSTER_HULL_SWITCH_ID, "checked"),
    Input(_VIEW_STATE_STORE_ID, "data"),
)
def render_pathway_stylesheet(show_hulls, view_state):
    if (view_state or {}).get("mode") == "ego":
        return _build_pathway_stylesheet(False)
    return _build_pathway_stylesheet(bool(show_hulls))


@callback(
    Output(_PATHWAY_MINIMAP_ID, "style"),
    Input(_MINIMAP_SWITCH_ID, "checked"),
)
def render_minimap_visibility(show_minimap):
    return {} if show_minimap else {"display": "none"}


# C-0d: focus 변경 → 우측 drill-down 4 카드
@callback(
    Output(_PATHWAY_BOTTOM_CARDS_ID, "children"),
    Input("focus-store", "data"),
    Input(_PATHWAY_DRUG_EXPANDED_STORE_ID, "data"),
)
def render_bottom_cards(focus, expanded):
    return _render_bottom_cards(focus, expanded)


@callback(
    Output(_PATHWAY_DRUG_EXPANDED_STORE_ID, "data"),
    Input({"type": _PATHWAY_DRUG_MORE_TYPE, "gene": ALL}, "n_clicks"),
    State(_PATHWAY_DRUG_EXPANDED_STORE_ID, "data"),
    prevent_initial_call=True,
)
def expand_drug_card(n_clicks_list, expanded):
    if not n_clicks_list or not any((click or 0) for click in n_clicks_list):
        return no_update
    trig = ctx.triggered_id
    if not isinstance(trig, dict):
        return no_update
    gene = str(trig.get("gene") or "").upper()
    if not gene:
        return no_update
    data = dict(expanded or {})
    data[gene] = True
    return data


# C-0e: autocomplete type chip → filter store
@callback(
    Output(_ENTITY_TYPE_FILTER_STORE_ID, "data"),
    Input({"type": _ENTITY_TYPE_CHIP, "value": ALL}, "n_clicks"),
    State(_ENTITY_TYPE_FILTER_STORE_ID, "data"),
    prevent_initial_call=True,
)
def update_entity_type_filter(n_clicks_list, active_filter):
    if not n_clicks_list or not any((n or 0) for n in n_clicks_list):
        return no_update
    trig = ctx.triggered_id
    if not isinstance(trig, dict):
        return no_update
    selected = trig.get("value")
    return None if selected == active_filter else selected


# C-0f: filter store → autocomplete data
@callback(
    Output("entity-search", "data"),
    Input(_ENTITY_TYPE_FILTER_STORE_ID, "data"),
)
def update_autocomplete_data(type_filter):
    return _build_autocomplete_data(type_filter)


# C-1: autocomplete 선택 → stack push + focus 갱신
@callback(
    Output("briefing-stack-store", "data", allow_duplicate=True),
    Output("focus-store", "data", allow_duplicate=True),
    Output("entity-search", "value"),
    Output(_SIGNOR_SEED_ID, "value", allow_duplicate=True),
    Output(_SIGNOR_SHOW_DRUGS_ID, "checked", allow_duplicate=True),
    Output(_VIEW_STATE_STORE_ID, "data", allow_duplicate=True),
    Output(_VIEW_HISTORY_STORE_ID, "data", allow_duplicate=True),
    Input("entity-search", "n_submit"),
    Input(_NODE_SEARCH_BUTTON_ID, "n_clicks"),
    State("entity-search", "value"),
    State("briefing-stack-store", "data"),
    prevent_initial_call=True,
)
def on_search_select(n_submit, button_clicks, value, stack):
    """Navigate only after an explicit Enter key or search-button submit."""
    if not n_submit and not button_clicks:
        return no_update, no_update, no_update, no_update, no_update, no_update, no_update
    resolved = _resolve_search_selection(value)
    if not resolved:
        return no_update, no_update, no_update, no_update, no_update, no_update, no_update
    typ, eid, entry = resolved
    if typ not in {"target", "protein", "drug"} or not eid:
        return no_update, no_update, no_update, no_update, no_update, no_update, no_update
    new_focus = {"id": eid, "type": typ, "_nav": True}
    if entry.get("label"):
        new_focus["label"] = _DISPLAY_ALIASES.get(str(eid).upper(), entry["label"])
    if typ == "drug":
        new_focus["compound_id"] = eid
    new_stack = _push_to_stack(stack, new_focus)
    seed_value = eid if typ == "target" else no_update
    show_drugs = True if typ == "drug" else no_update
    return new_stack, new_focus, "", seed_value, show_drugs, _view_state("cluster", None, new_focus), []   # 검색창 비우기


# C-2: cytoscape 노드 클릭 → stack push + focus 갱신
@callback(
    Output("briefing-stack-store", "data", allow_duplicate=True),
    Output("focus-store", "data", allow_duplicate=True),
    Output(_VIEW_STATE_STORE_ID, "data", allow_duplicate=True),
    Output(_VIEW_HISTORY_STORE_ID, "data", allow_duplicate=True),
    Input("pathway-cytoscape", "tapNodeData"),
    Input({"type": _TOP_INFLUENCED_BTN_TYPE, "gene": ALL}, "n_clicks"),
    State("briefing-stack-store", "data"),
    State(_VIEW_STATE_STORE_ID, "data"),
    State(_VIEW_HISTORY_STORE_ID, "data"),
    prevent_initial_call=True,
)
def on_node_click(node_data, top10_clicks, stack, current_view, view_history):
    trig = ctx.triggered_id
    if isinstance(trig, dict) and trig.get("type") == _TOP_INFLUENCED_BTN_TYPE:
        if not top10_clicks or not any((click or 0) for click in top10_clicks):
            return no_update, no_update, no_update, no_update
        gene = trig.get("gene")
        if not gene:
            return no_update, no_update, no_update, no_update
        typ = "target" if gene in _NSCLC_TARGET_SET else "protein"
        new_focus = {"id": gene, "type": typ, "_nav": True}
        new_stack = _push_to_stack(stack, new_focus)
        return new_stack, new_focus, no_update, no_update

    if not node_data:
        return no_update, no_update, no_update, no_update
    node_type = node_data.get("node_type", "gene")
    eid, typ = None, None
    focus_extra = {}
    if node_type == "protein":
        eid = _gene_from_node_data(node_data)
        typ = "target" if node_data.get("is_target") else "protein"
    elif node_type == "drug":
        eid = node_data.get("compound_id") or node_data.get("id")
        typ = "drug" if eid else None
        drug_label = (
            _DISPLAY_ALIASES.get(str(node_data.get("compound_id") or "").upper())
            or node_data.get("drug_name")
            or node_data.get("label")
        )
        focus_extra = {
            "label": drug_label,
            "compound_id": node_data.get("compound_id"),
            "signor_type": node_data.get("signor_type"),
            "targets": node_data.get("targets") or [],
            "mechanisms": node_data.get("mechanisms") or [],
            "pmids": node_data.get("pmids") or [],
        }
    elif node_type == "gene":
        gene_syms = node_data.get("gene_symbols") or []
        if gene_syms:
            eid, typ = gene_syms[0], "target"
    if not eid or not typ:
        logger.debug(f"on_node_click: skip {node_data}")
        return no_update, no_update, no_update, no_update
    new_focus = {"id": eid, "type": typ, **{k: v for k, v in focus_extra.items() if v}}
    if node_type == "protein":
        new_focus["_nav"] = True
    new_stack = _push_to_stack(stack, new_focus)
    if node_type == "protein":
        next_view = _view_state("ego", eid, new_focus)
        next_history = _push_view_history(view_history, current_view or _view_state())
        return new_stack, new_focus, next_view, next_history
    return new_stack, new_focus, no_update, no_update


# C-2a: 하단 카드 chip 클릭 → stack push + focus 갱신
@callback(
    Output("briefing-stack-store", "data", allow_duplicate=True),
    Output("focus-store", "data", allow_duplicate=True),
    Output(_VIEW_STATE_STORE_ID, "data", allow_duplicate=True),
    Output(_VIEW_HISTORY_STORE_ID, "data", allow_duplicate=True),
    Input({"type": _PATHWAY_NEIGHBOR_BTN_TYPE, "gene": ALL}, "n_clicks"),
    Input({"type": _PATHWAY_DRUG_CHIP_TYPE, "target": ALL, "drug": ALL, "compound_id": ALL}, "n_clicks"),
    State("briefing-stack-store", "data"),
    State(_VIEW_STATE_STORE_ID, "data"),
    State(_VIEW_HISTORY_STORE_ID, "data"),
    prevent_initial_call=True,
)
def on_bottom_card_chip_click(neighbor_clicks, drug_clicks, stack, current_view, view_history):
    trig = ctx.triggered_id
    if not isinstance(trig, dict):
        return no_update, no_update, no_update, no_update
    if trig.get("type") == _PATHWAY_NEIGHBOR_BTN_TYPE:
        if not neighbor_clicks or not any((click or 0) for click in neighbor_clicks):
            return no_update, no_update, no_update, no_update
        gene = str(trig.get("gene") or "").upper()
        if not gene:
            return no_update, no_update, no_update, no_update
        typ = "target" if gene in _NSCLC_TARGET_SET else "protein"
        new_focus = {"id": gene, "type": typ, "_nav": True}
        next_view = _view_state("ego", gene, new_focus)
        next_history = _push_view_history(view_history, current_view or _view_state())
        return _push_to_stack(stack, new_focus), new_focus, next_view, next_history
    if trig.get("type") == _PATHWAY_DRUG_CHIP_TYPE:
        if not drug_clicks or not any((click or 0) for click in drug_clicks):
            return no_update, no_update, no_update, no_update
        drug_name = str(trig.get("drug") or "")
        target = str(trig.get("target") or "")
        compound_id = str(trig.get("compound_id") or "")
        if not drug_name:
            return no_update, no_update, no_update, no_update
        new_focus = _drug_focus_payload(target, drug_name, compound_id)
        return _push_to_stack(stack, new_focus), new_focus, no_update, no_update
    return no_update, no_update, no_update, no_update


@callback(
    Output(_VIEW_STATE_STORE_ID, "data", allow_duplicate=True),
    Output(_VIEW_HISTORY_STORE_ID, "data", allow_duplicate=True),
    Output("focus-store", "data", allow_duplicate=True),
    Input(_VIEW_BACK_BUTTON_ID, "n_clicks"),
    State(_VIEW_HISTORY_STORE_ID, "data"),
    prevent_initial_call=True,
)
def on_view_back(back_clicks, view_history):
    if not back_clicks or not view_history:
        return no_update, no_update, no_update
    history = list(view_history or [])
    previous = history[-1] if history else _view_state()
    new_history = history[:-1]
    return previous, new_history, _state_focus_or_default(previous)


@callback(
    Output(_VIEW_BACK_BUTTON_ID, "disabled"),
    Output(_VIEW_BACK_BUTTON_ID, "className"),
    Output(_VIEW_BACK_BUTTON_ID, "title"),
    Input(_VIEW_HISTORY_STORE_ID, "data"),
    Input(_VIEW_STATE_STORE_ID, "data"),
)
def render_view_back_button(view_history, view_state):
    enabled = bool(view_history)
    mode = (view_state or {}).get("mode") or "cluster"
    label = "이전 ego view" if mode == "ego" else "이전 pathway view"
    return (
        not enabled,
        "pathway-view-back" + ("" if enabled else " is-disabled"),
        label if enabled else "이전 view 없음",
    )


# C-3: stack 변경 → 누적 탭 렌더
@callback(
    Output("briefing-tabs-container", "children"),
    Input("briefing-stack-store", "data"),
    State("focus-store", "data"),
)
def render_tabs(stack, focus):
    if not stack:
        return dmc.Text("노드를 클릭하거나 검색하세요.", size="xs", c="dimmed")

    # 활성 탭 = focus와 일치하는 인덱스, 없으면 마지막
    active = str(len(stack) - 1)
    if focus:
        for i, s in enumerate(stack):
            if (s.get("id") == focus.get("id")
                    and s.get("type") == focus.get("type")):
                active = str(i)
                break

    tab_children = []
    for i, s in enumerate(stack):
        is_active = str(i) == active
        tab_children.append(
            dmc.TabsTab(
                dmc.Group([
                    dmc.Text(
                        f"[{_tab_label(s)}]",
                        size="xs",
                        style={
                            "maxWidth": "96px",
                            "overflow": "hidden",
                            "textOverflow": "ellipsis",
                            "whiteSpace": "nowrap",
                            "color": "#F8FAFC" if is_active else "#94A3B8",
                        },
                    ),
                    html.Span(
                        "×",
                        id={"type": "tab-close", "index": i},
                        style={
                            "cursor": "pointer",
                            "color": "#CBD5E1" if is_active else "#64748B",
                            "fontSize": "14px",
                            "marginLeft": "4px",
                            "padding": "0 4px",
                            "width": "20px",
                            "height": "24px",
                            "display": "inline-flex",
                            "alignItems": "center",
                            "justifyContent": "center",
                            "lineHeight": 1,
                            "flex": "0 0 auto",
                        },
                        n_clicks=0,
                    ),
                ], gap=2, wrap="nowrap"),
                value=str(i),
                style={
                    "borderBottom": "2px solid #A78BFA" if is_active else "2px solid transparent",
                    "background": "rgba(88, 28, 135, 0.18)" if is_active else "transparent",
                    "transition": "background 120ms ease, border-color 120ms ease",
                },
            )
        )

    return dmc.Tabs(
        [
            dmc.TabsList(
                tab_children,
                className="atlas-tabs-list",
                style={"flexWrap": "wrap", "rowGap": "0px"},
            ),
        ],
        id="briefing-tabs",
        value=active,
        variant="outline",
        color="violet",
        className="atlas-tabs",
        style={"height": "auto"},
    )


# C-4: 탭 전환 → focus 갱신
@callback(
    Output("focus-store", "data", allow_duplicate=True),
    Input("briefing-tabs", "value"),
    State("briefing-stack-store", "data"),
    prevent_initial_call=True,
)
def on_tab_change(tab_value, stack):
    if tab_value is None or not stack:
        return no_update
    try:
        idx = int(tab_value)
    except (ValueError, TypeError):
        return no_update
    if 0 <= idx < len(stack):
        return stack[idx]
    return no_update


# C-5: 탭 닫기 (× 클릭) → stack에서 제거
@callback(
    Output("briefing-stack-store", "data", allow_duplicate=True),
    Output("focus-store", "data", allow_duplicate=True),
    Input({"type": "tab-close", "index": ALL}, "n_clicks"),
    State("briefing-stack-store", "data"),
    State("focus-store", "data"),
    prevent_initial_call=True,
)
def on_tab_close(n_clicks_list, stack, focus):
    if not n_clicks_list or not any((n or 0) for n in n_clicks_list):
        return no_update, no_update
    trig = ctx.triggered_id
    if not trig or "index" not in trig:
        return no_update, no_update
    idx = trig["index"]
    if not stack or idx >= len(stack):
        return no_update, no_update
    closed = stack[idx]
    new_stack = [s for i, s in enumerate(stack) if i != idx]
    new_focus = focus
    if (focus and focus.get("id") == closed.get("id")
            and focus.get("type") == closed.get("type")):
        new_focus = new_stack[-1] if new_stack else None
    return new_stack, new_focus


# C-6: focus 변경 → 카드 렌더
@callback(
    Output("briefing-card-container", "children"),
    Input("focus-store", "data"),
)
def update_card(focus):
    if not focus:
        return render_card(focus)
    typ = focus.get("type")
    if typ == "protein":
        return _signor_protein_card(focus.get("id"))
    if typ == "target":
        gene = focus.get("id")
        briefing = get_briefing_for_target(gene) if gene else None
        if briefing and briefing.get("available"):
            return _pathway_target_card(gene)
        return _signor_protein_card(gene)
    if typ == "drug":
        compound_id = focus.get("compound_id") or focus.get("id")
        try:
            briefing = get_briefing_for_drug(compound_id) if compound_id else None
            if briefing and briefing.get("available"):
                return html.Div(
                    [
                        render_card({"type": "drug", "id": compound_id}),
                        _render_mechanism_panel(
                            _drug_mechanism_name(focus, compound_id),
                            "drug",
                            role="SIGNOR drug-target interaction",
                        ),
                    ],
                    className="atlas-drug-card-stack",
                )
        except Exception as exc:
            logger.warning("drug card fallback for %s: %s", compound_id, exc)
        return html.Div(
            [
                _signor_drug_fallback_card(focus),
                _render_mechanism_panel(
                    _drug_mechanism_name(focus, compound_id),
                    "drug",
                    role="SIGNOR drug-target interaction",
                ),
            ],
            className="atlas-drug-card-stack",
        )
    return render_card(focus)


# C-7: focus 변경 → chatbot context-store
@callback(
    Output(CONTEXT_STORE_ID, "data"),
    Input("focus-store", "data"),
)
def update_chatbot_context(focus):
    """focus 변경 → chatbot grounding context 갱신."""
    if not focus:
        return None
    typ = focus.get("type")
    if typ == "target":
        gene = focus.get("id")
        if not gene:
            return None
        internal = get_top_compounds_for_target(gene, top_n=5)
        payload = build_context_payload(
            genes=[gene],
            internal_compounds=internal,
            external_chembl_compounds=[],
            ot_drugs=[],
            chembl_coverage=0.0,
        )
        payload.update({
            "node_type": "target",
            "display_label": gene,
            "pathway_id": "SIGNOR-v2",
            "pathway_name": "NSCLC SIGNOR",
        })
        return payload
    if typ == "protein":
        gene = focus.get("id")
        return {
            "node_type": "protein",
            "display_label": gene,
            "gene_symbol": gene,
            "gene_name": gene,
            "pathway_id": "SIGNOR-v2",
            "pathway_name": "NSCLC SIGNOR",
            "internal_compounds": [],
            "external_chembl": [],
            "clinical_drugs": [],
            "chembl_coverage_pct": None,
        }
    if typ == "drug":
        label = focus.get("label") or focus.get("id")
        cid = focus.get("compound_id") or focus.get("id")
        try:
            briefing = get_briefing_for_drug(cid) if cid else {}
        except Exception:
            briefing = {}
        model_score = (
            briefing.get("prob")
            or briefing.get("rank_score")
            if briefing and briefing.get("available")
            else None
        )
        return {
            "node_type": "drug",
            "display_label": label,
            "gene_symbol": label,
            "gene_name": label,
            "pathway_id": "SIGNOR-v2",
            "pathway_name": "NSCLC SIGNOR drug layer",
            "internal_compounds": (
                [{"compound_id": cid, "rank_score": model_score, "modality": "SIGNOR"}]
                if cid else []
            ),
            "external_chembl": [],
            "clinical_drugs": [
                {"name": label, "max_phase": None, "nsclc": False}
            ],
            "chembl_coverage_pct": None,
        }
    return None


# C-8: focus/search/top-10 → cytoscape viewport navigation
dash.clientside_callback(
    """
    function(focus, elements, showDrugs) {
      if (!focus || !focus.id || !focus._nav) {
        return "";
      }

	      const normalize = function(value) {
	        return String(value || "").trim().toLowerCase();
	      };
		      const clusterColors = {
		        RTK: "#22D3EE",
		        RAS_MAPK: "#F59E0B",
		        PI3K_AKT: "#22C55E",
		        APOPTOSIS: "#14B8A6",
		        CELL_CYCLE: "#A855F7",
		        TF: "#8B5CF6"
		      };
      const focusId = normalize(focus.compound_id || focus.id);
      const focusLabel = normalize(focus.label || focus.id);

      const findNode = function(cy) {
        let node = cy.getElementById(String(focus.compound_id || focus.id));
        if (node && node.length > 0) {
          return node;
        }
        node = cy.nodes().filter(function(ele) {
          const data = ele.data() || {};
          return normalize(data.id) === focusId
            || normalize(data.gene) === focusId
            || normalize(data.compound_id) === focusId
            || normalize(data.label) === focusId
            || normalize(data.drug_name) === focusLabel
            || normalize(data.label) === focusLabel;
        });
        return node && node.length > 0 ? node.first() : null;
      };

      const focusNode = function(attempt) {
        const cy = window.cy;
        if (!cy || typeof cy.nodes !== "function") {
          if (attempt < 20) {
            window.setTimeout(function() { focusNode(attempt + 1); }, 120);
          }
          return;
        }
        const node = findNode(cy);
        if (!node || node.length === 0) {
          if (attempt < 24) {
            window.setTimeout(function() { focusNode(attempt + 1); }, 140);
          }
          return;
        }

        if (window.__pathwayFocusedNodeId) {
          const prev = cy.getElementById(window.__pathwayFocusedNodeId);
          if (prev && prev.length > 0) {
            prev.removeStyle();
          }
        }
	        cy.nodes().unselect();
	        cy.edges().removeStyle();
	        node.select();
	        const clusterColor = clusterColors[node.data("cluster")] || "#A78BFA";
	        node.style({
	          "border-width": 5,
	          "border-color": clusterColor,
	          "border-opacity": 1,
	          "overlay-color": clusterColor,
	          "overlay-opacity": 0.34,
	          "overlay-padding": 11,
	          "z-index": 99
	        });
	        node.connectedEdges().style({
	          "width": 2.5,
	          "opacity": 0.85,
	          "line-color": clusterColor,
	          "target-arrow-color": clusterColor,
	          "z-index": 20
	        });
	        window.__pathwayFocusedNodeId = node.id();

        const targetZoom = Math.min(3.0, Math.max(cy.zoom() || 1, focus.type === "drug" ? 1.85 : 1.6));
        cy.animate(
          { center: { eles: node }, zoom: targetZoom },
          { duration: 260 }
        );
      };

      window.setTimeout(function() { focusNode(0); }, 50);
      return "";
    }
    """,
    Output(_CYTO_NAV_RESULT_ID, "children"),
    Input("focus-store", "data"),
    Input("pathway-cytoscape", "elements"),
    Input(_SIGNOR_SHOW_DRUGS_ID, "checked"),
    prevent_initial_call=True,
	)


# C-8a: cytoscape hover → 1-hop highlight + peripheral dim
dash.clientside_callback(
    """
    function(elements) {
      const bindHover = function(attempt) {
        const cy = window.cy;
        if (!cy || typeof cy.on !== "function") {
          if (attempt < 25) {
            window.setTimeout(function() { bindHover(attempt + 1); }, 100);
          }
          return;
        }
        if (cy.__pathwayHoverBound) {
          return;
        }

        const clearHover = function() {
          cy.elements().removeClass("faded highlighted hover_label edge-hover cluster-hover");
          if (typeof cy.__pathwayRenderVisualOverlay === "function") {
            cy.__pathwayRenderVisualOverlay();
          }
        };

        cy.on("mouseover", 'node[node_type = "protein"]', function(event) {
          const node = event.target;
          const neighborhood = node.closedNeighborhood();
          cy.elements().addClass("faded").removeClass("highlighted hover_label");
          neighborhood.removeClass("faded").addClass("highlighted");
          neighborhood.nodes().addClass("hover_label");
          neighborhood.edges().addClass("edge-hover");
          node.addClass("hover_label highlighted").removeClass("faded");
          if (typeof cy.__pathwayRenderVisualOverlay === "function") {
            cy.__pathwayRenderVisualOverlay();
          }
        });

        cy.on("mouseover", "edge", function(event) {
          const edge = event.target;
          cy.elements().addClass("faded").removeClass("highlighted hover_label edge-hover");
          edge.addClass("edge-hover highlighted").removeClass("faded");
          edge.connectedNodes().removeClass("faded").addClass("highlighted hover_label");
          if (typeof cy.__pathwayRenderVisualOverlay === "function") {
            cy.__pathwayRenderVisualOverlay();
          }
        });

        cy.on("mouseover", "node.cluster-hull", function(event) {
          const hull = event.target;
          const cluster = hull.data("visual_cluster") || hull.data("cluster");
          if (!cluster) {
            return;
          }
          cy.elements().addClass("faded").removeClass("highlighted hover_label cluster-hover");
          hull.addClass("cluster-hover").removeClass("faded");
          cy.nodes().filter(function(node) {
            return (node.data("visual_cluster") || node.data("cluster")) === cluster;
          }).removeClass("faded").addClass("highlighted");
          cy.edges().filter(function(edge) {
            return edge.data("source_visual_cluster") === cluster
              || edge.data("target_visual_cluster") === cluster
              || edge.data("source_cluster") === cluster
              || edge.data("target_cluster") === cluster;
          }).removeClass("faded").addClass("highlighted");
          if (typeof cy.__pathwayRenderVisualOverlay === "function") {
            cy.__pathwayRenderVisualOverlay();
          }
        });

        const clampClusterPosition = function(node) {
          const data = node.data() || {};
          const cx = Number(data.cluster_cx);
          const cy0 = Number(data.cluster_cy);
          const rx = Math.max(1, Number(data.cluster_rx) || 120);
          const ry = Math.max(1, Number(data.cluster_ry) || 90);
          if (!isFinite(cx) || !isFinite(cy0)) {
            return;
          }
          const pos = node.position();
          const dx = pos.x - cx;
          const dy = pos.y - cy0;
          const norm = Math.sqrt((dx * dx) / (rx * rx) + (dy * dy) / (ry * ry));
          if (norm <= 0.95) {
            return;
          }
          const scale = 0.95 / norm;
          node.position({
            x: cx + dx * scale,
            y: cy0 + dy * scale
          });
        };

        cy.on("drag", 'node[node_type = "protein"]', function(event) {
          clampClusterPosition(event.target);
          if (typeof cy.__pathwayRenderVisualOverlay === "function") {
            cy.__pathwayRenderVisualOverlay();
          }
        });

        cy.on("dragfree", 'node[node_type = "protein"]', function(event) {
          clampClusterPosition(event.target);
          if (typeof cy.__pathwayRenderVisualOverlay === "function") {
            cy.__pathwayRenderVisualOverlay();
          }
        });

        cy.on("mouseout", 'node[node_type = "protein"]', clearHover);
        cy.on("mouseout", "edge", clearHover);
        cy.on("mouseout", "node.cluster-hull", clearHover);
        cy.__pathwayHoverBound = true;
      };
      bindHover(0);
      return String(Date.now());
    }
    """,
    Output(_CYTO_HOVER_RESULT_ID, "children"),
    Input("pathway-cytoscape", "elements"),
)


# C-8b: detail drawer open/close. Node taps open it; layout width never changes.
dash.clientside_callback(
    """
    function(closeClicks, toggleClicks, nodeData, currentOpen) {
      const ctx = window.dash_clientside.callback_context;
      if (!ctx || !ctx.triggered || !ctx.triggered.length) {
        return !!currentOpen;
      }
      const propId = ctx.triggered[0].prop_id || "";
      if (propId.indexOf("pathway-detail-drawer-close-v6") === 0) {
        return false;
      }
      if (propId.indexOf("pathway-detail-drawer-toggle-v6") === 0) {
        return !currentOpen;
      }
      if (propId.indexOf("pathway-cytoscape") === 0 && nodeData) {
        return true;
      }
      return !!currentOpen;
    }
    """,
    Output(_DETAIL_DRAWER_OPEN_STORE_ID, "data"),
    Input(_DETAIL_DRAWER_CLOSE_ID, "n_clicks"),
    Input(_DETAIL_DRAWER_TOGGLE_ID, "n_clicks"),
    Input("pathway-cytoscape", "tapNodeData"),
    State(_DETAIL_DRAWER_OPEN_STORE_ID, "data"),
    prevent_initial_call=True,
)


dash.clientside_callback(
    """
    function(isOpen) {
      return "atlas-right-pane right-card-panel pathway-detail-drawer " + (isOpen ? "is-open" : "is-collapsed");
    }
    """,
    Output(_DETAIL_DRAWER_ID, "className"),
    Input(_DETAIL_DRAWER_OPEN_STORE_ID, "data"),
)


# C-8b: SVG Cluster Islands overlay → hulls, bundled edges, bead nodes, labels
dash.clientside_callback(
    """
    function(elements, showHulls) {
      const overlayId = "pathway-cluster-island-overlay-v6";
      const clusterOrder = ["SEED_HUB", "RTK", "RAS_MAPK", "PI3K_AKT", "APOPTOSIS", "CELL_CYCLE", "TF"];
      const clusterNames = {
        SEED_HUB: "egfr_hub",
        RTK: "rtk_receptor",
        RAS_MAPK: "ras_mapk",
        PI3K_AKT: "pi3k_akt",
        APOPTOSIS: "apoptosis",
        CELL_CYCLE: "cell_cycle",
        TF: "transcription"
      };

      const escapeHtml = function(value) {
        return String(value || "")
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;");
      };

      const clamp = function(value, min, max) {
        return Math.max(min, Math.min(max, value));
      };

      const hexToRgba = function(hex, alpha) {
        const clean = String(hex || "#64748B").replace("#", "");
        const value = clean.length === 3
          ? clean.split("").map(function(ch) { return ch + ch; }).join("")
          : clean.padEnd(6, "0").slice(0, 6);
        const intValue = parseInt(value, 16);
        const r = (intValue >> 16) & 255;
        const g = (intValue >> 8) & 255;
        const b = intValue & 255;
        return "rgba(" + r + "," + g + "," + b + "," + alpha + ")";
      };

      const smoothClosedPath = function(points) {
        if (!points || points.length < 3) {
          return "";
        }
        const midpoint = function(a, b) {
          return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
        };
        const last = points[points.length - 1];
        const first = points[0];
        let start = midpoint(last, first);
        let d = "M " + start.x.toFixed(1) + " " + start.y.toFixed(1) + " ";
        for (let i = 0; i < points.length; i += 1) {
          const current = points[i];
          const next = points[(i + 1) % points.length];
          const mid = midpoint(current, next);
          d += "Q " + current.x.toFixed(1) + " " + current.y.toFixed(1) + " "
            + mid.x.toFixed(1) + " " + mid.y.toFixed(1) + " ";
        }
        return d + "Z";
      };

      const convexHull = function(points) {
        if (!points || points.length < 3) {
          return points || [];
        }
        const sorted = points.slice().sort(function(a, b) {
          return a.x === b.x ? a.y - b.y : a.x - b.x;
        });
        const cross = function(o, a, b) {
          return (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
        };
        const lower = [];
        sorted.forEach(function(point) {
          while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], point) <= 0) {
            lower.pop();
          }
          lower.push(point);
        });
        const upper = [];
        sorted.slice().reverse().forEach(function(point) {
          while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], point) <= 0) {
            upper.pop();
          }
          upper.push(point);
        });
        upper.pop();
        lower.pop();
        return lower.concat(upper);
      };

      const organicHull = function(items, clusterKey) {
        const selected = clusterKey === "SEED_HUB";
        const pad = selected ? 38 : 30;
        const raw = (items || []).map(function(item) { return { x: item.x, y: item.y, r: item.r || 5 }; });
        if (raw.length < 3) {
          return { path: "", points: [], bounds: { minX: 0, maxX: 0, minY: 0, maxY: 0, cx: 0, cy: 0, rx: 0, ry: 0 } };
        }
        const rawXs = raw.map(function(point) { return point.x; });
        const rawYs = raw.map(function(point) { return point.y; });
        const bounds = {
          minX: Math.min.apply(null, rawXs),
          maxX: Math.max.apply(null, rawXs),
          minY: Math.min.apply(null, rawYs),
          maxY: Math.max.apply(null, rawYs)
        };
        const cx = (bounds.minX + bounds.maxX) / 2;
        const cy = (bounds.minY + bounds.maxY) / 2;
        const seed = clusterKey.split("").reduce(function(acc, ch) { return acc + ch.charCodeAt(0); }, 0);
        const padded = [];
        raw.forEach(function(point) {
          const localPad = pad + (point.r || 5) * 1.6;
          for (let i = 0; i < 8; i += 1) {
            const angle = (Math.PI * 2 * i) / 8;
            padded.push({
              x: point.x + Math.cos(angle) * localPad,
              y: point.y + Math.sin(angle) * localPad
            });
          }
        });
        let hull = convexHull(padded);
        hull = hull.map(function(point, idx) {
          const angle = Math.atan2(point.y - cy, point.x - cx);
          const wobble = 1
            + 0.026 * Math.sin(idx * 1.7 + seed * 0.17)
            + 0.018 * Math.cos(idx * 2.3 + seed * 0.11);
          return {
            x: cx + (point.x - cx) * wobble,
            y: cy + (point.y - cy) * wobble
          };
        });
        const xs = hull.map(function(point) { return point.x; });
        const ys = hull.map(function(point) { return point.y; });
        return {
          path: smoothClosedPath(hull),
          points: hull,
          bounds: {
            minX: Math.min.apply(null, xs),
            maxX: Math.max.apply(null, xs),
            minY: Math.min.apply(null, ys),
            maxY: Math.max.apply(null, ys),
            cx,
            cy,
            rx: (Math.max.apply(null, xs) - Math.min.apply(null, xs)) / 2,
            ry: (Math.max.apply(null, ys) - Math.min.apply(null, ys)) / 2
          }
        };
      };

      const relationForEdge = function(edge) {
        const data = edge.data() || {};
        const text = ((data.effect || "") + " " + (data.mechanism || "")).toLowerCase();
        if (edge.hasClass("signor-drug-edge") || data.node_type === "drug_edge") {
          return { label: "drug-target", color: "#A78BFA", key: "drug" };
        }
        if (edge.hasClass("signor-edge-up") || text.indexOf("up-regulates") >= 0 || text.indexOf("activation") >= 0) {
          return { label: "up", color: "#22D3EE", key: "up" };
        }
        if (edge.hasClass("signor-edge-down") || text.indexOf("down-regulates") >= 0 || text.indexOf("inhibition") >= 0) {
          return { label: "down", color: "#F43F5E", key: "down" };
        }
        return { label: "regulates", color: "#60A5FA", key: "regulates" };
      };

      const cubicPoint = function(p0, p1, p2, p3, t) {
        const mt = 1 - t;
        return {
          x: mt * mt * mt * p0.x + 3 * mt * mt * t * p1.x + 3 * mt * t * t * p2.x + t * t * t * p3.x,
          y: mt * mt * mt * p0.y + 3 * mt * mt * t * p1.y + 3 * mt * t * t * p2.y + t * t * t * p3.y
        };
      };

      const nodeKind = function(node) {
        const type = node.data("node_type") || node.data("type");
        if (type === "drug") {
          return "drug";
        }
        if (node.data("role") === "seed" || node.hasClass("ego-center")) {
          return "seed";
        }
        if (node.data("is_rwr_top10")) {
          return "heat";
        }
        if (node.data("is_champion_target") || node.data("is_target")) {
          return "target";
        }
        if (node.hasClass("ego-neighbor")) {
          return "ego";
        }
        return "default";
      };

      const nodeRadius = function(node, kind) {
        if (kind === "seed") {
          return node.hasClass("ego-center") ? 15 : 13;
        }
        if (kind === "heat") {
          return 8.5;
        }
        if (kind === "target") {
          return 7.5;
        }
        if (kind === "drug") {
          return 7;
        }
        if (kind === "ego") {
          return 6;
        }
        // ego mode neighbor (drill-down 진입 시) — fallback
        if (node.hasClass("ego-rwr")) {
          return 7.5;
        }
        if (node.hasClass("ego-neighbor")) {
          return 6;
        }
        // overview/cluster mode
        if (node.data("is_cluster_rep")) {
          return 8;
        }
        return 0;
      };

      const cleanNodeLabel = function(node) {
        const data = node.data() || {};
        const raw = data.gene || data.drug_name || data.label || data.id || node.id();
        return String(raw || "")
          .replace(/^ego::/i, "")
          .replace(/^[^A-Za-z0-9]+\\s*/, "")
          .trim();
      };

      const forceLabel = function(label) {
        return [
          "EGFR", "PIK3CA", "ERBB2", "MAPK1", "MAPK3", "RAF1", "BRAF", "MET", "ALK",
          "KRAS", "NRAS", "ERBB3", "PTK2", "SRC", "SHC1", "CDK4", "CDK6", "PPARG",
          "RET", "ROS1", "NTRK1", "CASP9", "STAT3", "GRB2", "AKT1"
        ].indexOf(String(label || "").toUpperCase()) >= 0;
      };

      const shouldShowNodeLabel = function(item) {
        const data = item.data || {};
        const label = cleanNodeLabel(item.node);
        return item.kind === "seed"
          || item.kind === "heat"
          || item.kind === "target"
          || item.kind === "ego"
          || item.kind === "drug"
          || data.is_cluster_rep
          || data.is_template_node
          || item.visualCluster === "SEED_HUB"
          || (Number(data.degree) || 0) >= 7
          || item.node.hasClass("ego-node")
          || item.node.hasClass("hover_label")
          || item.node.hasClass("highlighted")
          || forceLabel(label);
      };

      const labelPlacement = function(item, clusterCenter) {
        const center = clusterCenter || { x: item.x, y: item.y };
        const dx = item.x - center.x;
        const dy = item.y - center.y;
        const gap = item.kind === "seed" ? 18 : 13;
        if (item.kind === "seed") {
          return { x: item.x, y: item.y + gap + 1, anchor: "middle", baseline: "hanging" };
        }
        if (Math.abs(dx) > Math.abs(dy)) {
          if (dx > 0) {
            return { x: item.x - item.r - gap, y: item.y, anchor: "end", baseline: "central" };
          }
          return { x: item.x + item.r + gap, y: item.y, anchor: "start", baseline: "central" };
        }
        if (dy > 0) {
          return { x: item.x, y: item.y + item.r + gap, anchor: "middle", baseline: "hanging" };
        }
        return { x: item.x, y: item.y - item.r - gap, anchor: "middle", baseline: "baseline" };
      };

      const labelPriority = function(item) {
        const data = item.data || {};
        if (item.kind === "seed") return 0;
        if (item.visualCluster === "SEED_HUB") return 1;
        if (item.kind === "heat") return 2;
        if (data.is_cluster_rep) return 3;
        if (forceLabel(cleanNodeLabel(item.node))) return 4;
        if (item.kind === "target") return 5;
        return 8;
      };

      const bindOverlay = function(attempt) {
        const cy = window.cy;
        const overlay = document.getElementById(overlayId);
        if (!overlay || !cy || typeof cy.nodes !== "function") {
          if (attempt < 30) {
            window.setTimeout(function() { bindOverlay(attempt + 1); }, 100);
          }
          return;
        }

        window.__pathwayShowClusterHulls = !!showHulls;

        const renderVisualMap = function() {
          const target = document.getElementById(overlayId);
          if (!target) {
            if (target) {
              target.innerHTML = "";
            }
            return;
          }

          const width = Math.max(1, target.clientWidth || 1);
          const height = Math.max(1, target.clientHeight || 1);
          const groups = {};
          const parents = {};
          const visualNodes = [];
          const nodeMap = {};
          const isEgo = cy.nodes(".ego-center").length > 0;

          cy.nodes(".cluster-hull").forEach(function(parent) {
            const visualCluster = parent.data("visual_cluster") || parent.data("cluster");
            if (visualCluster) {
              parents[visualCluster] = parent;
            }
          });

          cy.nodes().forEach(function(node) {
            const data = node.data() || {};
            const nodeType = data.node_type || data.type;
            if (nodeType !== "protein" && nodeType !== "drug") {
              return;
            }
            const rendered = node.renderedPosition();
            if (!rendered || !isFinite(rendered.x) || !isFinite(rendered.y)) {
              return;
            }
            const visualCluster = data.visual_cluster || data.cluster || "";
            const kind = nodeKind(node);
            const r = nodeRadius(node, kind);
            const item = {
              node,
              id: node.id(),
              x: rendered.x,
              y: rendered.y,
              r,
              kind,
              data,
              visualCluster
            };
            visualNodes.push(item);
            nodeMap[node.id()] = item;

            if (nodeType === "protein" && visualCluster && parents[visualCluster] && !isEgo) {
              if (!groups[visualCluster]) {
                groups[visualCluster] = { nodes: [], parent: parents[visualCluster] };
              }
              groups[visualCluster].nodes.push(item);
            }
          });

          const halos = [];
          const hulls = [];
          const clusterLabels = [];
          const clusterCenters = {};

          clusterOrder.forEach(function(clusterKey) {
            const group = groups[clusterKey];
            if (!group || !group.nodes.length) {
              return;
            }
            const parent = group.parent;
            const color = parent.data("cluster_color") || "#64748B";
            const selected = parent.hasClass("selected-cluster") || clusterKey === "SEED_HUB";
            const blob = organicHull(group.nodes, clusterKey);
            const bounds = blob.bounds;
            clusterCenters[clusterKey] = { x: bounds.cx, y: bounds.cy };
            if (!window.__pathwayShowClusterHulls) {
              return;
            }
            const fillAlpha = selected ? 0.14 : 0.08;
            const strokeAlpha = selected ? 0.78 : 0.42;
            const strokeWidth = selected ? 1.5 : 1.1;
            const filter = selected ? "drop-shadow(0 0 16px " + hexToRgba(color, 0.16) + ")" : "none";

            if (selected) {
              halos.push(
                '<ellipse cx="' + bounds.cx.toFixed(1) + '" cy="' + bounds.cy.toFixed(1)
                + '" rx="' + (bounds.rx * 1.08).toFixed(1) + '" ry="' + (bounds.ry * 1.08).toFixed(1)
                + '" fill="' + hexToRgba(color, 0.08)
                + '" style="filter: blur(14px); opacity: 0.54;" />'
              );
            }

            hulls.push(
              '<path class="cluster-hull ' + (selected ? "selected" : "") + '" data-cluster="' + escapeHtml(clusterNames[clusterKey] || clusterKey)
              + '" d="' + blob.path + '" fill="' + hexToRgba(color, fillAlpha)
              + '" stroke="' + hexToRgba(color, strokeAlpha)
              + '" stroke-width="' + strokeWidth
              + '" style="filter: ' + filter + '; transition: fill-opacity 140ms ease, stroke-opacity 140ms ease;" />'
            );

            const title = escapeHtml(parent.data("cluster_label") || parent.data("label") || clusterKey);
            const subtitle = escapeHtml(parent.data("subtitle") || "");
            const isHub = clusterKey === "SEED_HUB";
            // [Fix v3] cluster label — cluster color + outside hull
            const labelX = isHub
              ? bounds.cx
              : Math.max(14, Math.min(width - 215, bounds.minX + 8));
            const labelY = Math.max(8, bounds.minY - 18);
            const anchor = isHub ? "middle" : "start";
            const titleFill = selected ? "#FBBF24" : color;
            const subtitleFill = selected ? "#FDE68A" : hexToRgba(color, 0.75);
            const bgWidth = Math.min(238, Math.max(title.length * 6.7, subtitle.length * 5.2) + 22);
            const bgX = isHub ? -bgWidth / 2 : -8;
            const bgFill = "rgba(5, 11, 20, 0.78)";
            const bgStroke = hexToRgba(color, 0.35);
            clusterLabels.push(
              '<g class="cluster-label" data-cluster="' + escapeHtml(clusterKey) + '" transform="translate(' + labelX.toFixed(1) + ',' + labelY.toFixed(1) + ')">'
              + '<rect class="cluster-label-bg" x="' + bgX.toFixed(1) + '" y="-15" width="' + bgWidth.toFixed(1)
              + '" height="32" rx="9" fill="' + bgFill + '" stroke="' + bgStroke + '" stroke-width="1" />'
              + '<text x="' + (isHub ? "0" : "4") + '" y="-1" fill="' + titleFill
              + '" text-anchor="' + anchor + '" font-size="11.5" font-weight="800" letter-spacing="0.05"'
              + ' style="paint-order: stroke; stroke: rgba(5,11,20,0.92); stroke-width: 2.6px;">'
              + title + '</text>'
              + '<text x="' + (isHub ? "0" : "4") + '" y="12" text-anchor="' + anchor + '" fill="' + subtitleFill
              + '" font-size="8.7" font-weight="600"'
              + ' style="paint-order: stroke; stroke: rgba(5,11,20,0.88); stroke-width: 2px;">'
              + subtitle + '</text></g>'
            );
          });

          const selectedNode = cy.nodes(":selected").length
            ? cy.nodes(":selected").first()
            : (window.__pathwayFocusedNodeId ? cy.getElementById(window.__pathwayFocusedNodeId) : cy.nodes('[role = "seed"]').first());
          const selectedId = selectedNode && selectedNode.length ? selectedNode.id() : "";
          const hoveredNode = cy.nodes(".hover_label").length ? cy.nodes(".hover_label").first() : null;
          const hoverActive = hoveredNode && hoveredNode.length;
          const edgeLabels = [];
          const interEdges = [];
          const intraEdges = [];

          const buildPath = function(edge, sourceItem, targetItem) {
            const s = { x: sourceItem.x, y: sourceItem.y };
            const t = { x: targetItem.x, y: targetItem.y };
            const isIntra = !!edge.data("is_intra_cluster");
            if (isIntra) {
              const dx = t.x - s.x;
              const dy = t.y - s.y;
              const len = Math.max(1, Math.sqrt(dx * dx + dy * dy));
              const curve = clamp(len * 0.10, 8, 22);
              const mx = (s.x + t.x) / 2 - (dy / len) * curve;
              const my = (s.y + t.y) / 2 + (dx / len) * curve;
              return {
                d: "M " + s.x.toFixed(1) + " " + s.y.toFixed(1)
                  + " Q " + mx.toFixed(1) + " " + my.toFixed(1)
                  + " " + t.x.toFixed(1) + " " + t.y.toFixed(1),
                mid: { x: mx, y: my }
              };
            }
            const sc = clusterCenters[sourceItem.visualCluster] || { x: (s.x + t.x) / 2, y: (s.y + t.y) / 2 };
            const tc = clusterCenters[targetItem.visualCluster] || sc;
            const p1 = { x: s.x * 0.64 + sc.x * 0.36, y: s.y * 0.64 + sc.y * 0.36 };
            const p2 = { x: t.x * 0.64 + tc.x * 0.36, y: t.y * 0.64 + tc.y * 0.36 };
            return {
              d: "M " + s.x.toFixed(1) + " " + s.y.toFixed(1)
                + " C " + p1.x.toFixed(1) + " " + p1.y.toFixed(1)
                + " " + p2.x.toFixed(1) + " " + p2.y.toFixed(1)
                + " " + t.x.toFixed(1) + " " + t.y.toFixed(1),
              mid: cubicPoint(s, p1, p2, t, 0.5)
            };
          };

          cy.edges().forEach(function(edge) {
            const sourceItem = nodeMap[edge.source().id()];
            const targetItem = nodeMap[edge.target().id()];
            if (!sourceItem || !targetItem) {
              return;
            }
            const rel = relationForEdge(edge);
            const isIntra = !!edge.data("is_intra_cluster");
            const isImportant = !!edge.data("is_important");
            const isHoverEdge = edge.hasClass("highlighted") || edge.hasClass("edge-hover");
            const isSelectedEdge = sourceItem.id === selectedId || targetItem.id === selectedId;
            const isHighlighted = isHoverEdge || isSelectedEdge;
            const isFaded = edge.hasClass("faded");
            const pathInfo = buildPath(edge, sourceItem, targetItem);
            let widthPx = isIntra ? 0.85 : 0.65;
            let opacity = isIntra ? 0.22 : 0.075;
            if (isImportant) {
              widthPx = isIntra ? 0.95 : 0.85;
              opacity = isIntra ? 0.25 : 0.10;
            }
            if (isHoverEdge) {
              widthPx = 1.3;
              opacity = 0.72;
            } else if (isSelectedEdge) {
              widthPx = 1.05;
              opacity = isIntra ? 0.34 : 0.20;
            } else if (isFaded || hoverActive) {
              opacity = isFaded ? 0.025 : opacity;
            }
            const edgeSvg = '<path class="edge ' + (isIntra ? "intra-cluster" : "inter-cluster")
              + (isImportant ? " important" : "") + '" d="' + pathInfo.d
              + '" fill="none" stroke="' + rel.color
              + '" stroke-width="' + widthPx.toFixed(2)
              + '" stroke-opacity="' + opacity.toFixed(3)
              + '" stroke-linecap="round" style="filter:' + (isHighlighted ? "url(#edge-soft-glow)" : "none") + ';" />';
            if (isIntra) {
              intraEdges.push(edgeSvg);
            } else {
              interEdges.push(edgeSvg);
            }

            const labelLimit = hoverActive ? 8 : 3;
            const showEdgeLabel = (edge.hasClass("edge-hover") || isSelectedEdge)
              && edgeLabels.length < labelLimit;
            if (showEdgeLabel) {
              const text = escapeHtml(rel.label);
              const textWidth = Math.max(54, text.length * 5.7 + 18);
              edgeLabels.push(
                '<g class="edge-label" transform="translate(' + pathInfo.mid.x.toFixed(1) + ',' + pathInfo.mid.y.toFixed(1) + ')">'
                + '<rect x="' + (-textWidth / 2).toFixed(1) + '" y="-9" width="' + textWidth.toFixed(1)
                + '" height="18" rx="5" fill="rgba(5, 11, 20, 0.78)" stroke="rgba(148, 163, 184, 0.18)" />'
                + '<text x="0" y="3.5" text-anchor="middle" font-size="9.5" font-weight="700" fill="' + rel.color + '">'
                + text + '</text></g>'
              );
            }
          });

          const nodeGlyphs = [];
          const nodeLabels = [];
          const selectedRings = [];
          const labelBoxes = [];
          const overlaps = function(a, b) {
            return !(a.x2 < b.x1 || a.x1 > b.x2 || a.y2 < b.y1 || a.y1 > b.y2);
          };
          visualNodes.slice().sort(function(a, b) {
            return labelPriority(a) - labelPriority(b);
          }).forEach(function(item) {
            const node = item.node;
            const kind = item.kind;
            const faded = node.hasClass("faded");
            const highlighted = node.hasClass("highlighted") || node.hasClass("hover_label") || item.id === selectedId;
            const showLabel = shouldShowNodeLabel(item);
            const baseOpacity = showLabel ? 0.94 : 0.46;
            const opacity = faded ? 0.16 : (highlighted ? 1 : baseOpacity);
            const palette = {
              seed: { fill: "url(#grad-seed)", stroke: "#FCA5A5", text: "#FFFFFF", glow: "drop-shadow(0 0 12px rgba(239,68,68,0.55))" },
              heat: { fill: "url(#grad-heat)", stroke: "#FCD34D", text: "#FDE68A", glow: "drop-shadow(0 0 9px rgba(245,158,11,0.40))" },
              target: { fill: "url(#grad-target)", stroke: "#86EFAC", text: "#BBF7D0", glow: "drop-shadow(0 0 9px rgba(34,197,94,0.36))" },
              drug: { fill: "url(#grad-drug)", stroke: "#C4B5FD", text: "#DDD6FE", glow: "drop-shadow(0 0 9px rgba(139,92,246,0.32))" },
              ego: { fill: "url(#grad-ego)", stroke: "#67E8F9", text: "#CFFAFE", glow: "drop-shadow(0 0 7px rgba(34,211,238,0.28))" },
              default: { fill: "url(#grad-default)", stroke: "#64748B", text: "#CBD5E1", glow: "none" }
            }[kind] || { fill: "url(#grad-default)", stroke: "#64748B", text: "#CBD5E1", glow: "none" };
            const isSelected = highlighted && item.id === selectedId;
            const filter = isSelected ? "drop-shadow(0 0 10px rgba(34,211,238,0.35))" : palette.glow;
            if (highlighted && item.id === selectedId) {
              selectedRings.push(
                '<circle class="selection-ring" cx="' + item.x.toFixed(1)
                + '" cy="' + item.y.toFixed(1)
                + '" r="' + (item.r + 7).toFixed(1)
                + '" fill="none" stroke="rgba(34, 211, 238, 0.80)"'
                + ' stroke-width="1.7" stroke-dasharray="4 4" opacity="0.9" />'
              );
            }
            if (item.r <= 0.5) { return; }
            nodeGlyphs.push(
              '<g class="node node-' + kind + '" transform="translate(' + item.x.toFixed(1) + ',' + item.y.toFixed(1)
              + ')" opacity="' + opacity.toFixed(3) + '">'
              + '<circle class="node-circle ' + kind + (isSelected ? " selected" : "")
              + '" r="' + item.r.toFixed(1)
              + '" fill="' + palette.fill
              + '" stroke="' + palette.stroke
              + '" stroke-width="' + (kind === "seed" ? 2.2 : 1.4)
              + '" vector-effect="non-scaling-stroke" style="filter:' + filter + ';" />'
              + '</g>'
            );
            if (showLabel) {
              const label = cleanNodeLabel(node);
              const clusterCenter = clusterCenters[item.visualCluster] || { x: item.x, y: item.y };
              const placement = labelPlacement(item, clusterCenter);
              const fontSize = kind === "seed" ? 12 : 10;
              const labelWidth = Math.max(26, label.length * (fontSize * 0.58));
              const labelHeight = fontSize + 5;
              const box = {
                x1: placement.anchor === "end" ? placement.x - labelWidth : (placement.anchor === "middle" ? placement.x - labelWidth / 2 : placement.x),
                x2: placement.anchor === "end" ? placement.x : (placement.anchor === "middle" ? placement.x + labelWidth / 2 : placement.x + labelWidth),
                y1: placement.y - labelHeight / 2,
                y2: placement.y + labelHeight / 2
              };
              const collision = labelBoxes.some(function(existing) { return overlaps(box, existing); });
              if (!collision || kind === "seed" || highlighted) {
                labelBoxes.push(box);
                nodeLabels.push(
                  '<text class="node-label node-label-' + kind
                  + '" x="' + placement.x.toFixed(1)
                  + '" y="' + placement.y.toFixed(1)
                  + '" text-anchor="' + placement.anchor
                  + '" dominant-baseline="' + placement.baseline
                  + '" font-size="' + fontSize
                  + '" font-weight="' + (kind === "seed" ? 800 : 700)
                  + '" fill="' + palette.text
                  + '" style="paint-order: stroke; stroke: rgba(5,11,20,0.88); stroke-width: 3px; pointer-events:none;">'
                  + escapeHtml(label) + '</text>'
                );
              }
            }
          });

          const defs = [
            '<defs>',
            '<radialGradient id="grad-seed" cx="35%" cy="30%" r="70%"><stop offset="0%" stop-color="#FCA5A5" stop-opacity="0.95"/><stop offset="55%" stop-color="#EF4444" stop-opacity="0.95"/><stop offset="100%" stop-color="#991B1B" stop-opacity="0.95"/></radialGradient>',
            '<radialGradient id="grad-heat" cx="35%" cy="30%" r="70%"><stop offset="0%" stop-color="#FDE68A" stop-opacity="0.95"/><stop offset="55%" stop-color="#F59E0B" stop-opacity="0.95"/><stop offset="100%" stop-color="#B45309" stop-opacity="0.95"/></radialGradient>',
            '<radialGradient id="grad-target" cx="35%" cy="30%" r="70%"><stop offset="0%" stop-color="#BBF7D0" stop-opacity="0.95"/><stop offset="55%" stop-color="#22C55E" stop-opacity="0.95"/><stop offset="100%" stop-color="#15803D" stop-opacity="0.95"/></radialGradient>',
            '<radialGradient id="grad-drug" cx="35%" cy="30%" r="70%"><stop offset="0%" stop-color="#DDD6FE" stop-opacity="0.95"/><stop offset="55%" stop-color="#8B5CF6" stop-opacity="0.95"/><stop offset="100%" stop-color="#6D28D9" stop-opacity="0.95"/></radialGradient>',
            '<radialGradient id="grad-ego" cx="35%" cy="30%" r="70%"><stop offset="0%" stop-color="#A5F3FC" stop-opacity="0.90"/><stop offset="55%" stop-color="#22D3EE" stop-opacity="0.90"/><stop offset="100%" stop-color="#0E7490" stop-opacity="0.90"/></radialGradient>',
            '<radialGradient id="grad-default" cx="35%" cy="30%" r="70%"><stop offset="0%" stop-color="#94A3B8" stop-opacity="0.85"/><stop offset="55%" stop-color="#475569" stop-opacity="0.85"/><stop offset="100%" stop-color="#1E293B" stop-opacity="0.85"/></radialGradient>',
            '<filter id="cluster-soft-glow" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="5" result="blur"/><feColorMatrix in="blur" type="matrix" values="1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 0.45 0" result="softBlur"/><feMerge><feMergeNode in="softBlur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>',
            '<filter id="cluster-strong-glow" x="-70%" y="-70%" width="240%" height="240%"><feGaussianBlur stdDeviation="8" result="blur1"/><feGaussianBlur stdDeviation="18" result="blur2"/><feMerge><feMergeNode in="blur2"/><feMergeNode in="blur1"/><feMergeNode in="SourceGraphic"/></feMerge></filter>',
            '<filter id="edge-soft-glow" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="2.5" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>',
            '<filter id="text-soft-glow" x="-30%" y="-80%" width="160%" height="240%"><feGaussianBlur stdDeviation="2.2" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>',
            '</defs>'
          ].join("");

          target.innerHTML = '<svg viewBox="0 0 ' + width + ' ' + height
            + '" preserveAspectRatio="none" aria-hidden="true">'
            + defs
            + '<style>@keyframes pulseRing{0%{opacity:.95}50%{opacity:.35}100%{opacity:.95}} .selection-ring{animation:pulseRing 1.8s ease-in-out infinite; transform-box:fill-box; transform-origin:center;} .node-circle{vector-effect:non-scaling-stroke;} .node-label{pointer-events:none;}</style>'
            + '<g class="pathway-island-halo-layer">' + halos.join("") + '</g>'
            + '<g class="pathway-island-hull-layer">' + hulls.join("") + '</g>'
            + '<g class="pathway-edge-layer inter">' + interEdges.join("") + '</g>'
            + '<g class="pathway-edge-layer intra">' + intraEdges.join("") + '</g>'
            + '<g class="pathway-selection-layer">' + selectedRings.join("") + '</g>'
            + '<g class="pathway-node-layer">' + nodeGlyphs.join("") + '</g>'
            + '<g class="pathway-island-label-layer">' + clusterLabels.join("") + '</g>'
            + '<g class="pathway-node-label-layer">' + nodeLabels.join("") + '</g>'
            + '<g class="pathway-edge-label-layer">' + edgeLabels.join("") + '</g>'
            + '</svg>';
        };

        const scheduleRender = function() {
          if (cy.__pathwayIslandOverlayFrame) {
            window.cancelAnimationFrame(cy.__pathwayIslandOverlayFrame);
          }
          cy.__pathwayIslandOverlayFrame = window.requestAnimationFrame(renderVisualMap);
        };

        cy.__pathwayRenderIslands = scheduleRender;
        cy.__pathwayRenderVisualOverlay = scheduleRender;
        if (!cy.__pathwayIslandOverlayBound) {
          cy.on("render pan zoom resize position add remove data style select unselect", scheduleRender);
          cy.__pathwayIslandOverlayBound = true;
        }
        window.setTimeout(scheduleRender, 40);
        window.setTimeout(scheduleRender, 180);
        window.setTimeout(scheduleRender, 420);
      };

      bindOverlay(0);
      return String(Date.now());
    }
    """,
    Output(_CLUSTER_OVERLAY_RESULT_ID, "children"),
    Input("pathway-cytoscape", "elements"),
    Input(_CLUSTER_HULL_SWITCH_ID, "checked"),
)


# C-9: map controls → cytoscape zoom/fit
dash.clientside_callback(
    """
    function(zoomInClicks, zoomOutClicks, fitClicks) {
      const ctx = window.dash_clientside.callback_context;
      if (!ctx || !ctx.triggered || !ctx.triggered.length) {
        return "";
      }
      const propId = ctx.triggered[0].prop_id || "";
      const cy = window.cy;
      if (!cy || typeof cy.zoom !== "function") {
        return "";
      }

      if (propId.indexOf("pathway-map-fit") === 0) {
        cy.fit(cy.elements(), 40);
        return String(Date.now());
      }

      const current = cy.zoom() || 1;
      let next = current;
      if (propId.indexOf("pathway-map-zoom-in") === 0) {
        next = Math.min(3.0, current * 1.25);
      } else if (propId.indexOf("pathway-map-zoom-out") === 0) {
        next = Math.max(0.3, current / 1.25);
      }
      cy.zoom({
        level: next,
        renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 }
      });
      return String(Date.now());
    }
    """,
    Output(_CYTO_CONTROL_RESULT_ID, "children"),
    Input(_MAP_ZOOM_IN_ID, "n_clicks"),
    Input(_MAP_ZOOM_OUT_ID, "n_clicks"),
    Input(_MAP_FIT_ID, "n_clicks"),
    prevent_initial_call=True,
)


# C-9a: Overview → fit reset
dash.clientside_callback(
    """
    function(overviewChecked) {
      const ctx = window.dash_clientside.callback_context;
      if (!ctx || !ctx.triggered || !ctx.triggered.length) {
        return "";
      }
      const propId = ctx.triggered[0].prop_id || "";
      const cy = window.cy;
      if (!cy || typeof cy.fit !== "function") {
        return "";
      }
      if (overviewChecked) {
        cy.fit(cy.elements(), 48);
        return String(Date.now());
      }
      return "";
    }
    """,
    Output(_OVERVIEW_RESULT_ID, "children"),
    Input(_OVERVIEW_SWITCH_ID, "checked"),
    prevent_initial_call=True,
)


# C-9b: minimap click/drag → main cytoscape pan
dash.clientside_callback(
    """
    function(elements, showMinimap) {
      const attachMinimap = function(attempt) {
        const minimap = document.getElementById("pathway-minimap-v6");
        if (!minimap) {
          if (attempt < 30) {
            window.setTimeout(function() { attachMinimap(attempt + 1); }, 100);
          }
          return;
        }
        minimap.style.display = showMinimap ? "" : "none";
        if (!showMinimap) {
          return;
        }

        const parseBound = function(name, fallback) {
          const value = Number(minimap.getAttribute(name));
          return Number.isFinite(value) ? value : fallback;
        };
        const bounds = function() {
          return {
            xMin: parseBound("data-x-min", -480),
            xMax: parseBound("data-x-max", 480),
            yMin: parseBound("data-y-min", -400),
            yMax: parseBound("data-y-max", 400)
          };
        };
        const viewportBox = minimap.querySelector(".pathway-minimap-viewport");

        const updateViewportBox = function() {
          const cy = window.cy;
          if (!cy || !viewportBox || typeof cy.extent !== "function") {
            return;
          }
          const rect = minimap.getBoundingClientRect();
          const b = bounds();
          const extent = cy.extent();
          const sx = rect.width / Math.max(1, b.xMax - b.xMin);
          const sy = rect.height / Math.max(1, b.yMax - b.yMin);
          const left = Math.max(0, Math.min(rect.width - 8, (extent.x1 - b.xMin) * sx));
          const top = Math.max(0, Math.min(rect.height - 8, (extent.y1 - b.yMin) * sy));
          const width = Math.max(16, Math.min(rect.width, (extent.x2 - extent.x1) * sx));
          const height = Math.max(14, Math.min(rect.height, (extent.y2 - extent.y1) * sy));
          viewportBox.style.left = left.toFixed(1) + "px";
          viewportBox.style.top = top.toFixed(1) + "px";
          viewportBox.style.width = width.toFixed(1) + "px";
          viewportBox.style.height = height.toFixed(1) + "px";
        };

        const panToEvent = function(event) {
          const cy = window.cy;
          if (!cy || typeof cy.pan !== "function" || typeof cy.zoom !== "function") {
            return;
          }
          const rect = minimap.getBoundingClientRect();
          const b = bounds();
          const xRatio = Math.max(0, Math.min(1, (event.clientX - rect.left) / Math.max(1, rect.width)));
          const yRatio = Math.max(0, Math.min(1, (event.clientY - rect.top) / Math.max(1, rect.height)));
          const modelX = b.xMin + xRatio * (b.xMax - b.xMin);
          const modelY = b.yMin + yRatio * (b.yMax - b.yMin);
          const zoom = cy.zoom() || 1;
          cy.pan({
            x: cy.width() / 2 - modelX * zoom,
            y: cy.height() / 2 - modelY * zoom
          });
          updateViewportBox();
        };
        window.__pathwayMiniPanToEvent = panToEvent;

        if (!window.__pathwayMiniDelegatedBound) {
          let documentDragging = false;
          const closestMini = function(target) {
            return target && typeof target.closest === "function"
              ? target.closest("#pathway-minimap-v6")
              : null;
          };
          document.addEventListener("mousedown", function(event) {
            const viewportTarget = event.target && typeof event.target.closest === "function"
              ? event.target.closest(".pathway-minimap-viewport")
              : null;
            if (viewportTarget && closestMini(event.target) && window.__pathwayMiniPanToEvent) {
              documentDragging = true;
              event.preventDefault();
              window.__pathwayMiniPanToEvent(event);
            }
          }, true);
          document.addEventListener("mousemove", function(event) {
            if (documentDragging && window.__pathwayMiniPanToEvent) {
              window.__pathwayMiniPanToEvent(event);
            }
          }, true);
          document.addEventListener("mouseup", function() {
            documentDragging = false;
          }, true);
          document.addEventListener("click", function(event) {
            if (!documentDragging && closestMini(event.target) && window.__pathwayMiniPanToEvent) {
              window.__pathwayMiniPanToEvent(event);
            }
          }, true);
          window.__pathwayMiniDelegatedBound = true;
        }

        if (!minimap.__pathwayMiniBound) {
          let dragging = false;
          minimap.addEventListener("click", function(event) {
            if (!dragging) {
              panToEvent(event);
            }
          });
          if (viewportBox) {
            viewportBox.addEventListener("mousedown", function(event) {
              dragging = true;
              event.preventDefault();
              event.stopPropagation();
              panToEvent(event);
            });
          }
          document.addEventListener("mousemove", function(event) {
            if (dragging) {
              panToEvent(event);
            }
          });
          document.addEventListener("mouseup", function() {
            dragging = false;
          });
          minimap.__pathwayMiniBound = true;
        }

        const bindCy = function(cyAttempt) {
          const cy = window.cy;
          if (!cy || typeof cy.on !== "function") {
            if (cyAttempt < 20) {
              window.setTimeout(function() { bindCy(cyAttempt + 1); }, 100);
            }
            return;
          }
          if (!cy.__pathwayMiniViewportBound) {
            cy.on("viewport resize", updateViewportBox);
            cy.__pathwayMiniViewportBound = true;
          }
          updateViewportBox();
        };
        bindCy(0);
      };
      attachMinimap(0);
      return String(Date.now());
    }
    """,
    Output(_MINIMAP_RESULT_ID, "children"),
    Input("pathway-cytoscape", "elements"),
    Input(_MINIMAP_SWITCH_ID, "checked"),
)


# C-10: chatbot FAB/popup open state
@callback(
    Output(CHAT_POPUP_OPEN_STORE_ID, "data"),
    Input(CHAT_POPUP_FAB_ID, "n_clicks"),
    Input(CHAT_POPUP_CLOSE_ID, "n_clicks"),
    Input(CHAT_POPUP_BACKDROP_ID, "n_clicks"),
    State(CHAT_POPUP_OPEN_STORE_ID, "data"),
    prevent_initial_call=True,
)
def toggle_chatbot_popup(fab_clicks, close_clicks, backdrop_clicks, is_open):
    trig = ctx.triggered_id
    if trig == CHAT_POPUP_FAB_ID:
        return not bool(is_open)
    if trig in {CHAT_POPUP_CLOSE_ID, CHAT_POPUP_BACKDROP_ID}:
        return False
    return no_update


@callback(
    Output(CHAT_POPUP_SHELL_ID, "className"),
    Output(CHAT_POPUP_SHELL_ID, "aria-hidden"),
    Input(CHAT_POPUP_OPEN_STORE_ID, "data"),
)
def render_chatbot_popup_state(is_open):
    if is_open:
        return "pathway-chat-popup-shell is-open", "false"
    return "pathway-chat-popup-shell", "true"


dash.clientside_callback(
    """
    function(isOpen) {
      window.__pathwayChatPopupOpen = !!isOpen;
      if (!window.__pathwayChatPopupEscapeBound) {
        document.addEventListener("keydown", function(event) {
          if (event.key === "Escape" && window.__pathwayChatPopupOpen) {
            window.__pathwayChatPopupOpen = false;
            if (window.dash_clientside && window.dash_clientside.set_props) {
              window.dash_clientside.set_props("pathway-chat-popup-open-store", {data: false});
            }
          }
        });
        window.__pathwayChatPopupEscapeBound = true;
      }
      return "";
    }
    """,
    Output(CHAT_POPUP_ESCAPE_LISTENER_ID, "children"),
    Input(CHAT_POPUP_OPEN_STORE_ID, "data"),
)
