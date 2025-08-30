#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Reset controlado de datos de jugadores e informes en SQLite.
- Crea backup del .db
- Detecta tablas relevantes (conocidas + heurística player_*/report_*)
- Borra en orden para respetar claves foráneas
- Vacuum para compactar
Uso:
  python tools/reset_player_data.py --db data/scouting.db --yes
  python tools/reset_player_data.py --dry-run
"""

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime

# Tablas conocidas (hijo -> padre) para borrar en orden seguro
KNOWN_ORDER = [
    # Hijas primero (dependen de reports/players)
    "report_files",
    # "report_tags", "report_links"  # si existieran
    "scout_reports",
    "player_career",
    # Padres al final
    "scouted_players",
]

# Heurística: todo lo que empiece por player_ o report_
HEURISTICS_PREFIX = ("player_", "report_")


def backup_db(db_path: str) -> str:
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"No existe la BD: {db_path}")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(os.path.dirname(db_path), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, f"{os.path.basename(db_path)}.{ts}.bak")
    shutil.copy2(db_path, backup_path)
    return backup_path


def list_tables(conn: sqlite3.Connection) -> list[str]:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return [r[0] for r in cur.fetchall()]


def compute_target_tables(conn: sqlite3.Connection) -> list[str]:
    existing = set(list_tables(conn))

    # 1) Intersección con conocidas
    targets = [t for t in KNOWN_ORDER if t in existing]

    # 2) Heurística: player_* y report_* que no estén ya
    guessed = [t for t in existing if t.startswith(HEURISTICS_PREFIX)]
    for t in guessed:
        if t not in targets:
            targets.append(t)

    # 3) Orden: primero las conocidas en su orden, luego el resto (por si acaso)
    ordered_known = [t for t in KNOWN_ORDER if t in targets]
    rest = [t for t in targets if t not in KNOWN_ORDER]
    # mover posibles tablas hijas por nombre (naive: *_files, *_links antes)
    rest_sorted = sorted(rest, key=lambda x: (not x.endswith("files"), not x.endswith("links"), x))

    final = ordered_known + rest_sorted
    # No tocar tablas internas de sqlite
    final = [t for t in final if not t.startswith("sqlite_")]
    return final


def wipe_tables(db_path: str, dry_run: bool = False) -> dict:
    """
    Devuelve {'planned': [...], 'done': [...]}.
    """
    result = {"planned": [], "done": []}
    conn = sqlite3.connect(db_path)
    try:
        conn.isolation_level = None  # control manual de transacción
        cur = conn.cursor()

        targets = compute_target_tables(conn)
        result["planned"] = targets.copy()

        if dry_run:
            return result

        # Desactivar FKs para borrado masivo controlado
        cur.execute("PRAGMA foreign_keys = OFF")
        cur.execute("BEGIN")

        for t in targets:
            # Borrado total de la tabla
            cur.execute(f"DELETE FROM {t}")
            result["done"].append(t)

        cur.execute("COMMIT")
        # Reactivar FKs
        cur.execute("PRAGMA foreign_keys = ON")

        # Compactar BD
        cur.execute("VACUUM")
    finally:
        conn.close()
    return result


def main():
    parser = argparse.ArgumentParser(description="Reset de datos de jugadores e informes (SQLite).")
    parser.add_argument("--db", default="data/scouting.db", help="Ruta a la BD SQLite (por defecto: data/scouting.db)")
    parser.add_argument("--yes", action="store_true", help="No pedir confirmación interactiva")
    parser.add_argument("--dry-run", action="store_true", help="No borra nada, solo muestra lo que haría")
    args = parser.parse_args()

    db_path = args.db

    if not os.path.exists(db_path):
        print(f"❌ No existe la BD en {db_path}")
        sys.exit(1)

    # Abrir para calcular plan
    conn = sqlite3.connect(db_path)
    try:
        targets = compute_target_tables(conn)
    finally:
        conn.close()

    if not targets:
        print("ℹ️ No se detectaron tablas de jugadores/informes para limpiar.")
        sys.exit(0)

    print("📋 Tablas que se van a vaciar (en orden):")
    for t in targets:
        print(f"  - {t}")

    if args.dry_run:
        print("\n✅ Dry run: no se borrará nada.")
        sys.exit(0)

    if not args.yes:
        print("\n⚠️ Esta operación borrará TODOS los datos de esas tablas.")
        conf = input("Escribe 'BORRAR' para confirmar: ").strip()
        if conf != "BORRAR":
            print("Operación cancelada.")
            sys.exit(1)

    # Backup
    backup_path = backup_db(db_path)
    print(f"💾 Backup creado: {backup_path}")

    # Wipe
    out = wipe_tables(db_path, dry_run=False)
    print("\n🧹 Tablas borradas:")
    for t in out["done"]:
        print(f"  - {t}")

    print("\n✅ Reset completado y BD compactada (VACUUM).")
    print("Si necesitas restaurar, sustituye el archivo por el backup creado.")

if __name__ == "__main__":
    main()
