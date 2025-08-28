# pages/4_Perfil_Jugador.py
from __future__ import annotations
import os, pandas as pd
import streamlit as st
from models.database import DatabaseManager
from datetime import date, datetime

st.set_page_config(page_title="Perfil de jugador", page_icon="🧾", layout="wide")

@st.cache_resource
def get_db(): 
    return DatabaseManager(os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "scouting.db"))

def _age_from_birthdate(s: str|None) -> str:
    if not s: return "-"
    for fmt in ("%Y-%m-%d","%d/%m/%Y"):
        try:
            d = datetime.strptime(s, fmt).date()
            today = date.today()
            years = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
            return str(years)
        except ValueError:
            continue
    return "-"

db = get_db()

# Lee player_id usando SOLO la API nueva
qp = st.query_params
player_id = None
if "player_id" in qp:
    raw = qp["player_id"]
    # puede venir como str o como list[str]
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    try:
        player_id = int(raw) if raw is not None else None
    except ValueError:
        player_id = None
# Fallback: si venimos desde 3_Informes por session_state
if not player_id and "__go_profile_pid" in st.session_state:
    try:
        player_id = int(st.session_state.pop("__go_profile_pid"))
    except Exception:
        player_id = None

st.title("🧾 Perfil de jugador")

# si no llega ID, buscador simple
if not player_id:
    q = st.text_input("Buscar jugador", "")
    if q:
        rows = db.search_players(q, limit=50)
        for r_idx, r in enumerate(rows):
            # Botón que navega con query param - usando índice para evitar duplicados
            if st.button(f"Ver: {r['name']} ({r.get('team','')})", key=f"pick_player_{r['id']}_{r_idx}"):
                st.query_params.clear()
                st.query_params["player_id"] = str(r["id"])
                st.rerun()  # En lugar de switch_page para evitar problemas de navegación
    st.stop()

p = db.get_player(player_id)
if not p:
    st.error("Jugador no encontrado.")
    st.stop()

# Cabecera
c1, c2 = st.columns([1,3])
with c1:
    img_shown = False
    photo_path = p.get("photo_path")
    if photo_path:
        abs_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), photo_path)
        if os.path.exists(abs_path):
            st.image(abs_path, use_container_width=True)
            img_shown = True
    if not img_shown and p.get("photo_url"):
        st.image(p["photo_url"], use_container_width=True)
        img_shown = True
    if not img_shown:
        st.image(os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "Escudo CAC.png"),
                 use_container_width=True)
        
def _calc_age(iso_date: str|None) -> str:
    if not iso_date:
        return "-"
    try:
        from datetime import date, datetime
        d = datetime.fromisoformat(iso_date).date()
        today = date.today()
        return str(today.year - d.year - ((today.month, today.day) < (d.month, d.day)))
    except Exception:
        return "-"

age_txt = _calc_age(p.get("birthdate"))

with c2:
    st.markdown(f"## {p['name']}")

    # Helpers locales
    from datetime import date, datetime

    def calc_age_from_birthdate(birth: str | None) -> str:
        if not birth:
            # fallback a edad guardada si existe
            return str(p.get("age")) if p.get("age") is not None else "—"
        try:
            d = datetime.strptime(birth, "%Y-%m-%d").date()
            today = date.today()
            years = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
            return str(years)
        except Exception:
            return str(p.get("age")) if p.get("age") is not None else "—"

    def fmt_value_keur(v) -> str:
        # v es miles de euros (K€)
        if isinstance(v, (int, float)) and v > 0:
            if v >= 1000:
                # Mostrar en millones con dos decimales
                return f"{(v/1000):.2f} M€"
            # Miles con separador (opcional: coma->punto)
            return f"{int(v):,} K€".replace(",", ".")
        return "—"

    age_txt = calc_age_from_birthdate(p.get("birthdate"))

    bio_cols = st.columns(4)
    bio_cols[0].markdown(f"**Equipo**: {p.get('team','-')}\n\n**Posición**: {p.get('position','-')}")
    bio_cols[1].markdown(f"**Edad**: {age_txt}\n\n**Altura**: {p.get('height_cm','-')} cm")
    bio_cols[2].markdown(f"**Peso**: {p.get('weight_kg','-')} kg\n\n**Pie**: {p.get('foot','-')}")
    bio_cols[3].markdown(
        f"**Dorsal**: {p.get('shirt_number','-')}\n\n"
        f"**Valor**: {fmt_value_keur(p.get('value_keur'))}\n\n"
        f"**ELO**: {p.get('elo','-')}"
    )

    if p.get("source_url"):
        st.caption(f"Fuente: BeSoccer | {p['source_url']}")

st.markdown("---")

tab1, tab2, tab3, tab4 = st.tabs(["Trayectoria", "Informes del club", "Vídeos", "Actualizar datos"])

with tab1:
    include_comp = st.checkbox("Ver detalle por competición", value=False)
    career = db.get_player_career(player_id, include_competitions=include_comp)
    if not career:
        st.info("Sin trayectoria guardada.")
    else:
        df = pd.DataFrame(career)
        # Renombrar columnas para mejor visualización
        df = df.rename(columns={
            "season":"Temporada", "club":"Club", "competition":"Competición",
            "pj":"PJ","goles":"G","asist":"A","ta":"TA","tr":"TR","pt":"PT","ps":"PS","min":"Min",
            "edad":"Edad","pts":"Pts","elo":"ELO"
        })
        
        # Mostrar solo las columnas que tienen datos
        cols_to_show = []
        for col in df.columns:
            if col in ["Temporada", "Club", "Competición"]:
                cols_to_show.append(col)
            elif df[col].notna().any() and (df[col] != 0).any():
                cols_to_show.append(col)
        
        if cols_to_show:
            st.dataframe(df[cols_to_show], use_container_width=True, hide_index=True)
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)

with tab2:
    reps = db.get_reports_for_player(player_id, limit=50)
    if not reps:
        st.info("Aún no hay informes guardados para este jugador.")
    else:
        for r_idx, r in enumerate(reps):
            # Usar contenedor para cada informe
            with st.container():
                # Header del informe
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"**{r.get('season','?')} · {r.get('match_date','')}** · {r['user']} · {r.get('recommendation','?')} ({r.get('confidence','?')}%)")
                with col2:
                    btn_key = f"edit_from_profile_{r['id']}"
                    if st.button("✏️ Editar", key=btn_key):
                        st.query_params["report_id"] = str(r["id"])
                        st.switch_page("pages/3_Informes.py")
                
                # Resumen rápido de ratings
                if r.get('ratings'):
                    ratings_summary = []
                    for cat, vals in r.get('ratings',{}).items():
                        if vals:  # Solo si tiene valores
                            avg = sum(vals.values()) / max(1, len(vals))
                            ratings_summary.append(f"{cat}: {avg:.1f}")
                    
                    if ratings_summary:
                        st.caption(f"Medias por categoría → {', '.join(ratings_summary)}")
                
                # Notas del informe
                if r.get("notes"):
                    with st.expander("Ver notas del informe"):
                        st.write(r["notes"])
                
                # Opponent info si existe
                if r.get("opponent"):
                    st.caption(f"Rival: {r['opponent']} | Minutos observados: {r.get('minutes_observed', '?')}")
                
                st.markdown("---")
with tab3:
    urls = db.list_video_links_for_player(player_id)
    if not urls:
        st.info("Sin vídeos guardados en los informes.")
    else:
        for u in urls:
            st.markdown(f"- [{u}]({u})")

with tab4:
    st.subheader("Actualizar datos del jugador")
    
    # Mostrar datos actuales
    col1, col2 = st.columns(2)
    with col1:
        st.write("**Datos actuales:**")
        st.write(f"- Equipo: {p.get('team', 'No especificado')}")
        st.write(f"- Posición: {p.get('position', 'No especificada')}")
        st.write(f"- Nacionalidad: {p.get('nationality', 'No especificada')}")
        st.write(f"- Fecha nacimiento: {p.get('birthdate', 'No especificada')}")
        st.write(f"- Altura: {p.get('height_cm', 'No especificada')} cm")
        st.write(f"- Peso: {p.get('weight_kg', 'No especificado')} kg")
    
    with col2:
        url = st.text_input("URL BeSoccer para sincronizar", value=p.get("source_url",""))
        
        if st.button("Actualizar desde BeSoccer", disabled=not url):
            if url:
                try:
                    from utils.scraping import sync_player_to_db
                    with st.spinner("Actualizando datos..."):
                        pid = sync_player_to_db(db, url, debug=True)
                    
                    if pid == player_id:
                        st.success("Datos actualizados correctamente.")
                        st.rerun()  # Recargar la página para mostrar datos actualizados
                    else:
                        st.warning(f"Se ha creado/actualizado otro jugador (ID: {pid})")
                except Exception as e:
                    st.error(f"Error al actualizar datos: {str(e)}")
    
    # Botón para regresar a búsqueda
    st.markdown("---")
    if st.button("← Volver a búsqueda de jugadores"):
        st.query_params.clear()
        st.switch_page("pages/4_Perfil_Jugador.py")