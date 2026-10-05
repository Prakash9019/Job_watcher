"""Unified job watcher: one command polls every enabled source and prints only NEW matching jobs.

    python job_watcher.py                  # poll forever (Ctrl+C to stop)
    python job_watcher.py --once           # one scan, then exit
    python job_watcher.py --sources linkedin,remoteok --once
    python job_watcher.py --freshness 60 --once
    python job_watcher.py --reset-state --once

Read-only link discovery: no login automation, no applying, no forms, no messages.
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from datetime import datetime

import filters
import output
from config import load_settings
from sources import ALL_SOURCE_NAMES, Context
from state_store import StateStore

RECORD_ALL_SOURCES = {"yc"}  # remember non-matching jobs so they are never re-evaluated


def run_cycle(settings, state, fetchers: dict, names: list, now=None) -> dict:
    """Query each named source once; print new matching jobs; return counters."""
    stats = {"queried": 0, "raw": 0, "matching": 0, "new": 0, "seen": 0, "old": 0, "filtered": 0, "failed": []}
    ctx = Context(state=state, log=lambda m: print(m, flush=True))
    for name in names:
        stats["queried"] += 1
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Querying {name}...", flush=True)
        try:
            jobs = fetchers[name](settings, ctx)
        except Exception as exc:  # one failing source must never stop the others
            stats["failed"].append(name)
            print(f"  {name} FAILED: {type(exc).__name__}: {exc}", flush=True)
            continue
        print(f"  {name}: {len(jobs)} results", flush=True)
        for job in jobs:
            stats["raw"] += 1
            verdict = filters.evaluate(job, settings, now)
            if verdict == "ok":
                job["match_score"] = filters.score_job(job, settings, now)
                if job["match_score"] < settings.min_match_score:
                    verdict = "lowscore"
            if verdict == "old":
                stats["old"] += 1
            elif verdict != "ok":
                stats["filtered"] += 1
                if name in RECORD_ALL_SOURCES and verdict in ("nomatch", "lowscore"):
                    state.mark_seen(job)
            else:
                stats["matching"] += 1
                if state.is_seen(job):
                    stats["seen"] += 1
                    state.mark_seen(job)  # refresh last_seen_at
                else:
                    output.emit_job(job, settings, duplicate_of=state.possible_duplicate_of(job))
                    state.mark_seen(job)
                    stats["new"] += 1
        state.save()
    return stats


def build_parser():
    p = argparse.ArgumentParser(description="Unified read-only job watcher")
    p.add_argument("--once", action="store_true", help="scan once and exit")
    p.add_argument("--sources", help=f"comma-separated subset of: {', '.join(ALL_SOURCE_NAMES)}")
    p.add_argument("--freshness", type=int, metavar="MINUTES", help="freshness window in minutes")
    p.add_argument("--min-score", type=int, metavar="N", help="minimum relevance score to print a job")
    p.add_argument("--poll-interval", type=int, metavar="SECONDS", help="seconds between cycles")
    p.add_argument("--reset-state", action="store_true", help="forget all seen jobs before scanning")
    p.add_argument("--json-output", metavar="FILE", help="append each new job as a JSON line")
    p.add_argument("--csv-output", metavar="FILE", help="append each new job as a CSV row")
    p.add_argument("--state-file", metavar="FILE", help="state file path (default state/seen_jobs.json)")
    p.add_argument("--no-notification", action="store_true", help="disable desktop notification and beep")
    return p


def main(argv=None, fetchers=None, sleep=time.sleep, settings=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")  # job titles may hold characters the console cannot show
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = settings or load_settings()

    known = set(fetchers) if fetchers is not None else set(ALL_SOURCE_NAMES)
    if args.sources:
        names = [s.strip().lower() for s in args.sources.split(",") if s.strip()]
        unknown = [n for n in names if n not in known]
        if unknown:
            parser.error(f"unknown source(s): {', '.join(unknown)}")
    else:
        names = [n for n in ALL_SOURCE_NAMES if settings.enabled.get(n) and n in known]
    if args.freshness:
        settings.freshness_minutes = args.freshness
    if args.min_score is not None:
        settings.min_match_score = args.min_score
    if args.poll_interval:
        settings.poll_interval = args.poll_interval
    if args.json_output:
        settings.json_output = args.json_output
    if args.csv_output:
        settings.csv_output = args.csv_output
    if args.state_file:
        settings.state_file = args.state_file
    if args.no_notification:
        settings.notify = False

    if fetchers is None:
        from sources import registry
        fetchers = registry()

    state = StateStore(settings.state_file)
    if args.reset_state:
        state.reset()
        print("State reset: all previously seen jobs forgotten.")

    print(f"Job watcher: {len(names)} source(s): {', '.join(names)}")
    print(f"Freshness: {settings.freshness_minutes} min | Location: {settings.location} | "
          + ("single scan" if args.once else f"polling every {settings.poll_interval}s. Ctrl+C to stop.") + "\n")
    try:
        while True:
            output.print_summary(run_cycle(settings, state, fetchers, names))
            if args.once:
                return 0
            wait = max(30, settings.poll_interval + random.uniform(-settings.poll_jitter, settings.poll_jitter))
            print(f"\nNext scan in {int(wait)}s.", flush=True)
            for _ in range(int(wait)):
                sleep(1)
    except KeyboardInterrupt:
        state.save()
        print("\nStopped by user.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
