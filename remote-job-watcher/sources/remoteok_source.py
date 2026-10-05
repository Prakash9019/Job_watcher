"""Remote OK public JSON API (first array element is a legal notice, skipped)."""
from __future__ import annotations

import http_client
from models import make_job


def parse(data) -> list[dict]:
    jobs = []
    for item in data:
        if not isinstance(item, dict) or not item.get("position"):
            continue
        job = make_job("Remote OK", item["position"], item.get("company"),
                       item.get("url") or item.get("apply_url"), location=item.get("location"),
                       posted=item.get("date") or item.get("epoch"), description=item.get("description"),
                       tags=item.get("tags"), external_id=item.get("id"), is_remote=True)
        if job:
            jobs.append(job)
    return jobs


def fetch(settings, ctx) -> list[dict]:
    return parse(http_client.get_json("https://remoteok.com/api", settings, params={"tag": "dev"}, log=ctx.log))
