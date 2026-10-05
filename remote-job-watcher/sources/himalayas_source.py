"""Himalayas public jobs API."""
from __future__ import annotations

import http_client
from models import make_job


def parse(data) -> list[dict]:
    items = data.get("jobs") or data.get("data") or [] if isinstance(data, dict) else data
    jobs = []
    for item in items:
        if not isinstance(item, dict):
            continue
        loc = item.get("locationRestrictions") or item.get("location") or ""
        if isinstance(loc, list):
            loc = ", ".join(str(x) for x in loc)
        company = item.get("companyName") or item.get("company_name") or (item.get("company") or {}).get("name")
        tags = item.get("categories") if isinstance(item.get("categories"), list) else item.get("tags")
        url = item.get("applicationLink") or item.get("url") or item.get("jobUrl") or item.get("guid")
        job = make_job("Himalayas", item.get("title"), company, url, location=loc,
                       posted=item.get("pubDate") or item.get("publishedAt") or item.get("createdAt"),
                       description=item.get("description") or item.get("excerpt"), tags=tags,
                       external_id=item.get("guid") or None, is_remote=True)
        if job:
            jobs.append(job)
    return jobs


def fetch(settings, ctx) -> list[dict]:
    return parse(http_client.get_json("https://himalayas.app/jobs/api", settings,
                                      params={"limit": 50}, log=ctx.log))
