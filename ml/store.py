"""ml/store.py  --  remember what was scored"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "observations.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    obs_id            TEXT PRIMARY KEY,
    site_id           TEXT NOT NULL,
    ts                TEXT NOT NULL,                -- ISO 8601, UTC, sortable
    narrative_sha1    TEXT NOT NULL,
    narrative         TEXT,                         -- NULL when SIF_STORE_TEXT=0
    sif_probability   REAL NOT NULL,
    band              TEXT,
    rules             TEXT NOT NULL DEFAULT '[]',   -- JSON array of IOGP rule ids
    model             TEXT,
    model_fingerprint TEXT,
    reported_by       TEXT,
    recorded_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_obs_site_ts ON observations (site_id, ts);
"""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def sha1(text: str) -> str:
    """Whitespace- and case-normalised, matching how the rest of the repo dedups."""
    return hashlib.sha1(" ".join(text.lower().split()).encode("utf-8")).hexdigest()


def to_iso(dt: datetime) -> str:
    """UTC, second resolution, always carrying an offset."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def parse_ts(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def store_text_enabled() -> bool:
    return os.getenv("SIF_STORE_TEXT", "1").lower() not in ("0", "false", "no")


class Store:
    """Append-only observation history."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else Path(os.getenv("SIF_STORE_DB") or DEFAULT_DB)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        if str(self.path) != ":memory:":
            self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def _insert(self, site_id: str, narrative: str, sif_probability: float,
                timestamp: datetime | str | None = None,
                rules: list[str] | None = None, band: str | None = None,
                model: str | None = None, model_fingerprint: str | None = None,
                reported_by: str | None = None) -> str:
        if isinstance(timestamp, str):
            when = parse_ts(timestamp)
        else:
            when = timestamp or utcnow()
        ts = to_iso(when)
        digest = sha1(narrative)
        obs_id = hashlib.sha1(f"{site_id}|{digest}|{ts}".encode("utf-8")).hexdigest()[:16]
        self.conn.execute(
            "INSERT OR IGNORE INTO observations (obs_id, site_id, ts, narrative_sha1,"
            " narrative, sif_probability, band, rules, model, model_fingerprint,"
            " reported_by, recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (obs_id, site_id, ts, digest,
             narrative if store_text_enabled() else None,
             float(sif_probability), band, json.dumps(sorted(rules or [])),
             model, model_fingerprint, reported_by, to_iso(utcnow())),
        )
        return obs_id

    def record(self, *args, **kwargs) -> str:
        """Record one scored report. Returns its obs_id. Repeat calls are no-ops."""
        obs_id = self._insert(*args, **kwargs)
        self.conn.commit()
        return obs_id

    def record_many(self, rows: list[dict]) -> list[str]:
        """One transaction for the whole batch."""
        ids = [self._insert(**row) for row in rows]
        self.conn.commit()
        return ids

    def observations(self, site_id: str | None = None,
                     since_days: float | None = None,
                     asof: datetime | None = None) -> list:
        """History, oldest first. `since_days` is measured back from `asof`."""
        from ml.clustering import Observation

        sql = "SELECT * FROM observations"
        where: list[str] = []
        args: list = []
        if site_id is not None:
            where.append("site_id = ?")
            args.append(site_id)
        if since_days is not None:
            cutoff = (asof or utcnow()) - timedelta(days=since_days)
            where.append("ts >= ?")
            args.append(to_iso(cutoff))
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY ts ASC"

        return [
            Observation(
                obs_id=r["obs_id"],
                site_id=r["site_id"],
                timestamp=parse_ts(r["ts"]),
                narrative=r["narrative"] or "",
                sif_probability=r["sif_probability"],
                rules=tuple(json.loads(r["rules"])),
                band=r["band"] or "",
            )
            for r in self.conn.execute(sql, args)
        ]

    def sites(self, since_days: float | None = None,
              asof: datetime | None = None) -> list[str]:
        sql = "SELECT DISTINCT site_id FROM observations"
        args: list = []
        if since_days is not None:
            cutoff = (asof or utcnow()) - timedelta(days=since_days)
            sql += " WHERE ts >= ?"
            args.append(to_iso(cutoff))
        return sorted(r["site_id"] for r in self.conn.execute(sql, args))

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) AS c FROM observations").fetchone()["c"]

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
