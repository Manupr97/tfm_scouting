CAC Web Scouting

Plataforma del Club Atlético Central para scouts, analistas, entrenadores y dirección deportiva. Permite hacer scouting de partidos y jugadores, combinar scraping con observación real, visualizar métricas (ELO, rendimiento por temporada) y generar informes PDF profesionales. Incluye un resumen automático con IA local (Ollama) para condensar múltiples informes en un documento manejable.

Funcionalidades clave

Catálogo y perfil de jugadores: foto, datos bio, equipo, pie, altura, peso, valor, ELO y trayectoria por temporada.

Informes de scouting: contexto del partido, valoraciones por categorías, notas del scout, enlaces de vídeo y adjuntos.

Scraping (BeSoccer) para pre-rellenar bio y carrera del jugador.

Descarga de informes:

Individual (un partido)

Resumen de todos los informes del jugador con IA (Ollama).

Visualizaciones: evolución de ELO, nota global y promedios por categoría.

Autenticación obligatoria.

Requisitos

Python ≥ 3.10

Ollama en local (servicio en http://localhost:11434) y un modelo instalado (ej. llama3)

Sistema operativo con permisos para crear data/scouting.db y data/exports/

Instalación rápida
# 1) Clonar
git clone <URL_DEL_REPO>
cd <carpeta_del_repo>

# 2) Entorno virtual
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows
.\.venv\Scripts\activate

# 3) Dependencias
pip install -r requirements.txt

# 4) Ollama (en otra terminal)
# Instalar y arrancar Ollama según tu SO
# Descargar el modelo (ejemplo):
ollama pull llama3

# 5) Ejecutar la app
streamlit run Home.py


La base de datos data/scouting.db se crea automáticamente al iniciar la app.

Uso básico

Login con tus credenciales (autenticación obligatoria).

Catálogo: busca jugadores y entra a su Perfil.

Informes: crea o edita informes de scouting (contexto, valoraciones, notas).

Descargar informes (en el perfil del jugador):

Individual: genera un PDF de ese reporte.

Resumen total: combina todos los informes del jugador y resume con IA. Añade gráficos de evolución (ELO, notas globales y por categorías).

Estructura del proyecto (resumen)
.
├─ Home.py                 # Entrada de la app (Streamlit)
├─ pages/
│  ├─ 1_Catálogo.py        # Búsqueda/listado de jugadores
│  ├─ 2_Scouting_Partidos.py
│  ├─ 3_Informes.py        # Creación/edición de informes
│  ├─ 4_Perfil_Jugador.py  # Perfil + pestaña "Descargar informes"
│  └─ 5_Visualizaciones.py
├─ models/
│  └─ database.py          # DatabaseManager (SQLite)
├─ utils/
│  ├─ scraping.py          # Helpers de scraping
│  ├─ besoccer_scraper.py  # Scraper específico BeSoccer
│  ├─ pdf_export.py        # Generación de PDFs + resumen IA (Ollama)
│  ├─ styles.py            # Estilos auxiliares
│  └─ simple_logging.py    # Logging básico
├─ assets/
│  ├─ Escudo CAC.png
│  └─ identidad_MPR_2.png  # Logo usado en este README
├─ data/
│  ├─ scouting.db          # BD (se genera en runtime)
│  └─ exports/             # PDFs generados
└─ requirements.txt

Notas sobre IA (Ollama)

La app llama al modelo local para resumir textos (notas de informes) en JSON estructurado (fortalezas, mejoras, evolución).

Asegúrate de que Ollama esté corriendo y el modelo esté descargado (ej. ollama pull llama3) antes de generar el Resumen de todos.

Desarrollo y contribuciones

Código en Streamlit con módulos separados para BD, scraping, PDFs y visualizaciones.

Se aceptan mejoras y PRs: limpieza de estados, optimización de scraping, nuevos modelos de IA local, más visualizaciones y métricas.