"""Greenhouse public Job Board API (read-only; no login, no application submission).

Board tokens are read from config/company_boards.json ("greenhouse": [...]). For each token:
    GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
A failed board is logged and skipped; the other boards (and other sources) keep going.
"""
from __future__ import annotations

import html as _html

import http_client
from config import load_company_boards
from models import make_job

API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


def parse(data, board_token: str) -> list[dict]:
    jobs = []
    for item in data.get("jobs", []) if isinstance(data, dict) else []:
        loc = item.get("location") or {}
        location = loc.get("name") if isinstance(loc, dict) else loc
        departments = [d.get("name") for d in (item.get("departments") or []) if isinstance(d, dict) and d.get("name")]
        content = _html.unescape(item.get("content") or "")  # Greenhouse double-escapes the HTML body
        job = make_job(
            "Greenhouse",
            title=item.get("title"),
            company=item.get("company_name") or board_token,
            url=item.get("absolute_url"),
            location=location,
            posted=item.get("updated_at") or item.get("first_published") or item.get("created_at"),
            description=content,
            tags=departments,
            external_id=item.get("id") or item.get("internal_job_id"),
        )
        if job:
            jobs.append(job)
    return jobs


def fetch(settings, ctx) -> list[dict]:
    tokens = load_company_boards(settings.company_boards_file)["greenhouse"]
    if not tokens:
        return []
    jobs, errors = {}, []
    for token in tokens:
        try:
            data = http_client.get_json(API.format(token=token), settings,
                                        params={"content": "true"}, log=ctx.log)
            for job in parse(data, token):
                jobs.setdefault(job["url"], job)
        except Exception as exc:
            errors.append(exc)
            ctx.log(f"  Greenhouse board '{token}' failed: {type(exc).__name__}: {exc}")
    if errors and not jobs:
        raise errors[0]  # every configured board failed -> mark the source failed
    return list(jobs.values())
