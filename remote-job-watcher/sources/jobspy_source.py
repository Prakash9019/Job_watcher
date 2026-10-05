"""JobSpy-backed sources (Indeed, Glassdoor, Google Jobs, Naukri) using the local jobspy package.
One adapter per site so a failure in one does not affect the others."""
from __future__ import annotations

import sys
from pathlib import Path

from models import make_job

SITES = {"indeed": "Indeed", "glassdoor": "Glassdoor", "google": "Google Jobs", "naukri": "Naukri"}


def _scrape(**kw):
    root = str(Path(__file__).resolve().parents[2])  # E:\JobSpy, holds the local jobspy package
    if root not in sys.path:
        sys.path.insert(0, root)
    from jobspy import scrape_jobs  # imported lazily: heavy, and only needed when enabled
    return scrape_jobs(**kw)


def rows_to_jobs(df, label: str) -> list[dict]:
    jobs = []
    if df is None or len(df) == 0:
        return jobs
    for row in df.to_dict("records"):
        job = make_job(label, row.get("title"), row.get("company"), row.get("job_url"),
                       location=row.get("location"), posted=row.get("date_posted"),
                       description=row.get("description"), external_id=row.get("id") or None,
                       is_remote=bool(row.get("is_remote")) if row.get("is_remote") == row.get("is_remote") else None)
        if job:
            jobs.append(job)
    return jobs


def make_fetcher(site: str):
    label = SITES[site]

    def fetch(settings, ctx) -> list[dict]:
        jobs = {}
        for term in settings.jobspy_terms:
            kw = dict(site_name=[site], search_term=term, location=settings.location,
                      results_wanted=settings.jobspy_results,
                      hours_old=max(1, settings.freshness_minutes // 60), country_indeed="india")
            if site == "google":
                kw["google_search_term"] = f"{term} jobs near {settings.location} since yesterday"
            for job in rows_to_jobs(_scrape(**kw), label):
                jobs.setdefault(job["url"], job)
        return list(jobs.values())

    return fetch
