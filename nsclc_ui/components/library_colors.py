"""
Library Mode — Color tokens & typography constants (dark theme only).

모든 Library 컴포넌트는 이 모듈의 상수만 사용한다.
하드코딩된 hex 값을 컴포넌트 파일에 직접 쓰지 않는다.
"""

# ── Background ────────────────────────────────────────────────────────────────
BG_PRIMARY = "#0F172A"
BG_SECONDARY = "#0B1220"
BG_CARD = "#1E293B"
BG_INPUT = "#1E293B"

# ── Border ────────────────────────────────────────────────────────────────────
BORDER_DEFAULT = "#334155"
BORDER_SUBTLE = "#1E293B"

# ── Text ──────────────────────────────────────────────────────────────────────
TEXT_PRIMARY = "#F1F5F9"
TEXT_SECONDARY = "#94A3B8"
TEXT_TERTIARY = "#64748B"
TEXT_MUTED = "#475569"

# ── Phase Chip (4종) ──────────────────────────────────────────────────────────
# phase: (background, foreground)
PHASE_COLORS: dict[str, tuple[str, str]] = {
    "A": ("#064E3B", "#6EE7B7"),   # 승인
    "B": ("#451A03", "#FBBF24"),   # 임상중
    "C": ("#1E1B4B", "#A78BFA"),   # 재창출
    "X": ("#1F2937", "#94A3B8"),   # 전임상
}

# Phase chip 라벨
PHASE_LABELS: dict[str, str] = {
    "A": "A 승인",
    "B": "B 임상중",
    "C": "C 재창출",
    "X": "X 전임상",
}

# ── Discovery Type Chip (4종) ─────────────────────────────────────────────────
# type: (background, foreground)
DISCOVERY_COLORS: dict[str, tuple[str, str]] = {
    "surprising": ("#1E1B4B", "#A78BFA"),       # violet
    "scaffold_novel": ("#042F2E", "#5EEAD4"),   # teal
    "target_rare": ("#431407", "#FB923C"),       # orange
    "repurpose_ready": ("#172554", "#60A5FA"),   # blue
}

# Discovery type 라벨
DISCOVERY_LABELS: dict[str, str] = {
    "surprising": "Surprising",
    "scaffold_novel": "Scaffold-novel",
    "target_rare": "Target-rare",
    "repurpose_ready": "Repurpose-ready",
}

# ── Cross-Source ──────────────────────────────────────────────────────────────
XS_FG = "#22D3EE"

# ── Accent (primary action) ───────────────────────────────────────────────────
ACCENT_CYAN = "#22D3EE"
ACCENT_CYAN_BG_SOFT = "rgba(34, 211, 238, 0.15)"
ACCENT_CYAN_BORDER_SOFT = "rgba(34, 211, 238, 0.4)"

# ── External Analyzer ─────────────────────────────────────────────────────────
EA_BORDER = "rgba(34, 211, 238, 0.4)"
EA_BUTTON_BG = "#22D3EE"
EA_BUTTON_FG = "#000000"

# ── Facet Filter ──────────────────────────────────────────────────────────────
FACET_COUNT_COLOR = "#22D3EE"
FACET_DIVIDER = "rgba(34, 211, 238, 0.3)"
FACET_LABEL_DISCOVERY = "#22D3EE"

# ── Warning ───────────────────────────────────────────────────────────────────
WARNING_BORDER = "#EAB308"

# ── Typography (px) ───────────────────────────────────────────────────────────
FONT_SIZE_MIN = 11
FONT_SIZE_CAPTION = 11
FONT_SIZE_BODY = 12
FONT_SIZE_HEADER = 13
FONT_SIZE_DRUG_NAME = 17
FONT_SIZE_FACET_COUNT = 22
FONT_SIZE_CARD_SCORE = 32
