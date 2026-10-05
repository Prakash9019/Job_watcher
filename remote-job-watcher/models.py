"""Normalized job model + URL/date helpers shared by all sources."""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING = {"ref", "trk", "trackingid", "refid", "fbclid", "gclid", "ref_src"}
_TAGS = re.compile(r"<[^>]+>")


def clean_text(value) -> str:
    if value is None or value != value:  # None / NaN
        return ""
    text = _TAGS.sub(" ", str(value))
    return re.sub(r"\s+", " ", text).strip()


def canonical_url(url) -> str:
    """Drop fragment, tracking params and trailing slash; keep other query params."""
    parts = urlsplit(clean_text(url))
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return ""
    query = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                   if not k.lower().startswith("utm_") and k.lower() not in _TRACKING)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(),
                       parts.path.rstrip("/"), urlencode(query), ""))


def parse_datetime(value):
    """Return (aware UTC datetime | None, date_only: bool). Naive values are assumed UTC."""
    if value is None or value != value or value == "":
        return None, False
    if isinstance(value, datetime):
        dt, date_only = value, False
    elif isinstance(value, date):
        dt, date_only = datetime(value.year, value.month, value.day), True
    elif isinstance(value, (int, float)) or (
            isinstance(value, str) and re.fullmatch(r"\d{9,13}(\.\d+)?", value.strip())):
        n = float(value)
        if n <= 0:
            return None, False
        dt, date_only = datetime.fromtimestamp(n / 1000 if n > 1e11 else n, tz=timezone.utc), False
    else:
        text = str(value).strip()
        date_only = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", text))
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                dt = parsedate_to_datetime(text)  # RFC 822 (RSS)
            except (TypeError, ValueError):
                return None, False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc), date_only


def humanize(dt, date_only: bool = False, now=None) -> str:
    if dt is None:
        return "unknown"
    if date_only:
        return dt.date().isoformat()
    mins = int(((now or datetime.now(timezone.utc)) - dt).total_seconds() // 60)
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{mins} minute{'s' if mins != 1 else ''} ago"
    if mins < 1440:
        return f"{mins // 60} hour{'s' if mins // 60 != 1 else ''} ago"
    return f"{mins // 1440} day{'s' if mins // 1440 != 1 else ''} ago"


def source_slug(source: str) -> str:
    return re.sub(r"[^a-z0-9]", "", source.lower())


def make_job(source, title, company, url, location="", posted=None, description="",
             tags=None, external_id=None, is_remote=None, now=None):
    """Build the normalized dict, or None when there is no direct http(s) job URL."""
    url = canonical_url(url)
    title = clean_text(title)
    if not url or not title:
        return None
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]
    tags = [clean_text(t) for t in (tags or []) if clean_text(t)]
    dt, date_only = parse_datetime(posted)
    location = clean_text(location)
    if is_remote is None:
        is_remote = "remote" in location.lower() or "remote" in [t.lower() for t in tags]
    return {
        "source": source,
        "external_id": str(external_id) if external_id not in (None, "") else None,
        "title": title,
        "company": clean_text(company) or "Unknown company",
        "location": location,
        "posted_at": dt.isoformat() if dt else None,
        "posted_at_display": humanize(dt, date_only, now),
        "url": url,
        "description": clean_text(description),
        "tags": tags,
        "is_remote": bool(is_remote),
        "date_status": "unknown" if dt is None else ("date_only" if date_only else "known"),
    }


def job_key(job: dict) -> str:
    slug = source_slug(job["source"])
    if job.get("external_id"):
        return f"{slug}:id:{job['external_id']}"
    return f"{slug}:url:{canonical_url(job['url'])}"
