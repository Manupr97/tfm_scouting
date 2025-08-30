# database.py (versión thread-safe)
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime
from typing import Dict, List, Optional
import logging


class DatabaseManager:
    """
    Capa de acceso a datos para usuarios y presets de filtros.
    Abre una conexión por operación para evitar problemas de hilos en Streamlit.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._lock = threading.RLock()
        
        # ← CAMBIAR A LOGGING SIMPLE
        from utils.simple_logging import get_logger
        self.logger = get_logger("database")
        
        self._create_tables_if_missing()

    @staticmethod
    def calculate_age(birthdate_str: str | None) -> int | None:
        """Calcula edad actual desde birthdate en formato ISO (YYYY-MM-DD)"""
        if not birthdate_str:
            return None
        
        try:
            from datetime import date, datetime
            # Intentar formato ISO primero
            try:
                birth_date = datetime.strptime(birthdate_str, "%Y-%m-%d").date()
            except ValueError:
                # Fallback formato español
                birth_date = datetime.strptime(birthdate_str, "%d/%m/%Y").date()
            
            today = date.today()
            age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
            return age if age >= 0 else None
            
        except Exception:
            return None

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Modo WAL para lecturas/escrituras concurrentes más estables
        conn.execute("PRAGMA journal_mode=WAL;")
        # Integridad y rendimiento razonable
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA synchronous=NORMAL;")     # Balance seguridad/velocidad
        conn.execute("PRAGMA cache_size=10000;")       # Cache más grande
        conn.execute("PRAGMA temp_store=memory;")      # Tablas temp en RAM
        return conn
    
    def _create_tables_if_missing(self) -> None:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            # Tabla de usuarios
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL
                )
            """)
            # Tabla de configuraciones de filtros
            cur.execute("""
                CREATE TABLE IF NOT EXISTS filter_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user TEXT NOT NULL,
                    name TEXT NOT NULL,
                    columns_json TEXT NOT NULL,
                    filters_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            # Índice/único para upsert lógico
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS ux_filter_configs_user_name
                ON filter_configs(user, name)
            """)
            conn.commit()
            # --------- SCOUTED PLAYERS ----------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS scouted_players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                team TEXT DEFAULT '',
                position TEXT,
                nationality TEXT,
                birthdate TEXT DEFAULT '',
                age INTEGER,
                height_cm REAL,
                weight_kg REAL,
                foot TEXT,
                photo_url TEXT,
                source_url TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """)
            # --- columnas nuevas en scouted_players (idempotentes) ---
            try:
                cur.execute("ALTER TABLE scouted_players ADD COLUMN shirt_number INTEGER")
            except sqlite3.OperationalError:
                pass
            try:
                cur.execute("ALTER TABLE scouted_players ADD COLUMN value_keur INTEGER")
            except sqlite3.OperationalError:
                pass
            try:
                cur.execute("ALTER TABLE scouted_players ADD COLUMN elo INTEGER")
            except sqlite3.OperationalError:
                pass
            cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_scouted_players
            ON scouted_players(name, birthdate, team);
            """)
            # ---------- SCOUT REPORTS / FILES (tal y como ya lo tenías) ----------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS scout_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL,
                user TEXT NOT NULL,
                season TEXT,
                match_date TEXT,
                opponent TEXT,
                minutes_observed INTEGER,
                context_json TEXT NOT NULL,
                ratings_json TEXT NOT NULL,
                traits_json TEXT,
                notes TEXT,
                recommendation TEXT,
                confidence INTEGER,
                links_json TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY(player_id) REFERENCES scouted_players(id) ON DELETE CASCADE
            )
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS report_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                label TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY(report_id) REFERENCES scout_reports(id) ON DELETE CASCADE
            )
            """)
            # ---------- PLAYER CAREER ----------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS player_career (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            season TEXT NOT NULL,
            club TEXT NOT NULL,
            competition TEXT DEFAULT '',       -- usamos '' en lugar de NULL
            pj INTEGER, goles INTEGER, asist INTEGER,
            ta INTEGER, tr INTEGER,
            pt INTEGER, ps INTEGER, min INTEGER,
            edad INTEGER, pts REAL, elo INTEGER,
            raw_json TEXT,
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(player_id) REFERENCES scouted_players(id) ON DELETE CASCADE
            );
            """)
            cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_player_career
            ON player_career(player_id, season, club, competition);
            """)

    # === Helpers internos ===
    def _json_dumps(self, obj) -> str:
        return json.dumps(obj, ensure_ascii=False)

    def upsert_scouted_player(self, *, name: str, team: str|None=None, position: str|None=None,
                  nationality: str|None=None, birthdate: str|None=None,
                  height_cm: float|None=None, weight_kg: float|None=None, foot: str|None=None,
                  photo_url: str|None=None, source_url: str|None=None,
                  shirt_number: int|None=None, value_keur: int|None=None, elo: int|None=None) -> int:
    
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            
            # PRIORIDAD 1: Buscar por source_url (identificador más confiable)
            if source_url and source_url.strip():
                cur.execute("SELECT id FROM scouted_players WHERE source_url = ?", (source_url.strip(),))
                row = cur.fetchone()
                if row:
                    pid = int(row["id"])
                    self._update_existing_player(cur, pid, locals())
                    conn.commit()
                    return pid
            
            # PRIORIDAD 2: Buscar por nombre + fecha nacimiento (sin equipo)
            if name and birthdate:
                cur.execute("""
                    SELECT id FROM scouted_players
                    WHERE LOWER(TRIM(name)) = LOWER(TRIM(?)) 
                    AND COALESCE(TRIM(birthdate),'') = COALESCE(TRIM(?), '')
                """, (name, birthdate))
                row = cur.fetchone()
                if row:
                    pid = int(row["id"])
                    self._update_existing_player(cur, pid, locals())
                    conn.commit()
                    return pid
            
            # PRIORIDAD 3: Buscar solo por nombre (caso riesgoso - avisar)
            if name:
                cur.execute("""
                    SELECT id, name, team, birthdate FROM scouted_players
                    WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))
                """, (name,))
                rows = cur.fetchall()
                
                if rows:
                    # Si hay múltiples coincidencias, loggear para revisión manual
                    if len(rows) > 1:
                        self.logger.warning(f"DUPLICADO POTENCIAL: {len(rows)} jugadores con nombre '{name}'. IDs: {[r['id'] for r in rows]}")
                    
                    # Tomar el más reciente (por updated_at)
                    cur.execute("""
                        SELECT id FROM scouted_players
                        WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))
                        ORDER BY updated_at DESC LIMIT 1
                    """, (name,))
                    row = cur.fetchone()
                    if row:
                        pid = int(row["id"])
                        self.logger.info(f"PLAYER_FOUND_BY_URL: pid={pid}, url={source_url}")
                        conn.commit()
                        return pid
                    
                    # Al crear nuevo jugador:
                    new_id = int(cur.lastrowid)
                    self.logger.info(f"PLAYER_CREATED: pid={new_id}, name='{name}', source_url='{source_url or 'None'}'")
                    return new_id
            
            # PRIORIDAD 4: Crear nuevo registro
            cur.execute("""
                INSERT INTO scouted_players
                    (name, team, position, nationality, birthdate, height_cm, weight_kg,
                    foot, photo_url, source_url, shirt_number, value_keur, elo)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (name, team, position, nationality, birthdate, height_cm, weight_kg,
                foot, photo_url, source_url, shirt_number, value_keur, elo))
            conn.commit()
            new_id = int(cur.lastrowid)
            
            if self.logger:
                self.logger.info(f"NUEVO JUGADOR creado: ID={new_id}, name='{name}', source_url='{source_url}'")
            
            return new_id

    def _update_existing_player(self, cur, player_id: int, data: dict) -> None:
        """Helper para actualizar jugador existente sin sobrescribir con None/vacío"""
        cur.execute("""
            UPDATE scouted_players
            SET team        = COALESCE(NULLIF(TRIM(?), ''), team),
                position    = COALESCE(NULLIF(TRIM(?), ''), position),
                nationality = COALESCE(NULLIF(TRIM(?), ''), nationality),
                birthdate   = COALESCE(NULLIF(TRIM(?), ''), birthdate),
                height_cm   = COALESCE(?, height_cm),
                weight_kg   = COALESCE(?, weight_kg),
                foot        = COALESCE(NULLIF(TRIM(?), ''), foot),
                photo_url   = COALESCE(NULLIF(TRIM(?), ''), photo_url),
                source_url  = COALESCE(NULLIF(TRIM(?), ''), source_url),
                shirt_number= COALESCE(?, shirt_number),
                value_keur  = COALESCE(?, value_keur),
                elo         = COALESCE(?, elo),
                updated_at  = datetime('now')
            WHERE id = ?
        """, (
            data.get('team'), data.get('position'), data.get('nationality'), 
            data.get('birthdate'), data.get('height_cm'), data.get('weight_kg'), 
            data.get('foot'), data.get('photo_url'), data.get('source_url'),
            data.get('shirt_number'), data.get('value_keur'), data.get('elo'),
            player_id
        ))

    def sync_player_with_id(self, player_id: int, *, name: str=None, team: str=None, position: str=None,
                       nationality: str=None, birthdate: str=None,
                       height_cm: float=None, weight_kg: float=None, foot: str=None,
                       photo_url: str=None, source_url: str=None,
                       shirt_number: int=None, value_keur: int=None, elo: int=None) -> None:
        """Actualiza un jugador existente por ID específico."""
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE scouted_players
                SET name        = COALESCE(?, name),
                    team        = COALESCE(NULLIF(?, ''), team),
                    position    = COALESCE(?, position),
                    nationality = COALESCE(?, nationality),
                    birthdate   = COALESCE(NULLIF(?, ''), birthdate),
                    height_cm   = COALESCE(?, height_cm),
                    weight_kg   = COALESCE(?, weight_kg),
                    foot        = COALESCE(?, foot),
                    photo_url   = COALESCE(?, photo_url),
                    source_url  = COALESCE(?, source_url),
                    shirt_number= COALESCE(?, shirt_number),
                    value_keur  = COALESCE(?, value_keur),
                    elo         = COALESCE(?, elo),
                    updated_at  = datetime('now')
                WHERE id = ?
            """, (name, team, position, nationality, birthdate, height_cm, weight_kg, foot,
                photo_url, source_url, shirt_number, value_keur, elo, player_id))
            conn.commit()

    def get_player(self, player_id: int) -> dict|None:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM scouted_players WHERE id = ?", (player_id,))
            row = cur.fetchone()
            if not row:
                return None
            
            player_data = dict(row)
            # Calcular edad automáticamente
            player_data["age"] = self.calculate_age(player_data.get("birthdate"))
            return player_data

    def _ensure_column(self, table: str, col: str, ddl: str):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(f"PRAGMA table_info({table})")
            cols = {r["name"] for r in cur.fetchall()}
            if col not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
                conn.commit()

    def set_player_photo_path(self, player_id: int, photo_path: str) -> None:
        # crea la columna si no existe
        self._ensure_column("scouted_players", "photo_path", "photo_path TEXT")
        with self._connect() as conn:
            conn.execute("UPDATE scouted_players SET photo_path = ?, updated_at = datetime('now') WHERE id = ?",
                        (photo_path, player_id))
            conn.commit()


    def search_players(self, q: str, limit: int = 50) -> list[dict]:
        pat = f"%{q}%"
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM scouted_players
                WHERE name LIKE ? OR COALESCE(team,'') LIKE ? OR COALESCE(nationality,'') LIKE ?
                ORDER BY updated_at DESC LIMIT ?
            """, (pat, pat, pat, limit))
            return [dict(r) for r in cur.fetchall()]
        
    def search_players_advanced(self, *, 
                           query: str = "", 
                           team: str = "", 
                           position: str = "",
                           nationality: str = "",
                           min_age: int = None,
                           max_age: int = None,
                           has_reports: bool = None,
                           limit: int = 50,
                           order_by: str = "updated_at") -> list[dict]:
        """Búsqueda avanzada con filtros SQL optimizados"""
        
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            
            # Query base con JOINs para reports si necesario
            base_query = """
                SELECT DISTINCT p.*, 
                    CASE WHEN p.birthdate IS NOT NULL 
                            THEN CAST((julianday('now') - julianday(p.birthdate)) / 365.25 AS INTEGER)
                            ELSE NULL END as age_calculated,
                    COUNT(r.id) as report_count
                FROM scouted_players p
                LEFT JOIN scout_reports r ON p.id = r.player_id
                WHERE 1=1
            """
            
            params = []
            
            # Filtros dinámicos
            if query.strip():
                base_query += " AND (LOWER(p.name) LIKE ? OR LOWER(COALESCE(p.team,'')) LIKE ? OR LOWER(COALESCE(p.nationality,'')) LIKE ?)"
                pattern = f"%{query.strip().lower()}%"
                params.extend([pattern, pattern, pattern])
            
            if team.strip():
                base_query += " AND LOWER(COALESCE(p.team,'')) LIKE ?"
                params.append(f"%{team.strip().lower()}%")
            
            if position.strip():
                base_query += " AND LOWER(COALESCE(p.position,'')) LIKE ?"
                params.append(f"%{position.strip().lower()}%")
            
            if nationality.strip():
                base_query += " AND LOWER(COALESCE(p.nationality,'')) LIKE ?"
                params.append(f"%{nationality.strip().lower()}%")
            
            # Filtros de edad usando birthdate
            if min_age is not None:
                base_query += " AND p.birthdate IS NOT NULL AND (julianday('now') - julianday(p.birthdate)) / 365.25 >= ?"
                params.append(float(min_age))
            
            if max_age is not None:
                base_query += " AND p.birthdate IS NOT NULL AND (julianday('now') - julianday(p.birthdate)) / 365.25 <= ?"
                params.append(float(max_age))
            
            # Filtro por existencia de informes
            if has_reports is not None:
                if has_reports:
                    base_query += " HAVING COUNT(r.id) > 0"
                else:
                    base_query += " HAVING COUNT(r.id) = 0"
            else:
                base_query += " GROUP BY p.id"
            
            # Ordenación segura
            valid_orders = {
                "name": "p.name COLLATE NOCASE", 
                "team": "COALESCE(p.team,'') COLLATE NOCASE", 
                "updated_at": "p.updated_at DESC",
                "report_count": "report_count DESC",
                "age": "age_calculated"
            }
            order_column = valid_orders.get(order_by, "p.updated_at DESC")
            base_query += f" ORDER BY {order_column}"
            
            base_query += " LIMIT ?"
            params.append(limit)
            
            try:
                cur.execute(base_query, params)
                rows = cur.fetchall()
                
                # Procesar resultados
                result = []
                for row in rows:
                    player_data = dict(row)
                    # Usar edad calculada en SQL
                    if player_data.get("age_calculated"):
                        player_data["age"] = int(player_data["age_calculated"])
                    else:
                        player_data["age"] = self.calculate_age(player_data.get("birthdate"))
                    
                    # Limpiar campos auxiliares
                    player_data.pop("age_calculated", None)
                    result.append(player_data)
                
                return result
                
            except Exception as e:
                self.logger.error(f"Error en search_players_advanced: {e}")
                # Fallback a búsqueda simple
                return self.search_players(query, limit)
        
    def upsert_player_career(self, *, player_id:int, season:str, club:str,
                     competition:str|None, data:dict, raw_json:str|None=None) -> None:
        fields = ["pj","goles","asist","ta","tr","pt","ps","min","edad","pts","elo"]
        vals = [data.get(k) for k in fields]
        comp_norm = competition or ""  # normalizamos para buscar
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id FROM player_career
                WHERE player_id=? AND season=? AND club=? AND COALESCE(competition,'')=?
            """, (player_id, season, club, comp_norm))
            row = cur.fetchone()
            if row:
                cur.execute(f"""
                    UPDATE player_career
                    SET competition=?,
                        pj=?, goles=?, asist=?, ta=?, tr=?, pt=?, ps=?, min=?, edad=?, pts=?, elo=?,
                        raw_json=?, updated_at=datetime('now')
                    WHERE id=?
                """, (competition, *vals, raw_json, row["id"]))
                self.logger.info(f"CAREER_UPDATE: player_id={player_id}, season={season}, club={club}")
            else:
                cur.execute(f"""
                    INSERT INTO player_career
                        (player_id, season, club, competition,
                        pj, goles, asist, ta, tr, pt, ps, min, edad, pts, elo, raw_json, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, ?, datetime('now'))
                """, (player_id, season, club, competition, *vals, raw_json))
                self.logger.info(f"CAREER_INSERT: player_id={player_id}, season={season}, club={club}")
            conn.commit()

    def get_player_career(self, player_id:int, include_competitions:bool=False) -> list[dict]:
        # CORREGIR: La condición WHERE estaba mal construida
        if include_competitions:
            where_clause = "1=1"  # Mostrar todas las filas
        else:
            where_clause = "COALESCE(competition, '') = ''"  # Solo filas sin competición específica
        
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(f"""
                SELECT season, club, competition, pj, goles, asist, ta, tr, pt, ps, min, edad, pts, elo
                FROM player_career
                WHERE player_id = ? AND {where_clause}
                ORDER BY season DESC, club ASC, COALESCE(competition,'') ASC
            """, (player_id,))
            rows = cur.fetchall()
        
        self.logger.debug(f"get_player_career: player_id={player_id}, include_competitions={include_competitions}, found={len(rows)} rows")
        return [dict(r) for r in rows]

    def get_reports_for_player(self, player_id:int, limit:int=20) -> list[dict]:
        return self.list_reports(player_id=player_id, limit=limit)

    def get_reports_by_player(self, player_id: int, limit: int = 200) -> list[dict]:
        """Alias de get_reports_for_player para compatibilidad con PDF export"""
        return self.get_reports_for_player(player_id, limit)
    
    # === Informes ===
    def create_report(self, *, player_id: int, user: str, season: str|None,
                    match_date: str|None, opponent: str|None, minutes_observed: int|None,
                    context: dict, ratings: dict, traits: list[str]|None,
                    notes: str|None, recommendation: str|None, confidence: int|None,
                    links: list[str]|None) -> int:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO scout_reports
                    (player_id, user, season, match_date, opponent, minutes_observed,
                    context_json, ratings_json, traits_json, notes, recommendation, confidence, links_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (player_id, user, season, match_date, opponent, minutes_observed,
                self._json_dumps(context), self._json_dumps(ratings),
                self._json_dumps(traits or []), notes, recommendation, confidence,
                self._json_dumps(links or [])))
            conn.commit()
            return int(cur.lastrowid)

    def update_report(self, report_id: int, **fields) -> None:
        # fields puede contener context, ratings, traits, notes, recommendation, confidence, links...
        m = []
        vals = []
        for k, v in fields.items():
            if k in ("context","ratings","traits","links"):
                m.append(f"{k}_json = ?"); vals.append(self._json_dumps(v))
            else:
                m.append(f"{k} = ?"); vals.append(v)
        m.append("updated_at = datetime('now')")
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute(f"UPDATE scout_reports SET {', '.join(m)} WHERE id = ?", (*vals, report_id))
            conn.commit()

    def get_report(self, report_id: int) -> dict|None:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM scout_reports WHERE id = ?", (report_id,))
            row = cur.fetchone()
        if not row: return None
        r = dict(row)
        for k in ("context_json","ratings_json","traits_json","links_json"):
            if k in r and r[k] is not None:
                r[k.replace("_json","")] = json.loads(r.pop(k))
        return r

    def list_reports(self, *, user: str|None=None, player_id: int|None=None, limit: int = 100) -> list[dict]:
        q = "SELECT * FROM scout_reports WHERE 1=1"
        params=[]
        if user: q += " AND user = ?"; params.append(user)
        if player_id is not None: q += " AND player_id = ?"; params.append(player_id)
        q += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute(q, tuple(params))
            rows = cur.fetchall()
        out=[]
        for row in rows:
            r=dict(row)
            for k in ("context_json","ratings_json","traits_json","links_json"):
                if k in r and r[k] is not None:
                    r[k.replace("_json","")] = json.loads(r.pop(k))
            out.append(r)
        return out

    # === Adjuntos ===
    def add_report_file(self, report_id: int, file_path: str, label: str|None=None) -> int:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO report_files (report_id, file_path, label) VALUES (?,?,?)",
                        (report_id, file_path, label))
            conn.commit()
            return int(cur.lastrowid)

    def get_report_files(self, report_id: int) -> list[dict]:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM report_files WHERE report_id = ? ORDER BY created_at DESC", (report_id,))
            return [dict(r) for r in cur.fetchall()]

    def list_video_links_for_player(self, player_id:int) -> list[str]:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT links_json FROM scout_reports WHERE player_id=? ORDER BY created_at DESC", (player_id,))
            urls=set()
            for r in cur.fetchall():
                if r["links_json"]:
                    try:
                        for u in json.loads(r["links_json"]):
                            if u: urls.add(u.strip())
                    except Exception:
                        pass
        return sorted(urls)

    # ------------------- Gestión de usuarios -------------------
    def create_user(self, username: str, password_hash: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, password_hash),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def get_user_password(self, username: str) -> Optional[str]:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
            row = cur.fetchone()
            return row["password_hash"] if row else None

    # ----------- Gestión de configuraciones de filtros ----------
    def save_filter_config(
        self,
        user: str,
        name: str,
        columns: List[str],
        filters: Dict[str, Dict[str, object]]
    ) -> int:
        columns_json = json.dumps(columns)
        filters_json = json.dumps(filters)

        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            # UPSERT por (user, name)
            cur.execute(
                """
                INSERT INTO filter_configs (user, name, columns_json, filters_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user, name) DO UPDATE SET
                    columns_json = excluded.columns_json,
                    filters_json = excluded.filters_json,
                    created_at = excluded.created_at
                """,
                (user, name, columns_json, filters_json, datetime.utcnow().isoformat()),
            )
            conn.commit()

            # Recuperar id estable de la fila
            cur.execute(
                "SELECT id FROM filter_configs WHERE user = ? AND name = ?",
                (user, name)
            )
            row = cur.fetchone()
            return int(row["id"]) if row else -1

    def get_filter_configs(self, user: str):
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, name, columns_json, filters_json
                FROM filter_configs
                WHERE user = ?
                ORDER BY created_at DESC
                """,
                (user,),
            )
            rows = cur.fetchall()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "columns": json.loads(r["columns_json"]),
                "filters": json.loads(r["filters_json"]),
            } for r in rows
        ]

    # PDF export (stubs, se implementarán en utils/pdf_export.py)
    def get_reports_by_player(self, player_id: int, limit: int = 200) -> list[dict]:
        return self.list_reports(player_id=player_id, limit=limit)

    # Método de compatibilidad; ya no hay conexión viva que cerrar
    def close(self) -> None:
        pass