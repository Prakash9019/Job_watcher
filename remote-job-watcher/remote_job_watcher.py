import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


SEEN_FILE = Path("seen_remote_job_urls.json")
TIMEOUT_SECONDS = 20

# Change these to your preferred roles/skills.
KEYWORDS = [
    "react",
    "react native",
    "frontend",
    "full stack",
    "fullstack",
    "python",
    "backend",
    "software engineer",
]

# Optional: keep jobs that mention one of these locations/eligibility terms.
# Keep empty [] to accept global remote jobs.
LOCATION_KEYWORDS = [
    "india",
    "asia",
    "worldwide",
    "global",
    "anywhere",
    "remote",
]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_url(url: str) -> str:
    url = clean_text(url)
    url = url.split("#")[0]
    return url.rstrip("/")


def load_seen_urls() -> set[str]:
    if not SEEN_FILE.exists():
        return set()

    try:
        data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        return set(data if isinstance(data, list) else [])
    except (json.JSONDecodeError, OSError):
        print("Warning: seen URL file is invalid. Starting with an empty history.")
        return set()


def save_seen_urls(seen_urls: set[str]) -> None:
    SEEN_FILE.write_text(
        json.dumps(sorted(seen_urls), indent=2),
        encoding="utf-8",
    )


def request_json(url: str, params: dict | None = None) -> Any:
    headers = {
        "User-Agent": "personal-remote-job-watcher/1.0 (link discovery only)",
        "Accept": "application/json",
    }

    response = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def make_job(
    source: str,
    title: Any,
    company: Any,
    url: Any,
    location: Any = "",
    posted_at: Any = "",
    description: Any = "",
    tags: Any = "",
) -> dict | None:
    normalized_url = normalize_url(str(url or ""))

    if not normalized_url.startswith(("https://", "http://")):
        return None

    if isinstance(tags, list):
        tags = ", ".join(clean_text(tag) for tag in tags)

    return {
        "source": source,
        "title": clean_text(title),
        "company": clean_text(company),
        "url": normalized_url,
        "location": clean_text(location),
        "posted_at": clean_text(posted_at),
        "description": clean_text(description),
        "tags": clean_text(tags),
    }


def fetch_remote_ok() -> list[dict]:
    data = request_json("https://remoteok.com/api")

    jobs = []
    for item in data:
        if not isinstance(item, dict) or not item.get("position"):
            continue

        job = make_job(
            source="Remote OK",
            title=item.get("position"),
            company=item.get("company"),
            url=item.get("apply_url") or item.get("url"),
            location=item.get("location"),
            posted_at=item.get("date") or item.get("epoch"),
            description=item.get("description"),
            tags=item.get("tags", []),
        )
        if job:
            jobs.append(job)

    return jobs


def fetch_remotive() -> list[dict]:
    data = request_json("https://remotive.com/api/remote-jobs")

    jobs = []
    for item in data.get("jobs", []):
        job = make_job(
            source="Remotive",
            title=item.get("title"),
            company=item.get("company_name"),
            url=item.get("url"),
            location=item.get("candidate_required_location"),
            posted_at=item.get("publication_date"),
            description=item.get("description"),
            tags=item.get("tags", []),
        )
        if job:
            jobs.append(job)

    return jobs


def fetch_himalayas() -> list[dict]:
    data = request_json("https://himalayas.app/jobs/api")

    # Himalayas can return either a dict with jobs/data or a direct list.
    if isinstance(data, dict):
        items = data.get("jobs") or data.get("data") or []
    else:
        items = data

    jobs = []
    for item in items:
        if not isinstance(item, dict):
            continue

        job = make_job(
            source="Himalayas",
            title=item.get("title"),
            company=(
                item.get("companyName")
                or item.get("company_name")
                or (item.get("company") or {}).get("name")
            ),
            url=item.get("url") or item.get("jobUrl") or item.get("job_url"),
            location=item.get("location") or item.get("locationRestrictions"),
            posted_at=item.get("publishedAt") or item.get("createdAt"),
            description=item.get("description"),
            tags=item.get("tags", []),
        )
        if job:
            jobs.append(job)

    return jobs


def fetch_jobicy() -> list[dict]:
    data = request_json(
        "https://jobicy.com/api/v2/remote-jobs",
        params={
            "count": 50,
            "geo": "anywhere",
        },
    )

    jobs = []
    for item in data.get("jobs", []):
        job = make_job(
            source="Jobicy",
            title=item.get("jobTitle"),
            company=item.get("companyName"),
            url=item.get("url") or item.get("jobUrl"),
            location=item.get("jobGeo"),
            posted_at=item.get("pubDate"),
            description=item.get("jobDescription"),
            tags=item.get("jobIndustry") or item.get("jobType"),
        )
        if job:
            jobs.append(job)

    return jobs


def job_matches(job: dict) -> bool:
    searchable_text = " ".join(
        [
            job["title"],
            job["company"],
            job["location"],
            job["description"],
            job["tags"],
        ]
    ).lower()

    keyword_match = any(keyword.lower() in searchable_text for keyword in KEYWORDS)

    if not keyword_match:
        return False

    if not LOCATION_KEYWORDS:
        return True

    location_text = " ".join(
        [job["location"], job["description"], job["tags"]]
    ).lower()

    return any(keyword.lower() in location_text for keyword in LOCATION_KEYWORDS)


def dedupe_current_results(jobs: list[dict]) -> list[dict]:
    unique_jobs = {}
    for job in jobs:
        unique_jobs[job["url"]] = job
    return list(unique_jobs.values())


def print_job(job: dict) -> None:
    print(f"\n[{job['source']}]")
    print(f"{job['title']} — {job['company'] or 'Unknown company'}")

    if job["location"]:
        print(f"Location: {job['location']}")

    if job["posted_at"]:
        print(f"Posted: {job['posted_at']}")

    print(job["url"])


def main() -> None:
    sources = [
        ("Remote OK", fetch_remote_ok),
        ("Remotive", fetch_remotive),
        ("Himalayas", fetch_himalayas),
        ("Jobicy", fetch_jobicy),
    ]

    all_jobs = []

    print("Fetching remote jobs...")

    for source_name, fetcher in sources:
        try:
            jobs = fetcher()
            all_jobs.extend(jobs)
            print(f"  {source_name}: fetched {len(jobs)} jobs")
        except requests.RequestException as error:
            print(f"  {source_name}: failed — {error}")
        except (TypeError, ValueError, KeyError) as error:
            print(f"  {source_name}: response format changed — {error}")

    filtered_jobs = [job for job in all_jobs if job_matches(job)]
    unique_jobs = dedupe_current_results(filtered_jobs)

    seen_urls = load_seen_urls()
    new_jobs = [job for job in unique_jobs if job["url"] not in seen_urls]

    # Mark all matching jobs as seen, including existing ones.
    # This prevents the same remote jobs from repeatedly printing.
    seen_urls.update(job["url"] for job in unique_jobs)
    save_seen_urls(seen_urls)

    print(
        f"\nFetched {len(all_jobs)} total jobs | "
        f"{len(unique_jobs)} matching jobs | "
        f"{len(new_jobs)} newly discovered jobs"
    )

    if not new_jobs:
        print("\nNo new matching remote jobs found.")
        return

    for job in sorted(
        new_jobs,
        key=lambda item: (item["source"], item["title"].lower()),
    ):
        print_job(job)


if __name__ == "__main__":
    main()