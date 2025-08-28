# pages/2_Scouting_Partidos.py
from __future__ import annotations
import datetime as dt
import streamlit as st
import os

st.set_page_config(page_title="Scouting de Partidos", page_icon="⚽", layout="wide")

# Guardarraíl de login (mismo patrón que en tus otras páginas)
if "logged_in" not in st.session_state or not st.session_state.logged_in:
    st.warning("Debes iniciar sesión para acceder al scouting de partidos.")
    st.stop()

st.title("⚽ Scouting de partidos (BeSoccer)")

from utils.besoccer_scraper import obtener_alineaciones_besoccer
from utils.matches_adapter import list_matches_by_date
from models.database import DatabaseManager
from utils.scraping import scrape_player_full, sync_player_to_db

@st.cache_resource
def get_db():
    return DatabaseManager(os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "scouting.db"))

db = get_db()

def _season_from_date(d: dt.date) -> str:
    y = d.year
    # temporada "Y1/Y2" empieza en julio
    if d.month >= 7:
        return f"{y}/{(y+1)%100:02d}"
    return f"{y-1}/{y%100:02d}"

# === 1) Selector de fecha + filtro de ligas ===
c1, c2 = st.columns([1, 2])
with c1:
    fecha = st.date_input("Fecha", value=dt.date.today())
with c2:
    st.caption("Filtra competiciones (texto libre, coma para varias).")
    liga_filtro = st.text_input(
        "Competiciones a incluir",
        value="Primera Federación, Segunda Federación, Tercera Federación",
        help="Se hace 'contains' sobre el nombre de competición si está disponible."
    )

if st.button("🔎 Buscar partidos", type="primary", key="btn_buscar_partidos"):
    with st.spinner("Consultando BeSoccer..."):
        st.session_state["_matches"] = list_matches_by_date(fecha, liga_filtro)
        st.session_state.pop("_lineups", None)   # resetea alineaciones al cambiar lista

matches = st.session_state.get("_matches", [])
if not matches:
    st.info("Elige fecha y pulsa ‘Buscar partidos’.")
    st.stop()

# === 2) Listado/selector de partidos ===
labels = []
for m in matches:
    comp = m.get("competicion") or ""
    hora = m.get("hora") or ""
    labels.append(
        f"{m.get('equipo_local','?')} vs {m.get('equipo_visitante','?')}  —  {hora}  {('· ' + comp) if comp else ''}"
    )

idx = st.selectbox("Partidos:", list(range(len(matches))), format_func=lambda i: labels[i], key="match_select_idx")
match = matches[idx]

st.markdown("---")

# === 3) Alineaciones ===

# Botón para cargar alineaciones del partido seleccionado
if st.button("Cargar alineaciones", key=f"aline_{idx}"):
    # Usamos la URL COMPLETA, y si no existe, caemos al /partido/<id>/alineaciones
    url_full = (
        match.get("url_completa")
        or match.get("url_partido")
        or f"https://es.besoccer.com/partido/{match.get('besoccer_id')}"
    )
    # Aseguramos sufijo /alineaciones
    if not url_full.endswith("/alineaciones"):
        url_full = url_full.rstrip("/") + "/alineaciones"

    with st.spinner("Descargando alineaciones..."):
        data = obtener_alineaciones_besoccer(url_full)
        if not data or not data.get("encontrado"):
            st.warning(data.get("mensaje", "No se han podido obtener alineaciones."))
            st.stop()

        # El scraper devuelve alineacion_local / alineacion_visitante con ambos (titulares+suplentes),
        # y cada jugador lleva "es_titular": True/False. Separamos aquí:
        local_all = data.get("alineacion_local", []) or []
        visit_all = data.get("alineacion_visitante", []) or []

        home_starters = [j for j in local_all if j.get("es_titular")]
        home_bench    = [j for j in local_all if not j.get("es_titular")]

        away_starters = [j for j in visit_all if j.get("es_titular")]
        away_bench    = [j for j in visit_all if not j.get("es_titular")]
        st.caption(
            f"Local: {len(home_starters)} titulares / {len(home_bench)} suplentes · "
            f"Visitante: {len(away_starters)} titulares / {len(away_bench)} suplentes"
        )
        st.session_state["_lineups"] = {
            "home": {
                "name":  match.get("local") or match.get("equipo_local") or "Local",
                "badge": match.get("escudo_local"),
                "starters": home_starters,
                "bench":    home_bench,
            },
            "away": {
                "name":  match.get("visitante") or match.get("equipo_visitante") or "Visitante",
                "badge": match.get("escudo_visitante"),
                "starters": away_starters,
                "bench":    away_bench,
            },
        }

# Pintado
lineups = st.session_state.get("_lineups")
if not lineups:
    st.info("Pulsa ‘Cargar alineaciones’.")
    st.stop()

home = lineups["home"]
away = lineups["away"]

c1, c2 = st.columns(2)

def _bloque_equipo(box: dict, rival_name: str):
    st.subheader(box["name"])
    if box.get("badge"):
        st.image(box["badge"], width=48)

    # Titulares
    st.markdown("**Titulares**")
    if not box["starters"]:
        st.caption("Sin datos de titulares.")
    else:
        for p in box["starters"]:
            numero = p.get("numero") or p.get("number") or ""
            nombre = p.get("nombre") or p.get("name") or "¿?"
            pos    = p.get("posicion") or p.get("position") or ""
            foto   = p.get("imagen_url") or p.get("photo_url")
            url    = p.get("url_besoccer") or p.get("besoccer_url")
            cols = st.columns([1, 3, 2])
            with cols[0]:
                if foto: st.image(foto, width=48)
            with cols[1]:
                st.markdown(f"**{numero}  {nombre}**")
                st.caption(pos or "—")
            with cols[2]:
                if st.button("📌 Evaluar", key=f"eval_{box['name']}_T_{numero}_{nombre}"):
                    # 1) Scrape del perfil del jugador (BIO + CAREER)
                    bio_data = {}
                    try:
                        if url:
                            data = scrape_player_full(url, debug=True)  # trae {'bio':..., 'career':...}
                            bio_data = data.get("bio", {}) or {}
                            # 2) (Opcional pero recomendable) Persistir en BBDD para tener foto/trayectoria ya guardada
                            try:
                                if url:
                                    # NO pasar player_id para que use la lógica de upsert normal
                                    sync_player_to_db(db, url, player_id=None, debug=True)
                            except Exception as e:
                                print("[EVAL] sync_player_to_db falló:", e)
                    except Exception as e:
                        print("[EVAL] scrape_player_full falló:", e)

                    # 3) Prefills a sesión para 3_Informes
                    st.session_state["prefill_name"]        = bio_data.get("name") or nombre
                    st.session_state["prefill_team"]        = box["name"]
                    st.session_state["prefill_pos"]         = bio_data.get("position") or pos
                    st.session_state["prefill_url"]         = url
                    st.session_state["prefill_photo"]       = bio_data.get("photo_url") or foto
                    st.session_state["prefill_nationality"] = bio_data.get("nationality")
                    st.session_state["prefill_birthdate"]   = bio_data.get("birthdate")
                    st.session_state["prefill_foot"]        = bio_data.get("foot")
                    st.session_state["prefill_height_cm"]   = bio_data.get("height_cm")
                    st.session_state["prefill_weight_kg"]   = bio_data.get("weight_kg")
                    st.session_state["prefill_shirt_number"]= bio_data.get("shirt_number")
                    st.session_state["prefill_value_keur"]  = bio_data.get("value_keur")
                    st.session_state["prefill_elo"]         = bio_data.get("elo")

                    # 4) Prefill de contexto del partido
                    st.session_state["prefill_match_date"]  = fecha  # la 'fecha' de la página
                    st.session_state["prefill_opponent"]    = rival_name  # parámetro que ya pasas a _bloque_equipo
                    st.session_state["prefill_season"]      = _season_from_date(fecha)

                    # 5) Ir a la página de informe
                    st.switch_page("pages/3_Informes.py")

    # Suplentes
    st.markdown("**Suplentes**")
    if not box["bench"]:
        st.caption("Sin datos de suplentes.")
    else:
        for p in box["bench"]:
            numero = p.get("numero") or p.get("number") or ""
            nombre = p.get("nombre") or p.get("name") or "¿?"
            pos    = p.get("posicion") or p.get("position") or ""
            foto   = p.get("imagen_url") or p.get("photo_url")
            url    = p.get("url_besoccer") or p.get("besoccer_url")
            cols = st.columns([1, 3, 2])
            with cols[0]:
                if foto: st.image(foto, width=48)
            with cols[1]:
                st.markdown(f"{numero}  {nombre}")
                st.caption(pos or "—")
            with cols[2]:
                if st.button("📌 Evaluar", key=f"eval_{box['name']}_S_{numero}_{nombre}"):
                    # 1) Scrape del perfil del jugador (BIO + CAREER)
                    bio_data = {}
                    try:
                        if url:
                            data = scrape_player_full(url, debug=True)  # trae {'bio':..., 'career':...}
                            bio_data = data.get("bio", {}) or {}
                            # 2) (Opcional pero recomendable) Persistir en BBDD para tener foto/trayectoria ya guardada
                            try:
                                if url:
                                    # NO pasar player_id para que use la lógica de upsert normal
                                    sync_player_to_db(db, url, player_id=None, debug=True)
                            except Exception as e:
                                print("[EVAL] sync_player_to_db falló:", e)
                    except Exception as e:
                        print("[EVAL] scrape_player_full falló:", e)

                    # 3) Prefills a sesión para 3_Informes
                    st.session_state["prefill_name"]        = bio_data.get("name") or nombre
                    st.session_state["prefill_team"]        = box["name"]
                    st.session_state["prefill_pos"]         = bio_data.get("position") or pos
                    st.session_state["prefill_url"]         = url
                    st.session_state["prefill_photo"]       = bio_data.get("photo_url") or foto
                    st.session_state["prefill_nationality"] = bio_data.get("nationality")
                    st.session_state["prefill_birthdate"]   = bio_data.get("birthdate")
                    st.session_state["prefill_foot"]        = bio_data.get("foot")
                    st.session_state["prefill_height_cm"]   = bio_data.get("height_cm")
                    st.session_state["prefill_weight_kg"]   = bio_data.get("weight_kg")
                    st.session_state["prefill_shirt_number"]= bio_data.get("shirt_number")
                    st.session_state["prefill_value_keur"]  = bio_data.get("value_keur")
                    st.session_state["prefill_elo"]         = bio_data.get("elo")

                    # 4) Prefill de contexto del partido
                    st.session_state["prefill_match_date"]  = fecha  # la 'fecha' de la página
                    st.session_state["prefill_opponent"]    = rival_name  # parámetro que ya pasas a _bloque_equipo
                    st.session_state["prefill_season"]      = _season_from_date(fecha)

                    # 5) Ir a la página de informe
                    st.switch_page("pages/3_Informes.py")

with c1:
    _bloque_equipo(home, away["name"])
with c2:
    _bloque_equipo(away, home["name"])

