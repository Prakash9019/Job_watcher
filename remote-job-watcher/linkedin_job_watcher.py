"""
LinkedIn Job Watcher
---------------------
Polls LinkedIn's public "guest" job search endpoint every N minutes for new
postings matching your filters, and notifies you (desktop notification +
console + log file) when a new job appears.

SETUP:
    pip install requests plyer

USAGE:
    python linkedin_job_watcher.py

NOTES:
- Uses LinkedIn's guest job search endpoint (no login required). This is not
  an official API, so LinkedIn can change or block it without notice.
- Keep the poll interval reasonable (default 300s = 5 min, jittered) to
  avoid being rate-limited or IP-blocked.
- Seen job IDs are stored in seen_jobs.json so you don't get repeat alerts
  for the same posting across restarts.
- This script also fetches each candidate job's full posting page to check
  the stated years-of-experience requirement. That means it makes one extra
  request per candidate job per poll cycle -- keep an eye on how often you
  poll, since more requests means more chance of being rate-limited.
- Anti-blocking measures included: randomized jitter on the poll interval,
  a small randomized delay between each job-description fetch, a capped
  number of description fetches per cycle, retry-with-backoff on failures,
  and a persistent session with browser-like headers.
"""

import re
import random
import requests
import time
import json
import os
from datetime import datetime

# ---------------- CONFIG ----------------
# Roles matched to a 1+ year full-stack (MERN/Angular/React Native) background
KEYWORDS = (
    '"Full Stack Developer" OR "Software Development Engineer" OR '
    '"Software Engineer" OR "Frontend Developer" OR "Backend Developer" OR '
    '"React Developer" OR "React Native Developer" OR "Node.js Developer" OR '
    '"MERN Stack Developer" OR "JavaScript Developer" OR "Angular Developer"'
)
LOCATION = "India"
EXPERIENCE_LEVEL = "2,3"     # 2=Entry level, 3=Associate (fits ~1 yr experience, excludes fresher-only/internship roles)
TIME_POSTED_RANGE = "1200"   # seconds -> only jobs posted in the last 20 minutes (fresh postings only)
POLL_INTERVAL_SECONDS = 300  # 5 minutes base interval -- with a 20-min freshness window this gives
                              # plenty of overlap so a slightly delayed cycle still won't miss a posting
POLL_JITTER_SECONDS = 30     # +/- random jitter added to the poll interval so requests don't look
                              # perfectly periodic (reduces bot-pattern detection)
MAX_DESC_FETCHES_PER_CYCLE = 8   # cap on job-description page fetches per cycle, to avoid request bursts
DESC_FETCH_DELAY_RANGE = (2, 5)  # seconds -- random delay between each description fetch
MAX_RETRIES = 3              # retry attempts for a failed request before giving up for this cycle
RETRY_BACKOFF_BASE = 5        # seconds -- backoff doubles each retry (5s, 10s, 20s...)
MAX_EXPERIENCE_YEARS = 2     # skip jobs whose description asks for more than this
TITLE_EXCLUDE_KEYWORDS = [   # skip jobs whose title contains any of these (case-insensitive)
    "senior", "sr.", "sr ", "lead", "principal", "manager", "architect",
    "staff", " ii", " iii", " iv", "3+", "4+", "5+", 
    "intern", "internship", "trainee", "fresher", "apprentice", "campus"
]
COMPANY_EXCLUDE_KEYWORDS = [  # skip jobs posted by these companies (case-insensitive, partial match)
    "scoutit", "Crossing Hurdles"
]
SEEN_JOBS_FILE = "seen_jobs.json"
LOG_FILE = "new_jobs_log.txt"
# -----------------------------------------

BASE_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.linkedin.com/jobs/search/",
}

# Reuse a single session (connection pooling looks more like a real browser
# than a fresh connection per request, and is a bit lighter on LinkedIn's end)
SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def load_seen_jobs():
    if os.path.exists(SEEN_JOBS_FILE):
        with open(SEEN_JOBS_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_seen_jobs(seen):
    with open(SEEN_JOBS_FILE, "w") as f:
        json.dump(list(seen), f)


def request_with_retry(url, params=None):
    """GET a URL with exponential backoff retries. Returns response text,
    or raises the last exception if all retries are exhausted."""
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = SESSION.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.RequestException as e:
            last_exc = e
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF_BASE * (2 ** attempt)
                print(f"  Request failed ({e}); retrying in {wait}s...")
                time.sleep(wait)
    if last_exc is None:
        raise RuntimeError("request_with_retry made no attempts (MAX_RETRIES < 1)")
    raise last_exc


def fetch_jobs(start=0):
    params = {
        "keywords": KEYWORDS,
        "location": LOCATION,
        "f_E": EXPERIENCE_LEVEL,
        "f_TPR": f"r{TIME_POSTED_RANGE}",
        "start": start,
    }
    return request_with_retry(BASE_URL, params=params)  # HTML fragment with <li> job cards


def parse_jobs(html):
    """Very lightweight parsing without extra dependencies (regex-based)."""
    jobs = []
    ids = re.findall(r'data-entity-urn="urn:li:jobPosting:(\d+)"', html)
    titles = re.findall(r'class="base-search-card__title">\s*(.*?)\s*</h3>', html, re.S)
    companies = re.findall(
        r'class="base-search-card__subtitle">\s*<a[^>]*>\s*(.*?)\s*</a>', html, re.S
    )
    links = re.findall(r'href="(https://www\.linkedin\.com/jobs/view/[^?"]+)', html)

    for i, job_id in enumerate(ids):
        jobs.append({
            "id": job_id,
            "title": titles[i].strip() if i < len(titles) else "Unknown title",
            "company": companies[i].strip() if i < len(companies) else "Unknown company",
            "url": links[i] if i < len(links) else f"https://www.linkedin.com/jobs/view/{job_id}",
        })
    return jobs


def title_looks_senior(title):
    t = title.lower()
    return any(kw in t for kw in TITLE_EXCLUDE_KEYWORDS)


def company_is_excluded(company):
    c = company.lower()
    return any(kw.lower() in c for kw in COMPANY_EXCLUDE_KEYWORDS)


def fetch_job_description(url):
    try:
        return request_with_retry(url)
    except Exception:
        return ""


def description_requires_more_experience(html, max_years=MAX_EXPERIENCE_YEARS):
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.lower()

    patterns = [
        r"(\d+)\s*\+\s*years",
        r"(\d+)\s*-\s*\d+\s*years",
        r"(\d+)\s*to\s*\d+\s*years",
        r"minimum\s*of\s*(\d+)\s*years",
        r"at least\s*(\d+)\s*years",
    ]

    min_found = None
    for pat in patterns:
        for match in re.finditer(pat, text):
            years = int(match.group(1))
            if min_found is None or years < min_found:
                min_found = years

    if min_found is not None and min_found > max_years:
        return True
    return False


def notify(job):
    message = f"{job['title']} — {job['company']}"
    print(f"\n🔔 NEW JOB: {message}\n{job['url']}\n")

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] {message}\n{job['url']}\n\n")

    try:
        from plyer import notification
        notification.notify(
            title="New LinkedIn Job Posted",
            message=message,
            timeout=10,
        )
    except Exception:
        pass

    play_alert_sound()


def play_alert_sound():
    try:
        import winsound
        winsound.Beep(1000, 200)
        winsound.Beep(1400, 200)
    except ImportError:
        print("\a", end="", flush=True)


def main():
    seen = load_seen_jobs()
    print(f"Starting LinkedIn job watcher. Polling every {POLL_INTERVAL_SECONDS}s.")
    print(f"Keywords: {KEYWORDS} | Location: {LOCATION}")
    print("Press Ctrl+C to stop.\n")
    play_alert_sound()

    while True:
        try:
            html = fetch_jobs()
            jobs = parse_jobs(html)

            new_jobs = [j for j in jobs if j["id"] not in seen]

            candidate_jobs = []
            for job in new_jobs:
                if title_looks_senior(job["title"]):
                    seen.add(job["id"])
                    continue
                if company_is_excluded(job["company"]):
                    seen.add(job["id"])
                    continue
                candidate_jobs.append(job)

            qualifying_jobs = []
            for job in candidate_jobs[:MAX_DESC_FETCHES_PER_CYCLE]:
                desc_html = fetch_job_description(job["url"])
                if desc_html and description_requires_more_experience(desc_html):
                    seen.add(job["id"])
                    continue
                qualifying_jobs.append(job)
                time.sleep(random.uniform(*DESC_FETCH_DELAY_RANGE))

            leftover_candidates = candidate_jobs[MAX_DESC_FETCHES_PER_CYCLE:]

            if qualifying_jobs:
                for job in qualifying_jobs:
                    notify(job)
                    seen.add(job["id"])
                save_seen_jobs(seen)
            elif new_jobs:
                save_seen_jobs(seen)
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] "
                    f"{len(new_jobs)} new posting(s) found, but filtered out (experience too high)."
                )
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] No new jobs.")

        except requests.exceptions.RequestException as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Request failed: {e}")
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Unexpected error: {e}")

        sleep_for = POLL_INTERVAL_SECONDS + random.uniform(-POLL_JITTER_SECONDS, POLL_JITTER_SECONDS)
        time.sleep(max(30, sleep_for))


if __name__ == "__main__":
    main()
