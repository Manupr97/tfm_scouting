# pages/3_Informes.py
from __future__ import annotations
import os, json, re, datetime as dt
import pandas as pd
import streamlit as st
from typing import Dict, List
from models.database import DatabaseManager  # ajusta el import a tu ruta real
from utils.scraping import sync_player_to_db, scrape_player_full
from utils.styles import inject_global_styles, create_player_card, create_page_header

inject_global_styles()  # ← AÑADIR

st.set_page_config(page_title="Informes", page_icon="📊", layout="wide")

def detectar_duplicados_potenciales(db, nombre: str) -> list[dict]:
    """Busca jugadores similares para alertar sobre posibles duplicados"""
    if not nombre or len(nombre.strip()) < 3:
        return []
    
    with db._connect() as conn:
        cur = conn.cursor()
        # Búsqueda fuzzy por nombre similar
        nombre_clean = nombre.strip().lower()
        cur.execute("""
            SELECT id, name, team, birthdate, source_url 
            FROM scouted_players 
            WHERE LOWER(name) LIKE ?
            ORDER BY updated_at DESC
            LIMIT 5
        """, (f"%{nombre_clean}%",))
        
        return [dict(row) for row in cur.fetchall()]

def slug(s: str) -> str: return re.sub(r"[^a-z0-9]+","_", s.lower()).strip("_")

def limpiar_estados_formulario():
    """Limpia todos los estados del formulario para empezar limpio"""
    prefill_keys = [k for k in st.session_state.keys() if k.startswith("prefill_")]
    form_keys = [k for k in st.session_state.keys() if k.startswith("form_")]
    temp_keys = ["_bio_prefill", "_career_prefill", "_last_synced_pid", "__prefill_done", 
                 "__current_editing_id", "last_saved_pid", "last_saved_rid"]
    
    keys_to_remove = prefill_keys + form_keys + temp_keys
    
    for key in keys_to_remove:
        if key in st.session_state:
            del st.session_state[key]

def es_edicion_nueva():
    """Detecta si estamos editando un informe diferente al anterior"""
    current_id = st.query_params.get("report_id")
    last_id = st.session_state.get("__current_editing_id")
    return current_id and str(current_id) != str(last_id)

# guardarríl login como en catálogo
if "logged_in" not in st.session_state or not st.session_state.logged_in:
    st.warning("Debes iniciar sesión para acceder a los informes.")
    st.stop()

@st.cache_resource
def get_db() -> DatabaseManager:
    return DatabaseManager(os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "scouting.db"))

db = get_db()
user = st.session_state.get("username","anon")
qp = st.query_params
report_id = None
if "report_id" in qp:
    try:
        rid_raw = qp["report_id"]
        if isinstance(rid_raw, list): rid_raw = rid_raw[0]
        report_id = int(rid_raw)
    except Exception:
        report_id = None

# Fallback si venimos desde “Buscar/Editar” con session_state
if not report_id and "__edit_report_id" in st.session_state:
    try:
        report_id = int(st.session_state.pop("__edit_report_id"))
    except Exception:
        report_id = None

report = db.get_report(report_id) if report_id else None
editing = report is not None
if editing:
    st.info(f"✏️ Estás editando el informe #{report['id']} del jugador #{report['player_id']}.")

# === Plantillas de categorías/métricas (ejemplo, ajusta a tu club)
TEMPLATES = {
  "Portero": {
    "Juego con pies": ["Pase corto","Pase largo","Decisiones bajo presión"],
    "Paradas": ["Reflejos","Aéreos","1v1"],
    "Colocación": ["Posicionamiento","Salidas"],
  },
  "Central": {
    "Defensa": ["Duelos","Aéreos","Interceptaciones","Entradas"],
    "Salida de balón": ["Pase corto","Pase largo","Progresión"],
    "Concentración": ["Errores","Coberturas"],
  },
  "Lateral": {
    "Defensa": ["Duelos","Aéreos","Interceptaciones"],
    "Ataque": ["Centros","Progresión","Aportación ofensiva"],
    "Físico": ["Resistencia","Velocidad"],
  },
  "Mediocentro defensivo": {
    "Defensa": ["Coberturas","Intercepciones","Duelos"],
    "Construcción": ["Pase corto","Cambio de orientación","Lectura"],
    "Transición": ["Posicionamiento","Ritmo sin balón"],
  },
  "Mediocentro": {
    "Creación": ["Pase clave","Progresión","Conducción"],
    "Organización": ["Ritmo","Visión","Perfilado"],
    "Defensa": ["Presión","Recuperación"],
  },
  "Extremo": {
    "1v1": ["Regate","Aceleración"],
    "Centro/Asistencia": ["Centros","Decisión en último tercio"],
    "Finalización": ["Tiro","Desmarque segundo palo"],
  },
  "Delantero": {
    "Área": ["Desmarques","Definición","Juego de espaldas"],
    "Asociación": ["Descargas","Paredes"],
    "Presión": ["Primer esfuerzo","Orientación presión"],
  },
}

# === Auto-prefill cuando se viene desde "Evaluar" (página 2) ===
if (not editing) and st.session_state.get("prefill_from_lineups") and not st.session_state.get("__prefill_done"):
    pre_url = st.session_state.get("prefill_url")
    if pre_url:
        # 1) Traer bio + trayectoria (sin mostrar botones en UI)
        from utils.scraping import scrape_player_full, sync_player_to_db
        data = scrape_player_full(pre_url, debug=True)            # bio + career a memoria
        st.session_state["_bio_prefill"]    = data.get("bio", {})
        st.session_state["_career_prefill"] = data.get("career", [])

        # 2) Persistir en BBDD (jugador + trayectoria) para tener perfil listo
        pid = sync_player_to_db(db, pre_url, debug=True)
        st.session_state["_last_synced_pid"] = pid

    st.session_state["__prefill_done"] = True

# --- Prefill en session_state cuando venimos a editar ---
def _set_if_missing(k, v):
    if k not in st.session_state:
        st.session_state[k] = v

def _prefill_editing_form(report: dict):
    """Carga en session_state todos los valores del informe/ jugador para que los widgets salgan rellenados."""
    player = db.get_player(report["player_id"]) or {}

    # Marcar qué informe estamos editando (para no reinyectar en cada rerun)
    st.session_state["__current_editing_id"] = report["id"]

    # Identificación jugador
    _set_if_missing("form_name",        player.get("name",""))
    _set_if_missing("form_team",        player.get("team",""))
    _set_if_missing("form_position",    player.get("position",""))
    _set_if_missing("form_nationality", player.get("nationality",""))
    _set_if_missing("form_birthdate",   player.get("birthdate",""))
    _set_if_missing("form_height",      float(player.get("height_cm") or 0.0))
    _set_if_missing("form_weight",      float(player.get("weight_kg") or 0.0))
    _set_if_missing("form_url",         player.get("source_url",""))

    # Contexto del informe
    _set_if_missing("form_season",      report.get("season",""))
    # match_date → date
    try:
        d = report.get("match_date")
        _set_if_missing("form_match_date", dt.date.fromisoformat(d) if d else dt.date.today())
    except Exception:
        _set_if_missing("form_match_date", dt.date.today())
    _set_if_missing("form_opponent",        report.get("opponent","") or "")
    _set_if_missing("form_minutes",         int(report.get("minutes_observed") or 90))

    # Plantilla y ratings
    template_used = (report.get("context") or {}).get("template")
    if template_used in TEMPLATES:
        _set_if_missing("form_template", template_used)
    else:
        _set_if_missing("form_template", list(TEMPLATES.keys())[0])

    # Cargar sliders de ratings
    rdict = report.get("ratings") or {}
    for cat, metrics in TEMPLATES[st.session_state["form_template"]].items():
        for m in metrics:
            key = f"rate_{slug(cat)}_{slug(m)}"
            _set_if_missing(key, int((rdict.get(cat, {})).get(m, 5)))

    # Rasgos, notas, recomendación, confianza, links
    traits_list = report.get("traits") or []
    _set_if_missing("form_traits_raw", ", ".join(traits_list))
    _set_if_missing("form_notes", report.get("notes","") or "")
    _set_if_missing("form_reco",  report.get("recommendation","SEGUIMIENTO") or "SEGUIMIENTO")
    _set_if_missing("form_conf",  int(report.get("confidence") or 70))
    _set_if_missing("form_links_raw", ", ".join(report.get("links") or []))

# Detectar cambio de informe editado y limpiar estados obsoletos
if editing and es_edicion_nueva():
    limpiar_estados_formulario()
    _prefill_editing_form(report)
elif editing and st.session_state.get("__current_editing_id") != report["id"]:
    _prefill_editing_form(report)

# ===== Prefill cuando estamos editando =====
player_prefill = db.get_player(report["player_id"]) if editing else {}

# Datos básicos del jugador
default_name       = player_prefill.get("name", "")
default_team       = player_prefill.get("team", "")
default_position   = player_prefill.get("position", "")
default_nationality= player_prefill.get("nationality", "")
default_birthdate  = player_prefill.get("birthdate", "")
default_height     = player_prefill.get("height_cm") or 0.0
default_weight     = player_prefill.get("weight_kg") or 0.0
default_source_url = player_prefill.get("source_url", "")

# --- Prefill ligero si venimos de 2_Scouting_Partidos ---
if not default_name and st.session_state.get("prefill_name"):
    default_name = st.session_state.get("prefill_name") or default_name
if not default_team and st.session_state.get("prefill_team"):
    default_team = st.session_state.get("prefill_team") or default_team
if not default_position and st.session_state.get("prefill_pos"):
    default_position = st.session_state.get("prefill_pos") or default_position
if not default_source_url and st.session_state.get("prefill_url"):
    default_source_url = st.session_state.get("prefill_url") or default_source_url
# No tocamos _bio_prefill aquí; el usuario puede pulsar "Autocompletar bio" si quiere

# Contexto del informe
default_season     = (report.get("season") if editing else "25/26") or "25/26"
default_match_date = dt.date.today()
if editing and report.get("match_date"):
    try:
        default_match_date = dt.date.fromisoformat(report["match_date"])
    except Exception:
        pass
default_opponent   = report.get("opponent", "") if editing else ""
default_minutes    = int(report.get("minutes_observed") or 90) if editing else 90

# Plantilla elegida en ese informe (si la hay)
default_template   = (report.get("context", {}) or {}).get("template") if editing else None

# Valoraciones guardadas (para precargar sliders)
existing_ratings   = report.get("ratings", {}) if editing else {}

# Rasgos / notas / recomendación / confianza / links
default_traits     = report.get("traits", ["competitivo", "agresivo"]) if editing else ["competitivo", "agresivo"]
default_notes      = report.get("notes", "") if editing else ""
default_reco       = report.get("recommendation", "SEGUIMIENTO") if editing else "SEGUIMIENTO"
default_conf       = int(report.get("confidence", 70)) if editing else 70
default_links_raw  = ", ".join(report.get("links", [])) if editing else ""
# ===== Fin prefill =====

# === Scraper BeSoccer (URL -> dict bio) ===
def scrape_besoccer_player(url: str) -> dict:
    try:
        import requests
        from bs4 import BeautifulSoup
        r = requests.get(url, timeout=10, headers={"User-Agent":"Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")

        # heurística: intenta JSON-LD primero
        bio = {"source_url": url}
        for script in soup.find_all("script", attrs={"type":"application/ld+json"}):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    person = data if data.get("@type") in ("Person","Athlete") else None
                elif isinstance(data, list):
                    person = next((x for x in data if isinstance(x, dict) and x.get("@type") in ("Person","Athlete")), None)
                else:
                    person = None
                if person:
                    bio["name"] = person.get("name") or bio.get("name")
                    bio["birthdate"] = person.get("birthDate") or None
                    bio["nationality"] = (person.get("nationality") or {}).get("name") if isinstance(person.get("nationality"), dict) else person.get("nationality")
                    bio["height_cm"] = float(str(person.get("height")).replace(" cm","")) if person.get("height") else None
                    bio["weight_kg"] = float(str(person.get("weight")).replace(" kg","")) if person.get("weight") else None
                    break
            except Exception:
                pass

        # texto suelto: busca etiquetas típicas (fallback)
        txt = soup.get_text(" ", strip=True)
        def grab(regex, cast=str):
            m = re.search(regex, txt, re.I)
            if not m: return None
            val = m.group(1).strip()
            try: return cast(val)
            except: return val

        if "birthdate" not in bio or not bio["birthdate"]:
            bio["birthdate"] = grab(r"Nacimiento:\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})")
        if "nationality" not in bio or not bio["nationality"]:
            bio["nationality"] = grab(r"Nacionalidad:\s*([A-Za-zÀÁÉÍÓÚÜÑàáéíóúüñ ]+)")
        if "height_cm" not in bio or not bio["height_cm"]:
            h = grab(r"Altura:\s*([0-9]{1,3})\s*cm")
            bio["height_cm"] = float(h) if h else None
        if "weight_kg" not in bio or not bio["weight_kg"]:
            w = grab(r"Peso:\s*([0-9]{1,3})\s*kg")
            bio["weight_kg"] = float(w) if w else None

        # edad si tenemos fecha
        if bio.get("birthdate"):
            try:
                d = dt.datetime.strptime(bio["birthdate"], "%Y-%m-%d")
            except ValueError:
                try: d = dt.datetime.strptime(bio["birthdate"], "%d/%m/%Y")
                except: d = None
            if d:
                today = dt.date.today()
                bio["age"] = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
        return bio
    except Exception as e:
        st.warning(f"No se pudo obtener bio desde BeSoccer: {e}")
        return {"source_url": url}

# === UI ===
create_page_header("📊 Informes de jugadores", "Creación y gestión de informes de scouting")

# === BREADCRUMB ===
breadcrumb_parts = ["🏠 Inicio"]
if editing:
    player_name = (db.get_player(report["player_id"]) or {}).get("name", "Jugador")
    breadcrumb_parts.extend([
        "👤 Perfil",
        f"✏️ Editando informe de {player_name}"
    ])
else:
    breadcrumb_parts.append("🆕 Nuevo informe")

st.caption(" → ".join(breadcrumb_parts))
# === BARRA DE ACCIONES RÁPIDAS ===
col_quick1, col_quick2, col_quick3 = st.columns([2, 2, 1])

with col_quick1:
    if st.button("🆕 Nuevo informe limpio", key="btn_nuevo_limpio"):
        limpiar_estados_formulario()
        st.query_params.clear()
        st.success("✅ Formulario limpiado")
        st.rerun()

with col_quick2:
    if editing:
        if st.button("❌ Cancelar edición", key="btn_cancelar_edicion"):
            limpiar_estados_formulario()
            st.query_params.clear()
            st.success("✅ Edición cancelada")
            st.rerun()

with col_quick3:
    # Indicador de modo
    if editing:
        st.info(f"✏️ Editando #{report['id']}")
    else:
        st.info("🆕 Nuevo")

tab_new, tab_search = st.tabs(["Nuevo informe", "Buscar/Editar"])

with tab_new:
    st.subheader("Identificación del jugador")
    bio_prefill = st.session_state.get("_bio_prefill", {})
    SS = st.session_state

    # Identificación del jugador
    c1, c2 = st.columns([2,1])
    with c1:
        name = st.text_input("Nombre", SS.get("prefill_name", default_name))
        
        # ← AÑADIR: Detección de duplicados en tiempo real
        if name and len(name.strip()) >= 3 and not editing:
            similares = detectar_duplicados_potenciales(db, name)
            similares_filtrados = [s for s in similares if s['name'].lower() != name.lower()]
            
            if similares_filtrados:
                st.warning(f"⚠️ Encontrados {len(similares_filtrados)} jugadores con nombres similares:")
                for sim in similares_filtrados[:3]:  # Máximo 3
                    team_info = f" ({sim['team']})" if sim.get('team') else ""
                    birth_info = f" - {sim['birthdate']}" if sim.get('birthdate') else ""
                    st.caption(f"• **{sim['name']}**{team_info}{birth_info}")
                
                if len(similares_filtrados) > 3:
                    st.caption(f"... y {len(similares_filtrados) - 3} más")
        team     = st.text_input("Equipo",   SS.get("prefill_team",   default_team))
        position = st.text_input("Posición", SS.get("prefill_pos",    default_position))
    with c2:
        url = st.text_input("URL BeSoccer (opcional)", SS.get("prefill_url", ""))

    # Fila extra con foto (opcional, solo mostrar)
    if SS.get("prefill_photo"):
        st.image(SS["prefill_photo"], caption="Foto (BeSoccer)", width=120)

    c3, c4, c5, c6 = st.columns(4)
    with c3:
        nationality = st.text_input("Nacionalidad", SS.get("prefill_nationality", default_nationality))
    with c4:
        birthdate = st.text_input("Fecha nacimiento (YYYY-MM-DD)", SS.get("prefill_birthdate", default_birthdate))
        
        # ← AÑADIR: Mostrar edad calculada automáticamente
        if birthdate:
            try:
                from models.database import DatabaseManager
                edad_calc = DatabaseManager.calculate_age(birthdate)
                if edad_calc:
                    st.caption(f"✅ Edad: {edad_calc} años")
                else:
                    st.caption("⚠️ Formato fecha incorrecto")
            except:
                st.caption("⚠️ Fecha inválida")
        else:
            st.caption("Introduce fecha para calcular edad")
    with c5:
        height_cm = st.number_input("Altura (cm)", value=float(max(0.0, (SS.get("prefill_height_cm") or default_height or 0.0))), step=1.0, min_value=0.0)
    with c6:
        weight_kg = st.number_input("Peso (kg)", value=float(max(0.0, (SS.get("prefill_weight_kg") or default_weight or 0.0))), step=1.0, min_value=0.0)

    # NUEVA fila: pie, dorsal, valor y ELO
    c7a, c7b, c7c, c7d = st.columns(4)
    with c7a:
        foot = st.text_input("Pie preferido", SS.get("prefill_foot", ""))
    with c7b:
        shirt_number = st.number_input("Dorsal", min_value=0, max_value=99, value=int(SS.get("prefill_shirt_number") or 0), step=1)
    with c7c:
        value_keur = st.number_input("Valor (K€)", min_value=0, value=int(SS.get("prefill_value_keur") or 0), step=50)
    with c7d:
        elo = st.number_input("ELO", min_value=0, max_value=999, value=int(SS.get("prefill_elo") or 0), step=1)

    st.markdown("---")
    st.subheader("Contexto del informe")
    c7, c8, c9, c10 = st.columns(4)
    with c7:
        season = st.text_input("Temporada", SS.get("prefill_season", default_season))
    with c8:
        match_date = st.date_input("Fecha del partido", value=SS.get("prefill_match_date", default_match_date))
    with c9:
        opponent = st.text_input("Rival", SS.get("prefill_opponent", default_opponent))
    with c10:
        minutes_observed = st.number_input("Minutos observados", min_value=0, max_value=120, value=int(default_minutes), step=5)

    st.markdown("---")
    st.subheader("Valoración por categorías")

    template_options = list(TEMPLATES.keys())
    # Ajustar plantilla y valores iniciales de sliders si hay informe
    pref_context = report.get("context", {}) if editing else {}
    pref_template = pref_context.get("template") if isinstance(pref_context, dict) else None
    template_keys = list(TEMPLATES.keys())
    try:
        template_index = template_keys.index(pref_template) if pref_template else 0
    except ValueError:
        template_index = 0

    template_name = st.selectbox("Plantilla", template_keys, index=template_index)

    ratings: Dict[str, Dict[str, int]] = {}
    saved = report.get("ratings", {}) if editing else {}
    for cat, metrics in TEMPLATES[template_name].items():
        st.markdown(f"**{cat}**")
        cols = st.columns(3)
        block = {}
        for i, m in enumerate(metrics):
            default_val = int(saved.get(cat, {}).get(m, 5)) if isinstance(saved, dict) else 5
            with cols[i % 3]:
                block[m] = st.slider(m, 0, 10, default_val, key=f"rate_{cat}_{m}")
        ratings[cat] = block

    st.markdown("---")
    st.subheader("Rasgos y notas")
    if hasattr(st, "tags_input"):
        traits = st.tags_input("Rasgos (enter para añadir)", value=default_traits)
    else:
        traits = st.text_input("Rasgos (separados por comas)", ", ".join(default_traits)).split(",")

    notes = st.text_area("Observaciones cualitativas", height=180,
                        value=default_notes,
                        placeholder="Con balón, sin balón, transición, balón parado...")

    st.markdown("---")
    st.subheader("Recomendación")
    c11, c12, c13 = st.columns([1,2,1])
    with c11:
        recommendation = st.selectbox("Decisión", ["FICHAR","SEGUIMIENTO","DESCARTAR"],
                                    index=["FICHAR","SEGUIMIENTO","DESCARTAR"].index(default_reco))
    with c12:
        confidence = st.slider("Confianza", 0, 100, int(default_conf))
    with c13:
        links_raw = st.text_input("Links de vídeo (separados por coma)", default_links_raw)

    st.markdown("---")
    st.subheader("Adjuntos")
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    files = st.file_uploader("Subir archivos", type=["png","jpg","jpeg","pdf"], accept_multiple_files=True)

    bio_prefill = st.session_state.get("_bio_prefill", {})

    # === VALIDACIÓN DE DATOS MÍNIMOS ===
    def validar_informe_minimo(name, team, position, ratings, season, minutes_observed):
        errores = []
        
        # Datos básicos obligatorios
        if not name or len(name.strip()) < 2:
            errores.append("El nombre del jugador es obligatorio")
        
        if not team or len(team.strip()) < 2:
            errores.append("El equipo es obligatorio")
        
        if not position or len(position.strip()) < 1:
            errores.append("La posición es obligatoria")
        
        # Al menos una valoración > 0
        tiene_valoraciones = False
        for cat, metrics in ratings.items():
            if any(v > 0 for v in metrics.values()):
                tiene_valoraciones = True
                break
        
        if not tiene_valoraciones:
            errores.append("Debe incluir al menos una valoración mayor a 0")
        
        # Contexto mínimo
        if not season or len(season.strip()) < 4:
            errores.append("La temporada es obligatoria (ej: 24/25)")
        
        if minutes_observed < 5:
            errores.append("Los minutos observados deben ser al menos 5")
        
        return errores

    # Ejecutar validación CON PARÁMETROS
    errores_validacion = validar_informe_minimo(name, team, position, ratings, season, minutes_observed)

    # Mostrar errores si los hay
    if errores_validacion:
        st.error("**Corrige estos errores antes de guardar:**")
        for error in errores_validacion:
            st.write(f"• {error}")

    # Botón condicional
    boton_habilitado = len(errores_validacion) == 0
    if st.button("💾 Guardar informe", type="primary", disabled=not boton_habilitado):
        # 1) Normaliza números (evita min_value y NaN)
        height_val = float(height_cm or 0) or None
        weight_val = float(weight_kg or 0) or None

        # 2) TRANSACCIÓN AGRUPADA para evitar estados inconsistentes
        try:
            pid = db.upsert_scouted_player(
                name=name.strip(),
                team=(team or "").strip() or None,
                position=(position or "").strip() or None,
                nationality=(nationality or "").strip() or None,
                birthdate=(birthdate or "").strip() or None,
                height_cm=height_val,
                weight_kg=weight_val,
                foot=(foot or "").strip() or None,
                photo_url=st.session_state.get("prefill_photo"),
                source_url=(url or st.session_state.get("prefill_url") or "").strip() or None,
                shirt_number=int(shirt_number) if shirt_number else None,
                value_keur=int(value_keur) if value_keur else None,
                elo=int(elo) if elo else None,
            )

            # 3) Informe (si edito -> update; si no -> create)
            context = {"template": template_name}
            links = [l.strip() for l in (links_raw or "").split(",") if l.strip()]

            if editing:
                rid = int(report_id)  # reutilizamos el mismo ID
                db.update_report(
                    rid,
                    player_id=pid,
                    user=user,
                    season=season.strip(),
                    match_date=str(match_date) if match_date else None,
                    opponent=(opponent or "").strip() or None,
                    minutes_observed=int(minutes_observed),
                    context=context,
                    ratings=ratings,
                    traits=[t.strip() for t in (traits or []) if t],
                    notes=(notes or "").strip() or None,
                    recommendation=recommendation,
                    confidence=int(confidence),
                    links=links,
                )
            else:
                rid = db.create_report(
                    player_id=pid,
                    user=user,
                    season=season.strip(),
                    match_date=str(match_date) if match_date else None,
                    opponent=(opponent or "").strip() or None,
                    minutes_observed=int(minutes_observed),
                    context=context,
                    ratings=ratings,
                    traits=[t.strip() for t in (traits or []) if t],
                    notes=(notes or "").strip() or None,
                    recommendation=recommendation,
                    confidence=int(confidence),
                    links=links,
                )

            # 4) Adjuntos
            file_paths = []
            for f in (files or []):
                fname = f"{slug(name)}_{slug(str(match_date))}_{slug(f.name)}"
                save_path = os.path.join(upload_dir, fname)
                with open(save_path, "wb") as out:
                    out.write(f.read())
                file_paths.append((save_path, f.name))

            st.success(f"Informe guardado completamente (jugador #{pid}, informe #{rid}).")

            # Limpiar estados tras guardar exitoso
            if st.button("🔄 Crear otro informe", key="btn_otro_informe"):
                limpiar_estados_formulario()
                st.query_params.clear()
                st.rerun()

            # Auto-limpiar prefills de alineaciones tras guardar
            for key in list(st.session_state.keys()):
                if key.startswith("prefill_") and key != "prefill_from_lineups":
                    del st.session_state[key]

        except Exception as e:
            st.error(f"Error guardando informe: {str(e)}")
            # Limpiar archivos si falló
            for save_path, _ in file_paths:
                try:
                    os.unlink(save_path)
                except:
                    pass

with tab_search:
    st.subheader("Buscar/Editar informes")

    # === FILTROS AVANZADOS ===
    with st.expander("🔍 Búsqueda avanzada", expanded=True):
        col_f1, col_f2, col_f3 = st.columns(3)
        
        with col_f1:
            q = st.text_input("Buscar por nombre", "", key="search_players_q")
            team_filter = st.text_input("Filtrar por equipo", "", key="search_team")
        
        with col_f2:
            pos_filter = st.text_input("Filtrar por posición", "", key="search_pos")
            nationality_filter = st.text_input("Filtrar por nacionalidad", "", key="search_nat")
        
        with col_f3:
            col_age1, col_age2 = st.columns(2)
            with col_age1:
                min_age = st.number_input("Edad mín", min_value=15, max_value=45, value=15, key="search_min_age")
            with col_age2:
                max_age = st.number_input("Edad máx", min_value=15, max_value=45, value=45, key="search_max_age")
            
            has_reports = st.selectbox("Con informes", ["Todos", "Solo con informes", "Solo sin informes"], key="search_reports")
            order_by = st.selectbox("Ordenar por", ["Última actualización", "Nombre", "Equipo", "Cantidad informes", "Edad"], key="search_order")

    # Mapear opciones UI a parámetros
    has_reports_param = None if has_reports == "Todos" else (True if has_reports == "Solo con informes" else False)
    order_mapping = {
        "Última actualización": "updated_at",
        "Nombre": "name", 
        "Equipo": "team",
        "Cantidad informes": "report_count",
        "Edad": "age"
    }
    order_param = order_mapping[order_by]

    # Ejecutar búsqueda optimizada
    players = db.search_players_advanced(
        query=q,
        team=team_filter,
        position=pos_filter,
        nationality=nationality_filter,
        min_age=min_age if min_age > 15 else None,
        max_age=max_age if max_age < 45 else None,
        has_reports=has_reports_param,
        limit=100,
        order_by=order_param
    )

    # === PAGINACIÓN ===
    if len(players) == 100:  # Límite alcanzado
        st.warning("⚠️ Mostrando primeros 100 resultados. Usa filtros más específicos para ver todos.")

    # === ESTADÍSTICAS DE BÚSQUEDA ===
    if players:
        col_stats1, col_stats2, col_stats3 = st.columns(3)
        
        with col_stats1:
            st.metric("Resultados", len(players))
        
        with col_stats2:
            con_informes = len([p for p in players if p.get("report_count", 0) > 0])
            st.metric("Con informes", con_informes)
        
        with col_stats3:
            if players:
                edad_promedio = sum(p.get("age", 0) for p in players if p.get("age")) / max(1, len([p for p in players if p.get("age")]))
                st.metric("Edad promedio", f"{edad_promedio:.1f} años")

    # Ejecutar búsqueda optimizada CON KEYWORD ARGUMENTS
    try:
        players = db.search_players_advanced(
            query=q or "",
            team=team_filter or "",
            position=pos_filter or "",
            nationality=nationality_filter or "",
            min_age=min_age if min_age > 15 else None,
            max_age=max_age if max_age < 45 else None,
            has_reports=has_reports_param,
            limit=100,
            order_by=order_param
        )
    except Exception as e:
        # Fallback a búsqueda simple si hay algún error
        st.warning(f"🔄 Usando búsqueda básica: {e}")
        players = db.search_players(q or "", limit=50)
        players = sorted(players, key=lambda r: (r.get("name") or "").lower())

    if not players:
        st.info("Sin resultados.")
    else:
        cols = st.columns(3, gap="small")   # grid 3 columnas
        for idx, p in enumerate(players):
            col = cols[idx % 3]
            with col:
                # Tarjeta consistente con el sistema de diseño
                st.markdown(create_player_card(p), unsafe_allow_html=True)
                c1, c2 = st.columns(2)
                with c1:
                    # Botón PERFIL (usa session_state -> switch_page)
                    if st.button("🔎 Perfil", key=f"profile_{p['id']}"):
                        st.session_state["__go_profile_pid"] = int(p["id"])
                        st.switch_page("pages/4_Perfil_Jugador.py")
                with c2:
                    # Botón NUEVO INFORME preseleccionando nombre/equipo (opcional)
                    if st.button("➕ Nuevo informe", key=f"newrep_{p['id']}"):
                        # Si quieres pre-rellenar nombre/equipo, guárdalos en session_state
                        st.session_state["prefill_name"] = p.get("name","")
                        st.session_state["prefill_team"] = p.get("team","")
                        st.switch_page("pages/3_Informes.py")

                # Informes recientes de ese jugador
                reports = db.list_reports(player_id=p["id"], limit=5)
                if not reports:
                    st.caption("Sin informes.")
                else:
                    with st.expander("Informes recientes", expanded=False):
                        for r in reports:
                            r_label = f"{r.get('season','?')} · {r.get('match_date','')} · {r['user']} · {r.get('recommendation','?')} ({r.get('confidence','?')}%)"
                            row1, row2 = st.columns([1, 3])
                            with row1:
                                if st.button("✏️ Editar", key=f"edit_{p['id']}_{r['id']}"):
                                    # Navega “dentro” de la misma página pasando report_id por la URL
                                    st.query_params.clear()
                                    st.query_params["report_id"] = str(r["id"])
                                    st.rerun()
                            with row2:
                                st.write(r_label)
