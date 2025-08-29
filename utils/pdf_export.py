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
    Devuelve una nota única por informe.
    Si existe report['final_score'] úsala; si no, promedia los valores numéricos de ratings_json.
    """
    # 1) final_score explícita
    fs = report.get("final_score") or report.get("score") or report.get("nota") or None
    if fs is not None:
        v = _safe_float(fs)
        if v is not None:
            return v

    # 2) promedio de ratings_json
    ratings = report.get("ratings") or report.get("ratings_json")
    if isinstance(ratings, dict) and ratings:
        vals = [_safe_float(v) for v in ratings.values()]
        vals = [v for v in vals if v is not None]
        if vals:
            return float(mean(vals))
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
    PDF individual (placeholder). No depende de IA.
    """
    r = db.get_report(report_id)
    p = db.get_player(player_id)
    if not r or not p:
        raise ValueError("Jugador o informe no encontrado")

    scout = r.get("created_by") or r.get("user") or r.get("author") or "?"
    match_date = r.get("match_date") or r.get("date") or r.get("created_at") or "?"
    opponent = r.get("opponent") or r.get("rival") or r.get("team") or "?"
    minutes = r.get("minutes_observed") or r.get("minutes") or r.get("min") or "?"
    reco = r.get("recommendation") or r.get("reco") or r.get("decision") or "?"
    conf = r.get("confidence") or r.get("conf") or r.get("confidence_pct") or "?"
    notes = r.get("notes") or r.get("observations") or "—"

    title = f"Informe individual — {p.get('name','Jugador')} (ID {player_id})"
    lines = [
        f"Informe #{r['id']} · Scout: {scout} · Fecha: {match_date}",
        f"Rival: {opponent} · Minutos observados: {minutes}",
        f"Recomendación: {reco} · Confianza: {conf}",
        "",
        "Notas:",
        str(notes)[:2000],
    ]
    _write_pdf_minimal(out_path, title, lines)
    return out_path

def build_player_summary_pdf(db, player_id: int, out_path: str, *, ollama_model: Optional[str] = None) -> str:
    """
    PDF resumen de TODOS los informes con IA (si disponible).
    """
    p = db.get_player(player_id)
    reps = db.get_reports_for_player(player_id, limit=500)
    if not p:
        raise ValueError("Jugador no encontrado")

    # Montar blob de notas
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
    summary = _summarize_reports_structured(notes_blob, model=ollama_model)

    # Render
    c = canvas.Canvas(out_path, pagesize=A4)
    w, h = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawString(2*cm, h-2*cm, f"Resumen de Informes — {p.get('name','')}")
    c.setFont("Helvetica", 12)
    c.drawString(2*cm, h-3*cm, f"Total de informes: {len(reps)}")

    y = h - 4*cm
    left = 2*cm
    right_limit = w - 2*cm
    max_text_width = right_limit - left

    # Bloque 1: Fortalezas
    c.setFont("Helvetica-Bold", 12)
    c.drawString(left, y, "Fortalezas recurrentes")
    y -= 0.5*cm
    y = _draw_bulleted_list(c, left, y, summary.get("fortalezas", []), max_text_width)

    # Bloque 2: Aspectos a mejorar
    y -= 0.3*cm
    c.setFont("Helvetica-Bold", 12)
    if y < 2*cm: c.showPage(); y = h - 2*cm
    c.drawString(left, y, "Aspectos a mejorar")
    y -= 0.5*cm
    y = _draw_bulleted_list(c, left, y, summary.get("mejoras", []), max_text_width)

    # Bloque 3: Evolución
    y -= 0.3*cm
    c.setFont("Helvetica-Bold", 12)
    if y < 2*cm: c.showPage(); y = h - 2*cm
    c.drawString(left, y, "Evolución")
    y -= 0.5*cm
    y = _draw_bulleted_list(c, left, y, summary.get("evolucion", []), max_text_width)

    c.showPage()
    c.save()
    return out_path

# Export explícito (opcional, por claridad)
__all__ = ["build_player_report_pdf", "build_player_summary_pdf"]
