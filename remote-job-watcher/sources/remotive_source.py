"""Remotive public API."""
from __future__ import annotations

import http_client
from models import make_job


def parse(data) -> list[dict]:
    jobs = []
    for item in data.get("jobs", []):
        job = make_job("Remotive", item.get("title"), item.get("company_name"), item.get("url"),
                       location=item.get("candidate_required_location"),
                       posted=item.get("publication_date"), description=item.get("description"),
                       tags=item.get("tags"), external_id=item.get("id"), is_remote=True)
        if job:
            jobs.append(job)
    return jobs


def fetch(settings, ctx) -> list[dict]:
    return parse(http_client.get_json("https://remotive.com/api/remote-jobs", settings, log=ctx.log))
