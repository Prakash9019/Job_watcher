"""Lever public Postings API (read-only; no login, no application submission).

Lever site names are read from config/company_boards.json ("lever": [...]). For each site:
    GET https://api.lever.co/v0/postings/{site_name}?mode=json
A failed site is logged and skipped; the other sites (and other sources) keep going.
"""
from __future__ import annotations

import http_client
from config import load_company_boards
from models import make_job

API = "https://api.lever.co/v0/postings/{site}"


def parse(data, site: str) -> list[dict]:
    jobs = []
    for item in data if isinstance(data, list) else []:
        cats = item.get("categories") or {}
        tags = [cats.get("team"), cats.get("department"), cats.get("commitment")]
        job = make_job(
            "Lever",
            title=item.get("text"),
            company=item.get("companyName") or site,
            url=item.get("hostedUrl") or item.get("applyUrl"),
            location=cats.get("location"),
            posted=item.get("createdAt"),  # epoch ms, when present
            description=item.get("descriptionPlain") or item.get("description"),
            tags=[t for t in tags if t],
            external_id=item.get("id"),
        )
        if job:
            jobs.append(job)
    return jobs


def fetch(settings, ctx) -> list[dict]:
    sites = load_company_boards(settings.company_boards_file)["lever"]
    if not sites:
        return []
    jobs, errors = {}, []
    for site in sites:
        try:
            data = http_client.get_json(API.format(site=site), settings,
                                        params={"mode": "json"}, log=ctx.log)
            for job in parse(data, site):
                jobs.setdefault(job["url"], job)
        except Exception as exc:
            errors.append(exc)
            ctx.log(f"  Lever site '{site}' failed: {type(exc).__name__}: {exc}")
    if errors and not jobs:
        raise errors[0]  # every configured site failed -> mark the source failed
    return list(jobs.values())
