"""
NSCLC Insight Engine — Design tokens & MantineTheme (Dark)
"""

# ── Color tokens ──────────────────────────────────────────────────────────────
COLORS = {
    "bg_primary":      "#0F1923",
    "bg_secondary":    "#162231",
    "bg_tertiary":     "#1E2D3D",
    "border":          "#2A3A4A",
    "border_strong":   "#3A4A5A",
    "text_primary":    "#E8ECF1",
    "text_secondary":  "#8899AA",
    "text_tertiary":   "#5A6A7A",
    # semantic
    "success_bg":      "#0D3B2E",
    "success_text":    "#00D4AA",
    "danger_bg":       "#3B1A1A",
    "danger_text":     "#FF6B6B",
    "info_bg":         "#1A2D4A",
    "info_text":       "#4DABF7",
    "warning_bg":      "#3B2E0D",
    "warning_text":    "#FFD43B",
    # accent
    "accent":          "#4DABF7",
    "accent_hover":    "#339AF0",
    # Modality 5색 (고정)
    "mod_drug":        "#00D4AA",
    "mod_adc":         "#FF922B",
    "mod_protac":      "#9775FA",
    "mod_glue":        "#F06595",
    "mod_rlt":         "#FFD43B",
    # Pathway V6 visual policy
    "cluster_rtk":        "#22D3EE",
    "cluster_ras_mapk":   "#F59E0B",
    "cluster_pi3k_akt":   "#22C55E",
    "cluster_apoptosis":  "#14B8A6",
    "cluster_cell_cycle": "#A855F7",
    "cluster_tf":         "#8B5CF6",
    "node_seed":          "#EF4444",
    "node_target":        "#22C55E",
    "node_heat":          "#F59E0B",
    "node_drug":          "#8B5CF6",
    "node_default":       "#475569",
    "edge_up":            "#22D3EE",
    "edge_down":          "#F43F5E",
    "edge_regulates":     "#60A5FA",
    "edge_unknown":       "#64748B",
}

# ── Typography ─────────────────────────────────────────────────────────────────
FONT_SANS  = '-apple-system, "Pretendard", system-ui, sans-serif'
FONT_MONO  = '"JetBrains Mono", "SF Mono", "Fira Code", monospace'

# ── Mantine theme override dict ────────────────────────────────────────────────
MANTINE_THEME = {
    "colorScheme": "dark",
    "fontFamily": FONT_SANS,
    "fontFamilyMonospace": FONT_MONO,
    "primaryColor": "cyan",
    "defaultRadius": "sm",
    "colors": {
        "dark": [
            "#E8ECF1", "#8899AA", "#5A6A7A", "#3A4A5A",
            "#2A3A4A", "#1E2D3D", "#162231", "#0F1923",
            "#0B1219", "#070D12",
        ],
        "cyan": [
            "#E3FAFC", "#C5F6FA", "#99E9F2", "#66D9E8",
            "#3BC9DB", "#22B8CF", "#15AABF", "#1098AD",
            "#0C8599", "#0B7285",
        ],
    },
    "components": {
        "Button": {
            "styles": {
                "root": {
                    "fontWeight": "500",
                    "fontSize": "12px",
                    "height": "32px",
                }
            }
        },
        "Badge": {
            "styles": {
                "root": {
                    "fontWeight": "500",
                    "fontSize": "11px",
                    "borderRadius": "4px",
                    "textTransform": "none",
                }
            }
        },
        "Text": {
            "styles": {
                "root": {
                    "fontFamily": FONT_SANS,
                }
            }
        },
    },
    "headings": {
        "fontWeight": "500",
        "sizes": {
            "h1": {"fontSize": "22px"},
            "h2": {"fontSize": "18px"},
            "h3": {"fontSize": "16px"},
            "h4": {"fontSize": "14px"},
        },
    },
}

# ── Shared inline style helpers ────────────────────────────────────────────────
def card_style(padding="16px", radius="12px"):
    return {
        "background": COLORS["bg_secondary"],
        "border": f"1px solid {COLORS['border']}",
        "borderRadius": radius,
        "padding": padding,
    }

def metric_card_style():
    return {
        "background": COLORS["bg_tertiary"],
        "borderRadius": "8px",
        "padding": "12px 16px",
    }

# Modality color lookup
MOD_COLORS = {
    "drug": COLORS["mod_drug"],
    "adc": COLORS["mod_adc"],
    "protac": COLORS["mod_protac"],
    "glue": COLORS["mod_glue"],
    "rlt": COLORS["mod_rlt"],
}

# Pathway V6 cluster-island palette.
CLUSTER_COLORS = {
    "RTK": COLORS["cluster_rtk"],
    "RAS_MAPK": COLORS["cluster_ras_mapk"],
    "PI3K_AKT": COLORS["cluster_pi3k_akt"],
    "APOPTOSIS": COLORS["cluster_apoptosis"],
    "CELL_CYCLE": COLORS["cluster_cell_cycle"],
    "TF": COLORS["cluster_tf"],
}

SEED_COLOR = COLORS["node_seed"]
CHAMPION_BADGE = "⭐"
RWR_TOP10_BADGE = "🟢"
