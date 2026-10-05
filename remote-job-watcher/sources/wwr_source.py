"""We Work Remotely public RSS feeds (programming categories). Item titles look like 'Company: Role'."""
from __future__ import annotations

import xml.etree.ElementTree as ET

import http_client
from models import make_job

FEEDS = [
    "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-front-end-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
]


def parse(xml_text: str) -> list[dict]:
    jobs = []
    for item in ET.fromstring(xml_text).iter("item"):
        raw_title = (item.findtext("title") or "").strip()
        company, _, title = raw_title.partition(": ")
        if not title:
            company, title = "", raw_title
        job = make_job("We Work Remotely", title, company, item.findtext("link"),
                       location=item.findtext("region") or "", posted=item.findtext("pubDate"),
                       description=item.findtext("description"), is_remote=True)
        if job:
            jobs.append(job)
    return jobs


def fetch(settings, ctx) -> list[dict]:
    jobs, errors = {}, []
    for feed in FEEDS:
        try:
            for job in parse(http_client.get_text(feed, settings, log=ctx.log)):
                jobs.setdefault(job["url"], job)
        except Exception as exc:
            errors.append(exc)
    if errors and not jobs:
        raise errors[0]  # every feed failed
    return list(jobs.values())
