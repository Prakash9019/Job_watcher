"""Persistent seen-job state (state/seen_jobs.json).

Records are keyed by 'source:id:<external_id>' or, without a stable ID,
'source:url:<canonical url>'. Titles/companies are never used as keys.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from models import job_key

PRUNE_AFTER_DAYS = 180


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateStore:
    def __init__(self, path):
        self.path = Path(path)
        self.records: dict = {}
        self._similar: dict = {}
        self.load()

    def load(self):
        self.records = {}
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("expected a JSON object")
                self.records = data
            except (ValueError, OSError) as exc:
                backup = self.path.with_suffix(".corrupt.json")
                try:
                    os.replace(self.path, backup)
                except OSError:
                    pass
                print(f"Warning: state file unreadable ({exc}); moved to {backup.name}, starting empty.")
        else:
            self._migrate_legacy()
        self._reindex()

    def _migrate_legacy(self):
        """One-time import of LinkedIn IDs from the old seen_jobs.json so they are not re-announced."""
        legacy = self.path.parent.parent / "seen_jobs.json"
        try:
            ids = json.loads(legacy.read_text(encoding="utf-8")) if legacy.exists() else []
        except (ValueError, OSError):
            return
        if isinstance(ids, list):
            for jid in ids:
                self.records[f"linkedin:id:{jid}"] = {
                    "source": "LinkedIn", "external_id": str(jid), "url": f"https://www.linkedin.com/jobs/view/{jid}",
                    "title": "", "company": "", "first_seen_at": _now(), "last_seen_at": _now(),
                    "migrated": True}

    def _reindex(self):
        self._similar = {}
        for key, rec in self.records.items():
            if rec.get("title") and rec.get("company"):
                self._similar.setdefault((rec["title"].lower(), rec["company"].lower()), rec["source"])

    def is_seen(self, job: dict) -> bool:
        return job_key(job) in self.records

    def mark_seen(self, job: dict):
        key, now = job_key(job), _now()
        rec = self.records.get(key)
        if rec:
            rec["last_seen_at"] = now
            return
        self.records[key] = {
            "source": job["source"], "external_id": job.get("external_id"), "url": job["url"],
            "title": job["title"], "company": job["company"], "first_seen_at": now, "last_seen_at": now}
        self._similar.setdefault((job["title"].lower(), job["company"].lower()), job["source"])

    def possible_duplicate_of(self, job: dict):
        """Name of another source that already listed the same title+company, else None. Informational only."""
        other = self._similar.get((job["title"].lower(), job["company"].lower()))
        return other if other and other != job["source"] else None

    def save(self):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=PRUNE_AFTER_DAYS)).isoformat()
        self.records = {k: v for k, v in self.records.items() if v.get("last_seen_at", cutoff) >= cutoff}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.records, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    def reset(self):
        self.records, self._similar = {}, {}
        if self.path.exists():
            self.path.unlink()
