"""Hacker News 'Ask HN: Who is hiring?' via the public Algolia HN API (read-only).
Each top-level comment is one posting; the URL is the comment's own HN permalink.
Comment timestamps are real (created_at_i)."""
from __future__ import annotations

import html
import re

import http_client
from models import make_job

API = "https://hn.algolia.com/api/v1"


def find_thread_id(settings, log=print):
    data = http_client.get_json(f"{API}/search_by_date", settings, log=log, params={
        "query": "Ask HN: Who is hiring?", "tags": "story,author_whoishiring", "hitsPerPage": 5})
    for hit in data.get("hits", []):
        if re.search(r"who is hiring", hit.get("title") or "", re.I) and "wants to be hired" not in (hit.get("title") or "").lower():
            return hit["objectID"]
    return None


def parse(data, thread_id) -> list[dict]:
    jobs = []
    for hit in data.get("hits", []):
        if str(hit.get("parent_id")) != str(thread_id):
            continue  # replies to postings, not postings
        text = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<p>", "\n", hit.get("comment_text") or ""))).strip()
        first = text.split("\n")[0]
        parts = [p.strip() for p in first.split("|") if p.strip()]
        if not parts:
            continue
        # Typical header: Company | Role | Location | ...  (bare URLs are not roles)
        company = parts[0][:80]
        roles = [p for p in parts[1:] if not re.match(r"https?://|www\.", p)]
        title = roles[0] if roles else first[:100]
        loc = " | ".join(parts[1:])  # location is matched against the whole header
        job = make_job("Hacker News", title or first[:100], company,
                       f"https://news.ycombinator.com/item?id={hit['objectID']}", location=loc,
                       posted=hit.get("created_at_i"), description=text, external_id=hit["objectID"])
        if job:
            jobs.append(job)
    return jobs


def fetch(settings, ctx) -> list[dict]:
    thread_id = find_thread_id(settings, ctx.log)
    if not thread_id:
        raise RuntimeError("could not find the current 'Who is hiring?' thread")
    data = http_client.get_json(f"{API}/search_by_date", settings, log=ctx.log, params={
        "tags": f"comment,story_{thread_id}", "hitsPerPage": 200})
    return parse(data, thread_id)
