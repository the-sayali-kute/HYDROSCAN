"""Small SQLite-backed analysis history for local-first HydroScan deployments."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def data_root() -> Path:
    override = os.environ.get("HYDROSCAN_DATA_DIR")
    root = Path(override).expanduser() if override else Path(__file__).resolve().parents[1] / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root


def database_path() -> Path:
    return data_root() / "hydroscan.sqlite3"


@contextmanager
def connect():
    connection = sqlite3.connect(database_path(), timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize() -> None:
    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY,
                report_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                observation_date TEXT,
                mode TEXT NOT NULL,
                area_label TEXT NOT NULL,
                threshold REAL NOT NULL,
                grid_signature TEXT,
                analysis_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS analyses_created_at_idx ON analyses(created_at DESC)"
        )


def save_analysis(analysis: dict[str, Any]) -> None:
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO analyses
                (id, report_id, created_at, observation_date, mode, area_label, threshold, grid_signature, analysis_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                report_id = excluded.report_id,
                created_at = excluded.created_at,
                observation_date = excluded.observation_date,
                mode = excluded.mode,
                area_label = excluded.area_label,
                threshold = excluded.threshold,
                grid_signature = excluded.grid_signature,
                analysis_json = excluded.analysis_json
            """,
            (
                analysis["id"],
                analysis["reportId"],
                analysis["createdAt"],
                analysis.get("observationDate"),
                analysis["mode"],
                analysis["areaLabel"],
                analysis["threshold"],
                analysis.get("gridSignature"),
                json.dumps(analysis, separators=(",", ":"), allow_nan=False),
            ),
        )


def get_analysis(analysis_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT analysis_json FROM analyses WHERE id = ?", (analysis_id,)
        ).fetchone()
    if row is None:
        return None
    return json.loads(row["analysis_json"])


def list_analyses() -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT analysis_json FROM analyses ORDER BY created_at DESC"
        ).fetchall()
    return [json.loads(row["analysis_json"]) for row in rows]

