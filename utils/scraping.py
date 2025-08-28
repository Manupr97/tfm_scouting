# utils/scraping.py
from __future__ import annotations
import re, datetime as dt
from typing import Optional, Tuple, List, Dict

import requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0"}

MESES_ES = {
    "enero":1, "febrero":2, "marzo":3, "abril":4, "mayo":5, "junio":6,
    "julio":7, "agosto":8, "septiembre":9, "setiembre":9, "octubre":10,
    "noviembre":11, "diciembre":12,
}

def _sanitize_player_name(name: str | None) -> str | None:
    if not name:
        return None
    s = name.strip()
    
    # Extraer solo el nombre del jugador si viene con formato "Estadísticas Nombre Apellido, Club | ..."
    match = re.search(r"Estadísticas\s+(.+?),", s)
    if match:
        s = match.group(1).strip()
    
    # También manejar el caso "Nombre Apellido | BeSoccer"
    if " | BeSoccer" in s:
        s = s.replace(" | BeSoccer", "").strip()
    
    # Palabras que indican que no es un nombre válido
    bad_words = ["estadísticas", "trayectoria", "noticias", "besoccer"]
    if any(bad_word in s.lower() for bad_word in bad_words):
        return None
    
    # nombres absurdamente largos => descartar
    if len(s) > 60:
        return None
    
    # Nombres muy cortos también son sospechosos
    if len(s) < 2:
        return None
        
    return s

def upgrade_besoccer_img(url: str, size: int = 500) -> str | None:
    """
    Mejora las URLs de imágenes de BeSoccer (cdn.resfu.com) a más calidad.
    - fuerza size=<size>x
    - desactiva 'lossy'
    - intenta sustituir 'small/medium' por 'big' si existe
    """
    if not url:
        return None
    if "cdn.resfu.com" not in url:
        return url

    import re
    # sustituye cualquier size=###x por el solicitado
    url = re.sub(r"size=\d+x", f"size={size}x", url)
    if "size=" not in url:
        url += ("&" if "?" in url else "?") + f"size={size}x"

    # desactiva compresión con pérdida
    url = re.sub(r"lossy=\d", "lossy=0", url)
    if "lossy=" not in url:
        url += "&lossy=0"

    # si hay carpetas small/medium, intenta big
    url = url.replace("/small/", "/big/").replace("/medium/", "/big/")

    return url

def _num(x: Optional[str]) -> Optional[float]:
    """Convierte a número positivo (o None)."""
    if not x: return None
    s = re.sub(r"[^\d.]", "", str(x))
    if s == "": return None
    try:
        val = float(s)
        return val if val >= 0 else None
    except Exception:
        return None

def _text(el) -> str:
    return el.get_text(" ", strip=True) if el else ""

def _find_meta(soup: BeautifulSoup, prop: str) -> Optional[str]:
    tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
    return tag.get("content") if tag and tag.get("content") else None

def _fmt_iso(d: dt.date) -> str:
    return d.strftime("%Y-%m-%d")

def _parse_fecha_es(texto: str) -> Optional[str]:
    """
    'Nacido el 11 mayo 1988'  -> '1988-05-11'
    'Nacido el 17 junio 2003 en Sevilla' -> '2003-06-17'
    """
    m = re.search(r"Nacido el\s+(\d{1,2})\s+([A-Za-záéíóúñ]+)\s+(\d{4})", texto, re.I)
    if not m: 
        return None
    d = int(m.group(1))
    mes_nom = m.group(2).lower()
    mes = MESES_ES.get(mes_nom)
    anio = int(m.group(3))
    if not mes: 
        return None
    try:
        return _fmt_iso(dt.date(anio, mes, d))
    except Exception:
        return None

def parse_basic_profile(soup: BeautifulSoup, debug: bool=False) -> Dict:
    """
    Extrae: name, age, birthdate (ISO), nationality (nombre país), height_cm, weight_kg,
            position (abreviado si aparece), foot, photo_url.
    """
    bio = {}

    # 1) Nombre mejorado - buscar en diferentes lugares
    name_candidates = []
    
    # a) Título de la página pero limpiarlo
    og_title = _find_meta(soup, "og:title")
    if og_title:
        name_candidates.append(og_title)
    
    # b) H1 principal
    h1 = soup.find("h1")
    if h1:
        name_candidates.append(_text(h1))
    
    # c) Buscar en el breadcrumb o navegación
    breadcrumb = soup.select_one(".breadcrumb li:last-child")
    if breadcrumb:
        name_candidates.append(_text(breadcrumb))
    
    # Probar cada candidato hasta encontrar uno válido
    for candidate in name_candidates:
        clean_name = _sanitize_player_name(candidate)
        if clean_name:
            bio["name"] = clean_name
            break
    
    if debug and not bio.get("name"):
        print(f"[SCRAPER] No se pudo extraer nombre válido de: {name_candidates}")

    # 2) Foto del jugador
    img_player = soup.select_one(".img-container img[src*='img_data/players']")
    if img_player and img_player.get("src"):
        bio["photo_url"] = upgrade_besoccer_img(img_player["src"], size=500)
    else:
        # Fallback a los metas
        meta_img = _find_meta(soup, "og:image") or _find_meta(soup, "twitter:image")
        bio["photo_url"] = upgrade_besoccer_img(meta_img, size=500)

    # 3) Bloque superior de estadísticas (4 columnas)
    for stat in soup.select(".panel-body.stat-list .stat"):
        big = _text(stat.select_one(".big-row"))
        small = _text(stat.select_one(".small-row"))
        # nacionalidad (aparece como pequeño texto bajo la bandera)
        if small and small.lower() in ("españa","argentina","francia","italia","alemania","portugal", "croacia", "inglaterra") and big:
            bio["nationality"] = small
        # edad / kgs / cms
        if small.lower() == "años":
            bio["age"] = _num(big) and int(_num(big))
        elif small.lower() == "kgs":
            bio["weight_kg"] = _num(big)
        elif small.lower() == "cms":
            bio["height_cm"] = _num(big)
        # posición (abreviatura dentro de .round-row .bg-role)
        abbr = stat.select_one(".round-row.bg-role span")
        if abbr:
            bio["position"] = _text(abbr)

        smalls = [(_text(s) or "").strip() for s in stat.select(".small-row")]
        smalls_lower = [s.lower() for s in smalls]
        
        if ("m.€" in smalls_lower or "k.€" in smalls_lower) and big:
            try:
                val = float(big.replace(",", "."))
                if "m.€" in smalls_lower:
                    bio["value_keur"] = int(round(val * 1000))
                else:
                    bio["value_keur"] = int(round(val))
            except Exception:
                pass

        # ELO -> número dentro de .round-row span
        if any(s.upper() == "ELO" for s in smalls):
            sp = stat.select_one(".round-row span")
            if sp:
                elo_txt = sp.get_text(strip=True)
                if elo_txt.isdigit():
                    bio["elo"] = int(elo_txt)

        # Dorsal -> número dentro de .round-row span
        if "dorsal" in smalls_lower:
            sp = stat.select_one(".round-row span")
            if sp:
                d_txt = sp.get_text(strip=True)
                if d_txt.isdigit():
                    bio["shirt_number"] = int(d_txt)

    # Fallback nacionalidad por bandera (alt='es', 'fr'...)
    if not bio.get("nationality"):
        flag = soup.select_one(".img-container img.flag")
        if flag and flag.get("alt"):
            code = flag["alt"].lower().strip()
            NMAP = {
                "es":"España","ar":"Argentina","fr":"Francia","it":"Italia","de":"Alemania",
                "pt":"Portugal","br":"Brasil","gb":"Inglaterra","en":"Inglaterra","nl":"Países Bajos",
                "uy":"Uruguay","mx":"México","cl":"Chile","co":"Colombia","pe":"Perú",
            }
            bio["nationality"] = NMAP.get(code, code.upper())

    # 4) Tabla de "Datos personales"
    for row in soup.select(".panel-body.table-list .table-body .table-row"):
        key = _text(row.select_one("div"))
        val_el = row.select_one(".image-row") or row.select(".table-row > div")[-1] if row.select(".table-row > div") else None
        val = _text(val_el)
        if "Nacionalidad" in key and val:
            bio["nationality"] = val
        if "País nacimiento" in key and val and not bio.get("nationality"):
            bio["nationality"] = val
        if "Pie preferido" in key and val:
            bio["foot"] = val

    # 5) Fecha nacimiento (párrafo bajo stats)
    p = soup.select_one(".panel-body.ta-c p")
    if p:
        bd = _parse_fecha_es(_text(p))
        if bd: 
            bio["birthdate"] = bd

    if debug:
        print("[SCRAPER] BIO ->", bio)

    return bio

def parse_career_table(soup: BeautifulSoup, debug: bool=False) -> List[Dict]:
    """
    Tabla de trayectoria (padre/hijo). Devuelve filas con o sin 'competition'.
    """
    out: List[Dict] = []
    club = season = None

    for tr in soup.select(".team-result table.table_parents tbody tr"):
        cls = " ".join(tr.get("class", []))
        tds = tr.find_all("td")
        if "parent_row" in cls:
            # Fila agregada por club/temporada
            club = _text(tds[0].select_one("span")) or _text(tds[0])
            season = _text(tds[1]).strip()
            # Índices rápidos por data-content-tab
            val = {}
            # rendimiento (tprc1): PJ G A TA TR
            tpr = [x for x in tds if x.get("data-content-tab") == "tprc1"]
            if len(tpr) >= 5:
                val["pj"] = _num(_text(tpr[0])) or 0
                val["goles"] = _num(_text(tpr[1])) or 0
                val["asist"] = _num(_text(tpr[2])) or 0
                val["ta"] = _num(_text(tpr[3])) or 0
                val["tr"] = _num(_text(tpr[4])) or 0
            # participación (tptc1): PJ PT PS MIN
            tpt = [x for x in tds if x.get("data-content-tab") == "tptc1"]
            if len(tpt) >= 4:
                val["pj"] = _num(_text(tpt[0])) or val.get("pj", 0)
                val["pt"] = _num(_text(tpt[1])) or 0
                val["ps"] = _num(_text(tpt[2])) or 0
                val["min"] = _num(_text(tpt[3])) or 0
            # condición (tcdc1): Edad, Pts, ELO
            tcd = [x for x in tds if x.get("data-content-tab") == "tcdc1"]
            if len(tcd) >= 3:
                val["edad"] = _num(_text(tcd[0])) or None
                val["pts"] = _num(_text(tcd[1])) or None
                val["elo"] = _num(_text(tcd[2])) or None

            out.append({
                "season": season,
                "club": club,
                "competition": None,
                **val
            })

        elif "parent_son" in cls:
            # Detalle por competición (usa season/club vigentes)
            comp = _text(tds[0].select_one("span")) or _text(tds[0])
            val = {}
            tpr = [x for x in tds if x.get("data-content-tab") == "tprc1"]
            if len(tpr) >= 5:
                val["pj"] = _num(_text(tpr[0])) or 0
                val["goles"] = _num(_text(tpr[1])) or 0
                val["asist"] = _num(_text(tpr[2])) or 0
                val["ta"] = _num(_text(tpr[3])) or 0
                val["tr"] = _num(_text(tpr[4])) or 0
            tpt = [x for x in tds if x.get("data-content-tab") == "tptc1"]
            if len(tpt) >= 4:
                val["pj"] = _num(_text(tpt[0])) or val.get("pj", 0)
                val["pt"] = _num(_text(tpt[1])) or 0
                val["ps"] = _num(_text(tpt[2])) or 0
                val["min"] = _num(_text(tpt[3])) or 0
            tcd = [x for x in tds if x.get("data-content-tab") == "tcdc1"]
            if len(tcd) >= 3:
                val["edad"] = _num(_text(tcd[0])) or None
                val["pts"] = _num(_text(tcd[1])) or None
                val["elo"] = _num(_text(tcd[2])) or None

            out.append({
                "season": season,
                "club": club,
                "competition": comp,
                **val
            })

    if debug:
        print(f"[SCRAPER] CAREER rows: {len(out)}")
        for r in out[:5]:
            print("  ", r)
    return out

def scrape_player_full(url: str, debug: bool=False) -> Dict:
    """Devuelve {'bio': {...}, 'career':[...]}"""
    r = requests.get(url, timeout=15, headers=UA)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    bio = parse_basic_profile(soup, debug=debug)
    career = parse_career_table(soup, debug=debug)
    return {"bio": bio, "career": career}

def sync_player_to_db(db, url: str, player_id: int = None, debug: bool=False) -> int:
    """
    Scrapea BeSoccer y guarda bio + trayectoria. 
    Si player_id se pasa, actualiza ese registro específico.
    Devuelve player_id.
    """
    data = scrape_player_full(url, debug=debug)
    bio = data["bio"]
    if debug: 
        print("[SYNC] BIO IN:", bio)

    name = _sanitize_player_name(bio.get("name"))
    if not name:
        print("[SCRAPER] Nombre inválido detectado; abortando upsert.")
        return None

    bio["name"] = name

    if player_id:
        # Actualizar jugador específico
        db.sync_player_with_id(
            player_id,
            name=name.strip(),
            position=bio.get("position"),
            nationality=bio.get("nationality"),
            birthdate=bio.get("birthdate"),
            age=bio.get("age"),
            height_cm=bio.get("height_cm"),
            weight_kg=bio.get("weight_kg"),
            foot=bio.get("foot"),
            photo_url=bio.get("photo_url"),
            source_url=url,
            shirt_number=bio.get("shirt_number"),
            value_keur=bio.get("value_keur"),
            elo=bio.get("elo"),
        )
        pid = player_id
    else:
        # Buscar/crear jugador (sin team para evitar duplicados)
        pid = db.upsert_scouted_player(
            name=name.strip(),
            team=None,
            position=bio.get("position"),
            nationality=bio.get("nationality"),
            birthdate=bio.get("birthdate"),
            age=bio.get("age"),
            height_cm=bio.get("height_cm"),
            weight_kg=bio.get("weight_kg"),
            foot=bio.get("foot"),
            photo_url=bio.get("photo_url"),
            source_url=url,
            shirt_number=bio.get("shirt_number"),
            value_keur=bio.get("value_keur"),
            elo=bio.get("elo"),
        )

    # trayectoria
    for row in data["career"]:
        db.upsert_player_career(
            player_id=pid,
            season=row.get("season") or "",
            club=row.get("club") or "",
            competition=row.get("competition"),
            data=row,
            raw_json=None,
        )

    if debug:
        print(f"[SYNC] Guardado player_id={pid}, career_rows={len(data['career'])}")
        # AGREGAR ESTAS LÍNEAS DE DEBUG:
        saved_career = db.get_player_career(pid, include_competitions=True)
        print(f"[SYNC] CAREER verificación: {len(saved_career)} filas guardadas en BBDD")
        for i, row in enumerate(saved_career[:3]):
            print(f"[SYNC] CAREER[{i}]: {row}")
    return pid