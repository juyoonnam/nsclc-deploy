"""
cytoscape_styles.py
Pathway Map cytoscape 색상 + 스타일시트 정의.

pathway_map.py에서 분리. 다른 cytoscape 사용처(Mode 1 Library 등)에서도 재사용.
"""

# Color palette
COLORS_CYTO = {
    "bg": "#06101f",
    "edge": "#94A3B8",
    "edge_inhibit": "#FF5B5B",
    "edge_activate": "#22D3EE",
    "edge_default": "#CBD5E1",
    "kegg_compound": "#F59F00",
    "node_target": "#0B1D35",
    "node_target_active": "#0F2A32",
    "node_pathway": "#51CF66",
    "node_default": "#0B1629",
    "text": "#F8FAFC",
    "text_dim": "#94A3B8",
}

# Stylesheet (cytoscape selectors)
STYLESHEET = [
    # 기본 노드
    {
        "selector": "node",
        "style": {
            "background-color": COLORS_CYTO["node_default"],
            "label": "data(label)",
            "color": COLORS_CYTO["text"],
            "text-valign": "center",
            "text-halign": "center",
            "font-size": "11px",
            "font-weight": "700",
            "text-wrap": "wrap",
            "text-max-width": "78px",
            "border-width": 2,
            "border-color": "#4A5568",
            "shape": "roundrectangle",
            "width": 92,
            "height": 30,
            "shadow-blur": 6,
            "shadow-color": "rgba(74, 85, 104, 0.34)",
            "shadow-opacity": 0.42,
            "z-index": 4,
        },
    },
    # 프로젝트 타겟 (EGFR, ALK 등 NSCLC 핵심)
    {
        "selector": "node.project-target",
        "style": {
            "background-color": "#10243B",
            "border-color": "#51CF66",
            "border-width": 2,
            "color": "#FFFFFF",
            "shape": "roundrectangle",
            "width": 104,
            "height": 34,
            "font-size": "12px",
            "font-weight": "800",
            "text-max-width": "90px",
            "shadow-blur": 14,
            "shadow-color": "#51CF66",
            "shadow-opacity": 0.46,
            "z-index": 9,
        },
    },
    # 약물이 있는 타겟 (강조)
    {
        "selector": "node.has-compounds",
        "style": {
            "background-color": "#102A2B",
            "border-color": "#51CF66",
            "border-width": 3,
            "color": "#FFFFFF",
            "shape": "roundrectangle",
            "width": 112,
            "height": 34,
            "font-weight": "800",
            "font-size": "12px",
            "text-max-width": "98px",
            "shadow-blur": 16,
            "shadow-color": "#51CF66",
            "shadow-opacity": 0.64,
            "z-index": 12,
        },
    },
    # 긴 라벨 전용: 좌표는 유지하고 박스만 키워 잘림 방지
    {
        "selector": "node.long-label",
        "style": {
            "width": 118,
            "height": 38,
            "font-size": "10px",
            "line-height": 1.05,
            "text-max-width": "104px",
            "z-index": 11,
        },
    },
    # KEGG fallback node_167처럼 근접 노드와 겹치는 박스
    {
        "selector": "node.overlap-compact",
        "style": {
            "width": 74,
            "height": 26,
            "font-size": "9px",
            "text-max-width": "62px",
            "border-width": 2,
            "z-index": 18,
            "shadow-blur": 5,
        },
    },
    # Cytoscape 내부 drug capsule
    {
        "selector": "node.drug-capsule",
        "style": {
            "background-color": "rgba(4, 13, 25, 0.9)",
            "label": "data(label)",
            "shape": "roundrectangle",
            "width": 122,
            "height": 48,
            "font-size": "13px",
            "font-weight": "800",
            "text-wrap": "wrap",
            "text-max-width": "108px",
            "line-height": 1.05,
            "border-width": 2,
            "color": "#F8FAFC",
            "z-index": 25,
            "shadow-blur": 20,
            "shadow-opacity": 0.7,
        },
    },
    {
        "selector": "node.drug-green",
        "style": {
            "color": "#51CF66",
            "border-color": "#51CF66",
            "shadow-color": "#51CF66",
        },
    },
    {
        "selector": "node.drug-purple",
        "style": {
            "color": "#C084FC",
            "border-color": "#A78BFA",
            "shadow-color": "#A78BFA",
        },
    },
    {
        "selector": "node.drug-amber",
        "style": {
            "color": "#F59F00",
            "border-color": "#F59F00",
            "shadow-color": "#F59F00",
        },
    },
    # KEGG compound (작은 노드)
    {
        "selector": "node.kegg-compound",
        "style": {
            "background-color": "rgba(245, 159, 0, 0.18)",
            "border-color": COLORS_CYTO["kegg_compound"],
            "border-width": 2,
            "color": COLORS_CYTO["kegg_compound"],
            "shape": "ellipse",
            "width": 28,
            "height": 28,
            "font-size": "9px",
            "shadow-blur": 12,
            "shadow-color": "#F59F00",
            "shadow-opacity": 0.5,
        },
    },
    # 기본 엣지
    {
        "selector": "edge",
        "style": {
            "width": 2,
            "line-color": COLORS_CYTO["edge_default"],
            "curve-style": "bezier",
            "target-arrow-shape": "triangle",
            "target-arrow-color": COLORS_CYTO["edge_default"],
            "arrow-scale": 0.9,
            "line-style": "solid",
        },
    },
    {
        "selector": "edge.drug-link",
        "style": {
            "width": 2.2,
            "line-color": "#22D3EE",
            "target-arrow-color": "#22D3EE",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            "line-style": "dashed",
            "line-dash-pattern": [7, 7],
            "z-index": 2,
        },
    },
    # 활성 엣지 (녹색)
    {
        "selector": "edge.activation",
        "style": {
            "line-color": COLORS_CYTO["edge_activate"],
            "target-arrow-color": COLORS_CYTO["edge_activate"],
            "target-arrow-shape": "triangle",
            "width": 2.4,
            "line-style": "dashed",
            "line-dash-pattern": [8, 8],
        },
    },
    # 억제 엣지 (빨강)
    {
        "selector": "edge.inhibition",
        "style": {
            "line-color": COLORS_CYTO["edge_inhibit"],
            "target-arrow-color": COLORS_CYTO["edge_inhibit"],
            "target-arrow-shape": "tee",
            "width": 2.4,
        },
    },
    # 선택된 노드
    {
        "selector": "node:selected",
        "style": {
            "border-width": 4,
            "border-color": "#22D3EE",
            "shadow-blur": 28,
            "shadow-color": "#22D3EE",
            "shadow-opacity": 0.9,
        },
    },
]
