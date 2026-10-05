# Unified Job Watcher

One command polls every enabled job source and prints only **new, matching, recent** jobs.
Read-only link discovery: no login automation, no applying, no forms, no messages.

All files live in `E:\JobSpy\remote-job-watcher\`. The older `linkedin_job_watcher.py` and
`remote_job_watcher.py` are untouched; the `jobspy` package is reused, not rewritten.

## Install

From `E:\JobSpy\remote-job-watcher`:

```
pip install -r requirements.txt
```

`pandas`, `numpy`, `beautifulsoup4`, `pydantic`, `tls-client`, `markdownify` and `regex` are only needed for the
JobSpy-backed sources (Indeed, Glassdoor, Google, Naukri). `pytest` is for the tests.

## Run

```
python job_watcher.py                        # continuous: scan now, wait, repeat. Ctrl+C stops cleanly
python job_watcher.py --once                 # one scan, then exit
python job_watcher.py --reset-state --once   # explicitly forget all seen jobs, then scan once
```

Other flags:

| Flag | Effect |
|---|---|
| `--sources linkedin,remoteok` | Query only these sources (overrides the enabled list) |
| `--freshness 60` | Freshness window in minutes (60 = 1h, 360 = 6h, 1440 = 24h, 10080 = 7d) |
| `--min-score N` | Minimum relevance score to print a job (default 20) |
| `--poll-interval 600` | Seconds between cycles (minimum wait is 30s) |
| `--json-output FILE` | Append each new job as a JSON line |
| `--csv-output FILE` | Append each new job as a CSV row |
| `--state-file FILE` | Use a different state file |
| `--no-notification` | Disable desktop notification and beep |

State is never reset automatically, only with `--reset-state`.

## Example output

```
============================================================
NEW JOB FOUND
============================================================
Source: LinkedIn
Title: Full Stack Developer
Company: Enterlyze Private Limited
Location: Pune, Maharashtra, India
Posted: 2026-10-03
First seen by watcher: 2026-10-03T23:29:41+05:30 (Asia/Kolkata)
Match score: 85
URL: https://www.linkedin.com/jobs/view/4473418619
============================================================

Cycle summary:
- Sources queried: 9
- Raw results: 451
- Matching results: 45
- New results printed: 45
- Skipped as already seen: 0
- Skipped as too old: 184
- Filtered out (keywords/location/title/company/no date): 222
- Failed sources: 0
```

If nothing is new it prints `No new matching jobs found.`

## Configuration

Defaults are constants at the top of `config.py`: keywords, location, remote location keywords, title and company
exclusions, freshness, polling interval and jitter, timeout, retries, enabled sources and LinkedIn settings.

Overrides go in `.env` (copy `.env.example`; real environment variables win) or in CLI flags:

```
FRESHNESS_MINUTES=1440
POLL_INTERVAL_SECONDS=900
LOCATION=India
STRICT_FRESHNESS=true      # false = ignore posting dates entirely
PRINT_UNKNOWN_DATE=true    # false = drop jobs whose source gives no date
NOTIFY=true
MIN_MATCH_SCORE=20
SOURCES=linkedin,indeed,remoteok,remotive,himalayas,jobicy,wwr,yc,hn,greenhouse,lever
KEYWORDS=react native,react,python
```

A job is printed only if it passes all of these:

1. It is within the freshness window. Jobs with no reliable date are marked "unknown" and are never treated as recent.
2. It matches a keyword in the title, description, tags or skills. LinkedIn and JobSpy sources skip this check because their search query already did it (`SERVER_FILTERED_SOURCES`).
3. It passes the location/remote rule (global remote sources, YC, HN and company boards).
4. Its title and company are not excluded, and its location does not state an explicit region lock-out (see below).
5. Its relevance score is at least `MIN_MATCH_SCORE`.
6. It has not been seen before.

### Remote-eligibility exclusions

A job is rejected when its location or tags explicitly lock out your region, even if it also says "remote".
The phrases (`REMOTE_EXCLUDE_KEYWORDS` in `config.py`) are: United States only, US only, U.S. only, USA only,
must be based in US, North America only, Canada only, UK only, Europe only, EU only, Germany only, Australia only.
A bare "US" (e.g. "Remote (US)") is **not** a lock-out; only the explicit "... only" phrases are.

### Relevance scoring

Every accepted job gets a score (printed as `Match score:` and logged):

| Signal | Points (`config.py`) |
|---|---|
| Target keyword in the **title** | `SCORE_TITLE_KEYWORD` (50) |
| Target keyword only in description/tags | `SCORE_BODY_KEYWORD` (20) |
| Source already keyword-matched server-side (LinkedIn/Indeed) | `SCORE_SERVER_FILTERED` (20) |
| India / global / worldwide eligibility | `SCORE_ELIGIBILITY` (15) |
| Recent source-provided date | `SCORE_FRESH` (15) |

Jobs scoring below `MIN_MATCH_SCORE` (default 20, set via config, `.env`, or `--min-score`) are filtered out.
Senior/lead/manager titles and region-locked roles are rejected earlier, before scoring.

### First seen vs. posted

- **Posted** is the source-reported timestamp, or "unknown" when the source gives none. It is never guessed.
- **First seen by watcher** is the local discovery time in Asia/Kolkata (+05:30). It is never shown as the posted date.

## Company boards (Greenhouse and Lever)

Both are optional, read-only, and off until you list tokens. No login, no applications.

1. Copy the example config:
   ```
   copy config\company_boards.example.json config\company_boards.json   (Windows)
   cp   config/company_boards.example.json config/company_boards.json   (bash)
   ```
   `config/company_boards.json` is gitignored and stays user-managed.

2. **Add a Greenhouse board token.** Find it in the public board URL
   `https://boards.greenhouse.io/<board_token>` (or `https://job-boards.greenhouse.io/<board_token>`);
   the last path segment is the token. Add it to the `greenhouse` list:
   ```json
   { "greenhouse": ["stripe", "airbnb"], "lever": [] }
   ```
   The watcher calls `https://boards-api.greenhouse.io/v1/boards/<board_token>/jobs?content=true`.

3. **Add a Lever site name.** Find it in the public postings URL `https://jobs.lever.co/<site_name>`;
   the segment after `lever.co/` is the site name. Add it to the `lever` list:
   ```json
   { "greenhouse": [], "lever": ["netlify", "leverdemo"] }
   ```
   The watcher calls `https://api.lever.co/v0/postings/<site_name>?mode=json`.

4. Run as usual — company boards are included by default:
   ```
   python job_watcher.py --sources greenhouse,lever --once
   ```

Each board/site is fetched independently: if one fails, the others (and all other sources) keep running.
Company-board jobs pass through the same keyword, location, freshness, scoring, deduplication and logging rules.

## Sources

| Source | Status |
|---|---|
| LinkedIn | Live tested, works. Dates are day-level only, so the freshness window is enforced server-side. |
| Indeed | Live tested, works. |
| Remote OK, Remotive, Himalayas, Jobicy, We Work Remotely | Live tested, works. |
| Y Combinator | Live tested. Listings carry no posting date, so everything shows "unknown". No detail pages are fetched. |
| Hacker News "Who is hiring?" | Live tested. Title parsing from the comment header is best-effort. |
| Greenhouse | Enabled, but a no-op until you add board tokens to `config/company_boards.json`. Parser unit-tested with mocked payloads; not verified against a live board (no tokens shipped). |
| Lever | Enabled, but a no-op until you add site names to `config/company_boards.json`. Parser unit-tested with mocked payloads; not verified against a live site (no sites shipped). |
| Naukri | Disabled by default. Returns "recaptcha required"; not worked around. |
| Glassdoor | Disabled by default. Returned 0 results when tested; cause unknown. |
| Google Jobs | Disabled by default. Never run. |
| Startup.jobs | Not integrated. No existing code and no known safe public feed. |

## State and logs

- `state/seen_jobs.json` has one record per job, keyed `source:id:<external_id>` or, without a stable ID,
  `source:url:<canonical url>`. Titles are never used as keys, so same-titled jobs are not merged.
- URLs are canonicalised: fragment, tracking params and trailing slash removed; other query parameters kept.
- The same title and company on another source gets a "possible duplicate" note but is still printed.
- On first run, IDs from the old LinkedIn `seen_jobs.json` are imported once. The old `seen_remote_job_urls.json`
  is not imported, so expect a one-time batch of remote jobs on the first scan.
- State is written atomically, a corrupt file is moved aside, and records older than 180 days are pruned.
- `logs/new_jobs.log` records discovery time, source, title, company, location, posted time, first-seen time (Asia/Kolkata),
match score and URL for every printed job.

## Polling and failures

- Default poll interval is 900s with ±30s jitter. Each source has a 25s timeout and 3 attempts with exponential backoff.
- Retries cover connection errors, 5xx and 429. Other 4xx errors fail immediately.
- A failing source is reported in the summary and the others continue.
- LinkedIn keeps the original behaviour: max 8 description fetches per cycle with delays, and jobs beyond the cap are retried next cycle.
- Seen jobs are not re-fetched.

## Tests

```
python -m pytest tests -q
```

59 tests with mocked HTTP only, covering URL and date handling, keyword/title/location filters, remote-eligibility
exclusions (US-only/EU-only rejection, India/global acceptance), relevance scoring and the `MIN_MATCH_SCORE` gate,
the first-seen (Asia/Kolkata) output field, freshness, missing timestamps, dedup, state persistence, failing sources
(including per-board Greenhouse/Lever isolation), CLI `--once`/`--min-score`/source selection/reset/freshness override,
Ctrl+C in the polling loop, retry logic and every adapter's parser (including the Greenhouse and Lever parsers).

If pytest fails with a permission error on the system temp folder, add `--basetemp=<a folder you can write to>`.

## Behaviour notes

- Title exclusion matches whole words, so "Internal Tools Engineer" is not excluded by "intern".
- The location rule checks location and tags only, not the description. Because "remote" is in
  `REMOTE_LOCATION_KEYWORDS`, US-only remote roles from YC and HN still pass.
- The 2-year experience cap from the LinkedIn watcher also applies to YC postings, using the "min experience" field.
- Jobicy and Remote OK are queried with their dev filters so results are mostly tech roles.
