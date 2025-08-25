"""
database.py
===============

This module defines a simple database layer for the web scouting application.

The goal is to encapsulate all SQLite operations behind a small API.  The
``DatabaseManager`` class opens a connection to a SQLite database file,
creates the necessary tables if they do not already exist and exposes
functions for importing player catalogues from Excel and for inserting
scouting reports.

Two primary data sources exist in this project:

* A **catalogue** of players scraped from Wyscout and stored in one or
  more Excel files.  These records include the player's unique ID,
  name, team, age, position and a relative path to their headshot
  image.  This information is considered read‑only.
* A collection of **scouting reports** created by users of the application.
  Reports may refer to players in the catalogue, but can also refer to
  completely new players.  Each report captures qualitative evaluations
  (e.g. technical, tactical, physical and mental scores), an overall
  recommendation and arbitrary notes.

Tables
------

``players_catalogue``
    Stores the data imported from the Excel catalogues.  Primary key is
    ``player_id``.  Columns mirror the fields present in the Excel files.

``observed_players``
    Aggregates scouting information about players not present in the
    catalogue.  Fields include a generated primary key, the player's
    name, team and other optional attributes (age, height, etc.) and
    aggregated statistics such as the number of reports and the average
    rating.

``reports``
    Stores individual scouting reports.  Each report may reference a
    player in the catalogue (via ``player_id``) or an observed player
    (via ``observed_player_id``).  Reports contain evaluation scores
    saved as JSON and additional fields such as the report date,
    comments and a recommendation.

All write operations commit their changes automatically.  When the
``DatabaseManager`` instance is destroyed, the underlying database
connection is closed.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd


class DatabaseManager:
    """Encapsulates a connection to an SQLite database and provides helper
    methods for reading and writing scouting data.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database file.  The file will be created if it
        does not already exist.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        # Create directory for the database if necessary
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row  # convenient row access as dict
        self._create_tables_if_missing()

    # ------------------------------------------------------------------
    # Table definitions
    # ------------------------------------------------------------------
    def _create_tables_if_missing(self) -> None:
        """Create tables on the first run if they don't already exist."""
        cur = self.conn.cursor()
        # Table for players from the Wyscout catalogue
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS players_catalogue (
                player_id TEXT PRIMARY KEY,
                nombre TEXT NOT NULL,
                equipo TEXT,
                posicion TEXT,
                edad INTEGER,
                nacionalidad TEXT,
                liga TEXT,
                minutos INTEGER,
                partidos INTEGER,
                goles INTEGER,
                asistencias INTEGER,
                tarjetas_amarillas INTEGER,
                tarjetas_rojas INTEGER,
                foto_path TEXT
            )
            """
        )
        # Table for players observed manually (not present in the catalogue)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS observed_players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                equipo TEXT,
                posicion TEXT,
                edad INTEGER,
                nacionalidad TEXT,
                altura REAL,
                peso REAL,
                liga TEXT,
                numero_informes INTEGER DEFAULT 0,
                nota_media REAL DEFAULT 0.0,
                nota_max REAL DEFAULT 0.0,
                nota_min REAL DEFAULT 0.0,
                ultima_fecha TEXT,
                foto_path TEXT
            )
            """
        )
        # Table for individual scouting reports
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id TEXT,
                observed_player_id INTEGER,
                scout TEXT NOT NULL,
                fecha TEXT NOT NULL,
                minutos INTEGER,
                tipo_evaluacion TEXT,
                nota_general REAL,
                potencial TEXT,
                recomendacion TEXT,
                fortalezas TEXT,
                debilidades TEXT,
                observaciones TEXT,
                metricas_json TEXT NOT NULL,
                FOREIGN KEY(player_id) REFERENCES players_catalogue(player_id),
                FOREIGN KEY(observed_player_id) REFERENCES observed_players(id)
            )
            """
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Catalogue import
    # ------------------------------------------------------------------
    def import_catalogue_from_excel(self, files: Iterable[str]) -> int:
        """Import one or more Excel files into the ``players_catalogue`` table.

        Each Excel file is expected to contain columns matching the table
        definition.  Rows with duplicate ``player_id`` values are skipped.

        Parameters
        ----------
        files : Iterable[str]
            Paths to Excel files to import.

        Returns
        -------
        int
            Number of new records inserted.
        """
        cur = self.conn.cursor()
        inserted = 0
        for file_path in files:
            df = pd.read_excel(file_path)
            # Ensure expected columns exist; if not, attempt to map them
            expected_cols = set([
                "player_id",
                "nombre",
                "equipo",
                "posicion",
                "edad",
                "nacionalidad",
                "liga",
                "minutos",
                "partidos",
                "goles",
                "asistencias",
                "tarjetas_amarillas",
                "tarjetas_rojas",
                "foto_path",
            ])
            missing = expected_cols - set(df.columns)
            if missing:
                raise ValueError(f"Missing columns {missing} in {file_path}")
            # Insert rows
            for _, row in df.iterrows():
                # Skip if player already exists
                cur.execute(
                    "SELECT 1 FROM players_catalogue WHERE player_id = ?",
                    (row["player_id"],),
                )
                if cur.fetchone():
                    continue
                cur.execute(
                    """
                    INSERT INTO players_catalogue (
                        player_id, nombre, equipo, posicion, edad,
                        nacionalidad, liga, minutos, partidos, goles,
                        asistencias, tarjetas_amarillas, tarjetas_rojas, foto_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["player_id"],
                        row["nombre"],
                        row["equipo"],
                        row["posicion"],
                        int(row["edad"]) if not pd.isna(row["edad"]) else None,
                        row["nacionalidad"],
                        row["liga"],
                        int(row["minutos"]) if not pd.isna(row["minutos"]) else None,
                        int(row["partidos"]) if not pd.isna(row["partidos"]) else None,
                        int(row["goles"]) if not pd.isna(row["goles"]) else None,
                        int(row["asistencias"]) if not pd.isna(row["asistencias"]) else None,
                        int(row["tarjetas_amarillas"]) if not pd.isna(row["tarjetas_amarillas"]) else None,
                        int(row["tarjetas_rojas"]) if not pd.isna(row["tarjetas_rojas"]) else None,
                        row["foto_path"],
                    ),
                )
                inserted += 1
        self.conn.commit()
        return inserted

    # ------------------------------------------------------------------
    # Report insertion
    # ------------------------------------------------------------------
    def add_report(
        self,
        *,
        scout: str,
        metricas: Dict[str, Dict[str, float]],
        nota_general: float,
        potencial: str,
        recomendacion: str,
        fortalezas: str,
        debilidades: str,
        observaciones: str,
        minutos: Optional[int] = None,
        tipo_evaluacion: str = "Completa",
        player_id: Optional[str] = None,
        observed_player_id: Optional[int] = None,
    ) -> int:
        """Insert a new scouting report into the database.

        Parameters
        ----------
        scout : str
            Username or identifier of the scout creating the report.
        metricas : Dict[str, Dict[str, float]]
            Dictionary of evaluation metrics organised by category (technical,
            tactical, physical, mental).  Values should be numeric scores.
        nota_general : float
            Overall rating assigned to the player.
        potencial : str
            Assessment of the player's potential (e.g. "Alto", "Medio").
        recomendacion : str
            Scout's recommendation (e.g. "Fichar", "Seguir observando").
        fortalezas : str
            Free‑text description of the player's strengths.
        debilidades : str
            Free‑text description of the player's weaknesses.
        observaciones : str
            Additional observations not captured elsewhere.
        minutos : Optional[int], optional
            Number of minutes observed.  May be left ``None`` if unknown.
        tipo_evaluacion : str, optional
            Name of the evaluation type, default "Completa".
        player_id : Optional[str], optional
            Reference to a player in the catalogue.  Provide this if the
            report concerns an existing player.
        observed_player_id : Optional[int], optional
            Reference to a player in the ``observed_players`` table.  Use
            when the player is not in the catalogue.  Exactly one of
            ``player_id`` or ``observed_player_id`` should be non‑null.

        Returns
        -------
        int
            The ID of the newly inserted report.
        """
        if (player_id is None) == (observed_player_id is None):
            raise ValueError(
                "Exactly one of player_id or observed_player_id must be provided"
            )
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO reports (
                player_id,
                observed_player_id,
                scout,
                fecha,
                minutos,
                tipo_evaluacion,
                nota_general,
                potencial,
                recomendacion,
                fortalezas,
                debilidades,
                observaciones,
                metricas_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                player_id,
                observed_player_id,
                scout,
                datetime.utcnow().isoformat(),
                minutos,
                tipo_evaluacion,
                nota_general,
                potencial,
                recomendacion,
                fortalezas,
                debilidades,
                observaciones,
                json.dumps(metricas),
            ),
        )
        report_id = cur.lastrowid
        # Update aggregate stats for observed players
        if observed_player_id is not None:
            self._update_observed_player_aggregates(observed_player_id, nota_general)
        self.conn.commit()
        return report_id

    # ------------------------------------------------------------------
    # Observed players management
    # ------------------------------------------------------------------
    def add_observed_player(
        self,
        *,
        nombre: str,
        equipo: Optional[str] = None,
        posicion: Optional[str] = None,
        edad: Optional[int] = None,
        nacionalidad: Optional[str] = None,
        altura: Optional[float] = None,
        peso: Optional[float] = None,
        liga: Optional[str] = None,
        foto_path: Optional[str] = None,
    ) -> int:
        """Insert a new observed player and return its generated ID."""
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO observed_players (
                nombre,
                equipo,
                posicion,
                edad,
                nacionalidad,
                altura,
                peso,
                liga,
                numero_informes,
                nota_media,
                nota_max,
                nota_min,
                ultima_fecha,
                foto_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0.0, 0.0, 0.0, NULL, ?)
            """,
            (
                nombre,
                equipo,
                posicion,
                edad,
                nacionalidad,
                altura,
                peso,
                liga,
                foto_path,
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def _update_observed_player_aggregates(self, observed_player_id: int, nota_general: float) -> None:
        """Recompute aggregate statistics for an observed player after a new report."""
        cur = self.conn.cursor()
        # Fetch current aggregates
        cur.execute(
            """
            SELECT numero_informes, nota_media, nota_max, nota_min
            FROM observed_players WHERE id = ?
            """,
            (observed_player_id,),
        )
        row = cur.fetchone()
        if row is None:
            return
        num = row["numero_informes"] + 1
        # Recalculate mean
        nueva_media = ((row["nota_media"] * row["numero_informes"]) + nota_general) / num
        nueva_max = max(row["nota_max"], nota_general) if row["numero_informes"] > 0 else nota_general
        nueva_min = (
            min(row["nota_min"], nota_general)
            if row["numero_informes"] > 0
            else nota_general
        )
        cur.execute(
            """
            UPDATE observed_players
            SET numero_informes = ?, nota_media = ?, nota_max = ?, nota_min = ?, ultima_fecha = ?
            WHERE id = ?
            """,
            (
                num,
                nueva_media,
                nueva_max,
                nueva_min,
                datetime.utcnow().isoformat(),
                observed_player_id,
            ),
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Query utilities
    # ------------------------------------------------------------------
    def get_catalogue_players(self) -> List[sqlite3.Row]:
        """Return all players from the catalogue."""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM players_catalogue")
        return cur.fetchall()

    def get_observed_players(self) -> List[sqlite3.Row]:
        """Return all observed players."""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM observed_players")
        return cur.fetchall()

    def get_reports(self) -> List[sqlite3.Row]:
        """Return all reports."""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM reports")
        return cur.fetchall()

    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()


__all__ = ["DatabaseManager"]