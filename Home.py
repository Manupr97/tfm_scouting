"""
Home.py
======

Punto de entrada para la aplicación de scouting del Club Atlético Central.

Este script implementa una interfaz de usuario basada en Streamlit con
autenticación básica y una página de inicio personalizada.  Se ha
incluido una configuración de colores corporativos (negro y blanco) y la
posibilidad de mostrar el escudo del club junto con el eslogan "#SoñarEsGratis".

Para ejecutar la aplicación localmente, activa tu entorno virtual y
ejecuta en la raíz del proyecto::

    streamlit run Home.py

"""

from __future__ import annotations
import base64
import os
from pathlib import Path
import time
import streamlit as st
from utils.auth import authenticate

# Inicializar logging al arrancar la app
from utils.simple_logging import get_logger
logger = get_logger("Home")  # ← AÑADIR NOMBRE

# ---------------------------------------------------------------------------
# Configuración inicial de la página
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Scouting - Club Atlético Central",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def load_image(image_path: str) -> bytes:
    """Read an image file and return its bytes.

    Parameters
    ----------
    image_path : str
        Ruta relativa al archivo de imagen.

    Returns
    -------
    bytes
        Contenido del archivo en formato binario.
    """
    with open(image_path, "rb") as f:
        return f.read()


def get_image_html(image_path: str, width: int = 200) -> str:
    """Devuelve un fragmento HTML para mostrar una imagen centrada.

    La imagen se codifica en base64 para incrustarla directamente en
    HTML. Si el archivo no existe, devuelve una cadena vacía.

    Parameters
    ----------
    image_path : str
        Ruta al archivo de la imagen.
    width : int
        Ancho de la imagen en píxeles.

    Returns
    -------
    str
        Etiqueta ``<img>`` con la imagen embebida o cadena vacía.
    """
    try:
        with open(image_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode()
        return f"<img src='data:image/png;base64,{encoded}' width='{width}' />"
    except FileNotFoundError:
        return ""

def show_splash_screen() -> None:
    """Muestra una pantalla de carga inicial con el escudo y el eslogan.

    Esta función utiliza un estado de sesión ``show_splash`` para
    determinar si debe mostrarse la pantalla de bienvenida.  Al
    reproducirse por primera vez, la función muestra el escudo y el
    eslogan centrados durante unos segundos, luego actualiza el
    estado y recarga la página mediante ``st.rerun()``.
    """
    if "show_splash" not in st.session_state:
        st.session_state.show_splash = True
    if st.session_state.show_splash:
        # Construir contenido HTML para el splash
        logo_path = Path(__file__).parent / "assets" / "Escudo CAC.png"
        logo_html = get_image_html(str(logo_path), width=200)
        splash_html = f"""
        <div id="splash-container" style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;">
            {logo_html if logo_html else ''}
            <h2 style="color:white;">#SoñarEsGratis</h2>
        </div>
        <style>
        #splash-container {{
            animation: fadeInOut 2s ease-in-out forwards;
        }}
        @keyframes fadeInOut {{
            0% {{ opacity: 0; }}
            50% {{ opacity: 1; }}
            100% {{ opacity: 0; }}
        }}
        </style>
        """
        st.markdown(splash_html, unsafe_allow_html=True)
        # Esperar a que se reproduzca la animación
        time.sleep(2)
        st.session_state.show_splash = False
        st.rerun()


# La función authenticate se importa desde utils.auth.  Se deja el alias
# para mantener compatibilidad con el resto de este módulo.



def login_form() -> None:
    """Mostrar el formulario de inicio de sesión centrado.

    Se coloca el escudo encima del formulario y se centra el contenido
    mediante columnas.  Utiliza el estado de sesión para almacenar
    ``logged_in``.  Cuando las credenciales son correctas, refresca la
    página con ``st.rerun()`` para evitar el doble clic.
    """
    st.markdown("""<h2 style='text-align:center;'>Iniciar sesión</h2>""", unsafe_allow_html=True)
    # Centrar el contenido
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        logo_path = Path(__file__).parent / "assets" / "Escudo CAC.png"
        logo_html = get_image_html(str(logo_path), width=150)
        if logo_html:
            # Renderizar imagen y eslogan centrados en HTML
            st.markdown(
                f"<div style='text-align:center'>{logo_html}</div>",
                unsafe_allow_html=True,
            )
        st.markdown(
            "<h4 style='text-align:center;'>#SoñarEsGratis</h4>",
            unsafe_allow_html=True,
        )
        st.write("Introduce tus credenciales para acceder a la aplicación.")
        with st.form("login_form"):
            username = st.text_input("Usuario", max_chars=50)
            password = st.text_input("Contraseña", type="password")
            submitted = st.form_submit_button("Acceder")
            if submitted:
                if authenticate(username, password):
                    st.success("Inicio de sesión correcto")
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    # Forzar recarga para evitar doble clic
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos")


def home_page() -> None:
    """Mostrar la página de inicio tras el inicio de sesión con contenido centrado."""
    # Centrar el contenido con columnas
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(
            """<h1 style='text-align:center;'>Inicio</h1>""",
            unsafe_allow_html=True,
        )
        st.markdown(
            """<h2 style='text-align:center;'>Club Atlético Central - Plataforma de Scouting</h2>""",
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <p style='text-align: justify;'>
            Bienvenido a la herramienta de scouting del Club Atlético Central. Esta plataforma ha sido diseñada
            para ofrecer a nuestro equipo de ojeadores una forma sencilla y eficiente de registrar y revisar
            informes de jugadores. Aquí podrás consultar el catálogo de jugadores, crear informes detallados
            y gestionar tu lista de observación.<br><br>

            El proyecto forma parte de tu Trabajo Fin de Máster y nace de la necesidad de optimizar los recursos
            de un club modesto. A partir de datos básicos y valoraciones subjetivas, buscamos evitar fichajes erróneos
            y centrarnos en talentos que se ajusten a nuestro estilo de juego y nuestras posibilidades económicas.
            </p>
            """,
            unsafe_allow_html=True,
        )
        # Mostrar logo centrado mediante HTML
        logo_path = Path(__file__).parent / "assets" / "Escudo CAC.png"
        logo_html = get_image_html(str(logo_path), width=200)
        if logo_html:
            st.markdown(
                f"<div style='text-align:center'>{logo_html}</div>",
                unsafe_allow_html=True,
            )
        else:
            st.warning(
                "No se encontró el archivo de logo. Asegúrate de colocar el escudo en 'assets/Escudo CAC.png'", 
            )
        # Mostrar eslogan centrado
        st.markdown(
            "<h3 style='text-align:center;'>#SoñarEsGratis</h3>",
            unsafe_allow_html=True,
        )


def main() -> None:
    """Función principal de la aplicación Streamlit."""
    # Mostrar splash screen si procede
    show_splash_screen()
    # Inicializar estado de sesión para autenticación
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.username = ""
    # Mostrar página según autenticación
    if st.session_state.logged_in:
        home_page()
    else:
        login_form()


if __name__ == "__main__":
    main()