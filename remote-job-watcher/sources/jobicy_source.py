"""Jobicy public API."""
from __future__ import annotations

import http_client
from models import make_job


def parse(data) -> list[dict]:
    jobs = []
    for item in data.get("jobs", []):
        tags = [item.get("jobIndustry"), item.get("jobType")]
        flat = [t for x in tags for t in (x if isinstance(x, list) else [x]) if t]
        job = make_job("Jobicy", item.get("jobTitle"), item.get("companyName"),
                       item.get("url") or item.get("jobUrl"), location=item.get("jobGeo"),
                       posted=item.get("pubDate"), description=item.get("jobDescription") or item.get("jobExcerpt"),
                       tags=flat, external_id=item.get("id"), is_remote=True)
        if job:
            jobs.append(job)
    return jobs


def fetch(settings, ctx) -> list[dict]:
    return parse(http_client.get_json("https://jobicy.com/api/v2/remote-jobs", settings,
                                      params={"count": 50, "industry": "dev"}, log=ctx.log))
