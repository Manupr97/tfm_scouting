# utils/simple_logging.py
import os
from datetime import datetime
from typing import Optional

class SimpleLogger:
    """Logger simple que evita conflictos con Streamlit watchdog"""
    
    def __init__(self, name: str = "scouting"):
        self.name = name
        self.log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
        
        # Crear directorio si no existe (sin makedirs recursivo)
        if not os.path.exists(self.log_dir):
            try:
                os.mkdir(self.log_dir)
            except:
                self.log_dir = os.path.dirname(os.path.dirname(__file__))  # fallback
        
        fecha = datetime.now().strftime("%Y%m%d")
        self.log_file = os.path.join(self.log_dir, f"{name}_{fecha}.log")
    
    def _write(self, level: str, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_line = f"{timestamp} | {level:8} | {self.name:12} | {message}\n"
        
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_line)
        except:
            pass  # Silencioso si falla
    
    def info(self, message: str): self._write("INFO", message)
    def warning(self, message: str): self._write("WARNING", message)
    def error(self, message: str): self._write("ERROR", message)
    def debug(self, message: str): self._write("DEBUG", message)

# Instancias globales
_loggers = {}

def get_logger(name: str) -> SimpleLogger:
    if name not in _loggers:
        _loggers[name] = SimpleLogger(name)
    return _loggers[name]