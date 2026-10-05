import argparse
import os
import sys
import time
import signal
import logging
import pandas as pd

from jobspy import scrape_jobs
from jobspy.matcher import evaluate_job_match
from jobspy.dedup import JobDeduplicator
from jobspy.notifier import handle_new_job
from jobspy.yc import fetch_yc_jobs

# Set up logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Watcher")

# Flag for graceful shutdown
running = True

def signal_handler(sig, frame):
    global running
    logger.info("Interrupt received! Stopping watcher gracefully...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def load_config():
    """
    Loads configuration settings from environment variables or .env file.
    """
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip())

    sites_raw = os.environ.get("SITES", "linkedin,indeed,zip_recruiter,google")
    sites = [s.strip() for s in sites_raw.split(",") if s.strip()]

    terms_raw = os.environ.get("SEARCH_TERMS", "software engineer,full stack engineer,backend engineer,AI engineer")
    search_terms = [t.strip() for t in terms_raw.split(",") if t.strip()]

    location = os.environ.get("LOCATION", "India")
    is_remote = os.environ.get("REMOTE", "true").lower() in ("true", "1", "yes")
    interval = int(os.environ.get("WATCH_INTERVAL_MINUTES", 15))
    hours_old = int(os.environ.get("HOURS_OLD", 24))
    results_wanted = int(os.environ.get("RESULTS_WANTED", 50))

    yc_enabled = os.environ.get("YC_ENABLED", "true").lower() in ("true", "1", "yes")

    return {
        "yc_enabled": yc_enabled,
        "sites": sites,
        "search_terms": search_terms,
        "location": location,
        "is_remote": is_remote,
        "interval_minutes": interval,
        "hours_old": hours_old,
        "results_wanted": results_wanted,
    }


def process_job_dict(job_dict: dict, dedup: JobDeduplicator):
    """
    Matches a job against the resume, dedups it, and notifies if new + relevant.
    """
    # Evaluate resume match
    match_res = evaluate_job_match(job_dict)

    # Deduplicate and register state
    is_new, job_key = dedup.process_job(
        job_dict=job_dict,
        match_score=match_res["match_score"],
        match_status=match_res["match_status"]
    )

    # Trigger event only for NEW + relevant jobs that haven't been notified
    if is_new and not dedup.is_notified(job_dict):
        if match_res["match_status"] != "EXPERIENCE_TOO_HIGH" and match_res["match_score"] >= 30:
            job_dict["match_result"] = match_res
            try:
                handle_new_job(job_dict)
                dedup.mark_notified(job_dict)
            except Exception as ne:
                logger.error(f"Error handling notification for job {job_key}: {ne}")
        else:
            logger.debug(f"Job {job_key} skipped notification (Status: {match_res['match_status']}, Score: {match_res['match_score']})")


def run_yc_cycle(config: dict, dedup: JobDeduplicator):
    """
    Polls Y Combinator Work at a Startup listings and runs each job through the pipeline.
    """
    logger.info("Fetching Y Combinator (Work at a Startup) jobs...")
    try:
        jobs = fetch_yc_jobs(remote_only=config["is_remote"])
    except Exception as e:
        logger.error(f"YC fetch failed: {e}. Continuing operation.")
        return
    logger.info(f"Fetched {len(jobs)} YC jobs. Evaluating against resume...")
    for job in jobs:
        if not running:
            break
        process_job_dict(job, dedup)


def run_watcher_cycle(config: dict, dedup: JobDeduplicator):
    """
    Runs a single scraping and matching iteration.
    """
    logger.info(f"Starting job scrape for terms: {config['search_terms']} | Location: {config['location']}")
    
    for term in config["search_terms"]:
        if not running:
            break
        try:
            logger.info(f"Scraping term '{term}' across sites: {config['sites']}")
            jobs_df: pd.DataFrame = scrape_jobs(
                site_name=config["sites"],
                search_term=term,
                location=config["location"],
                is_remote=config["is_remote"],
                results_wanted=config["results_wanted"],
                hours_old=config["hours_old"],
            )

            if jobs_df is None or jobs_df.empty:
                logger.info(f"No jobs found for term '{term}'.")
                continue

            logger.info(f"Fetched {len(jobs_df)} jobs for '{term}'. Evaluating against resume...")

            for _, job_row in jobs_df.iterrows():
                if not running:
                    break
                process_job_dict(job_row.to_dict(), dedup)

        except Exception as e:
            logger.error(f"Error occurred during scrape cycle for term '{term}': {e}. Continuing operation.")
            continue

    if config.get("yc_enabled") and running:
        run_yc_cycle(config, dedup)


def main():
    parser = argparse.ArgumentParser(description="JobSpy Continuous Job Watcher & Resume Matcher")
    parser.add_argument("--once", action="store_true", help="Run a single scrape cycle and exit")
    parser.add_argument("--interval", type=int, help="Override check interval in minutes")
    args = parser.parse_args()

    config = load_config()
    if args.interval:
        config["interval_minutes"] = args.interval

    dedup = JobDeduplicator()
    logger.info("JobSpy Watcher initialized.")
    logger.info(f"Interval: {config['interval_minutes']} mins | Mode: {'Single Run (--once)' if args.once else 'Continuous'}")

    backoff_seconds = 10

    while running:
        start_time = time.time()
        try:
            run_watcher_cycle(config, dedup)
            backoff_seconds = 10 # reset backoff on successful cycle
        except Exception as e:
            logger.error(f"Unhandled error in main watcher loop: {e}. Retrying in {backoff_seconds} seconds.")
            time.sleep(backoff_seconds)
            backoff_seconds = min(backoff_seconds * 2, 300) # exponential backoff up to 5 min
            continue

        if args.once or not running:
            logger.info("Completed single run cycle (--once). Exiting.")
            break

        sleep_seconds = config["interval_minutes"] * 60
        logger.info(f"Cycle completed. Waiting {config['interval_minutes']} minutes before next run...")
        
        # Sleep in small increments to allow immediate response to Ctrl+C signal
        for _ in range(int(sleep_seconds)):
            if not running:
                break
            time.sleep(1)

    logger.info("Watcher stopped.")

if __name__ == "__main__":
    main()
