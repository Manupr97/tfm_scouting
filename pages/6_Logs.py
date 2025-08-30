# pages/6_Logs.py
import streamlit as st
import os
import glob
from datetime import datetime

st.set_page_config(page_title="Logs", page_icon="📋", layout="wide")

if "logged_in" not in st.session_state or not st.session_state.logged_in:
    st.warning("Debes iniciar sesión para acceder a los logs.")
    st.stop()

st.title("📋 Logs del sistema")

log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")

# === LOGS BÁSICOS ===
if os.path.exists(log_dir):
    log_files = sorted([f for f in os.listdir(log_dir) if f.endswith('.log')], reverse=True)
    
    if log_files:
        selected_log = st.selectbox("Archivo de log", log_files)
        log_path = os.path.join(log_dir, selected_log)
        
        # Leer últimas líneas
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Mostrar últimas 100 líneas
            recent_lines = lines[-100:] if len(lines) > 100 else lines
            
            st.text_area(
                f"Últimas {len(recent_lines)} líneas de {selected_log}",
                value="".join(recent_lines),
                height=400
            )
            
            # Estadísticas básicas
            col1, col2, col3 = st.columns(3)
            col1.metric("Total líneas", len(lines))
            col2.metric("Errores", len([l for l in recent_lines if "ERROR" in l]))
            col3.metric("Advertencias", len([l for l in recent_lines if "WARNING" in l]))
            
        except Exception as e:
            st.error(f"Error leyendo log: {e}")
    else:
        st.info("No hay archivos de log.")
else:
    st.info("Directorio de logs no existe aún.")

# === LIMPIEZA SIMPLE ===
st.markdown("---")
if st.button("🗑️ Limpiar logs antiguos (>7 días)"):
    if os.path.exists(log_dir):
        try:
            import time
            limite = time.time() - (7 * 24 * 3600)
            eliminados = 0
            
            for archivo in os.listdir(log_dir):
                path = os.path.join(log_dir, archivo)
                if os.path.isfile(path) and os.path.getmtime(path) < limite:
                    os.unlink(path)
                    eliminados += 1
            
            st.success(f"✅ {eliminados} archivos eliminados")
            st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")