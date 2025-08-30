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

tab1, tab2, tab3, tab4, tab5 = st.tabs([
"Trayectoria", "Informes del club", "Vídeos", "Actualizar datos", "Descargar informes"
])

with tab1:
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader("Trayectoria profesional")
    with col2:
        include_comp = st.checkbox("Ver detalle por competición", value=False)
    
    career = db.get_player_career(player_id, include_competitions=include_comp)
    
    if not career:
        st.info("Sin trayectoria guardada.")
    else:
        df = pd.DataFrame(career)
        
        # Renombrar columnas para mejor visualización
        column_names = {
            "season": "Temporada", "club": "Club", "competition": "Competición",
            "pj": "PJ", "goles": "G", "asist": "A", "ta": "TA", "tr": "TR",
            "pt": "PT", "ps": "PS", "min": "Min", "edad": "Edad", "pts": "Pts", "elo": "ELO"
        }
        df = df.rename(columns=column_names)
        
        # Limpiar columna Competition (convertir None a "General")
        if "Competición" in df.columns:
            df["Competición"] = df["Competición"].fillna("General")
            df.loc[df["Competición"] == "", "Competición"] = "General"
        
        # Definir columnas siempre visibles
        core_columns = ["Temporada", "Club"]
        if include_comp:
            core_columns.append("Competición")
        
        # Detectar qué columnas de stats tienen datos
        stats_columns = ["PJ", "G", "A", "TA", "TR", "PT", "PS", "Min", "Edad", "Pts", "ELO"]
        visible_stats = []
        
        for col in stats_columns:
            if col in df.columns and df[col].notna().any() and (df[col] != 0).any():
                visible_stats.append(col)
        
        # Combinar columnas finales
        final_columns = core_columns + visible_stats
        
        # Configuración de formato para el DataFrame
        column_config = {}
        
        # Formatear columnas numéricas
        for col in visible_stats:
            if col in ["Pts"]:
                column_config[col] = st.column_config.NumberColumn(
                    col, format="%.1f", width="small"
                )
            elif col in ["Min"]:
                column_config[col] = st.column_config.NumberColumn(
                    col, format="%d", width="small"
                )
            else:
                column_config[col] = st.column_config.NumberColumn(
                    col, format="%d", width="small"
                )
        
        # Configurar columnas de texto
        column_config["Temporada"] = st.column_config.TextColumn("Temporada", width="small")
        column_config["Club"] = st.column_config.TextColumn("Club", width="medium")
        if "Competición" in final_columns:
            column_config["Competición"] = st.column_config.TextColumn("Competición", width="medium")
        
        # Mostrar tabla con configuración
        if final_columns:
            # Colorear filas alternas para mejor legibilidad
            st.dataframe(
                df[final_columns],
                use_container_width=True,
                hide_index=True,
                column_config=column_config,
                height=min(400, 35 * len(df) + 38)  # Altura dinámica
            )
            
            # Estadísticas resumen
            if not include_comp:  # Solo mostrar resumen cuando vemos totales
                st.markdown("---")
                st.subheader("📊 Resumen de carrera")
                
                # Calcular totales de carrera (solo filas "General")
                general_rows = df[df["Competición"] == "General"] if "Competición" in df.columns else df
                
                if not general_rows.empty:
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        total_pj = general_rows["PJ"].sum() if "PJ" in general_rows.columns else 0
                        total_min = general_rows["Min"].sum() if "Min" in general_rows.columns else 0
                        st.metric("Partidos jugados", f"{int(total_pj)}")
                        st.caption(f"{int(total_min):,} minutos".replace(',', '.'))
                    
                    with col2:
                        total_goles = general_rows["G"].sum() if "G" in general_rows.columns else 0
                        total_asist = general_rows["A"].sum() if "A" in general_rows.columns else 0
                        st.metric("Goles", f"{int(total_goles)}")
                        st.caption(f"{int(total_asist)} asistencias")
                    
                    with col3:
                        total_ta = general_rows["TA"].sum() if "TA" in general_rows.columns else 0
                        total_tr = general_rows["TR"].sum() if "TR" in general_rows.columns else 0
                        st.metric("Tarjetas amarillas", f"{int(total_ta)}")
                        st.caption(f"{int(total_tr)} rojas")
                    
                    with col4:
                        if "Pts" in general_rows.columns and general_rows["Pts"].notna().any():
                            avg_pts = general_rows["Pts"].mean()
                            st.metric("Media puntuación", f"{avg_pts:.1f}")
                        
                        if "ELO" in general_rows.columns and general_rows["ELO"].notna().any():
                            current_elo = general_rows["ELO"].iloc[0]  # ELO más reciente
                            st.caption(f"ELO actual: {int(current_elo)}")
                
                # Gráfico de evolución (solo si hay datos de puntuación o ELO)
                if len(general_rows) > 1 and ("Pts" in general_rows.columns or "ELO" in general_rows.columns):
                    st.markdown("---")
                    st.subheader("📈 Evolución")
                    
                    # Preparar datos para gráfico
                    plot_data = general_rows.copy()
                    plot_data = plot_data.sort_values("Temporada")
                    
                    # Crear gráfico con plotly si está disponible
                    try:
                        import plotly.express as px
                        import plotly.graph_objects as go
                        
                        fig = go.Figure()
                        
                        if "Pts" in plot_data.columns and plot_data["Pts"].notna().any():
                            fig.add_trace(go.Scatter(
                                x=plot_data["Temporada"],
                                y=plot_data["Pts"],
                                mode='lines+markers',
                                name='Puntuación media',
                                line=dict(color='#1f77b4', width=3),
                                marker=dict(size=8)
                            ))
                        
                        if "ELO" in plot_data.columns and plot_data["ELO"].notna().any():
                            fig.add_trace(go.Scatter(
                                x=plot_data["Temporada"],
                                y=plot_data["ELO"],
                                mode='lines+markers',
                                name='ELO',
                                yaxis='y2',
                                line=dict(color='#ff7f0e', width=3),
                                marker=dict(size=8)
                            ))
                        
                        # Configurar layout
                        fig.update_layout(
                            title="Evolución del rendimiento por temporada",
                            xaxis_title="Temporada",
                            yaxis_title="Puntuación media",
                            yaxis2=dict(
                                title="ELO",
                                overlaying='y',
                                side='right'
                            ),
                            height=400,
                            showlegend=True,
                            hovermode='x unified'
                        )
                        
                        st.plotly_chart(fig, use_container_width=True)
                        
                    except ImportError:
                        # Fallback a gráfico simple de Streamlit
                        if "Pts" in plot_data.columns:
                            st.line_chart(plot_data.set_index("Temporada")["Pts"])
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
                        # Pasar el player_id actual para actualizar el mismo registro
                        pid = sync_player_to_db(db, url, player_id=player_id, debug=True)
                    
                    if pid == player_id:
                        st.success("Datos actualizados correctamente.")
                        st.rerun()  # Recargar la página para mostrar datos actualizados
                    else:
                        st.warning(f"Advertencia: se actualizó otro jugador (ID: {pid})")
                except Exception as e:
                    st.error(f"Error al actualizar datos: {str(e)}")
    
# === Nueva pestaña: Descargar informes ===
with tab5:
    st.subheader("Descargar informes")

    # 1) Obtener informes del jugador
    # Necesitamos un método en DatabaseManager: get_reports_by_player(player_id)
    try:
        reports = db.get_reports_by_player(player_id) # ← implementaremos si no existe
    except AttributeError:
        reports = []
        st.warning("Falta implementar db.get_reports_by_player(player_id). Lo añadimos en el paso 2.")


    if not reports:
        st.info("Este jugador aún no tiene informes o no se pudieron recuperar.")
    else:
        import pandas as pd

        # Normaliza a lista de dicts
        rep_rows = list(reports) if not isinstance(reports, list) else reports
        df_rep = pd.DataFrame(rep_rows)
        # Renombrar 'user' a 'created_by' para mejor visualización
        if 'user' in df_rep.columns:
            df_rep = df_rep.rename(columns={'user': 'created_by'})

        # Columnas sugeridas para mostrar si existen
        base_cols = ["id", "match_date", "season", "opponent", "created_at", "created_by", "recommendation"]
        show_cols = [c for c in base_cols if c in df_rep.columns]
        st.dataframe(df_rep[show_cols] if show_cols else df_rep, use_container_width=True, hide_index=True)

        # 2) Selector de modo de descarga
        mode = st.radio(
            "Modo de descarga",
            ["Informe individual", "Resumen de todos"],
            horizontal=True,
            key=f"dl_mode_{player_id}"
            )
        
        if mode == "Informe individual":
            # Mapea a un dict legible → id
            opciones = {}
            for r in rep_rows:
                rid = r.get("id")
                label = f"#{rid} · {r.get('match_date','?')} · {r.get('opponent','?')}"
                opciones[label] = rid

            if not opciones:
                st.info("No hay informes individuales para este jugador.")

            else:
                sel_label = st.selectbox("Elige informe", list(opciones.keys()), key=f"pick_one_{player_id}")
                sel_id = opciones[sel_label]

                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Generar PDF (individual)", type="primary", key=f"btn_pdf_one_{player_id}"):
                        # Dejamos preparada una señal en session_state para el siguiente paso (generación)
                        st.session_state["__pending_pdf"] = {
                            "type": "single",
                            "player_id": player_id,
                            "report_id": int(sel_id)
                        }
                        st.success("Preparado: Generación de PDF individual (implementaremos en el paso 2).")

                with c2:
                    st.download_button(
                        "Descargar último PDF (individual)",
                        data=b"",
                        file_name="informe_individual.pdf",
                        disabled=True,
                        help="Se habilitará cuando generemos y guardemos el PDF."
                    )

        else:
            st.caption("Se generará un resumen con IA de todos los informes + visualizaciones.")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Generar PDF (resumen de todos)", type="primary", key=f"btn_pdf_all_{player_id}"):
                    st.session_state["__pending_pdf"] = {
                        "type": "all",
                        "player_id": player_id
                    }
                    st.success("Preparado: Generación de PDF resumen (implementaremos en el paso 2).")
            with c2:
                st.download_button(
                    "Descargar último PDF (resumen)",
                    data=b"",
                    file_name="informe_resumen.pdf",
                    disabled=True,
                    help="Se habilitará cuando generemos y guardemos el PDF."
                )

        from utils.pdf_export import build_player_report_pdf, build_player_summary_pdf

        pending = st.session_state.pop("__pending_pdf", None)
        if pending:
            out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "exports")
            os.makedirs(out_dir, exist_ok=True)

            if pending["type"] == "single":
                out_path = os.path.join(out_dir, f"player_{pending['player_id']}_report_{pending['report_id']}.pdf")
                with st.spinner("Generando PDF del informe individual..."):
                    try:
                        pdf_path = build_player_report_pdf(db, pending["player_id"], pending["report_id"], out_path)
                        with open(pdf_path, "rb") as f:
                            st.download_button("Descargar PDF (individual)", f.read(), file_name=os.path.basename(pdf_path))
                        st.success("PDF individual generado.")
                    except Exception as e:
                        st.error(f"Error generando PDF individual: {e}")

            elif pending["type"] == "all":
                out_path = os.path.join(out_dir, f"player_{pending['player_id']}_resumen.pdf")
                with st.spinner("Generando PDF resumen de todos los informes..."):
                    try:
                        pdf_path = build_player_summary_pdf(db, pending["player_id"], out_path, ollama_model="llama3")
                        with open(pdf_path, "rb") as f:
                            st.download_button("Descargar PDF (resumen)", f.read(), file_name=os.path.basename(pdf_path))
                        st.success("PDF resumen generado.")
                    except Exception as e:
                        st.error(f"Error generando PDF resumen: {e}")

# Botón para regresar a búsqueda
st.markdown("---")
if st.button("← Volver a búsqueda de jugadores"):
    st.query_params.clear()
    st.switch_page("pages/4_Perfil_Jugador.py")