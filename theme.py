"""
Palette et styles partagés par l'application.
Centralisé ici pour que planning_app et planning_stats
utilisent exactement les mêmes couleurs.
"""
import html
import streamlit as st

# ============================================================
# PALETTE COLLABORATEURS
# Pastilles claires sur fond sombre : le texte reste très
# foncé pour garder le contraste à l'intérieur de la cellule.
# ============================================================
PALETTE = [
    {"bg": "#B5D4F4", "fg": "#042C53", "dim": "#185FA5", "dot": "#378ADD"},
    {"bg": "#9FE1CB", "fg": "#04342C", "dim": "#0F6E56", "dot": "#1D9E75"},
    {"bg": "#F5C4B3", "fg": "#4A1B0C", "dim": "#993C1D", "dot": "#D85A30"},
    {"bg": "#CECBF6", "fg": "#26215C", "dim": "#534AB7", "dot": "#7F77DD"},
    {"bg": "#F4C0D1", "fg": "#4B1528", "dim": "#993556", "dot": "#D4537E"},
    {"bg": "#FAC775", "fg": "#412402", "dim": "#854F0B", "dot": "#BA7517"},
    {"bg": "#C0DD97", "fg": "#173404", "dim": "#3B6D11", "dot": "#639922"},
    {"bg": "#D3D1C7", "fg": "#2C2C2A", "dim": "#5F5E5A", "dot": "#888780"},
]

# ============================================================
# NEUTRES (thème sombre)
# ============================================================
SURFACE = "#1E2126"      # conteneur / carte de fond
CARD = "#262A31"         # carte posée sur la surface
BORDER = "#343941"
TEXT = "#E8E6E0"
TEXT_SOFT = "#A8A59D"
TEXT_MUTED = "#75736D"

# Couleurs de statut
DANGER_BG = "#2E1A1A"
DANGER_FG = "#F09595"
DANGER_LINE = "#A32D2D"
OK_BG = "#9FE1CB"
OK_FG = "#04342C"
WARN_BG = "#FAC775"
WARN_FG = "#412402"
NEUTRAL_BG = "#343941"
NEUTRAL_FG = "#A8A59D"


def user_theme(users: dict) -> dict:
    """Associe une entrée de palette à chaque collaborateur."""
    return {
        email: PALETTE[i % len(PALETTE)]
        for i, email in enumerate(sorted(users))
    }


def esc(value) -> str:
    """Échappe une valeur avant injection dans du HTML."""
    return html.escape(str(value if value is not None else ""))


def rate_color(pct: float) -> str:
    """Couleur de la barre de taux selon le niveau d'atteinte."""
    if pct >= 85:
        return "#97C459"
    if pct >= 60:
        return "#EF9F27"
    return "#F09595"


def gap_color(gap: int) -> str:
    """Couleur d'un écart d'heures."""
    if gap < 0:
        return "#F09595"
    if gap > 0:
        return "#97C459"
    return TEXT_SOFT


def inject_css() -> None:
    """Styles globaux de l'application."""
    st.markdown(
        f"""
<style>
:root {{
  --pl-surface: {SURFACE};
  --pl-card: {CARD};
  --pl-border: {BORDER};
  --pl-text: {TEXT};
  --pl-soft: {TEXT_SOFT};
  --pl-muted: {TEXT_MUTED};
}}

.block-container {{padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1180px;}}
#MainMenu, footer {{visibility: hidden;}}

h1, h2, h3 {{font-weight: 500; letter-spacing: -0.01em;}}

.stTabs [data-baseweb="tab-list"] {{
  gap: 2px; background: var(--pl-surface); padding: 4px;
  border-radius: 10px; border: none;
}}
.stTabs [data-baseweb="tab"] {{
  height: 36px; padding: 0 14px; border-radius: 7px;
  font-size: 14px; color: var(--pl-soft); background: transparent;
}}
.stTabs [aria-selected="true"] {{
  background: var(--pl-card); color: var(--pl-text);
}}
.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] {{display: none;}}

.stButton button {{
  border-radius: 8px; font-size: 14px; font-weight: 400;
  border: 1px solid var(--pl-border); transition: all .12s ease;
}}
.stButton button:hover {{border-color: #4A5058; background: var(--pl-card);}}

div[data-testid="stSelectbox"] label,
div[data-testid="stNumberInput"] label,
div[data-testid="stTextInput"] label {{
  font-size: 13px; color: var(--pl-soft); font-weight: 400;
}}

hr {{margin: 1.4rem 0; border-color: var(--pl-border);}}

.pl-head {{
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 10px; margin-bottom: 14px;
}}
.pl-title {{font-size: 19px; font-weight: 500; color: var(--pl-text);}}
.pl-badge {{
  font-size: 12px; padding: 3px 11px; border-radius: 20px;
  display: inline-block; vertical-align: 2px; margin-left: 9px;
}}
.pl-grid {{display: grid; grid-template-columns: repeat(7, 1fr); gap: 5px;}}
.pl-dow {{
  font-size: 11px; color: var(--pl-muted); text-align: center;
  padding-bottom: 5px; letter-spacing: .03em;
}}
.pl-cell {{border-radius: 8px; padding: 8px 7px; min-height: 56px;}}
.pl-num {{font-size: 12px; line-height: 1.2;}}
.pl-name {{font-size: 11px; margin-top: 3px; line-height: 1.25;}}
.pl-off {{min-height: 56px; padding: 8px 7px;}}
.pl-off .pl-num {{color: #40444B;}}
.pl-legend {{display: flex; gap: 7px; flex-wrap: wrap; margin-top: 14px;}}
.pl-chip {{font-size: 11px; padding: 3px 11px; border-radius: 20px;}}
.pl-stats {{
  display: flex; gap: 26px; margin-top: 14px;
  padding-top: 13px; border-top: 1px solid var(--pl-border);
}}
.pl-stat-l {{font-size: 11px; color: var(--pl-muted);}}
.pl-stat-v {{font-size: 17px; color: var(--pl-text); margin-top: 1px;}}
.pl-wrap {{background: var(--pl-surface); border-radius: 12px; padding: 18px 20px;}}
.pl-cards {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 10px; margin-bottom: 18px;
}}
.pl-card {{background: var(--pl-surface); border-radius: 9px; padding: 13px 15px;}}
.pl-card-l {{font-size: 12px; color: var(--pl-muted);}}
.pl-card-v {{
  font-size: 23px; font-weight: 500; margin-top: 2px;
  line-height: 1.15; color: var(--pl-text);
}}
.pl-card-s {{font-size: 11px; color: var(--pl-muted); margin-top: 1px;}}
.pl-tbl {{
  background: var(--pl-surface); border: 1px solid var(--pl-border);
  border-radius: 11px; overflow: hidden;
}}
.pl-tr {{
  display: grid; grid-template-columns: 1.6fr .8fr .8fr .8fr .7fr .7fr 1.5fr;
  gap: 8px; padding: 11px 15px; align-items: center;
  font-size: 13px; color: var(--pl-text);
}}
.pl-th {{
  font-size: 11px; color: var(--pl-muted);
  border-bottom: 1px solid var(--pl-border);
  padding: 10px 15px; letter-spacing: .02em;
}}
.pl-tr + .pl-tr {{border-top: 1px solid #2B2F36;}}
.pl-dot {{
  width: 8px; height: 8px; border-radius: 50%;
  display: inline-block; margin-right: 8px; vertical-align: 1px;
}}
.pl-bar {{
  height: 6px; border-radius: 4px; background: #343941;
  overflow: hidden; flex: 1;
}}
.pl-bar span {{display: block; height: 100%;}}
</style>
""",
        unsafe_allow_html=True,
    )