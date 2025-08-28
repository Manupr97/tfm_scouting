# pages/2_📊_Visualizaciones.py
from __future__ import annotations
import os, re, sys, glob
import json
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import matplotlib.pyplot as plt
from mplsoccer import Radar, grid
import io
import matplotlib as mpl
from datetime import datetime
import matplotlib.patheffects as pe
from matplotlib.patches import Patch

# === Tema oscuro global para Matplotlib ===
BG     = "#0f1116"   # fondo app
RING   = "#2b3145"   # anillos
INK    = "#e9edf1"   # texto
MUTED  = "#9aa4b2"   # texto secundario
PALETTE = ["#06b6d4", "#e11d48", "#22c55e", "#f59e0b", "#a855f7"]  # cian vs magenta → alto contraste
FILL_ALPHA_SINGLE = 0.55
FILL_ALPHA_MULTI  = 0.48
EDGE_WIDTH_SINGLE = 3.0
EDGE_WIDTH_MULTI  = 3.0

mpl.rcParams.update({
    "figure.facecolor": BG,
    "axes.facecolor": BG,
    "savefig.facecolor": BG,
    "savefig.edgecolor": BG,
    "text.color": INK,
    "axes.labelcolor": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.edgecolor": BG,
    "figure.edgecolor": BG,
    "axes.linewidth": 0,
    "patch.linewidth": 0,
})
plt.style.use('dark_background')
# ===== Config =====
st.set_page_config(page_title="Visualizaciones", page_icon="📊", layout="wide", initial_sidebar_state="collapsed")

# ===== Estilos discretos =====
st.markdown("""
<style>
:root{ --bg:#0f1116; --card:#12151d; --ink:#e9edf1; --muted:#9aa4b2; --stroke:#232838; --brand:#1f7aec; }
.stApp{ background:var(--bg); color:var(--ink); }
.block-container{ padding-top: 1rem; }
.card{ background:var(--card); border:1px solid var(--stroke); border-radius:14px; padding:16px; }
.kpi{ background:#121922; border:1px solid var(--stroke); border-radius:14px; padding:14px; }
hr{ border:none; border-top:1px solid var(--stroke); margin: 8px 0 16px; }
</style>
""", unsafe_allow_html=True)

# ===== Guardarraíl de login como en 1_Catálogo =====
if "logged_in" not in st.session_state or not st.session_state.logged_in:
    st.warning("Debes iniciar sesión para acceder a las visualizaciones.")
    st.stop()

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# ===== Utilidades =====
def nice_label(name: str) -> str:
    s = str(name).replace("_", " ").replace("/", " / ").strip()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("%", "% ").replace(" ,", ",").replace(" .", ".")
    return s.capitalize()

def guess_columns(df: pd.DataFrame) -> dict:
    cols = [c.lower() for c in df.columns]
    m = dict(zip([c.lower() for c in df.columns], df.columns))

    def pick(options):
        for o in options:
            if o in m: return m[o]
        # fuzzy
        for o in options:
            for c in cols:
                if o in c: return m[c]
        return None

    return {
        "player":   pick(["jugador","player","nombre"]),
        "team":     pick(["equipo_durante_el_período_seleccionado","equipo","team"]),
        "position": pick(["pos_principal","posicion","posición","position"]),
        "age":      pick(["edad","age"]),
        "minutes":  pick(["min","minutos","minutes"]),
        "matches":  pick(["partidos_jugados","partidos","matches"]),
        "competition": "competicion" if "competicion" in df.columns else None
    }

@st.cache_data(show_spinner=False)
def load_all_excels(data_dir: str) -> tuple[pd.DataFrame, dict, dict]:
    # coge cualquier Excel tipo wyscout_*limp*.xlsx
    files = sorted(glob.glob(os.path.join(data_dir, "wyscout_*limp*.xlsx")))
    frames = []
    for path in files:
        try:
            df = pd.read_excel(path)
            df = df.copy()
            comp = os.path.splitext(os.path.basename(path))[0]
            df["competicion"] = comp
            frames.append(df)
        except Exception:
            pass
    if not frames:
        return pd.DataFrame(), {}, {}

    df = pd.concat(frames, ignore_index=True)

    from pandas.api.types import is_numeric_dtype
    # intenta convertir numéricos en columnas object
    def maybe_to_numeric(s: pd.Series) -> pd.Series:
        try:
            return pd.to_numeric(s)  # intenta directo
        except Exception:
            s_num = pd.to_numeric(s, errors="coerce")
            return s_num if s_num.notna().sum() > 0 else s

    for c in df.columns:
        if df[c].dtype == "object":
            df[c] = df[c].replace(["-", "", "N/A", "nan", "null"], np.nan)
            conv = maybe_to_numeric(df[c])
            if is_numeric_dtype(conv):
                df[c] = conv

        detected = guess_columns(df)

    # resumen
    summary = {}
    if detected.get("team"):     summary["equipos"] = df[detected["team"]].nunique()
    if detected.get("position"): summary["posiciones"] = df[detected["position"]].nunique()
    if detected.get("age"):      summary["edad_media"] = float(df[detected["age"]].mean())
    summary["jugadores"] = len(df)
    return df, detected, summary

df, C, S = load_all_excels(DATA_DIR)
if df.empty:
    st.error("No he encontrado Excels limpios en /data (patrón: wyscout_*limp*.xlsx). Súbelos o cambia el loader.")
    st.stop()

def num_cols(df_: pd.DataFrame) -> list[str]:
    return [c for c in df_.columns if str(df_[c].dtype) in ("float64","int64") and df_[c].notna().sum() > 0]

def fmt(x):
    if pd.isna(x): return "N/A"
    try:
        x = float(x)
        if x.is_integer() and abs(x) < 10000: return f"{int(x)}"
        if abs(x) < 1: return f"{x:.3f}"
        return f"{x:.1f}"
    except Exception:
        return str(x)

def available_metrics(df_: pd.DataFrame, candidates: list[str]) -> list[str]:
    # devuelve solo las que existan y sean numéricas
    nc = set(num_cols(df_))
    out = []
    for m in candidates:
        # prueba exacto y búsqueda laxa
        if m in nc:
            out.append(m); continue
        hits = [c for c in nc if m.lower() in c.lower()]
        if hits: out.append(hits[0])
    # máximo 8 para radar
    return out[:8]

def percentile(col: pd.Series, value) -> float:
    s = col.dropna().astype(float)
    if len(s) < 2 or pd.isna(value): return 0.0
    return float((s <= float(value)).mean() * 100)

# ===== Catálogo de métricas por bloques (ajústalo a tus columnas) =====
CATS = {
  "Rendimiento Ofensivo":  ["goles/90","goles","xg/90","remates/90","%tiros","xa/90","toques_area/90","goles_ex_pen"],
  "Creatividad y Pases":   ["pases/90","%precisión_pases","pases_largos/90","pases_progre/90","pases_área/90","claves/90","en_profundidad/90"],
  "Duelos y Defensa":      ["duelos/90","%duelos_ganados","duelos_def/90","%duelos_def_ganados","aéreos/90","%aéreos_ganados","intercep/90","entradas/90"],
  "Movilidad y Técnica":   ["regates/90","%regates","carreras_progresión/90","aceleraciones/90","faltas_recibidas/90","desmarques/90"],
  "Porteros":              ["goles_recibidos/90","%paradas","xg_en_contra/90","goles_evitados/90","salidas/90"]
}

# ===== Header + KPIs =====
st.markdown(f"""
<div class="card" style="padding:20px; margin-bottom:12px">
  <h1 style="margin:0">📊 Visualizaciones</h1>
  <div style="color:#9aa4b2">Dataset combinado de {len(df):,} registros</div>
</div>
""", unsafe_allow_html=True)

k1,k2,k3,k4 = st.columns(4)
with k1: st.markdown(f"<div class='kpi'><b>👥 Jugadores</b><br>{S.get('jugadores',0):,}</div>", unsafe_allow_html=True)
with k2: st.markdown(f"<div class='kpi'><b>🏟️ Equipos</b><br>{S.get('equipos','N/A')}</div>", unsafe_allow_html=True)
with k3: st.markdown(f"<div class='kpi'><b>⚽ Posiciones</b><br>{S.get('posiciones','N/A')}</div>", unsafe_allow_html=True)
with k4: st.markdown(f"<div class='kpi'><b>📈 Edad media</b><br>{fmt(S.get('edad_media'))} años</div>", unsafe_allow_html=True)

# ===== Selector de modo (fuera del sidebar) =====
mode = st.radio("Tipo de análisis", ["🎯 Radar individual","👥 Comparación","📈 Dispersión","🏟️ Por equipo","🔥 Correlaciones"],
                horizontal=True, label_visibility="collapsed", key="viz_mode_main")

# ===== Filtros globales =====
with st.expander("🎛️ Filtros", expanded=False):
    c1,c2,c3,c4 = st.columns([2,2,2,2])
    q = ""
    teams_sel = pos_sel = None
    age_rng = None
    if C.get("player"):
        with c1: q = st.text_input("Buscar jugador", "")
    if C.get("team"):
        with c2:
            opts = sorted(df[C["team"]].dropna().unique().tolist())
            teams_sel = st.multiselect("Equipos", opts)
    if C.get("position"):
        with c3:
            opts = sorted(df[C["position"]].dropna().unique().tolist())
            pos_sel = st.multiselect("Posiciones", opts)
    if C.get("age"):
        with c4:
            amin, amax = int(df[C["age"]].min()), int(df[C["age"]].max())
            age_rng = st.slider("Edad", amin, amax, (amin, amax))
    c5,c6 = st.columns(2)
    with c5:
        min_min = st.number_input("Minutos mínimos", min_value=0, step=100, value=0)
    with c6:
        min_match = st.number_input("Partidos mínimos", min_value=0, step=1, value=0)
    c7, = st.columns(1)
    with c7:
        if "competicion" in df.columns:
            all_comp = sorted(df["competicion"].dropna().unique().tolist())
            ds_sel = st.multiselect("Dataset / competición", all_comp, default=all_comp, key="ds_sel_viz")
        else:
            ds_sel = None

def apply_filters(df_: pd.DataFrame) -> pd.DataFrame:
    out = df_.copy()
    if q and C.get("player"): out = out[out[C["player"]].astype(str).str.contains(q, case=False, na=False)]
    if teams_sel and C.get("team"): out = out[out[C["team"]].isin(teams_sel)]
    if pos_sel and C.get("position"): out = out[out[C["position"]].isin(pos_sel)]
    if age_rng and C.get("age"): out = out[(out[C["age"]]>=age_rng[0])&(out[C["age"]]<=age_rng[1])]
    if C.get("minutes") and min_min>0: out = out[out[C["minutes"]]>=min_min]
    if C.get("matches") and min_match>0: out = out[out[C["matches"]]>=min_match]
    if ds_sel:
        out = out[out["competicion"].isin(ds_sel)]
    return out

df_f = apply_filters(df)

# ===== Helpers radar =====
def _extract_vertices(out):
    """Devuelve array Nx2 de vértices o None. Soporta Polygon, PolyCollection, ndarray y tuplas varias."""
    items = list(out) if isinstance(out, (list, tuple)) else [out]

    # 1) si viene un ndarray con vértices
    for obj in items:
        if hasattr(obj, "ndim") and getattr(obj, "ndim", 0) == 2 and getattr(obj, "shape", (0,0))[1] == 2:
            return np.asarray(obj)

    # 2) patches.Polygon -> get_xy()
    for obj in items:
        if hasattr(obj, "get_xy"):
            try:
                v = np.asarray(obj.get_xy())
                if v.ndim == 2 and v.shape[1] == 2:
                    return v
            except Exception:
                pass

    # 3) collections.PolyCollection -> get_paths()[0].vertices
    for obj in items:
        if hasattr(obj, "get_paths"):
            try:
                paths = obj.get_paths()
                if paths:
                    v = np.asarray(paths[0].vertices)
                    if v.ndim == 2 and v.shape[1] == 2:
                        return v
            except Exception:
                pass
    return None

def _radar_labels(labels):
    out=[]
    for l in labels:
        s = str(l).replace("_"," ").replace("/", " / ").strip().title()
        if len(s) > 18:
            w = s.split(); mid = len(w)//2
            s = "\n".join([" ".join(w[:mid]), " ".join(w[mid:])])
        out.append(s)
    return out

def _grid_safe(figheight=8.5,
               grid_height=0.84, title_height=0.08, endnote_height=0.05,
               title_space=0.015, endnote_space=0.015, bottom=0.02):
    total = grid_height + title_height + endnote_height + title_space + endnote_space + bottom
    if total > 0.99:
        k = 0.99 / total
        grid_height *= k; title_height *= k; endnote_height *= k
        title_space *= k; endnote_space *= k
    try:
        fig, axs = grid(figheight=figheight, grid_height=grid_height,
                        title_height=title_height, endnote_height=endnote_height,
                        title_space=title_space, endnote_space=endnote_space,
                        bottom=bottom, grid_key='radar', axis=False)
    except TypeError:
        fig, axs = grid(figheight=figheight, grid_height=grid_height,
                        title_height=title_height, endnote_height=endnote_height,
                        title_space=title_space, endnote_space=endnote_space,
                        grid_key='radar', axis=False)

    # TODO: clave anti-sábana blanca -> todo transparente
    fig.patch.set_facecolor('none'); fig.patch.set_alpha(0)
    for k in axs:
        axs[k].set_facecolor('none')
        axs[k].patch.set_alpha(0)
    return fig, axs

def draw_radar_single(values, labels, title, subtitle, scale: float = 1.0):
    labels = _radar_labels(labels)
    low = [0]*len(labels); high=[100]*len(labels)
    rad = Radar(labels, low, high, num_rings=4,
                ring_width=max(0.6, 1*scale), center_circle_radius=1)

    fig, axs = _grid_safe(figheight=9.2*scale,
                          grid_height=0.84, title_height=0.08*scale, endnote_height=0.05*scale,
                          title_space=0.012*scale, endnote_space=0.012*scale, bottom=0.015*scale)
    rad.setup_axis(ax=axs["radar"])
    rad.draw_circles(ax=axs["radar"], facecolor="none", edgecolor=RING, linewidth=1.2*scale)

    # --- llamada compatible con cualquier versión ---
    out = rad.draw_radar(
        values, ax=axs["radar"],
        kwargs_radar={
            "facecolor": PALETTE[0],
            "alpha": FILL_ALPHA_SINGLE,
            "edgecolor": PALETTE[0],
            "linewidth": EDGE_WIDTH_SINGLE*scale
        }
    )
    poly = out[0] if isinstance(out, (list, tuple)) else out
    # halo para delimitar bien el perímetro
    poly.set_path_effects([
        pe.Stroke(linewidth=EDGE_WIDTH_SINGLE*scale + 2, foreground="#0b0e14"),
        pe.Normal()
    ])
    # -----------------------------------------------

    rad.draw_range_labels(ax=axs["radar"], fontsize=max(8, int(10*scale)), color="#ffffff")
    rad.draw_param_labels(ax=axs["radar"], fontsize=max(9, int(11*scale)), color=INK)

    axs["title"].text(.5,.66, title, ha="center", va="center",
                      fontsize=max(16, int(20*scale)), weight="bold", color=INK)
    axs["title"].text(.5,.25, subtitle, ha="center", va="center",
                      fontsize=max(10, int(12*scale)), color=MUTED)
    axs["endnote"].text(.5,.5, "Valores en percentil", ha="center", va="center",
                        fontsize=max(8, int(9*scale)), color=MUTED)
    return fig

def draw_radar_multi(values_by_player: dict[str, list[float]],
                     labels,
                     players_info: dict[str, str] | None = None,
                     scale: float = 1.0):
    labels = _radar_labels(labels)
    low = [0]*len(labels); high=[100]*len(labels)
    rad = Radar(labels, low, high, num_rings=4,
                ring_width=max(0.6, 1*scale), center_circle_radius=1)

    fig, axs = _grid_safe(figheight=9.2*scale,
                          grid_height=0.84, title_height=0.10*scale, endnote_height=0.07*scale,
                          title_space=0.010*scale, endnote_space=0.010*scale, bottom=0.015*scale)
    rad.setup_axis(ax=axs["radar"])
    rad.draw_circles(ax=axs["radar"], facecolor="none", edgecolor=RING, linewidth=1.2*scale)

    names = list(values_by_player.keys())
    verts = []
    for i, name in enumerate(names):
        color = PALETTE[i % len(PALETTE)]
        out = rad.draw_radar(
            values_by_player[name], ax=axs["radar"],
            kwargs_radar={
                "facecolor": color,
                "alpha": FILL_ALPHA_MULTI,
                "edgecolor": color,
                "linewidth": EDGE_WIDTH_MULTI*scale
            }
        )
        # halo al borde para separar figuras
        poly = out[0] if isinstance(out, (list, tuple)) else out
        if hasattr(poly, "set_path_effects"):
            poly.set_path_effects([
                pe.Stroke(linewidth=EDGE_WIDTH_MULTI*scale + 2, foreground="#0b0e14"),
                pe.Normal()
            ])
        v = _extract_vertices(out)
        if v is not None:
            verts.append(v)

    # puntos en vértices solo si los tenemos
    for i, v in enumerate(verts):
        axs["radar"].scatter(v[:, 0], v[:, 1],
                             s=30*scale, c=PALETTE[i % len(PALETTE)],
                             edgecolors="#0b0e14", linewidths=1.0, zorder=5)


    rad.draw_range_labels(ax=axs["radar"], fontsize=max(8, int(10*scale)), color="#ffffff")
    rad.draw_param_labels(ax=axs["radar"], fontsize=max(9, int(11*scale)), color=INK)

    # título abajo
    axs["endnote"].text(.5, .5, "Comparación en percentiles", ha="center", va="center",
                        fontsize=max(12, int(14*scale)), color=INK)

    # textos arriba izq/der con color del jugador (sin cajas)
    if players_info and len(names) >= 1:
        left_name = names[0]; left_color = PALETTE[0]
        left_info = players_info.get(left_name, "")
        axs["title"].text(0.01, 0.98, left_name, ha="left", va="top",
                          fontsize=max(13, int(15*scale)), color=left_color, weight="bold")
        axs["title"].text(0.01, 0.72, left_info, ha="left", va="top",
                          fontsize=max(9, int(11*scale)), color=left_color)
    if players_info and len(names) >= 2:
        right_name = names[1]; right_color = PALETTE[1]
        right_info = players_info.get(right_name, "")
        axs["title"].text(0.99, 0.98, right_name, ha="right", va="top",
                          fontsize=max(13, int(15*scale)), color=right_color, weight="bold")
        axs["title"].text(0.99, 0.72, right_info, ha="right", va="top",
                          fontsize=max(9, int(11*scale)), color=right_color)

    return fig

def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")

def fig_to_png_bytes(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(
        buf, format="png", bbox_inches="tight", dpi=200,
        transparent=True   # se mantiene el fondo transparente
    )
    return buf.getvalue()

def show_fig_with_download(fig, filename_base: str, display_width: int = 640):
    png = fig_to_png_bytes(fig)
    st.image(png, width=display_width)  # <- fijo, no se estira a todo el contenedor
    st.download_button(
        "⬇️ Descargar imagen (PNG)",
        data=png,
        file_name=f"{_slug(filename_base)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
        mime="image/png",
        use_container_width=True
    )
    plt.close(fig)

# ===== Renderers =====
def render_radar():
    st.subheader("🎯 Radar individual")
    if not C.get("player"):
        st.info("No encuentro columna de jugador en el dataset.")
        return

    players = sorted(df_f[C["player"]].dropna().unique().tolist())
    if not players:
        st.info("Sin jugadores con los filtros actuales.")
        return
    p = st.selectbox("Jugador", players, key="radar_player")

    # categoría y pool de métricas válidas
    cat = st.selectbox("Categoría", list(CATS.keys()), key="radar_cat")
    pool = available_metrics(df_f, CATS[cat])
    if len(pool) < 3:
        st.warning("No hay suficientes métricas numéricas para el radar.")
        return

    # selector de métricas (máx. 8), con etiquetas limpias
    label_map = {nice_label(m): m for m in pool}
    chosen_labels = st.multiselect(
        "Métricas (máx. 8)",
        list(label_map.keys()),
        default=list(label_map.keys())[:6],
        max_selections=8,
        key="radar_metrics",
    )
    metrics = [label_map[k] for k in chosen_labels] if chosen_labels else pool[:6]

    # fila jugador y percentiles [0,100]
    row = df_f.loc[df_f[C["player"]] == p].iloc[0]
    vals = []
    for m in metrics:
        v = row.get(m, np.nan)
        pct = percentile(df_f[m], v) if pd.notna(v) else 0.0
        vals.append(float(min(100.0, max(0.0, pct))))

    subtitle = " | ".join([
        str(row.get(C.get("team"), "N/A")),
        str(row.get(C.get("position"), "N/A")),
        f"{fmt(row.get(C.get('age')))} años"
    ])

    fig = draw_radar_single(vals, metrics, str(row.get(C["player"])), subtitle, scale=1.0)
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        show_fig_with_download(fig, f"radar_{row.get(C['player'])}_{cat}", display_width=860)


    table = pd.DataFrame({
        "Métrica": [nice_label(m) for m in metrics],
        "Valor":   [fmt(row.get(m)) for m in metrics],
        "Percentil": [f"{int(v)}%" for v in vals],
    })
    st.dataframe(table, hide_index=True, use_container_width=True)

def render_comp():
    st.subheader("👥 Comparación")
    if not C.get("player"): 
        st.info("No hay columna de jugador."); 
        return

    players = sorted(df_f[C["player"]].dropna().unique().tolist())
    sel_players = st.multiselect("Jugadores", players, max_selections=5)
    if len(sel_players) < 2:
        st.info("Selecciona al menos 2 jugadores.")
        return

    cat = st.selectbox("Categoría", list(CATS.keys()))
    metrics = available_metrics(df_f, CATS[cat])
    if not metrics:
        st.warning("No hay métricas válidas en esta categoría.")
        return

    vista = st.radio("Vista", ["Barras","Radar"], horizontal=True)

    # percentiles por jugador-métrica
    rows=[]
    for p in sel_players:
        row = df_f[df_f[C["player"]]==p].iloc[0]
        for m in metrics:
            v = row.get(m, np.nan)
            rows.append({"Jugador": p, "Métrica": m, "Percentil": percentile(df_f[m], v) if pd.notna(v) else np.nan})
    dat = pd.DataFrame(rows)

    if vista == "Barras":
        dat["Métrica"] = dat["Métrica"].apply(lambda s: s.replace("_"," ").title())
        fig = px.bar(dat, x="Métrica", y="Percentil", color="Jugador", barmode="group", title="Comparación (percentiles)")
        fig.update_yaxes(range=[0,100])
        st.plotly_chart(fig, use_container_width=True)

    elif vista == "Radar":
        if len(sel_players) != 2:
            st.warning("Para el radar comparativo usa exactamente 2 jugadores (izquierda y derecha).")
            return

        ordered_metrics = sorted(dat["Métrica"].unique().tolist())

        # matriz de percentiles y la info para los textos
        mat = {}
        info_map = {}
        for p in sel_players:
            r = df_f[df_f[C["player"]]==p].iloc[0]
            vals = [dat[(dat["Jugador"]==p)&(dat["Métrica"]==m)]["Percentil"].values[0]
                    for m in ordered_metrics]
            mat[p] = [0 if pd.isna(x) else float(x) for x in vals]
            info_map[p] = " | ".join([
                str(r.get(C.get("team"), "N/A")),
                str(r.get(C.get("position"), "N/A")),
                f"{fmt(r.get(C.get('age')))} años"
            ])

        fig = draw_radar_multi(mat, ordered_metrics, players_info=info_map, scale=1.0)

        c1, c2, c3 = st.columns([1,2,1])
        with c2:
            show_fig_with_download(fig, f"radar_comparacion_{'_'.join(sel_players)}", display_width=860)

        # ===== Tablas comparativas debajo =====
        pvt = dat.copy()
        pvt["Métrica"] = pvt["Métrica"].apply(nice_label)

        # Percentiles (sin applymap -> sin warning)
        pvt_perc = pvt.pivot(index="Métrica", columns="Jugador", values="Percentil").round(0)
        pvt_disp = pvt_perc.apply(lambda s: s.map(lambda v: f"{int(v)}%" if pd.notna(v) else "N/A"))
        st.markdown("#### Percentiles")
        st.dataframe(pvt_disp, use_container_width=True)

        # Valores brutos
        rows = []
        for m in ordered_metrics:
            row_vals = {"Métrica": nice_label(m)}
            for p in sel_players:
                try:
                    rv = df_f.loc[df_f[C["player"]]==p, m].iloc[0]
                except Exception:
                    rv = np.nan
                row_vals[p] = fmt(rv)
            rows.append(row_vals)
        raw_df = pd.DataFrame(rows).set_index("Métrica")
        st.markdown("#### Valores brutos")
        st.dataframe(raw_df, use_container_width=True)

def render_scatter():
    st.subheader("📈 Dispersión")

    numeric = num_cols(df_f)
    if len(numeric) < 2:
        st.info("No hay suficientes métricas numéricas.")
        return

    # Mapeo "etiqueta bonita" -> columna
    dnames = {nice_label(c): c for c in numeric}
    pretty_sorted = sorted(dnames.keys())

    c1, c2 = st.columns(2)
    with c1:
        x_name = st.selectbox("Métrica X", pretty_sorted, key="sc_x")
        x = dnames[x_name]
        xr = df_f[x].dropna()
        x_rng = st.slider(f"Rango {x_name}", float(xr.min()), float(xr.max()),
                          (float(xr.min()), float(xr.max())))
    with c2:
        y_name = st.selectbox("Métrica Y", [k for k in pretty_sorted if k != x_name], key="sc_y")
        y = dnames[y_name]
        yr = df_f[y].dropna()
        y_rng = st.slider(f"Rango {y_name}", float(yr.min()), float(yr.max()),
                          (float(yr.min()), float(yr.max())))

    # Extras de visualización
    c3, c4, c5 = st.columns([2,2,1])
    with c3:
        size_by_label = st.selectbox("Tamaño por", ["(ninguno)"] + pretty_sorted, index=0, key="sc_size")
        size_by = dnames.get(size_by_label)
        size_max = st.slider("Tamaño máx. burbuja", 8, 40, 26) if size_by else 26
    with c4:
        color_by_label = st.selectbox("Color por", ["(ninguno)"] + pretty_sorted, index=0, key="sc_color")
        color_by = dnames.get(color_by_label)
    with c5:
        opacity = st.slider("Opacidad", 0.2, 1.0, 0.9)

    show_trend  = st.checkbox("Línea de tendencia", value=True)
    show_avg    = st.checkbox("Líneas promedio", value=True)
    show_labels = st.checkbox("Mostrar nombres bajo las burbujas", value=False)

    # Aplicar rangos
    d = df_f[(df_f[x].between(*x_rng)) & (df_f[y].between(*y_rng))].copy()

    # Construir kwargs de forma segura
    common_kwargs = dict(
        x=x, y=y,
        hover_data=[c for c in [C.get("player"), C.get("team"), C.get("position")] if c and c in d],
        labels={x: nice_label(x), y: nice_label(y)},
        trendline="ols" if show_trend else None,
    )
    if size_by:  common_kwargs["size"] = size_by
    if color_by: common_kwargs["color"] = color_by
    if color_by: common_kwargs["color_continuous_scale"] = "viridis"

    fig = px.scatter(d, **common_kwargs)
    fig.update_traces(marker=dict(line=dict(width=0), opacity=opacity))
    if not size_by:  # tamaño fijo cuando no haya métrica de tamaño
        fig.update_traces(marker=dict(size=10))

    # Etiquetas bajo los puntos
    if show_labels and C.get("player") in d:
        fig.update_traces(
            text=d[C["player"]],
            textposition="bottom center",
            textfont=dict(color="#e9edf1", size=10),
            mode="markers+text"
        )

    # Líneas promedio con colores visibles en oscuro
    if show_avg:
        xm, ym = float(d[x].mean()), float(d[y].mean())
        fig.add_vline(x=xm, line_dash="dash", line_width=1.6, line_color="#00c2a8", opacity=0.9)
        fig.add_hline(y=ym, line_dash="dash", line_width=1.6, line_color="#ffd166", opacity=0.9)

    # Tamaño y márgenes decentes
    fig.update_layout(
        height=720,
        margin=dict(l=60, r=30, t=40, b=60),
        plot_bgcolor="#11151c",
        paper_bgcolor="#11151c",
        legend_title_text=nice_label(color_by) if color_by else None,
    )
    st.plotly_chart(fig, use_container_width=True)

def render_team():
    st.subheader("🏟️ Por equipo")
    if not C.get("team"): st.info("No hay columna de equipo."); return
    numeric = num_cols(df_f)
    candidates = [c for c in numeric if any(k in c.lower() for k in ["gol","asist","pase","duel","xg","min","xa","regat","remat"])]
    if not candidates: st.info("No encuentro métricas útiles."); return
    m_name = st.selectbox("Métrica", sorted([nice_label(c) for c in candidates]))
    m_col = {nice_label(c):c for c in candidates}[m_name]
    agg = st.radio("Agregación", ["Promedio","Total","Mediana"], horizontal=True)
    if agg=="Promedio": s = df_f.groupby(C["team"])[m_col].mean()
    elif agg=="Total": s = df_f.groupby(C["team"])[m_col].sum()
    else: s = df_f.groupby(C["team"])[m_col].median()
    s = s.sort_values(ascending=False)
    fig = px.bar(x=s.values, y=s.index, orientation="h", color=s.values, color_continuous_scale="viridis",
                 title=f"{agg} de {nice_label(m_col)} por equipo")
    fig.update_layout(height=max(450, 24*len(s)), showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

def render_corr():
    st.subheader("🔥 Correlaciones")
    cat = st.selectbox("Categoría", list(CATS.keys()))
    metrics = available_metrics(df_f, CATS[cat])
    if len(metrics) < 3: st.info("Se necesitan al menos 3 métricas."); return
    cm = df_f[metrics].corr()
    cm.index = [nice_label(c) for c in cm.index]
    cm.columns = [nice_label(c) for c in cm.columns]
    fig = px.imshow(cm, color_continuous_scale="RdBu_r", zmin=-1, zmax=1, aspect="auto", title=f"Correlaciones · {cat}")
    fig.update_layout(height=620, xaxis=dict(tickangle=45))
    st.plotly_chart(fig, use_container_width=True)

def render_explorer():
    st.subheader("🔍 Explorador")
    base = [C.get("player"), C.get("team"), C.get("position"), C.get("age")]
    base = [c for c in base if c in df_f]
    # elige 4 métricas numéricas “populares”
    metrics = [c for c in num_cols(df_f) if any(k in c.lower() for k in ["gol","asist","xg","min","remat","xa"])]
    show = base + metrics[:4]
    if not show: st.info("No hay columnas para mostrar."); return
    st.dataframe(df_f[show].rename(columns={c:nice_label(c) for c in show}).head(30), use_container_width=True, hide_index=True)

# ===== Dispatcher =====
if mode == "🎯 Radar individual":   render_radar()
elif mode == "👥 Comparación":      render_comp()
elif mode == "📈 Dispersión":       render_scatter()
elif mode == "🏟️ Por equipo":      render_team()
elif mode == "🔥 Correlaciones":    render_corr()
else:                               render_explorer()
