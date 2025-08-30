# utils/styles.py
import streamlit as st
import os

# === PALETA DE COLORES DEL CLUB ===
COLORS = {
    "primary": "#FF6B35",      # Naranja principal
    "secondary": "#000000",    # Negro
    "background": "#0f1116",   # Fondo oscuro
    "card": "#12151d",         # Tarjetas
    "border": "#232838",       # Bordes
    "text": "#e9edf1",         # Texto principal
    "text_muted": "#9aa4b2",   # Texto secundario
    "success": "#22c55e",      # Verde éxito
    "warning": "#f59e0b",      # Amarillo advertencia
    "error": "#ef4444",        # Rojo error
}

def inject_global_styles():
    """Inyecta estilos globales consistentes en toda la app"""
    st.markdown(f"""
    <style>
    /* === VARIABLES CSS === */
    :root {{
        --primary: {COLORS["primary"]};
        --secondary: {COLORS["secondary"]};
        --bg: {COLORS["background"]};
        --card: {COLORS["card"]};
        --border: {COLORS["border"]};
        --text: {COLORS["text"]};
        --text-muted: {COLORS["text_muted"]};
        --success: {COLORS["success"]};
        --warning: {COLORS["warning"]};
        --error: {COLORS["error"]};
    }}
    
    /* === FONDO Y LAYOUT === */
    .stApp {{
        background: var(--bg);
        color: var(--text);
    }}
    
    .block-container {{
        padding-top: 2rem;
        max-width: 1200px;
    }}
    
    /* === COMPONENTES REUTILIZABLES === */
    .club-card {{
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 1rem;
        margin-bottom: 0.5rem;
        transition: all 0.2s ease;
    }}
    
    .club-card:hover {{
        border-color: var(--primary);
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(255, 107, 53, 0.15);
    }}
    
    .player-card {{
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 0.75rem;
        margin-bottom: 0.5rem;
    }}
    
    .stats-card {{
        background: linear-gradient(135deg, var(--card) 0%, #1a1f2e 100%);
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
    }}
    
    /* === BADGES Y ELEMENTOS === */
    .position-badge {{
        background: var(--primary);
        color: white;
        padding: 0.2rem 0.5rem;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: bold;
    }}
    
    .team-badge {{
        background: var(--secondary);
        color: var(--text);
        padding: 0.15rem 0.4rem;
        border-radius: 4px;
        font-size: 0.7rem;
        border: 1px solid var(--border);
    }}
    
    /* === MÉTRICAS Y KPI === */
    .kpi-container {{
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
    }}
    
    .kpi-value {{
        font-size: 1.8rem;
        font-weight: bold;
        color: var(--primary);
        margin: 0;
    }}
    
    .kpi-label {{
        font-size: 0.9rem;
        color: var(--text-muted);
        margin: 0;
    }}
    
    /* === SEPARADORES === */
    hr, .divider {{
        border: none;
        border-top: 1px solid var(--border);
        margin: 1rem 0;
    }}
    
    /* === BOTONES MEJORADOS === */
    .stButton > button {{
        border-radius: 8px;
        border: 1px solid var(--border);
        transition: all 0.2s ease;
    }}
    
    .stButton > button:hover {{
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(255, 107, 53, 0.2);
    }}
    
    /* === INPUTS Y SELECTS === */
    .stTextInput > div > div > input,
    .stSelectbox > div > div > div,
    .stTextArea > div > div > textarea {{
        background-color: var(--card) !important;
        border: 1px solid var(--border) !important;
        color: var(--text) !important;
    }}
    
    /* === TABS === */
    .stTabs [data-baseweb="tab-list"] {{
        background: var(--card);
        border-radius: 8px;
        padding: 0.25rem;
    }}
    
    .stTabs [data-baseweb="tab"] {{
        border-radius: 6px;
        color: var(--text-muted);
    }}
    
    .stTabs [aria-selected="true"] {{
        background: var(--primary) !important;
        color: white !important;
    }}
    
    /* === DATAFRAMES === */
    .stDataFrame {{
        border: 1px solid var(--border);
        border-radius: 8px;
        overflow: hidden;
    }}
    
    /* === SIDEBAR === */
    .css-1d391kg {{
        background: var(--card);
    }}
    
    /* === EXPANDIR === */
    .streamlit-expanderHeader {{
        background: var(--card);
        border-radius: 8px;
        border: 1px solid var(--border);
    }}
    </style>
    """, unsafe_allow_html=True)

def create_player_card(player_data: dict) -> str:
    """Genera HTML para tarjeta de jugador consistente"""
    name = player_data.get('name', 'Sin nombre')
    team = player_data.get('team', '-')
    position = player_data.get('position', '-')
    nationality = player_data.get('nationality', '-')
    age = player_data.get('age', '-')
    report_count = player_data.get('report_count', 0)
    
    return f"""
    <div class="player-card">
        <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 0.5rem;">
            <div>
                <div style="font-weight: 700; font-size: 1.1rem; margin-bottom: 0.2rem;">{name}</div>
                <div style="color: {COLORS['text_muted']}; font-size: 0.85rem;">
                    <span class="team-badge">{team}</span>
                    <span class="position-badge" style="margin-left: 0.5rem;">{position}</span>
                </div>
            </div>
            <div style="text-align: right; font-size: 0.8rem; color: {COLORS['text_muted']};">
                {nationality} • {age} años<br>
                {report_count} informes
            </div>
        </div>
    </div>
    """

def create_kpi_card(label: str, value: str, subtitle: str = "") -> str:
    """Genera HTML para KPI card consistente"""
    return f"""
    <div class="kpi-container">
        <p class="kpi-value">{value}</p>
        <p class="kpi-label">{label}</p>
        {f'<p style="font-size: 0.7rem; color: {COLORS["text_muted"]}; margin-top: 0.25rem;">{subtitle}</p>' if subtitle else ''}
    </div>
    """

def create_page_header(title: str, subtitle: str = "", show_logo: bool = True) -> None:
    """Header consistente con logo del club - versión centrada"""
    
    if show_logo:
        # Layout con más espacio para el logo
        col_logo, col_title, col_spacer = st.columns([1, 3, 1])
        
        with col_logo:
            # Centrar verticalmente el logo
            st.markdown('<div style="padding-top: 2rem; text-align: center;"></div>', unsafe_allow_html=True)
            logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "Escudo CAC.png")
            if os.path.exists(logo_path):
                st.image(logo_path, width=75)
        
        with col_title:
            st.markdown(f"""
            <div style="padding-top: 1.5rem; padding-left: 1rem;">
                <h1 style="color: var(--text); margin-bottom: 0.5rem; font-size: 2.2rem;">{title}</h1>
                {f'<p style="color: var(--text-muted); font-size: 1.05rem; margin: 0; font-weight: 300;">{subtitle}</p>' if subtitle else ''}
            </div>
            """, unsafe_allow_html=True)
        
        with col_spacer:
            pass  # Columna vacía para balance
    else:
        st.title(title)
        if subtitle:
            st.caption(subtitle)
    
    st.markdown('<div style="margin: 1.5rem 0;"><div class="divider"></div></div>', unsafe_allow_html=True)

def show_custom_spinner(text: str = "Cargando..."):
    """Spinner personalizado con estilo del club"""
    return st.markdown(f"""
    <div style="display: flex; align-items: center; justify-content: center; padding: 2rem;">
        <div style="
            border: 3px solid {COLORS['border']};
            border-top: 3px solid {COLORS['primary']};
            border-radius: 50%;
            width: 30px;
            height: 30px;
            animation: spin 1s linear infinite;
            margin-right: 1rem;
        "></div>
        <span style="color: {COLORS['text_muted']}; font-size: 0.9rem;">{text}</span>
    </div>
    
    <style>
    @keyframes spin {{
        0% {{ transform: rotate(0deg); }}
        100% {{ transform: rotate(360deg); }}
    }}
    </style>
    """, unsafe_allow_html=True)