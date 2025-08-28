# utils/matches_adapter.py
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

# Importa tu scraper base
from utils.besoccer_scraper import BeSoccerScraper, BeSoccerAlineacionesScraper

_scraper = BeSoccerScraper()
_alineas = BeSoccerAlineacionesScraper()

def _tokens(filtro: str) -> list[str]:
    return [t.strip().lower() for t in (filtro or "").split(",") if t.strip()]

def list_matches_by_date(fecha: date, liga_filtro: str = "") -> List[Dict]:
    """
    Devuelve una lista normalizada de partidos para la fecha dada.
    Aplica filtro por competiciones (contains, tokens separados por coma).
    Campos clave en cada dict:
      - equipo_local, equipo_visitante
      - competicion
      - hora (string)
      - besoccer_id (str)
      - url_completa (str)
      - fecha (YYYY-MM-DD)
      - escudo_local, escudo_visitante (si el scraper los saca; si no, None)
    """
    fecha_str = fecha.strftime("%Y-%m-%d")
    partidos = _scraper.obtener_partidos_por_fecha(fecha_str) or []

    toks = _tokens(liga_filtro)
    if toks:
        filtrados = []
        for p in partidos:
            comp = (p.get("competicion") or p.get("liga") or "").lower()
            if any(tok in comp for tok in toks):
                filtrados.append(p)
        partidos = filtrados

    # Asegura consistencia de claves que usa la UI
    out = []
    for p in partidos:
        out.append({
            "equipo_local": p.get("equipo_local") or p.get("local"),
            "equipo_visitante": p.get("equipo_visitante") or p.get("visitante"),
            "competicion": p.get("competicion") or p.get("liga"),
            "hora": p.get("hora") or p.get("status"),
            "besoccer_id": str(p.get("besoccer_id") or p.get("id") or ""),
            "url_completa": p.get("url_completa") or p.get("url") or "",
            "fecha": p.get("fecha") or fecha_str,
            "escudo_local": p.get("escudo_local"),
            "escudo_visitante": p.get("escudo_visitante"),
        })
    return out

def get_lineups_for_match(
    *,
    besoccer_id: Optional[str] = None,
    url_partido: Optional[str] = None,
    equipo_local: Optional[str] = None,
    equipo_visitante: Optional[str] = None,
    fecha_partido: Optional[str] = None,
) -> Dict:
    """
    Puerta única a las alineaciones. Encapsula el método del scraper y
    acepta los mismos kwargs que vas a pasar desde la página.
    Devuelve un dict con:
      - encontrado (bool)
      - metodo (str)
      - alineacion_local [ {nombre, numero, posicion, imagen_url, url_besoccer, es_titular} ... ]
      - alineacion_visitante [ ... ]
    """
    return _alineas.obtener_alineaciones_partido(
        match_id=besoccer_id,
        url_partido=url_partido,
        equipo_local=equipo_local,
        equipo_visitante=equipo_visitante,
        fecha_partido=fecha_partido,
    )