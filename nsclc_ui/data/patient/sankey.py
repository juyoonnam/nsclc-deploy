"""
nsclc_ui.data.patient.sankey

변이 → 대표 경로 → 추천 약물 mini-sankey.

Hardcoded 20 actionable gene → pathway mapping (KEGG hsa05223 NSCLC 기반).
Narrative 단순화: full SIGNOR/KEGG query 대신 핵심 표준 매핑만 사용.
"""

import plotly.graph_objects as go

# 20 actionable gene → 대표 NSCLC pathway
# KEGG hsa05223 (NSCLC) 표준 분류
GENE_TO_PATHWAY = {
    "EGFR":    "EGFR signaling",
    "ERBB2":   "EGFR signaling",
    "KRAS":    "RAS/MAPK",
    "BRAF":    "RAS/MAPK",
    "MAP2K1":  "RAS/MAPK",
    "NF1":     "RAS/MAPK",
    "PIK3CA":  "PI3K/AKT",
    "PTEN":    "PI3K/AKT",
    "ALK":     "ALK/ROS1",
    "ROS1":    "ALK/ROS1",
    "MET":     "RTK signaling",
    "RET":     "RTK signaling",
    "NTRK1":   "RTK signaling",
    "NTRK2":   "RTK signaling",
    "NTRK3":   "RTK signaling",
    "TP53":    "Apoptosis",
    "RB1":     "Cell cycle",
    "CDKN2A":  "Cell cycle",
    "STK11":   "Metabolism (AMPK)",
    "KEAP1":   "Oxidative stress",
}

# Pathway 컬러 (4-source 검증 색조와 매칭)
PATHWAY_COLORS = {
    "EGFR signaling":    "#5DCAA5",   # green (primary actionable)
    "RAS/MAPK":          "#85B7EB",   # cyan
    "PI3K/AKT":          "#7F77DD",   # purple
    "ALK/ROS1":          "#5DCAA5",
    "RTK signaling":     "#85B7EB",
    "Apoptosis":         "#F0997B",   # orange (tumor suppressor)
    "Cell cycle":        "#F0997B",
    "Metabolism (AMPK)": "#D85A30",
    "Oxidative stress":  "#D85A30",
}

# Sankey link color (mutation → pathway, pathway → drug)
_LINK_MUT_TO_PATH = "rgba(127, 119, 221, 0.4)"   # 보라 (mutation)
_LINK_PATH_TO_DRUG = "rgba(93, 202, 165, 0.5)"   # 초록 (drug)


def get_sankey_figure(mutations: list, top_drugs: list, max_drugs: int = 5):
    """
    변이 → 경로 → 약물 sankey figure dict.

    Args:
        mutations: list of mutated gene names (e.g., ["EGFR", "TP53"])
        top_drugs: list of drug dicts (from compose_inference or get_patient_top_drugs)
            각 drug dict must have: drug_name, target_overlap_genes (or target),
                                    hybrid_tier (optional)
        max_drugs: 표시 drug 수 (default 5)

    Returns:
        Plotly figure dict (data + layout)
    """
    if not mutations:
        return _empty_figure("변이 정보 없음")
    if not top_drugs:
        return _empty_figure("추천 약물 없음")

    # 환자의 mutated gene set
    mut_set = set(mutations)

    # 사용된 pathway 추출
    active_pathways = []
    for g in mutations:
        p = GENE_TO_PATHWAY.get(g)
        if p and p not in active_pathways:
            active_pathways.append(p)

    if not active_pathways:
        return _empty_figure("매칭 경로 없음")

    # Drug → 어느 pathway에 연결되는지 (target_overlap_genes 기반)
    # max_drugs까지만, tier 1만 우선
    displayed_drugs = []
    for d in top_drugs[:max_drugs]:
        overlap_str = d.get("target_overlap_genes") or ""
        overlap_genes = [g.strip() for g in overlap_str.split(",") if g.strip()]
        # target_overlap_genes 없으면 drug.target 파싱
        if not overlap_genes:
            target_str = d.get("target") or ""
            target_genes = [g.strip().upper() for g in target_str.replace(";", ",").split(",")]
            overlap_genes = [g for g in target_genes if g in mut_set]

        # 연결할 pathway
        drug_pathways = []
        for g in overlap_genes:
            p = GENE_TO_PATHWAY.get(g)
            if p and p in active_pathways and p not in drug_pathways:
                drug_pathways.append(p)

        if not drug_pathways:
            # tier 2 또는 actionable 외 — generic "기타 효과"로 처리
            drug_pathways = ["기타 효과"]
            if "기타 효과" not in active_pathways:
                active_pathways.append("기타 효과")

        displayed_drugs.append({
            "name": d.get("drug_name", "?"),
            "pathways": drug_pathways,
            "tier": d.get("hybrid_tier", 2),
            "rank": d.get("rank_hybrid", 999),
        })

    # ─── Sankey node/link 구성 ───
    # Nodes: [mutations] + [pathways] + [drugs]
    mut_nodes = list(mutations)
    path_nodes = list(active_pathways)
    drug_nodes = [d["name"] for d in displayed_drugs]

    all_nodes = mut_nodes + path_nodes + drug_nodes
    n_mut = len(mut_nodes)
    n_path = len(path_nodes)

    # Node colors
    node_colors = []
    for g in mut_nodes:
        node_colors.append("#7F77DD")  # mutation = purple
    for p in path_nodes:
        node_colors.append(PATHWAY_COLORS.get(p, "#888780"))
    for d in displayed_drugs:
        node_colors.append("#5DCAA5" if d["tier"] == 1 else "#888780")

    # Links
    sources = []
    targets = []
    values = []
    link_colors = []

    # 1. Mutation → Pathway
    mut_idx = {g: i for i, g in enumerate(mut_nodes)}
    path_idx = {p: n_mut + i for i, p in enumerate(path_nodes)}
    seen_mp = set()
    for g in mut_nodes:
        p = GENE_TO_PATHWAY.get(g)
        if p and p in path_idx and (g, p) not in seen_mp:
            sources.append(mut_idx[g])
            targets.append(path_idx[p])
            values.append(1)
            link_colors.append(_LINK_MUT_TO_PATH)
            seen_mp.add((g, p))

    # 2. Pathway → Drug
    drug_idx = {d["name"]: n_mut + n_path + i for i, d in enumerate(displayed_drugs)}
    for d in displayed_drugs:
        d_node_idx = drug_idx[d["name"]]
        for p in d["pathways"]:
            if p in path_idx:
                sources.append(path_idx[p])
                targets.append(d_node_idx)
                values.append(1)
                # Tier 1 drug = 진한 초록, Tier 2 = 옅은 회색
                if d["tier"] == 1:
                    link_colors.append(_LINK_PATH_TO_DRUG)
                else:
                    link_colors.append("rgba(136, 135, 128, 0.3)")

    # ─── Plotly Sankey ───
    fig = {
        "data": [{
            "type": "sankey",
            "orientation": "h",
            "valueformat": ".0f",
            "node": {
                "pad": 12,
                "thickness": 14,
                "line": {"color": "rgba(255,255,255,0.1)", "width": 0.5},
                "label": all_nodes,
                "color": node_colors,
            },
            "link": {
                "source": sources,
                "target": targets,
                "value": values,
                "color": link_colors,
            },
        }],
        "layout": {
            "font": {"size": 11, "color": "#a0a8b8", "family": "system-ui, -apple-system, sans-serif"},
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor": "rgba(0,0,0,0)",
            "margin": {"t": 10, "b": 10, "l": 10, "r": 10},
            "height": 240,
        }
    }
    return fig


def _empty_figure(message: str):
    return {
        "data": [],
        "layout": {
            "annotations": [{
                "text": message,
                "x": 0.5, "y": 0.5,
                "xref": "paper", "yref": "paper",
                "showarrow": False,
                "font": {"size": 12, "color": "#6b7689"},
            }],
            "xaxis": {"visible": False},
            "yaxis": {"visible": False},
            "plot_bgcolor": "rgba(0,0,0,0)",
            "paper_bgcolor": "rgba(0,0,0,0)",
            "height": 240,
            "margin": {"t": 10, "b": 10, "l": 10, "r": 10},
        }
    }
