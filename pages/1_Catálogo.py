"""
Página de catálogo de jugadores
==============================

Esta página permite visualizar y filtrar los datos de los jugadores
provenientes de los ficheros Excel de Primera y Segunda Federación.  El
usuario puede seleccionar qué competiciones cargar, elegir qué
columnas mostrar y aplicar filtros por posición, edad y goles.  El
objetivo es facilitar al scout la búsqueda de perfiles específicos en
función de criterios básicos como posición, experiencia y rendimiento.

Para que esta página funcione correctamente, asegúrate de que los
ficheros ``data/wyscout_1RFEF_limpio.xlsx`` y
``data/wyscout_2RFEF_limpio.xlsx`` existen en el directorio ``data``.

Si tus ficheros se llaman de otra manera, actualiza el diccionario
``DATASETS`` más abajo.
"""

from __future__ import annotations

import json
from typing import Dict
import pandas as pd
import streamlit as st
import base64

# Importar el gestor de base de datos para poder guardar configuraciones de filtros
from models.database import DatabaseManager

# Mapeo de nombres legibles a rutas de archivos
DATASETS = {
    "Primera Federación": "data/wyscout_1RFEF_limpio.xlsx",
    "Segunda Federación": "data/wyscout_2RFEF_limpio.xlsx",
}


@st.cache_data(show_spinner=False)
def load_datasets(selected: list[str]) -> pd.DataFrame:
    """Carga los ficheros seleccionados y los combina en un solo DataFrame.

    Se añade una columna ``competicion`` indicando la procedencia de
    cada registro.

    Parameters
    ----------
    selected : list[str]
        Lista de nombres de competiciones a cargar (claves del diccionario
        ``DATASETS``).

    Returns
    -------
    pd.DataFrame
        DataFrame concatenado con todos los datos seleccionados.
    """
    frames = []
    for comp in selected:
        path = DATASETS.get(comp)
        if not path:
            continue
        df = pd.read_excel(path)
        df = df.copy()
        df["competicion"] = comp
        frames.append(df)
    if frames:
        return pd.concat(frames, ignore_index=True)
    return pd.DataFrame()


def show_catalogue_page() -> None:
    """Renderiza la página del catálogo con filtros y selección de columnas.

    Incluye un pequeño ajuste de CSS para que las etiquetas de selección
    (los elementos seleccionados en el multiselect) se muestren con un
    contraste adecuado sobre el fondo oscuro.  Este ajuste mejora la
    legibilidad de los filtros en un tema oscuro.
    """
    # Comprobar si el usuario ha iniciado sesión. Si no, mostrar advertencia
    # y detener la ejecución de la página.  Esto evita que usuarios no
    # autenticados accedan al catálogo de jugadores cuando navegan
    # directamente a la URL de la página desde el menú lateral.
    if "logged_in" not in st.session_state or not st.session_state.logged_in:
        st.warning("Debes iniciar sesión para acceder al catálogo de jugadores.")
        # Detener la ejecución para que no se carguen datos ni widgets
        st.stop()
    # Ajuste de estilo para las etiquetas seleccionadas en el multiselect, los sliders y
    # los encabezados de tablas.  Se inyecta CSS a nivel de página para asegurar que las
    # reglas se apliquen después de que Streamlit genere el HTML de los widgets.  El
    # selector `div[data-baseweb="tag"]` controla el fondo de las etiquetas en
    # `st.multiselect`.  Los selectores relacionados con `stSlider` y `stTickBar`
    # fuerzan el color del texto de los valores y ticks de los sliders a blanco.
    # Por último, los selectores para `thead th` aseguran que las cabeceras de las
    # tablas sean legibles en modo oscuro.
    st.markdown("""
        <style>
        /* Números de los sliders (min, max, valores seleccionados) */
        span[data-testid="stSliderValue"] {
            color: #fff !important;
        }
        div[role="slider"] span {
            color: #fff !important;
        }
        div[data-testid="stTickBar"] span {
            color: #fff !important;
        }
        /* Etiquetas y labels de sliders */
        .stSlider label, .stSlider * {
            color: #fff !important;
        }
        /* Cabeceras de tablas/dataframes */
        [data-testid="stDataFrame"] thead th {
            color: #fff !important;
            background-color: #2c2c2c !important;
        }
        .stDataFrame thead th, 
        .element-container [data-testid="column-header"] {
            color: #fff !important;
            background-color: #2c2c2c !important;
        }
        [data-testid="column-header"] * {
            color: #fff !important;
        }
        /* Barra del slider (track) en blanco */
        div[data-baseweb="slider"] > div > div {
            background: #fff !important;
        }
        </style>
        """, unsafe_allow_html=True)
    st.title("Catálogo de jugadores")
    st.write(
        "Explora los jugadores disponibles en nuestros datasets de Primera y Segunda Federación. "
        "Utiliza los filtros para acotar la búsqueda según tus necesidades."
    )
    # Selección de competiciones
    competitions = list(DATASETS.keys())
    selected_competitions = st.multiselect(
        "Elige competiciones a mostrar", competitions, default=competitions
    )
    if not selected_competitions:
        st.warning("Selecciona al menos una competición para cargar datos.")
        return
    # Cargar datos
    df = load_datasets(selected_competitions)
    if df.empty:
        st.warning("No se pudieron cargar datos. Revisa las rutas de los ficheros.")
        return
    # Determinar todas las columnas disponibles
    all_columns = df.columns.tolist()
    # Columnas básicas que siempre se mostrarán si están presentes
    # Fijamos un conjunto de columnas clave para el catálogo. Si alguna de estas no
    # está en el DataFrame, simplemente no se añade. Esto permite mantener un
    # esquema coherente: nombre del jugador, equipo, edad y estadísticas básicas.
    base_candidates = [
        "jugador",     # nombre o alias del jugador
        "nombre",      # en algunos datasets la columna puede llamarse 'nombre'
        "equipo",      # club al que pertenece
        "edad",        # edad del jugador
        "minutos",     # minutos jugados en la temporada
        "goles",       # goles anotados
    ]
    base_columns = [col for col in base_candidates if col in all_columns]
    # Permitir al usuario elegir columnas adicionales a mostrar (excluyendo las base)
    # Obtener valores predefinidos de columnas desde una configuración cargada
    # Si el usuario ha seleccionado previamente un preset, se almacenará en el estado de sesión
    preset_cols = st.session_state.get("preset_columns", [])
    with st.expander("Seleccionar columnas a mostrar", expanded=False):
        selected_columns = st.multiselect(
            "Columnas disponibles", options=[c for c in all_columns if c not in base_columns], default=preset_cols
        )
    # Columnas finales a mostrar (siempre incluir las base)
    columns_to_display = base_columns + selected_columns
    # Filtros dinámicos basados en las columnas seleccionadas
    filter_conditions: dict[str, tuple[str, object]] = {}

    # Recuperar filtros predefinidos si se seleccionó una configuración
    preset_filters: dict[str, dict[str, object]] = st.session_state.get("preset_filters", {})
    with st.expander("Filtros", expanded=False):
        # Distribuir los filtros en columnas para una interfaz más compacta
        cols_container = st.columns(3)
        filter_index = 0
        for col in columns_to_display:
            # No generar filtro para la ruta de la imagen ni para la imagen ya codificada
            if col in ["foto_path", "image_path", "Foto", "Foto_path"]:
                continue

            serie = df[col]
            # Seleccionamos la columna de disposición actual de forma circular
            current_col = cols_container[filter_index % len(cols_container)]

            # 1) Búsqueda por texto para columnas de nombre del jugador
            if col.lower() in ["jugador", "nombre"]:
                with current_col:
                    default_text = None
                    # Si existe un valor predefinido, usarlo como valor inicial
                    if col in preset_filters and preset_filters[col].get("type") == "contains":
                        default_text = str(preset_filters[col].get("value", ""))
                    text_value = st.text_input(f"Buscar {col}", value=default_text or "")
                    if text_value:
                        filter_conditions[col] = ("contains", text_value.lower())
                filter_index += 1
                continue

            # 2) Detectar columnas numéricas (int o float) o convertibles a numérico.
            is_numeric = False
            numeric_serie = None
            # Comprobar si la serie ya es de tipo numérico
            if pd.api.types.is_numeric_dtype(serie):
                is_numeric = True
                numeric_serie = pd.to_numeric(serie, errors='coerce')
            else:
                # Intentar convertir a numérico para detectar floats en strings
                tmp_numeric = pd.to_numeric(serie, errors='coerce')
                if tmp_numeric.notna().any():
                    is_numeric = True
                    numeric_serie = tmp_numeric

            if is_numeric:
                # Calcular el mínimo y máximo excluyendo NaN
                min_val = float(numeric_serie.min()) if not numeric_serie.dropna().empty else 0.0
                max_val = float(numeric_serie.max()) if not numeric_serie.dropna().empty else 0.0
                # Mostrar slider solo si hay rango
                if min_val != max_val:
                    # Definir paso: 1.0 para enteros, o paso relativo para floats
                    if pd.api.types.is_integer_dtype(numeric_serie.dropna()):
                        step_val = 1.0
                    else:
                        step_val = (max_val - min_val) / 100 if max_val != min_val else 0.1
                    with current_col:
                        # Si existe un valor predefinido para este slider, usarlo
                        default_range = (min_val, max_val)
                        if col in preset_filters and preset_filters[col].get("type") == "range":
                            try:
                                preset_range = preset_filters[col].get("value")
                                if preset_range and isinstance(preset_range, (list, tuple)) and len(preset_range) == 2:
                                    # Asegurarse de que el valor predefinido esté dentro del rango real
                                    low = float(max(min_val, float(preset_range[0])))
                                    high = float(min(max_val, float(preset_range[1])))
                                    default_range = (low, high)
                            except Exception:
                                pass
                        selected_range = st.slider(
                            f"Rango para {col}",
                            min_value=min_val,
                            max_value=max_val,
                            value=default_range,
                            step=step_val,
                        )
                        filter_conditions[col] = ("range", selected_range)
                filter_index += 1
                continue

            # 3) Columnas de texto o categóricas
            unique_values = serie.dropna().unique().tolist()
            # Para columnas con pocos valores únicos, usar multiselect
            if len(unique_values) <= 30:
                options = sorted(unique_values)
                with current_col:
                    # Utilizar opciones predefinidas si existen para esta columna
                    default_opts = options
                    if col in preset_filters and preset_filters[col].get("type") == "isin":
                        preset_vals = preset_filters[col].get("value", [])
                        # Mantener únicamente las opciones que siguen existiendo en el DataFrame
                        default_opts = [v for v in options if v in preset_vals] or options
                    selected_opts = st.multiselect(
                        f"Filtrar {col}", options=options, default=default_opts
                    )
                    filter_conditions[col] = ("isin", selected_opts)
                filter_index += 1
            # Para columnas con valores únicos moderados (hasta 100), también usar multiselect
            elif len(unique_values) <= 100:
                options = sorted(unique_values)
                with current_col:
                    default_opts = options
                    if col in preset_filters and preset_filters[col].get("type") == "isin":
                        preset_vals = preset_filters[col].get("value", [])
                        default_opts = [v for v in options if v in preset_vals] or options
                    selected_opts = st.multiselect(
                        f"Filtrar {col}", options=options, default=default_opts
                    )
                    filter_conditions[col] = ("isin", selected_opts)
                filter_index += 1
            else:
                # Para columnas con muchísimos valores únicos, usar búsqueda por texto
                with current_col:
                    default_search = None
                    if col in preset_filters and preset_filters[col].get("type") == "contains":
                        default_search = str(preset_filters[col].get("value", ""))
                    search_value = st.text_input(f"Buscar en {col}", value=default_search or "")
                    if search_value:
                        filter_conditions[col] = ("contains", search_value.lower())
                filter_index += 1
    # Aplicar filtros al DataFrame
    filtered_df = df.copy()
    for col, (cond_type, cond_value) in filter_conditions.items():
        if cond_type == "contains":
            filtered_df = filtered_df[
                filtered_df[col].astype(str).str.lower().str.contains(cond_value, na=False)
            ]
        elif cond_type == "isin":
            # Si ninguna opción seleccionada, no mostrar filas para esa columna
            if cond_value:
                filtered_df = filtered_df[filtered_df[col].isin(cond_value)]
        elif cond_type == "range":
            min_val, max_val = cond_value
            # Convertir a numérico si procede
            numeric_col = pd.to_numeric(filtered_df[col], errors='coerce')
            filtered_df = filtered_df[numeric_col.between(min_val, max_val)]
        else:
            # No filtrar si no se reconoce el tipo
            pass
    # Preparar visualización con imágenes si existe ruta
    display_df = filtered_df.copy()
    column_config = None
    if "foto_path" in display_df.columns:
        # Crear columna con imagen codificada en base64 solo para las filas filtradas
        def path_to_b64(path: str) -> str | None:
            try:
                with open(path, "rb") as img_f:
                    encoded = base64.b64encode(img_f.read()).decode()
                return f"data:image/png;base64,{encoded}"
            except Exception:
                return None
        display_df["Foto"] = display_df["foto_path"].apply(path_to_b64)
        # Si se va a mostrar la imagen, incluir en columnas a mostrar
        columns_display_final = ["Foto"] + [c for c in columns_to_display if c != "foto_path"]
        # Configurar columna de imagen
        column_config = {"Foto": st.column_config.ImageColumn(label="Foto", width="small")}
    else:
        columns_display_final = columns_to_display
    # Evitar repetir columnas si base y seleccionadas se solapan
    columns_display_final = list(dict.fromkeys(columns_display_final))
    # Mostrar resultados
    st.write(f"Resultados: {len(display_df)} jugadores")
    if column_config:
        st.dataframe(display_df[columns_display_final], column_config=column_config)
    else:
        st.dataframe(display_df[columns_display_final])

    # ------------------------------------------------------------------
    # Gestión de configuraciones de filtros
    # ------------------------------------------------------------------
    # Conectar con la base de datos (usando un recurso en caché)
    @st.cache_resource
    def get_db() -> DatabaseManager:
        # Guardar la base en el directorio data
        db_path = "data/scouting.db"
        return DatabaseManager(db_path)

    db = get_db()
    user = st.session_state.get("username", "") or "anon"

    # Recuperar configuraciones guardadas para el usuario
    configs = db.get_filter_configs(user)
    config_dict = {conf["name"]: conf for conf in configs}

    with st.expander("Configuraciones guardadas", expanded=False):
        if configs:
            selected_preset_name = st.selectbox(
                "Selecciona una configuración guardada",
                [""] + list(config_dict.keys()),
                format_func=lambda x: "(Selecciona)" if x == "" else x,
                key="preset_choice_simple",
            )
            if selected_preset_name and st.session_state.get("_last_preset_applied") != selected_preset_name:
                conf = config_dict[selected_preset_name]
                st.session_state["preset_columns"] = [
                    c for c in conf["columns"] if c not in base_columns
                ]
                st.session_state["preset_filters"] = conf["filters"]
                st.session_state["_last_preset_applied"] = selected_preset_name
                st.rerun()
        else:
            st.info("No tienes configuraciones guardadas")

    # Sección para guardar la configuración actual
    with st.expander("Guardar configuración actual", expanded=False):
        config_name = st.text_input("Nombre de la configuración", key="filter_config_name")
        if st.button("Guardar configuración"):
            if not config_name:
                st.error("Debes asignar un nombre a la configuración para guardarla")
            else:
                # Preparar lista de columnas a guardar (excluyendo bases duplicadas)
                columns_save = columns_to_display
                # Preparar filtros en formato serializable
                filters_save: Dict[str, Dict[str, object]] = {}
                for col, (cond_type, cond_val) in filter_conditions.items():
                    # Convertir tuplas a listas para JSON
                    if cond_type == "range":
                        # cond_val es un tuple (min, max)
                        filters_save[col] = {"type": cond_type, "value": [cond_val[0], cond_val[1]]}
                    else:
                        filters_save[col] = {"type": cond_type, "value": cond_val}
                # Guardar configuración en la base de datos
                db.save_filter_config(user, config_name, columns_save, filters_save)
                st.success(f"Configuración '{config_name}' guardada correctamente")

    # Limpiar valores predefinidos después de aplicar
    # Evitar que la configuración persista indefinidamente en el estado de sesión si el usuario
    # navega a otra página o cambia manualmente los filtros.  Al final de la página se borra.
    if "preset_columns" in st.session_state:
        st.session_state.pop("preset_columns")
    if "preset_filters" in st.session_state:
        st.session_state.pop("preset_filters")


# Ejecutar la página si se importa como módulo principal dentro de Streamlit
if __name__ == "__main__":
    show_catalogue_page()