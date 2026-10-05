"""Keyword / title / company / location / freshness rules shared by every source."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from models import parse_datetime, source_slug

_WORD = "a-z0-9"


@lru_cache(maxsize=None)
def _pattern(kw: str, plural: bool) -> re.Pattern:
    """Match kw as a whole word/phrase, so 'intern' does not hit 'internal'."""
    kw = kw.lower()
    pat = re.escape(kw)
    if kw[0].isalnum():
        pat = f"(?<![{_WORD}])" + pat
    if kw[-1].isalnum():
        pat += ("s?" if plural else "") + f"(?![{_WORD}])"
    return re.compile(pat)


def _contains_any(text: str, keywords, plural=False) -> bool:
    text = text.lower()
    return any(k.strip() and _pattern(k, plural).search(text) for k in keywords)


def title_excluded(title: str, settings) -> bool:
    return _contains_any(f" {title} ", settings.title_exclude)


def company_excluded(company: str, settings) -> bool:
    c = company.lower()
    return any(k.lower() in c for k in settings.company_exclude if k.strip())


def keyword_match(job: dict, settings) -> bool:
    text = " ".join([job["title"], job.get("description", ""), " ".join(job.get("tags", []))])
    return _contains_any(text, settings.keywords, plural=True)


def _location_text(job: dict) -> str:
    return " ".join([job.get("location", ""), " ".join(job.get("tags", []))]).strip()


def location_ineligible(job: dict, settings) -> bool:
    """True when the location/tags explicitly exclude this region (e.g. 'US only', 'EU only').
    Checked before a role is accepted merely for containing 'remote'."""
    return _contains_any(_location_text(job), settings.remote_exclude)


def location_ok(job: dict, settings) -> bool:
    if location_ineligible(job, settings):
        return False  # explicit region lock-out beats any 'remote' mention
    if source_slug(job["source"]) not in settings.location_checked:
        return True  # location already applied by the source's own query
    loc = _location_text(job)
    if not loc:
        return bool(job.get("is_remote"))  # remote boards with no stated restriction pass
    return _contains_any(loc, settings.remote_location_keywords)


def score_job(job: dict, settings, now=None) -> int:
    """Relevance score. Higher is better; printed in the terminal and gated by MIN_MATCH_SCORE."""
    score = 0
    if _contains_any(job["title"], settings.keywords, plural=True):
        score += settings.score_title_keyword          # keyword in title: strong signal
    elif keyword_match(job, settings):
        score += settings.score_body_keyword           # keyword only in description/tags
    if source_slug(job["source"]) in settings.server_filtered:
        score += settings.score_server_filtered        # source already keyword-matched server-side
    if _contains_any(_location_text(job), settings.eligibility_score_keywords):
        score += settings.score_eligibility            # India / global / worldwide eligibility
    if freshness(job, settings, now) == "fresh":
        score += settings.score_fresh                  # recent source-provided date
    return score


def freshness(job: dict, settings, now=None) -> str:
    """'fresh' | 'old' | 'unknown'. Never invents a date for jobs without one."""
    dt, date_only = parse_datetime(job.get("posted_at"))
    if dt is None:
        return "unknown"
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=settings.freshness_minutes)
    if date_only:  # day precision only: compare whole days
        return "fresh" if dt.date() >= cutoff.date() else "old"
    return "fresh" if dt >= cutoff else "old"


def evaluate(job: dict, settings, now=None) -> str:
    """Return 'ok', 'old', 'unknown_date', 'excluded' or 'nomatch'."""
    if title_excluded(job["title"], settings) or company_excluded(job["company"], settings):
        return "excluded"
    if location_ineligible(job, settings):
        return "excluded"  # explicit region lock-out (US only / EU only / ...)
    if settings.strict_freshness:
        f = freshness(job, settings, now)
        if f == "old":
            return "old"
        if f == "unknown" and not settings.print_unknown_date:
            return "unknown_date"
    if source_slug(job["source"]) not in settings.server_filtered and not keyword_match(job, settings):
        return "nomatch"
    if not location_ok(job, settings):
        return "nomatch"
    return "ok"
