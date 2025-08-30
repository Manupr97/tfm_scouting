# utils/pdf_export.py
from __future__ import annotations
import os
from typing import Optional
import json
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
import math
import math
from statistics import mean, median

def _safe_float(x):
    try:
        return float(x)
    except Exception:
        return None

def _extract_report_score(report: dict) -> float | None:
    """
    Extrae nota promedio de las valoraciones de un informe.
    Los informes guardan las valoraciones en 'ratings' como dict anidado.
    """
    # 1) Buscar en ratings (estructura: {"categoria": {"metrica": valor}})
    ratings = report.get("ratings")
    if isinstance(ratings, dict) and ratings:
        all_values = []
        for category_dict in ratings.values():
            if isinstance(category_dict, dict):
                all_values.extend([v for v in category_dict.values() if isinstance(v, (int, float))])
        
        if all_values:
            return float(sum(all_values) / len(all_values))
    
    # 2) Fallback: buscar campos directos
    for field in ["final_score", "score", "nota", "rating"]:
        val = report.get(field)
        if val is not None:
            try:
                return float(val)
            except:
                continue
    
    return None

def _compute_score_summary(reports: list[dict]) -> dict:
    """
    Calcula estadísticas básicas de notas: count, mean, median, min, max.
    También genera una señal de tendencia simple comparando tercio inicial vs final.
    """
    points = []
    for r in reports:
        sc = _extract_report_score(r)
        if sc is not None:
            # Fecha ordenable
            when = r.get("match_date") or r.get("created_at") or ""
            points.append((when, sc, r.get("id")))
    # Orden por fecha ascendente (cadena ISO funciona; si no, va “best effort”)
    points.sort(key=lambda t: (t[0] or ""))
    scores = [p[1] for p in points]

    if not scores:
        return {
            "count": 0, "mean": None, "median": None, "min": None, "max": None,
            "trend": None, "series": points
        }

    n = len(scores)
    stats = {
        "count": n,
        "mean": round(mean(scores), 2),
        "median": round(median(scores), 2),
        "min": round(min(scores), 2),
        "max": round(max(scores), 2),
        "series": points
    }

    # Tendencia: comparar media del primer tercio vs último tercio
    k = max(1, n // 3)
    start_avg = mean(scores[:k])
    end_avg   = mean(scores[-k:])
    delta = end_avg - start_avg
    if abs(delta) < 0.05:  # umbral pequeño para no flipar por ruido
        trend = "estable"
    elif delta > 0:
        trend = "al alza"
    else:
        trend = "a la baja"
    stats["trend"] = trend
    stats["delta"] = round(delta, 2)
    return stats

def _fmt(val):
    return "—" if val is None else (f"{val:.2f}" if isinstance(val, (int, float)) else str(val))

# ---------- helpers locales, sin dependencias externas en import ----------
def _ensure_dir(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)

def _write_pdf_minimal(out_path: str, title: str, lines: list[str]) -> None:
    """
    Intenta con reportlab; si falla, intenta fpdf. Solo crea 1+ páginas con texto.
    Lanzará RuntimeError si no hay ninguna de las dos librerías.
    """
    # Opción 1: reportlab
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import cm
        _ensure_dir(out_path)
        c = canvas.Canvas(out_path, pagesize=A4)
        w, h = A4
        y = h - 2*cm
        c.setFont("Helvetica-Bold", 16)
        c.drawString(2*cm, y, title)
        y -= 1.2*cm
        c.setFont("Helvetica", 11)
        for line in lines:
            if y < 2*cm:
                c.showPage(); y = h - 2*cm; c.setFont("Helvetica", 11)
            c.drawString(2*cm, y, line)
            y -= 0.75*cm
        c.showPage(); c.save()
        return
    except Exception:
        pass

    # Opción 2: fpdf
    try:
        from fpdf import FPDF
        _ensure_dir(out_path)
        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_font("Arial", size=16)
        pdf.multi_cell(0, 10, txt=title)
        pdf.set_font("Arial", size=11)
        for line in lines:
            pdf.multi_cell(0, 8, txt=line)
        pdf.output(out_path)
        return
    except Exception as e:
        raise RuntimeError("No se pudo generar PDF. Instala 'reportlab' o 'fpdf'. Error: " + str(e))

# ---------- IA: configuración floater (no rompe import si no hay ollama) ----------
import subprocess, textwrap, os

DEFAULT_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
OLLAMA_HTTP_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")

def _run_ollama_cli(prompt: str, model: str) -> str:
    proc = subprocess.run(
        ["ollama", "run", model],
        input=prompt.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return proc.stdout.decode("utf-8", errors="ignore").strip()

def _run_ollama_http(prompt: str, model: str) -> str:
    import requests
    payload = {"model": model, "prompt": prompt, "stream": False}
    r = requests.post(OLLAMA_HTTP_URL, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    return (data.get("response") or data.get("message") or "").strip()

def _summarize_reports_structured(notes_blob: str, model: str | None = None,
                                  max_chars: int = 8000,
                                  score_context: dict | None = None) -> dict:
    """
    Pide a Ollama salida JSON con 3 claves: fortalezas, mejoras, evolucion.
    Le pasamos 'score_context' con estadísticas (mean/median/min/max/trend) para guiar la evolución.
    """
    if not notes_blob.strip():
        return {"fortalezas": [], "mejoras": [], "evolucion": []}

    model = model or DEFAULT_OLLAMA_MODEL
    score_ctx_txt = ""
    if score_context:
        score_ctx_txt = f"""
[CONTEXTO CUANTITATIVO]
- informes_con_nota: {score_context.get('count')}
- media: {score_context.get('mean')}
- mediana: {score_context.get('median')}
- min: {score_context.get('min')}
- max: {score_context.get('max')}
- tendencia: {score_context.get('trend')} (delta={score_context.get('delta')})
"""

    prompt = f"""
Eres un analista de scouting. Resume en ESPAÑOL las observaciones de varios informes de un mismo jugador.

{score_ctx_txt}

DEVUELVE EXCLUSIVAMENTE JSON VÁLIDO con este esquema, sin texto adicional ni markdown:
{{
  "fortalezas": ["punto 1", "punto 2", ...],
  "mejoras": ["punto 1", "punto 2", ...],
  "evolucion": ["punto 1", "punto 2", ...]
}}

INSTRUCCIONES ESPECÍFICAS:
- "fortalezas": SOLO aspectos POSITIVOS y virtudes del jugador
- "mejoras": SOLO aspectos NEGATIVOS, defectos o áreas donde debe mejorar
- "evolucion": cambios observados a lo largo del tiempo, progresión o regresión

Evita frases vacías. Si no hay evidencia, deja la lista vacía sin inventar.

[OBSERVACIONES A RESUMIR]
{notes_blob[:max_chars]}
""".strip()

    # 1º CLI
    try:
        raw = _run_ollama_cli(prompt, model)
        return json.loads(raw)
    except Exception:
        pass
    # 2º HTTP
    try:
        raw = _run_ollama_http(prompt, model)
        return json.loads(raw)
    except Exception as e:
        return {
            "fortalezas": [f"[Aviso] JSON no válido: {e}"],
            "mejoras": [],
            "evolucion": []
        }

def _draw_bulleted_list(c: canvas.Canvas, x: float, y: float, lines: list[str], max_width: float, line_h: float = 0.6*cm) -> float:
    """
    Dibuja viñetas simples (- •) con salto de página automático.
    Devuelve la Y actualizada.
    """
    w, h = A4
    c.setFont("Helvetica", 11)
    for item in lines or []:
        # Wrap manual básico
        words = str(item).split()
        current = ""
        bullet = "• "
        while words:
            while words and c.stringWidth(bullet + current + words[0], "Helvetica", 11) < max_width:
                current += ("" if current == "" else " ") + words.pop(0)
            text = bullet + current if bullet else current
            if y < 2*cm:
                c.showPage()
                y = h - 2*cm
                c.setFont("Helvetica", 11)
            c.drawString(x, y, text)
            y -= line_h
            current = ""
            bullet = ""  # solo en la primera línea ponemos la bola
        if current:  # último resto
            if y < 2*cm:
                c.showPage(); y = h - 2*cm; c.setFont("Helvetica", 11)
            c.drawString(x, y, ("• " + current).strip())
            y -= line_h
    return y

# ---------- API pública: las DOS funciones que importas ----------
def build_player_report_pdf(db, player_id: int, report_id: int, out_path: str) -> str:
    """
    PDF individual profesional con diseño del club
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor
    import os
    
    # Colores del club
    NEGRO = HexColor("#000000")
    NARANJA = HexColor("#FF6B35")  # Naranja vibrante
    GRIS_CLARO = HexColor("#F5F5F5")
    
    r = db.get_report(report_id)
    p = db.get_player(player_id)
    if not r or not p:
        raise ValueError("Jugador o informe no encontrado")

    _ensure_dir(out_path)
    c = canvas.Canvas(out_path, pagesize=A4)
    w, h = A4
    
    # === CABECERA CON BANDAS DE COLOR ===
    # Banda vertical naranja izquierda
    c.setFillColor(NARANJA)
    c.rect(0, 0, 0.8*cm, h, fill=1, stroke=0)
    
    # Banda vertical negra derecha
    c.setFillColor(NEGRO)
    c.rect(w-0.8*cm, 0, 0.8*cm, h, fill=1, stroke=0)
    
    # Logo del club (esquina superior izquierda)
    logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "Escudo CAC.png")
    if os.path.exists(logo_path):
        c.drawImage(logo_path, 1.5*cm, h-3*cm, width=2*cm, height=2*cm, preserveAspectRatio=True, mask='auto')
    
    # === TÍTULO PRINCIPAL CENTRADO ===
    c.setFillColor(NEGRO)
    c.setFont("Helvetica-Bold", 18)
    # Calcular posición centrada manualmente
    titulo = "INFORME DE SCOUTING"
    titulo_width = c.stringWidth(titulo, "Helvetica-Bold", 18)
    c.drawString((w - titulo_width) / 2, h-2*cm, titulo)

    c.setFont("Helvetica", 12)
    c.setFillColor(NARANJA)
    fecha_informe = r.get("match_date") or r.get("created_at", "")[:10] if r.get("created_at") else ""
    subtitulo = f"Fecha: {fecha_informe} | Scout: {r.get('user', r.get('created_by', '?'))}"
    subtitulo_width = c.stringWidth(subtitulo, "Helvetica", 12)
    c.drawString((w - subtitulo_width) / 2, h-2.5*cm, subtitulo)
    
    # === FOTO Y DATOS BÁSICOS DEL JUGADOR ===
    y_current = h - 4*cm
    
    # Foto del jugador - usar la misma lógica que en perfil del jugador
    foto_mostrada = False

    # 1. Intentar photo_path local
    photo_path = p.get("photo_path")
    if photo_path:
        abs_photo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), photo_path)
        if os.path.exists(abs_photo_path):
            try:
                c.drawImage(abs_photo_path, 1.5*cm, y_current-3*cm, width=3*cm, height=3*cm, preserveAspectRatio=True, mask='auto')
                foto_mostrada = True
            except Exception as e:
                print(f"Error cargando foto local: {e}")

    # 2. Si no, intentar photo_url (descargar temporalmente)
    if not foto_mostrada and p.get("photo_url"):
        try:
            import requests, tempfile
            response = requests.get(p["photo_url"], timeout=10)
            if response.status_code == 200:
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                    tmp_file.write(response.content)
                    tmp_path = tmp_file.name
                try:
                    c.drawImage(tmp_path, 1.5*cm, y_current-3*cm, width=3*cm, height=3*cm, preserveAspectRatio=True, mask='auto')
                    foto_mostrada = True
                except Exception as e:
                    print(f"Error cargando foto URL: {e}")
                finally:
                    os.unlink(tmp_path)  # Limpiar archivo temporal
        except Exception as e:
            print(f"Error descargando foto: {e}")

    # 3. Placeholder si no hay foto
    if not foto_mostrada:
        # Dibujar un rectángulo gris como placeholder
        c.setFillColor(HexColor("#CCCCCC"))
        c.rect(1.5*cm, y_current-3*cm, 3*cm, 3*cm, fill=1, stroke=1)
        c.setFillColor(HexColor("#666666"))
        c.setFont("Helvetica", 8)
        c.drawCentredText(3*cm, y_current-1.3*cm, "Sin foto")
        
    # Datos básicos (columna derecha de la foto) - más centrado
    c.setFillColor(NEGRO)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(5.5*cm, y_current, p.get('name', 'Jugador'))

    c.setFont("Helvetica", 11)
    y_data = y_current - 0.6*cm
    
    datos_basicos = [
        f"Equipo: {p.get('team', '-')}",
        f"Posición: {p.get('position', '-')}",
        f"Edad: {p.get('age', '-')} años",
        f"Altura: {p.get('height_cm', '-')} cm",
        f"Peso: {p.get('weight_kg', '-')} kg",
        f"Nacionalidad: {p.get('nationality', '-')}",
        f"Pie: {p.get('foot', '-')}",
        f"Dorsal: {p.get('shirt_number', '-')}",
        f"Valor: {p.get('value_keur', '-')} K€" if p.get('value_keur') else "Valor: -",
        f"ELO: {p.get('elo', '-')}" if p.get('elo') else "ELO: -"
    ]
    
    for i, dato in enumerate(datos_basicos):
        if i < 5:  # Primera columna
            c.drawString(5.5*cm, y_data - i*0.4*cm, dato)
        else:  # Segunda columna
            c.drawString(10.5*cm, y_data - (i-5)*0.4*cm, dato)

    # URL BeSoccer
    if p.get('source_url'):
        c.setFillColor(NARANJA)
        c.drawString(5.5*cm, y_data - 2.5*cm, f"Perfil: {p.get('source_url')}")
    
    # === CONTEXTO DEL INFORME ===
    y_current -= 5*cm

    # Título sección (formato estándar)
    c.setFillColor(NEGRO)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(1.5*cm, y_current, "CONTEXTO DEL PARTIDO")

    # Línea separadora naranja (formato estándar)
    c.setStrokeColor(NARANJA)
    c.setLineWidth(2)
    c.line(1.5*cm, y_current-0.2*cm, w-1.5*cm, y_current-0.2*cm)

    # Separación estándar después de línea
    y_current -= 0.8*cm
    c.setFillColor(NEGRO)
    c.setFont("Helvetica", 11)

    contexto_items = [
        f"Rival: {r.get('opponent', '-')}",
        f"Temporada: {r.get('season', '-')}",
        f"Minutos observados: {r.get('minutes_observed', '-')}",
        f"Recomendación: {r.get('recommendation', '-')}",
        f"Confianza: {r.get('confidence', '-')}%"
    ]

    # Mostrar en formato 2 filas x 3 columnas
    col_positions = [1.5*cm, 8*cm, 12.5*cm]  # 3 columnas
    for i, item in enumerate(contexto_items[:6]):  # Máximo 6 items
        row = i // 3  # Fila (0 o 1)
        col = i % 3   # Columna (0, 1 o 2)
        x_pos = col_positions[col]
        y_pos = y_current - (row * 0.5*cm)
        c.drawString(x_pos, y_pos, item)

    # Ajustar y_current después de las 2 filas
    y_current -= 1*cm if len(contexto_items) > 3 else 0.5*cm

    # === VALORACIONES POR CATEGORÍAS ===
    y_current -= 0.5*cm  # Separación entre secciones

    # Título sección (formato estándar)
    c.setFillColor(NEGRO)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(1.5*cm, y_current, "VALORACIONES")

    # Línea separadora naranja (formato estándar)
    c.setStrokeColor(NARANJA)
    c.setLineWidth(2)
    c.line(1.5*cm, y_current-0.2*cm, w-1.5*cm, y_current-0.2*cm)

    # Separación estándar después de línea
    y_current -= 0.8*cm

    ratings = r.get("ratings")
    if ratings and isinstance(ratings, dict):
        c.setFont("Helvetica", 11)
        
        for cat, metrics in ratings.items():
            if metrics and isinstance(metrics, dict):
                avg = sum(metrics.values()) / len(metrics)
                c.setFillColor(NEGRO)
                c.drawString(1.5*cm, y_current, f"{cat}: {avg:.1f}/10")
                
                # Separación correcta antes de detalles
                y_current -= 0.4*cm
                
                # Detalles de métricas
                c.setFillColor(HexColor("#666666"))
                c.setFont("Helvetica", 9)
                detalles = [f"{k}: {v}" for k, v in metrics.items()]
                detalle_text = " | ".join(detalles)
                c.drawString(2*cm, y_current, detalle_text[:100] + "..." if len(detalle_text) > 100 else detalle_text)
                
                # Separación entre categorías
                y_current -= 0.6*cm
                c.setFont("Helvetica", 11)

    # === RASGOS DESTACADOS ===
    y_current -= 0.5*cm  # Separación entre secciones

    # Título sección (formato estándar)
    c.setFillColor(NEGRO)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(1.5*cm, y_current, "RASGOS DESTACADOS")

    # Línea separadora naranja (formato estándar)
    c.setStrokeColor(NARANJA)
    c.setLineWidth(2)
    c.line(1.5*cm, y_current-0.2*cm, w-1.5*cm, y_current-0.2*cm)

    # Separación estándar después de línea
    y_current -= 0.8*cm

    traits = r.get("traits")
    if traits and isinstance(traits, list) and traits:
        c.setFont("Helvetica", 11)
        c.setFillColor(NARANJA)
        traits_text = " • ".join(traits)
        c.drawString(1.5*cm, y_current, traits_text)
        y_current -= 0.5*cm

    # === OBSERVACIONES ===
    y_current -= 0.5*cm  # Separación entre secciones

    # Título sección (formato estándar)
    c.setFillColor(NEGRO)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(1.5*cm, y_current, "OBSERVACIONES")

    # Línea separadora naranja (formato estándar)
    c.setStrokeColor(NARANJA)
    c.setLineWidth(2)
    c.line(1.5*cm, y_current-0.2*cm, w-1.5*cm, y_current-0.2*cm)

    # Separación estándar después de línea
    y_current -= 0.8*cm

    notes = r.get("notes")
    if notes:
        c.setFont("Helvetica", 11)
        c.setFillColor(NEGRO)
        
        # Dividir texto en líneas
        lines = str(notes).split('\n')
        for line in lines:
            if y_current < 2*cm:  # Nueva página si es necesario
                c.showPage()
                y_current = h - 2*cm
            c.drawString(1.5*cm, y_current, line[:90])  # Limitar ancho
            y_current -= 0.5*cm  # Interlineado consistente

    # === VIDEOS (si los hay) ===
    links = r.get("links")
    if links and isinstance(links, list) and links:
        if y_current < 3*cm:
            c.showPage()
            y_current = h - 2*cm
        
        y_current -= 0.5*cm  # Separación entre secciones
        
        # Título sección (formato estándar)
        c.setFillColor(NEGRO)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(1.5*cm, y_current, "VIDEOS DE REFERENCIA")
        
        # Línea separadora naranja (formato estándar)
        c.setStrokeColor(NARANJA)
        c.setLineWidth(2)
        c.line(1.5*cm, y_current-0.2*cm, w-1.5*cm, y_current-0.2*cm)
        
        # Separación estándar después de línea
        y_current -= 0.8*cm
        
        c.setFillColor(NARANJA)
        c.setFont("Helvetica", 9)
        for link in links[:3]:  # Máximo 3 links
            c.drawString(1.5*cm, y_current, link)
            y_current -= 0.5*cm

    c.save()
    return out_path

def build_player_summary_pdf(db, player_id: int, out_path: str, *, ollama_model: Optional[str] = None) -> str:
    """
    PDF resumen completo con todos los elementos
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.colors import HexColor
    import matplotlib.pyplot as plt
    import os, tempfile, requests
    
    # Colores del club
    NEGRO = HexColor("#000000")
    NARANJA = HexColor("#FF6B35")
    
    p = db.get_player(player_id)
    reps = db.get_reports_for_player(player_id, limit=500)
    if not p:
        raise ValueError("Jugador no encontrado")

    # Calcular estadísticas de puntuaciones
    stats = _compute_score_summary(reps)
    
    # Montar blob de notas para IA
    notes_list = []
    for r in reps:
        rid = r.get("id", "?")
        date = r.get("match_date") or r.get("created_at") or "?"
        opp = r.get("opponent") or r.get("rival") or "?"
        txt = r.get("notes") or r.get("observations") or ""
        if txt:
            notes_list.append(f"[Informe #{rid} · {date} · vs {opp}]\n{txt}\n")
    notes_blob = "\n".join(notes_list)

    # Resumen IA estructurado
    summary = _summarize_reports_structured(notes_blob, model=ollama_model, score_context=stats)

    _ensure_dir(out_path)
    c = canvas.Canvas(out_path, pagesize=A4)
    w, h = A4
    
    # === PÁGINA 1: CABECERA + DATOS JUGADOR ===
    # Bandas de color
    c.setFillColor(NARANJA)
    c.rect(0, 0, 0.8*cm, h, fill=1, stroke=0)
    c.setFillColor(NEGRO)
    c.rect(w-0.8*cm, 0, 0.8*cm, h, fill=1, stroke=0)
    
    # Logo del club
    logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "Escudo CAC.png")
    if os.path.exists(logo_path):
        c.drawImage(logo_path, 1.5*cm, h-3*cm, width=2*cm, height=2*cm, preserveAspectRatio=True, mask='auto')
    
    # Título centrado
    c.setFillColor(NEGRO)
    c.setFont("Helvetica-Bold", 18)
    titulo = f"Resumen de Informes — {p.get('name','')}"
    titulo_width = c.stringWidth(titulo, "Helvetica-Bold", 18)
    c.drawString((w - titulo_width) / 2, h-2*cm, titulo)
    
    # Estadísticas básicas - MEJORADAS
    c.setFont("Helvetica", 11)
    c.setFillColor(NARANJA)
    if stats["count"] > 0:
        estadisticas = f"Total: {stats['count']} informes | Media: {stats['mean']:.1f} | Máx: {stats['max']:.1f} | Mín: {stats['min']:.1f} | Tendencia: {stats.get('trend', 'N/A')}"
    else:
        estadisticas = f"Total: {len(reps)} informes | Sin valoraciones numéricas disponibles"
    
    stats_width = c.stringWidth(estadisticas, "Helvetica", 11)
    c.drawString((w - stats_width) / 2, h-2.5*cm, estadisticas)
    
    # === FOTO Y DATOS BÁSICOS (como en individual) ===
    y_current = h - 4*cm
    
    # Foto del jugador
    foto_mostrada = False
    photo_path = p.get("photo_path")
    if photo_path:
        abs_photo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), photo_path)
        if os.path.exists(abs_photo_path):
            try:
                c.drawImage(abs_photo_path, 1.5*cm, y_current-3*cm, width=3*cm, height=3*cm, preserveAspectRatio=True, mask='auto')
                foto_mostrada = True
            except:
                pass
    
    if not foto_mostrada and p.get("photo_url"):
        try:
            response = requests.get(p["photo_url"], timeout=10)
            if response.status_code == 200:
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                    tmp_file.write(response.content)
                    tmp_path = tmp_file.name
                try:
                    c.drawImage(tmp_path, 1.5*cm, y_current-3*cm, width=3*cm, height=3*cm, preserveAspectRatio=True, mask='auto')
                    foto_mostrada = True
                finally:
                    os.unlink(tmp_path)
        except:
            pass
    
    if not foto_mostrada:
        c.setFillColor(HexColor("#CCCCCC"))
        c.rect(1.5*cm, y_current-3*cm, 3*cm, 3*cm, fill=1, stroke=1)
        c.setFillColor(HexColor("#666666"))
        c.setFont("Helvetica", 8)
        c.drawString(2.8*cm, y_current-1.3*cm, "Sin foto")
    
    # Datos básicos del jugador
    c.setFillColor(NEGRO)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(5.5*cm, y_current, p.get('name', 'Jugador'))
    
    c.setFont("Helvetica", 10)
    y_data = y_current - 0.5*cm
    
    datos_basicos = [
        f"Equipo: {p.get('team', '-')}",
        f"Posición: {p.get('position', '-')}",
        f"Edad: {p.get('age', '-')} años",
        f"Altura: {p.get('height_cm', '-')} cm",
        f"Peso: {p.get('weight_kg', '-')} kg",
        f"Nacionalidad: {p.get('nationality', '-')}",
        f"Pie: {p.get('foot', '-')}",
        f"Dorsal: {p.get('shirt_number', '-')}",
        f"Valor: {p.get('value_keur', '-')} K€" if p.get('value_keur') else "Valor: -",
        f"ELO: {p.get('elo', '-')}" if p.get('elo') else "ELO: -"
    ]

    for i, dato in enumerate(datos_basicos):
        if i < 5:  # Primera columna
            c.drawString(5.5*cm, y_data - i*0.4*cm, dato)
        else:  # Segunda columna
            c.drawString(10.5*cm, y_data - (i-5)*0.4*cm, dato)

    # URL BeSoccer
    if p.get('source_url'):
        c.setFillColor(NARANJA)
        c.drawString(5.5*cm, y_data - 2.5*cm, f"Perfil: {p.get('source_url')}")
        c.setFillColor(NEGRO)
    
    y = y_current - 4*cm
    left = 1.5*cm
    max_text_width = w - 3*cm
    
    # === RESUMEN DE OBSERVACIONES ===
    if notes_blob:
        c.setFillColor(NEGRO)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(left, y, "RESUMEN DE OBSERVACIONES")
        c.setStrokeColor(NARANJA)
        c.setLineWidth(2)
        c.line(left, y-0.2*cm, w-1.5*cm, y-0.2*cm)
        y -= 0.8*cm
        
        # Crear resumen unificado inteligente
        c.setFont("Helvetica", 10)
        c.setFillColor(HexColor("#333333"))
        
        # Extraer frases clave de todos los informes
        frases_clave = []
        for r in reps:
            notas = r.get("notes", "")
            if notas:
                # Dividir en frases y tomar las más descriptivas
                frases = [f.strip() for f in notas.replace('\n', '. ').split('.') if len(f.strip()) > 10]
                frases_clave.extend(frases[:2])  # Máximo 2 frases por informe
        
        # Crear párrafo unificado
        resumen_unificado = f"En base a {len(reps)} informes analizados, el jugador demuestra consistencia en varios aspectos clave. "
        if frases_clave:
            # Unir las mejores frases, evitando repeticiones
            frases_unicas = []
            palabras_vistas = set()
            for frase in frases_clave:
                palabras = set(frase.lower().split())
                if not palabras.intersection(palabras_vistas):
                    frases_unicas.append(frase)
                    palabras_vistas.update(palabras)
                if len(frases_unicas) >= 3:
                    break
            
            resumen_unificado += ". ".join(frases_unicas[:3]) + "."
        
        # Mostrar resumen con salto de línea automático
        words = resumen_unificado.split()
        line = ""
        for word in words:
            test_line = line + (" " if line else "") + word
            if c.stringWidth(test_line, "Helvetica", 10) > max_text_width:
                if line:
                    c.drawString(left, y, line)
                    y -= 0.4*cm
                    line = word
                else:
                    c.drawString(left, y, word)
                    y -= 0.4*cm
            else:
                line = test_line
        
        if line:
            c.drawString(left, y, line)
            y -= 0.8*cm
    
    # === FORTALEZAS ===
    if y < 4*cm:
        c.showPage()
        y = h - 2*cm
        # Bandas en nueva página
        c.setFillColor(NARANJA)
        c.rect(0, 0, 0.8*cm, h, fill=1, stroke=0)
        c.setFillColor(NEGRO) 
        c.rect(w-0.8*cm, 0, 0.8*cm, h, fill=1, stroke=0)

    c.setFillColor(NEGRO)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(left, y, "FORTALEZAS RECURRENTES")
    c.setStrokeColor(NARANJA)
    c.setLineWidth(2)
    c.line(left, y-0.2*cm, w-1.5*cm, y-0.2*cm)
    y -= 0.8*cm

    # Fallback si la IA falla - extraer manualmente de las notas
    fortalezas = summary.get("fortalezas", [])
    if not fortalezas or any("JSON no válido" in str(f) for f in fortalezas):
        # Extraer palabras positivas clave de las notas
        texto_completo = notes_blob.lower()
        fortalezas_clave = []
        palabras_positivas = ["buena", "gran", "espectacular", "bien colocado", "atento", "equilibrio", "visión"]
        
        for palabra in palabras_positivas:
            if palabra in texto_completo:
                fortalezas_clave.append(palabra.capitalize())
        
        fortalezas = fortalezas_clave[:4] if fortalezas_clave else ["Datos insuficientes"]

    y = _draw_bulleted_list(c, left, y, fortalezas, max_text_width)

    # === ASPECTOS A MEJORAR ===
    y -= 0.5*cm
    c.setFillColor(NEGRO)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(left, y, "ASPECTOS A MEJORAR")
    c.setStrokeColor(NARANJA)
    c.line(left, y-0.2*cm, w-1.5*cm, y-0.2*cm)
    y -= 0.8*cm

    mejoras = summary.get("mejoras", [])
    if not mejoras:
        mejoras = ["Continuar desarrollo integral", "Mantener constancia"]

    y = _draw_bulleted_list(c, left, y, mejoras, max_text_width)

    # === EVOLUCIÓN ===
    y -= 0.5*cm
    c.setFillColor(NEGRO)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(left, y, "EVOLUCIÓN")
    c.setStrokeColor(NARANJA)
    c.line(left, y-0.2*cm, w-1.5*cm, y-0.2*cm)
    y -= 0.8*cm

    # Crear narrativa detallada de evolución
    if stats["count"] > 1:
        series = stats["series"]
        
        # Identificar mejor y peor informe
        mejor_idx = max(range(len(series)), key=lambda i: series[i][1])
        peor_idx = min(range(len(series)), key=lambda i: series[i][1])
        
        mejor_informe = next((r for r in reps if r.get("id") == series[mejor_idx][2]), None)
        peor_informe = next((r for r in reps if r.get("id") == series[peor_idx][2]), None)
        
        rival_mejor = mejor_informe.get("opponent", "un rival") if mejor_informe else "un rival"
        rival_peor = peor_informe.get("opponent", "otro rival") if peor_informe else "otro rival"
        
        # Construir narrativa
        narrativa_partes = []
        
        narrativa_partes.append(f"Desde el primer informe del jugador, este ha mostrado diferentes niveles de rendimiento.")
        
        if mejor_idx != peor_idx:
            narrativa_partes.append(f"Su mejor valoración ({series[mejor_idx][1]:.1f}) se obtuvo contra {rival_mejor}, mientras que la más baja ({series[peor_idx][1]:.1f}) fue ante {rival_peor}.")
        
        if stats.get("trend") == "al alza":
            narrativa_partes.append(f"La recogida de informes muestra una tendencia ascendente con puntuación media de {stats['mean']:.1f}, lo que hace del jugador una opción muy recomendada.")
        elif stats.get("trend") == "a la baja":
            narrativa_partes.append(f"Aunque hay una ligera tendencia descendente, mantiene una puntuación media de {stats['mean']:.1f}, requiriendo seguimiento continuado.")
        else:
            narrativa_partes.append(f"El jugador muestra consistencia con una puntuación regular de {stats['mean']:.1f}, demostrando estabilidad en su rendimiento.")
        
        narrativa_completa = " ".join(narrativa_partes)
        
    else:
        narrativa_completa = f"Con {stats['count']} informe disponible, se requieren más observaciones para establecer patrones de evolución claros."

    # Mostrar narrativa con salto de línea
    c.setFont("Helvetica", 10)
    words = narrativa_completa.split()
    line = ""
    for word in words:
        test_line = line + (" " if line else "") + word
        if c.stringWidth(test_line, "Helvetica", 10) > max_text_width:
            if line:
                c.drawString(left, y, line)
                y -= 0.4*cm
                line = word
            else:
                c.drawString(left, y, word)
                y -= 0.4*cm
        else:
            line = test_line

    if line:
        c.drawString(left, y, line)
        y -= 0.5*cm
    
    # === PÁGINA 2: GRÁFICAS (si hay datos suficientes) ===
    if stats["count"] > 1:
        c.showPage()
        
        # Bandas de color en nueva página
        c.setFillColor(NARANJA)
        c.rect(0, 0, 0.8*cm, h, fill=1, stroke=0)
        c.setFillColor(NEGRO)
        c.rect(w-0.8*cm, 0, 0.8*cm, h, fill=1, stroke=0)
        
        # Logo más pequeño en segunda página
        if os.path.exists(logo_path):
            c.drawImage(logo_path, 1.5*cm, h-2.5*cm, width=1.2*cm, height=1.2*cm, preserveAspectRatio=True, mask='auto')
        
        # Título de gráficas
        c.setFillColor(NEGRO)
        c.setFont("Helvetica-Bold", 14)
        titulo_graficas = "Evolución de Rendimiento"
        titulo_width = c.stringWidth(titulo_graficas, "Helvetica-Bold", 14)
        c.drawString((w - titulo_width) / 2, h-1.8*cm, titulo_graficas)
        
        # Generar gráficas
        try:
            import matplotlib.pyplot as plt
            plt.style.use('default')
            
            # === GRÁFICA 1: PUNTUACIONES ===
            fig1, ax1 = plt.subplots(figsize=(8, 4))
            fig1.patch.set_facecolor('white')
            ax1.set_facecolor('white')
            
            series = stats["series"]
            informes_num = list(range(1, len(series) + 1))
            scores = [s[1] for s in series]
            
            ax1.plot(informes_num, scores, color='#FF6B35', linewidth=3, marker='o', markersize=6)
            ax1.set_title('Evolución de Puntuaciones', fontsize=12, pad=15, color='#000000')
            ax1.set_xlabel('Informe', fontsize=10)
            ax1.set_ylabel('Puntuación', fontsize=10)
            ax1.grid(True, alpha=0.3)
            ax1.axhline(y=stats["mean"], color='#22c55e', linestyle='--', alpha=0.8, linewidth=2, label=f'Media: {stats["mean"]:.1f}')
            ax1.legend(loc='upper left')
            ax1.set_xticks(informes_num)
            
            plt.tight_layout()
            temp_graph1 = os.path.join(os.path.dirname(out_path), "temp_scores.png")
            plt.savefig(temp_graph1, dpi=120, bbox_inches='tight', facecolor='white')
            plt.close()
            
            # === GRÁFICA 2: ELO HISTÓRICO ===
            career_data = db.get_player_career(player_id, include_competitions=False)
            if len(career_data) > 1:
                fig2, ax2 = plt.subplots(figsize=(8, 4))
                fig2.patch.set_facecolor('white')
                ax2.set_facecolor('white')
                
                # Filtrar datos con ELO
                elo_data = [(d["season"], d["elo"]) for d in career_data if d.get("elo")]
                elo_data.sort(key=lambda x: x[0])  # Ordenar por temporada

                if len(elo_data) > 1:
                    seasons = [d[0] for d in elo_data]
                    elos = [d[1] for d in elo_data]
                    
                    ax2.plot(range(len(elos)), elos, color='#1f77b4', linewidth=3, marker='s', markersize=6)
                    ax2.set_title('Evolución ELO por Temporada', fontsize=12, pad=15)
                    ax2.set_xlabel('Temporada', fontsize=10)
                    ax2.set_ylabel('ELO', fontsize=10)
                    ax2.grid(True, alpha=0.3)
                    ax2.set_xticks(range(len(seasons)))
                    ax2.set_xticklabels(seasons, rotation=45, ha='right')
                    
                    plt.tight_layout()
                    temp_graph2 = os.path.join(os.path.dirname(out_path), "temp_elo.png")
                    plt.savefig(temp_graph2, dpi=120, bbox_inches='tight', facecolor='white')
                    plt.close()
                else:
                    temp_graph2 = None
            else:
                temp_graph2 = None
            
            # Insertar gráficas en PDF - tamaño más pequeño para hacer espacio a tabla
            y_pos = h - 3.5*cm

            # Gráfica de puntuaciones
            if os.path.exists(temp_graph1):
                c.drawImage(temp_graph1, 1.5*cm, y_pos - 6*cm, width=16*cm, height=5.5*cm)
                os.unlink(temp_graph1)
                y_pos -= 6.5*cm

            # Gráfica de ELO
            if temp_graph2 and os.path.exists(temp_graph2):
                c.drawImage(temp_graph2, 1.5*cm, y_pos - 6*cm, width=16*cm, height=5.5*cm)
                os.unlink(temp_graph2)
            
        except Exception as e:
            c.setFont("Helvetica", 10)
            c.setFillColor(HexColor("#666666"))
            c.drawString(1.5*cm, h-8*cm, f"Error generando gráficas: {str(e)}")

    # === TABLA DE TRAYECTORIA (fuera del if de gráficas) ===
    career = db.get_player_career(player_id, include_competitions=False)
    if career:
        # Si no hay segunda página, crearla
        if stats["count"] <= 1:
            c.showPage()
            # Bandas de color en nueva página
            c.setFillColor(NARANJA)
            c.rect(0, 0, 0.8*cm, h, fill=1, stroke=0)
            c.setFillColor(NEGRO)
            c.rect(w-0.8*cm, 0, 0.8*cm, h, fill=1, stroke=0)
        
        y_pos_tabla = max(h - 22*cm, 2*cm)
        
        c.setFillColor(NEGRO)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(1.5*cm, y_pos_tabla, "TRAYECTORIA PROFESIONAL")
        
        # Línea separadora naranja
        c.setStrokeColor(NARANJA)
        c.setLineWidth(2)
        c.line(1.5*cm, y_pos_tabla-0.2*cm, w-1.5*cm, y_pos_tabla-0.2*cm)
        
        y_pos_tabla -= 0.8*cm
        
        # Configuración de tabla compacta
        col_positions = [1.5*cm, 3.7*cm, 9.7*cm, 11.2*cm, 12.7*cm, 14.2*cm]
        headers = ["Temp.", "Club", "PJ", "PT", "G", "Min."]
        
        # Cabecera de tabla
        c.setFillColor(NEGRO)
        c.setFont("Helvetica-Bold", 9)
        for header, pos in zip(headers, col_positions):
            c.drawString(pos, y_pos_tabla, header)
        
        # Línea bajo cabecera
        y_pos_tabla -= 0.3*cm
        c.setStrokeColor(HexColor("#CCCCCC"))
        c.setLineWidth(1)
        c.line(1.5*cm, y_pos_tabla, w-1.5*cm, y_pos_tabla)
        
        # Datos de trayectoria (últimas 6 temporadas)
        c.setFont("Helvetica", 8)
        for i, season_data in enumerate(career[:6]):
            y_pos_tabla -= 0.35*cm
            
            # Fondo alternado para legibilidad
            if i % 2 == 1:
                c.setFillColor(HexColor("#F8F8F8"))
                c.rect(1.5*cm, y_pos_tabla-0.05*cm, w-3*cm, 0.25*cm, fill=1, stroke=0)
            
            c.setFillColor(NEGRO)
            
            # Preparar datos de fila
            club_name = season_data.get("club", "-")
            if len(club_name) > 25:
                club_name = club_name[:22] + "..."
            
            row_data = [
                season_data.get("season", "-"),
                club_name,
                str(int(season_data.get("pj", 0))) if season_data.get("pj") else "-",
                str(int(season_data.get("pt", 0))) if season_data.get("pt") else "-",
                str(int(season_data.get("goles", 0))) if season_data.get("goles") else "-",
                str(int(season_data.get("min", 0))) if season_data.get("min") else "-"
            ]
            
            # Dibujar fila
            for data, pos in zip(row_data, col_positions):
                c.drawString(pos, y_pos_tabla, data)
            
            # Parar si no hay más espacio
            if y_pos_tabla < 3*cm:
                break

    c.save()
    return out_path

# Export explícito (opcional, por claridad)
__all__ = ["build_player_report_pdf", "build_player_summary_pdf"]
