"""LinkedIn public guest job search (no login). Behaviour preserved from linkedin_job_watcher.py:
same query/location/experience filters, server-side freshness (f_TPR), title/company exclusion,
years-of-experience check on the full posting, capped + delayed description fetches,
retry with backoff. Jobs rejected by the experience check are recorded as seen."""
from __future__ import annotations

import random
import re
import time

import filters
import http_client
from models import make_job

NAME = "LinkedIn"
BASE_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
PAGE_SIZE = 10
_HEADERS = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.linkedin.com/jobs/search/"}
_SPLIT = 'data-entity-urn="urn:li:jobPosting:'


def _first(pattern, chunk):
    m = re.search(pattern, chunk, re.S)
    return m.group(1).strip() if m else ""


def parse_jobs(html: str) -> list[dict]:
    """Parse the HTML fragment of <li> job cards, one card at a time."""
    jobs = []
    for chunk in html.split(_SPLIT)[1:]:
        m = re.match(r"(\d+)", chunk)
        if not m:
            continue
        job_id = m.group(1)
        job = make_job(
            NAME,
            title=_first(r'class="base-search-card__title">\s*(.*?)\s*</h3>', chunk),
            company=_first(r'class="base-search-card__subtitle">\s*(?:<a[^>]*>)?\s*(.*?)\s*(?:</a>|</h4>)', chunk),
            url=f"https://www.linkedin.com/jobs/view/{job_id}/",
            location=_first(r'class="job-search-card__location">\s*(.*?)\s*</span>', chunk),
            posted=_first(r'<time[^>]*datetime="([^"]+)"', chunk) or None,
            external_id=job_id,
        )
        if job:
            jobs.append(job)
    return jobs


def description_requires_more_experience(html: str, max_years: int) -> bool:
    text = re.sub(r"<[^>]+>", " ", html).lower()
    patterns = [r"(\d+)\s*\+\s*years", r"(\d+)\s*-\s*\d+\s*years", r"(\d+)\s*to\s*\d+\s*years",
                r"minimum\s*of\s*(\d+)\s*years", r"at least\s*(\d+)\s*years"]
    found = [int(m.group(1)) for p in patterns for m in re.finditer(p, text)]
    return bool(found) and min(found) > max_years


def fetch(settings, ctx) -> list[dict]:
    jobs, seen_ids = [], set()
    for page in range(settings.linkedin_max_pages):
        params = {"keywords": settings.linkedin_keywords, "location": settings.location,
                  "f_E": settings.linkedin_experience,
                  "f_TPR": f"r{max(settings.freshness_minutes, 1) * 60}",
                  "start": page * PAGE_SIZE}
        html = http_client.get_text(BASE_URL, settings, params=params, headers=_HEADERS, log=ctx.log)
        page_jobs = [j for j in parse_jobs(html) if j["external_id"] not in seen_ids]
        if not page_jobs:
            break
        seen_ids.update(j["external_id"] for j in page_jobs)
        jobs.extend(page_jobs)
        if page < settings.linkedin_max_pages - 1:
            time.sleep(random.uniform(1, 2))

    # Description (experience) check only for unseen jobs that passed the cheap filters.
    out, fetches = [], 0
    for job in jobs:
        if ctx.is_seen(job):
            out.append(job)  # pipeline counts it as already seen; no extra request
            continue
        if filters.title_excluded(job["title"], settings) or filters.company_excluded(job["company"], settings):
            ctx.mark_seen(job)
            continue
        if fetches >= settings.max_desc_fetches:
            continue  # deferred to a later cycle (not marked seen), as in the original watcher
        fetches += 1
        try:
            desc = http_client.get_text(job["url"], settings, headers=_HEADERS, log=ctx.log)
        except Exception:
            desc = ""
        if desc and description_requires_more_experience(desc, settings.max_experience_years):
            ctx.mark_seen(job)
            continue
        out.append(job)
        time.sleep(random.uniform(*settings.desc_fetch_delay))
    return out
