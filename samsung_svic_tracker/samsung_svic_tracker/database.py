from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from models import Document, Finding, utc_now


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS runs (
  run_id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL,
  finished_at TEXT, status TEXT NOT NULL, new_document_count INTEGER NOT NULL DEFAULT 0,
  new_finding_count INTEGER NOT NULL DEFAULT 0, error TEXT
);
CREATE TABLE IF NOT EXISTS source_state (
  source_name TEXT PRIMARY KEY, cursor TEXT, last_success_at TEXT,
  consecutive_failures INTEGER NOT NULL DEFAULT 0, last_error TEXT
);
CREATE TABLE IF NOT EXISTS documents (
  document_id INTEGER PRIMARY KEY AUTOINCREMENT, source_name TEXT NOT NULL,
  url TEXT NOT NULL, title TEXT, published_at TEXT, fetched_at TEXT NOT NULL,
  content_hash TEXT NOT NULL UNIQUE, official INTEGER NOT NULL,
  reliability REAL NOT NULL, raw_path TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS documents_source_url_hash
  ON documents(source_name, url, content_hash);
CREATE TABLE IF NOT EXISTS companies (
  record_id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_name_original TEXT NOT NULL, company_name_korean TEXT, country TEXT,
  listed_or_private TEXT, ticker TEXT, sector TEXT, technology TEXT,
  related_fund TEXT, fund_confirmation_status TEXT NOT NULL DEFAULT 'candidate',
  investment_date TEXT, announcement_date TEXT, investment_amount_original TEXT,
  currency TEXT, investment_amount_krw INTEGER, ownership_percentage REAL,
  funding_round TEXT, lead_or_participant TEXT, samsung_entity TEXT,
  samsung_business_unit TEXT, cooperation_type TEXT, development_stage TEXT,
  poc_status TEXT, customer_validation_status TEXT, certification_status TEXT,
  mass_production_status TEXT, revenue_status TEXT,
  samsung_customer_or_application TEXT, revenue_connection_path TEXT,
  expected_commercialization_date TEXT, source_1 TEXT, source_2 TEXT,
  official_source_exists INTEGER NOT NULL DEFAULT 0, confidence_level TEXT,
  failure_modes TEXT, last_checked_at TEXT, first_detected_at TEXT NOT NULL,
  update_hash TEXT NOT NULL UNIQUE, exchange_rate_date TEXT, exchange_rate REAL,
  exchange_rate_formula TEXT
);
CREATE TABLE IF NOT EXISTS findings (
  finding_id INTEGER PRIMARY KEY AUTOINCREMENT, alert_hash TEXT NOT NULL UNIQUE,
  company_name TEXT NOT NULL, event_type TEXT NOT NULL, announcement_date TEXT,
  summary TEXT NOT NULL, related_fund TEXT, fund_confirmation_status TEXT,
  investment_amount_original TEXT, official_source_exists INTEGER NOT NULL,
  confidence_level TEXT, source_urls TEXT NOT NULL, details_json TEXT NOT NULL,
  first_detected_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
  alert_hash TEXT PRIMARY KEY, finding_id INTEGER, created_at TEXT NOT NULL,
  delivered_at TEXT, delivery_error TEXT
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class Database:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def start_run(self) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs(started_at,status) VALUES(?, 'running')", (utc_now(),)
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, status: str, documents: int = 0, findings: int = 0, error: str | None = None) -> None:
        now = utc_now()
        self.conn.execute(
            "UPDATE runs SET finished_at=?,status=?,new_document_count=?,new_finding_count=?,error=? WHERE run_id=?",
            (now, status, documents, findings, error, run_id),
        )
        if status == "success":
            self.conn.execute(
                "INSERT INTO meta(key,value) VALUES('last_success_at',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (now,),
            )
        self.conn.commit()

    def last_success_at(self) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key='last_success_at'").fetchone()
        return row["value"] if row else None

    def add_document(self, doc: Document, raw_path: str) -> bool:
        cur = self.conn.execute(
            """INSERT OR IGNORE INTO documents
            (source_name,url,title,published_at,fetched_at,content_hash,official,reliability,raw_path)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (doc.source, doc.url, doc.title, doc.published_at, doc.fetched_at,
             doc.content_hash, int(doc.official), doc.reliability, raw_path),
        )
        self.conn.commit()
        return cur.rowcount == 1

    def source_succeeded(self, name: str, cursor: str | None = None) -> None:
        self.conn.execute(
            """INSERT INTO source_state(source_name,cursor,last_success_at,consecutive_failures,last_error)
            VALUES(?,?,?,0,NULL) ON CONFLICT(source_name) DO UPDATE SET
            cursor=excluded.cursor,last_success_at=excluded.last_success_at,
            consecutive_failures=0,last_error=NULL""", (name, cursor, utc_now())
        )
        self.conn.commit()

    def source_failed(self, name: str, error: str) -> int:
        self.conn.execute(
            """INSERT INTO source_state(source_name,consecutive_failures,last_error)
            VALUES(?,1,?) ON CONFLICT(source_name) DO UPDATE SET
            consecutive_failures=consecutive_failures+1,last_error=excluded.last_error""",
            (name, error),
        )
        self.conn.commit()
        return int(self.conn.execute(
            "SELECT consecutive_failures FROM source_state WHERE source_name=?", (name,)
        ).fetchone()[0])

    def add_finding(self, finding: Finding) -> int | None:
        cur = self.conn.execute(
            """INSERT OR IGNORE INTO findings
            (alert_hash,company_name,event_type,announcement_date,summary,related_fund,
             fund_confirmation_status,investment_amount_original,official_source_exists,
             confidence_level,source_urls,details_json,first_detected_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (finding.alert_hash, finding.company_name_original, finding.event_type,
             finding.announcement_date, finding.summary, finding.related_fund,
             finding.fund_confirmation_status, finding.investment_amount_original,
             int(finding.official_source_exists), finding.confidence_level,
             json.dumps(finding.source_urls, ensure_ascii=False),
             json.dumps(finding.details, ensure_ascii=False), utc_now()),
        )
        self.conn.commit()
        return int(cur.lastrowid) if cur.rowcount == 1 else None

    def reserve_alert(self, finding_id: int, alert_hash: str) -> bool:
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO alerts(alert_hash,finding_id,created_at) VALUES(?,?,?)",
            (alert_hash, finding_id, utc_now()),
        )
        self.conn.commit()
        return cur.rowcount == 1

    def mark_alert(self, alert_hash: str, error: str | None = None) -> None:
        self.conn.execute(
            "UPDATE alerts SET delivered_at=?,delivery_error=? WHERE alert_hash=?",
            (utc_now() if error is None else None, error, alert_hash),
        )
        self.conn.commit()

    def rows(self, query: str, params: Iterable = ()):
        return self.conn.execute(query, tuple(params)).fetchall()

