"""Y Combinator 'Work at a Startup' public listing pages. Reuses the approach of jobspy/yc.py:
the listing pages embed postings as JSON (Inertia data-page), which already contains title,
company, location, skills and creation date - so no per-job detail pages are fetched at all.
Read-only; no login, no applying."""
from __future__ import annotations

import html
import json
import random
import re
import time

import http_client
from models import make_job

YC_BASE = "https://www.ycombinator.com"
PAGES = ("/jobs/role/software-engineer/remote", "/jobs/role/software-engineer", "/jobs/location/remote")
_DATA_PAGE = re.compile(r'data-page="([^"]*)"')
RECORD_ALL = True  # remember non-matching YC jobs too


def parse_page(page_html: str) -> list[dict]:
    m = _DATA_PAGE.search(page_html)
    if not m:
        raise ValueError("no data-page JSON found (YC page layout may have changed)")
    postings = json.loads(html.unescape(m.group(1))).get("props", {}).get("jobPostings") or []
    jobs = []
    for p in postings:
        if p.get("id") is None or not p.get("url"):
            continue
        skills = p.get("skills") or []
        desc = " ".join(x for x in (p.get("companyOneLiner"), f"Skills: {', '.join(skills)}." if skills else "",
                                    f"Experience: {p['minExperience']}." if p.get("minExperience") else "") if x)
        job = make_job("Y Combinator", p.get("title"), p.get("companyName"), YC_BASE + p["url"],
                       location=p.get("location"), posted=p.get("createdAt"), description=desc,
                       tags=skills, external_id=p["id"])
        if job:
            jobs.append(job)
    return jobs


def fetch(settings, ctx) -> list[dict]:
    jobs, errors = {}, []
    for i, path in enumerate(PAGES):
        try:
            for job in parse_page(http_client.get_text(YC_BASE + path, settings, log=ctx.log)):
                jobs.setdefault(job["external_id"], job)
        except Exception as exc:
            errors.append(exc)
        if i < len(PAGES) - 1:
            time.sleep(random.uniform(0.8, 1.5))
    if errors and not jobs:
        raise errors[0]
    out = []
    for job in jobs.values():  # same years-of-experience cap as the LinkedIn watcher
        m = re.search(r"Experience: (\d+)", job["description"])
        if m and int(m.group(1)) > settings.max_experience_years:
            ctx.mark_seen(job)
        else:
            out.append(job)
    return out
