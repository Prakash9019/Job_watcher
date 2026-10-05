"""
Y Combinator "Work at a Startup" source.

YC has no documented public API, but its public listing pages embed the job
postings as JSON (Inertia `data-page` attribute). We read that JSON directly,
so a poll costs a few listing-page requests and no per-job detail fetches.
No login, no applying, no forms.
"""
import html
import json
import logging
import random
import re
import time
from typing import Any, Dict, List

import requests

logger = logging.getLogger("Watcher")

YC_BASE = "https://www.ycombinator.com"
DEFAULT_YC_PAGES = (
    "/jobs/role/software-engineer/remote",
    "/jobs/role/software-engineer",
    "/jobs/location/remote",
)
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobSpyWatcher/1.0)"}
_DATA_PAGE_RE = re.compile(r'data-page="([^"]*)"')


def _fetch_postings(path: str) -> List[Dict[str, Any]]:
    resp = requests.get(YC_BASE + path, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    match = _DATA_PAGE_RE.search(resp.text)
    if not match:
        raise ValueError("no data-page JSON found (YC page layout may have changed)")
    page = json.loads(html.unescape(match.group(1)))
    return page.get("props", {}).get("jobPostings", []) or []


def _to_job_dict(p: Dict[str, Any]) -> Dict[str, Any]:
    skills = p.get("skills") or []
    min_exp = p.get("minExperience") or ""
    # The matcher reads title + description, so fold the structured fields in.
    description = " ".join(
        part for part in (
            p.get("companyOneLiner") or "",
            f"Skills: {', '.join(skills)}." if skills else "",
            f"Experience: {min_exp}." if min_exp else "",
            f"Salary: {p['salaryRange']}." if p.get("salaryRange") else "",
        ) if part
    )
    return {
        "id": f"yc-{p['id']}",
        "site": "ycombinator",
        "title": p.get("title"),
        "company": p.get("companyName"),
        "location": p.get("location"),
        "job_url": YC_BASE + p["url"],
        "description": description,
        "date_posted": p.get("createdAt"),
        "is_remote": "remote" in (p.get("location") or "").lower(),
    }


def fetch_yc_jobs(pages=DEFAULT_YC_PAGES, remote_only: bool = False) -> List[Dict[str, Any]]:
    """Returns de-duplicated YC job dicts compatible with the watcher pipeline."""
    jobs: Dict[str, Dict[str, Any]] = {}
    for i, path in enumerate(pages):
        try:
            for posting in _fetch_postings(path):
                if posting.get("id") is None or not posting.get("url"):
                    continue
                job = _to_job_dict(posting)
                if remote_only and not job["is_remote"]:
                    continue
                jobs.setdefault(job["id"], job)
        except Exception as e:
            logger.error(f"YC page {path} failed: {e}")
        if i < len(pages) - 1:
            time.sleep(random.uniform(0.8, 1.5))  # gentle pacing
    return list(jobs.values())
