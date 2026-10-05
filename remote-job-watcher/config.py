"""Shared configuration for every source. Edit the constants below, put overrides
in .env (see .env.example), or use command-line flags (see job_watcher.py --help)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# ---------------- CONFIG ----------------
KEYWORDS = [
    "react native", "react", "typescript", "javascript", "node.js", "nodejs",
    "python", "fastapi", "django",
    "backend developer", "backend engineer", "frontend developer", "frontend engineer",
    "full stack developer", "full stack engineer", "fullstack",
    "software engineer", "software developer",
    "ai engineer", "machine learning engineer", "computer vision",
]
LOCATION = "India"
REMOTE_LOCATION_KEYWORDS = ["india", "asia", "worldwide", "global", "anywhere", "remote"]

# Union of the title exclusions from the LinkedIn watcher and the new spec.
TITLE_EXCLUDE_KEYWORDS = [
    "senior", "sr.", "sr ", "lead", "principal", "staff", "manager", "director",
    "architect", "intern", "interns", "internship", "trainee", "fresher", "apprentice",
    "campus", " ii", " iii", " iv", "3+", "4+", "5+",
]
COMPANY_EXCLUDE_KEYWORDS = ["scoutit", "Crossing Hurdles"]

# Explicit remote-eligibility exclusions. A job whose location/tags state any of these is
# rejected even if it also says "remote" (checked before the remote-keyword acceptance).
REMOTE_EXCLUDE_KEYWORDS = [
    "united states only", "us only", "u.s. only", "usa only", "must be based in us",
    "north america only", "canada only", "uk only", "europe only", "eu only",
    "germany only", "australia only",
]
# Eligibility terms that earn a positive relevance score.
ELIGIBILITY_SCORE_KEYWORDS = ["india", "worldwide", "global", "anywhere"]

# Relevance scoring. A job must score at least MIN_MATCH_SCORE to be printed.
MIN_MATCH_SCORE = 20
SCORE_TITLE_KEYWORD = 50          # a target keyword appears in the title
SCORE_BODY_KEYWORD = 20          # a target keyword appears only in description/tags
SCORE_SERVER_FILTERED = 20       # source already keyword-matched server-side
SCORE_ELIGIBILITY = 15           # India / global / worldwide eligibility
SCORE_FRESH = 15                 # has a recent source-provided date

FRESHNESS_MINUTES = 1440          # 60=1h, 360=6h, 1440=24h, 10080=7d
STRICT_FRESHNESS = True           # False: ignore posting dates entirely
PRINT_UNKNOWN_DATE = True         # print jobs whose source gives no reliable date
POLL_INTERVAL_SECONDS = 900
POLL_JITTER_SECONDS = 30
REQUEST_TIMEOUT_SECONDS = 25
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 3            # seconds; doubles per retry (3, 6, ...)

# LinkedIn (preserved from linkedin_job_watcher.py)
LINKEDIN_KEYWORDS = (
    '"Full Stack Developer" OR "Software Development Engineer" OR '
    '"Software Engineer" OR "Frontend Developer" OR "Backend Developer" OR '
    '"React Developer" OR "React Native Developer" OR "Node.js Developer" OR '
    '"MERN Stack Developer" OR "JavaScript Developer" OR "Angular Developer"'
)
LINKEDIN_EXPERIENCE_LEVEL = "2,3"     # 2=Entry, 3=Associate
LINKEDIN_MAX_PAGES = 3
MAX_DESC_FETCHES_PER_CYCLE = 8
DESC_FETCH_DELAY_RANGE = (2, 5)
MAX_EXPERIENCE_YEARS = 2

# JobSpy-backed sources
JOBSPY_SEARCH_TERMS = ["software engineer", "full stack developer", "backend developer", "react developer"]
JOBSPY_RESULTS_WANTED = 25

# Sources whose server-side query already did the keyword matching skip the
# client-side KEYWORDS check (title/company/freshness filters still apply).
SERVER_FILTERED_SOURCES = {"linkedin", "indeed", "glassdoor", "googlejobs", "naukri"}  # slugs of the source labels
# Sources that cover the whole world: the REMOTE_LOCATION_KEYWORDS rule applies.
LOCATION_CHECKED_SOURCES = {"remoteok", "remotive", "himalayas", "jobicy", "weworkremotely",
                            "ycombinator", "hackernews", "greenhouse", "lever"}

ENABLED_SOURCES = {
    "linkedin": True, "indeed": True, "glassdoor": False, "google": False, "naukri": False,  # naukri: CAPTCHA-gated; glassdoor: 0 results when tested
    "remoteok": True, "remotive": True, "himalayas": True, "jobicy": True, "wwr": True,
    "yc": True, "hn": True,
    # Company boards: no-ops until you list tokens in config/company_boards.json.
    "greenhouse": True, "lever": True,
}
STATE_FILE = BASE_DIR / "state" / "seen_jobs.json"
LOG_FILE = BASE_DIR / "logs" / "new_jobs.log"
COMPANY_BOARDS_FILE = BASE_DIR / "config" / "company_boards.json"
NOTIFY = True
# -----------------------------------------


@dataclass
class Settings:
    keywords: list = field(default_factory=lambda: list(KEYWORDS))
    location: str = LOCATION
    remote_location_keywords: list = field(default_factory=lambda: list(REMOTE_LOCATION_KEYWORDS))
    remote_exclude: list = field(default_factory=lambda: list(REMOTE_EXCLUDE_KEYWORDS))
    eligibility_score_keywords: list = field(default_factory=lambda: list(ELIGIBILITY_SCORE_KEYWORDS))
    title_exclude: list = field(default_factory=lambda: list(TITLE_EXCLUDE_KEYWORDS))
    company_exclude: list = field(default_factory=lambda: list(COMPANY_EXCLUDE_KEYWORDS))
    min_match_score: int = MIN_MATCH_SCORE
    score_title_keyword: int = SCORE_TITLE_KEYWORD
    score_body_keyword: int = SCORE_BODY_KEYWORD
    score_server_filtered: int = SCORE_SERVER_FILTERED
    score_eligibility: int = SCORE_ELIGIBILITY
    score_fresh: int = SCORE_FRESH
    freshness_minutes: int = FRESHNESS_MINUTES
    strict_freshness: bool = STRICT_FRESHNESS
    print_unknown_date: bool = PRINT_UNKNOWN_DATE
    poll_interval: int = POLL_INTERVAL_SECONDS
    poll_jitter: int = POLL_JITTER_SECONDS
    timeout: int = REQUEST_TIMEOUT_SECONDS
    max_retries: int = MAX_RETRIES
    backoff_base: float = RETRY_BACKOFF_BASE
    linkedin_keywords: str = LINKEDIN_KEYWORDS
    linkedin_experience: str = LINKEDIN_EXPERIENCE_LEVEL
    linkedin_max_pages: int = LINKEDIN_MAX_PAGES
    max_desc_fetches: int = MAX_DESC_FETCHES_PER_CYCLE
    desc_fetch_delay: tuple = DESC_FETCH_DELAY_RANGE
    max_experience_years: int = MAX_EXPERIENCE_YEARS
    jobspy_terms: list = field(default_factory=lambda: list(JOBSPY_SEARCH_TERMS))
    jobspy_results: int = JOBSPY_RESULTS_WANTED
    server_filtered: set = field(default_factory=lambda: set(SERVER_FILTERED_SOURCES))
    location_checked: set = field(default_factory=lambda: set(LOCATION_CHECKED_SOURCES))
    enabled: dict = field(default_factory=lambda: dict(ENABLED_SOURCES))
    state_file: Path = STATE_FILE
    log_file: Path = LOG_FILE
    company_boards_file: Path = COMPANY_BOARDS_FILE
    notify: bool = NOTIFY
    json_output: str = ""
    csv_output: str = ""

    def with_(self, **kw) -> "Settings":
        return replace(self, **kw)


_ENV_KEYS = {"FRESHNESS_MINUTES", "POLL_INTERVAL_SECONDS", "LOCATION", "STRICT_FRESHNESS",
             "PRINT_UNKNOWN_DATE", "NOTIFY", "SOURCES", "KEYWORDS", "MIN_MATCH_SCORE"}


def _bool(v: str) -> bool:
    return v.strip().lower() in ("1", "true", "yes", "on")


def read_env_file(path: Path = BASE_DIR / ".env") -> dict:
    """Parse KEY=VALUE lines; real environment variables take precedence."""
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip('"').strip("'")
    values.update({k: v for k, v in os.environ.items() if k in _ENV_KEYS})
    return values


def load_company_boards(path) -> dict:
    """Read config/company_boards.json -> {"greenhouse": [tokens], "lever": [sites]}.
    Missing/invalid file means no company boards (the sources become no-ops)."""
    import json
    result = {"greenhouse": [], "lever": []}
    path = Path(path)
    if not path.exists():
        return result
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        print(f"Warning: {path.name} is not valid JSON; ignoring company boards.")
        return result
    for key in result:
        values = data.get(key) or []
        if isinstance(values, list):
            result[key] = [str(v).strip() for v in values if str(v).strip()]
    return result


def load_settings(env: dict | None = None) -> Settings:
    env = read_env_file() if env is None else env
    s = Settings()
    if "FRESHNESS_MINUTES" in env: s.freshness_minutes = int(env["FRESHNESS_MINUTES"])
    if "POLL_INTERVAL_SECONDS" in env: s.poll_interval = int(env["POLL_INTERVAL_SECONDS"])
    if "LOCATION" in env: s.location = env["LOCATION"]
    if "STRICT_FRESHNESS" in env: s.strict_freshness = _bool(env["STRICT_FRESHNESS"])
    if "PRINT_UNKNOWN_DATE" in env: s.print_unknown_date = _bool(env["PRINT_UNKNOWN_DATE"])
    if "NOTIFY" in env: s.notify = _bool(env["NOTIFY"])
    if "MIN_MATCH_SCORE" in env: s.min_match_score = int(env["MIN_MATCH_SCORE"])
    if "KEYWORDS" in env: s.keywords = [k.strip() for k in env["KEYWORDS"].split(",") if k.strip()]
    if "SOURCES" in env:
        wanted = {k.strip().lower() for k in env["SOURCES"].split(",") if k.strip()}
        s.enabled = {k: (k in wanted) for k in s.enabled}
    return s
