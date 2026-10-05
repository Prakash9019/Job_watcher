"""Source registry. Each adapter exposes fetch(settings, ctx) -> list[normalized job dict]
and raises on failure (the watcher isolates failures per source)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class Context:
    """What adapters may use besides settings: seen-state lookups (to avoid extra requests
    for already-seen jobs) and a log function."""
    state: object = None
    log: Callable = print

    def is_seen(self, job: dict) -> bool:
        return bool(self.state) and self.state.is_seen(job)

    def mark_seen(self, job: dict):
        if self.state:
            self.state.mark_seen(job)


def registry() -> dict:
    from . import (greenhouse_source, himalayas_source, hn_source, jobicy_source, jobspy_source,
                   lever_source, linkedin_source, remoteok_source, remotive_source, wwr_source, yc_source)
    reg = {
        "linkedin": linkedin_source.fetch,
        "remoteok": remoteok_source.fetch,
        "remotive": remotive_source.fetch,
        "himalayas": himalayas_source.fetch,
        "jobicy": jobicy_source.fetch,
        "wwr": wwr_source.fetch,
        "yc": yc_source.fetch,
        "hn": hn_source.fetch,
        "greenhouse": greenhouse_source.fetch,
        "lever": lever_source.fetch,
    }
    for site in jobspy_source.SITES:
        reg[site] = jobspy_source.make_fetcher(site)
    return reg


ALL_SOURCE_NAMES = ["linkedin", "indeed", "glassdoor", "google", "naukri",
                    "remoteok", "remotive", "himalayas", "jobicy", "wwr", "yc", "hn",
                    "greenhouse", "lever"]
