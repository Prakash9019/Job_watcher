"""Terminal block, log file, optional desktop notification, optional JSON/CSV output."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

BAR = "=" * 60
CSV_FIELDS = ["discovered_at", "source", "title", "company", "location", "posted_at",
              "first_seen_at", "match_score", "url"]
# India has no DST, so a fixed +05:30 offset is correct for Asia/Kolkata without needing tzdata.
IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> str:
    return datetime.now(IST).isoformat(timespec="seconds")


def format_job(job: dict, duplicate_of: str | None = None, first_seen: str | None = None) -> str:
    posted = job.get("posted_at_display") or "unknown"
    if job.get("date_status") == "unknown":
        posted = "unknown (source gave no date)"
    score = job.get("match_score")
    lines = [BAR, "NEW JOB FOUND", BAR,
             f"Source: {job['source']}", f"Title: {job['title']}", f"Company: {job['company']}",
             f"Location: {job.get('location') or 'not stated'}",
             f"Posted: {posted}",
             f"First seen by watcher: {first_seen or now_ist()} (Asia/Kolkata)",
             f"Match score: {score if score is not None else 'n/a'}",
             f"URL: {job['url']}"]
    if duplicate_of:
        lines.append(f"Note: possible duplicate of a listing already seen on {duplicate_of}")
    lines.append(BAR)
    return "\n".join(lines)


def _beep():
    try:
        import winsound
        winsound.Beep(1000, 200)
        winsound.Beep(1400, 200)
    except ImportError:
        print("\a", end="", flush=True)


def emit_job(job: dict, settings, duplicate_of=None, discovered_at=None):
    """Print one job block and write it to every configured sink.
    discovered_at is the watcher's local first-seen time in Asia/Kolkata; it is never
    presented as the posted date."""
    discovered_at = discovered_at or now_ist()
    print("\n" + format_job(job, duplicate_of, first_seen=discovered_at), flush=True)

    log = Path(settings.log_file)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(f"[{discovered_at}] source={job['source']} | title={job['title']} | company={job['company']} | "
                f"location={job.get('location') or 'not stated'} | posted={job.get('posted_at') or 'unknown'} | "
                f"first_seen={discovered_at} | score={job.get('match_score', 'n/a')} | url={job['url']}\n")

    if settings.json_output:  # JSON Lines: one object per line, appended
        with open(settings.json_output, "a", encoding="utf-8") as f:
            f.write(json.dumps({**job, "discovered_at": discovered_at}, ensure_ascii=False) + "\n")
    if settings.csv_output:
        path = Path(settings.csv_output)
        new_file = not path.exists() or path.stat().st_size == 0
        with path.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            if new_file:
                w.writeheader()
            row = {k: job.get(k) if job.get(k) is not None else "" for k in CSV_FIELDS}
            row["discovered_at"] = discovered_at
            row["first_seen_at"] = discovered_at
            w.writerow(row)

    if settings.notify:
        try:
            from plyer import notification
            notification.notify(title=f"New job ({job['source']})", message=f"{job['title']} - {job['company']}", timeout=10)
        except Exception:
            pass
        _beep()


def print_summary(stats: dict):
    print("\nCycle summary:")
    print(f"- Sources queried: {stats['queried']}")
    print(f"- Raw results: {stats['raw']}")
    print(f"- Matching results: {stats['matching']}")
    print(f"- New results printed: {stats['new']}")
    print(f"- Skipped as already seen: {stats['seen']}")
    print(f"- Skipped as too old: {stats['old']}")
    print(f"- Filtered out (keywords/location/title/company/score/no date): {stats['filtered']}")
    print(f"- Failed sources: {len(stats['failed'])}" + (f" ({', '.join(stats['failed'])})" if stats["failed"] else ""))
    if not stats["new"]:
        print("\nNo new matching jobs found.")
