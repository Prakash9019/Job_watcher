import json
import os
from datetime import datetime
from typing import Dict, Any, Tuple, Optional

class JobDeduplicator:
    def __init__(self, filepath: str = "data/seen_jobs.json"):
        self.filepath = filepath
        self._ensure_dir()
        self.seen_jobs: Dict[str, Dict[str, Any]] = self._load()

    def _ensure_dir(self):
        dirname = os.path.dirname(self.filepath)
        if dirname:
            os.makedirs(dirname, exist_ok=True)

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading {self.filepath}: {e}. Initializing empty state.")
                return {}
        return {}

    def save(self):
        self._ensure_dir()
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.seen_jobs, f, indent=2, ensure_ascii=False)

    def get_job_identifier(self, job_dict: Dict[str, Any]) -> str:
        """
        Derives canonical job ID or URL primary identifier.
        """
        job_id = job_dict.get("id")
        job_url = job_dict.get("job_url_direct") or job_dict.get("job_url")
        
        if job_id and str(job_id).strip():
            return str(job_id).strip()
        if job_url and str(job_url).strip():
            return str(job_url).strip()
            
        # Fallback to hash of site + title + company
        site = str(job_dict.get("site", ""))
        title = str(job_dict.get("title", ""))
        company = str(job_dict.get("company", ""))
        return f"{site}:{company}:{title}".lower().replace(" ", "_")

    def process_job(
        self,
        job_dict: Dict[str, Any],
        match_score: int,
        match_status: str,
        notified: bool = False
    ) -> Tuple[bool, str]:
        """
        Processes a job entry.
        Returns:
            (is_new: bool, job_identifier: str)
        """
        job_key = self.get_job_identifier(job_dict)
        now_str = datetime.utcnow().isoformat()

        if job_key in self.seen_jobs:
            # Update last_seen_at
            self.seen_jobs[job_key]["last_seen_at"] = now_str
            if notified:
                self.seen_jobs[job_key]["notified"] = True
            self.save()
            return False, job_key
        else:
            # New job record
            self.seen_jobs[job_key] = {
                "id": job_key,
                "first_seen_at": now_str,
                "last_seen_at": now_str,
                "notified": notified,
                "match_score": match_score,
                "match_status": match_status,
                "title": job_dict.get("title"),
                "company": job_dict.get("company"),
                "job_url": job_dict.get("job_url_direct") or job_dict.get("job_url")
            }
            self.save()
            return True, job_key

    def is_notified(self, job_dict: Dict[str, Any]) -> bool:
        job_key = self.get_job_identifier(job_dict)
        if job_key in self.seen_jobs:
            return self.seen_jobs[job_key].get("notified", False)
        return False

    def mark_notified(self, job_dict: Dict[str, Any]):
        job_key = self.get_job_identifier(job_dict)
        if job_key in self.seen_jobs:
            self.seen_jobs[job_key]["notified"] = True
            self.save()
