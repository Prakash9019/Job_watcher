import os
import json
import pytest
from jobspy.matcher import evaluate_job_match, parse_experience_required
from jobspy.dedup import JobDeduplicator

def test_experience_parsing():
    assert parse_experience_required("Looking for a developer with 2+ years of experience") == 2
    assert parse_experience_required("Minimum 5 years of software engineering") == 5
    assert parse_experience_required("Requires 8+ years in backend development") == 8
    assert parse_experience_required("3-5 years exp in React") == 3
    assert parse_experience_required("Must have at least 6 yrs experience") == 6
    assert parse_experience_required("Entry level position") is None

def test_resume_matching_valid():
    job = {
        "title": "Software Engineer",
        "description": "We are looking for a Software Engineer with experience in React, Node.js, TypeScript, Python, and PostgreSQL. 2+ years required."
    }
    res = evaluate_job_match(job)
    assert res["experience_match"] is True
    assert res["match_status"] == "MATCH"
    assert "React" in res["matched_skills"]
    assert "Node.js" in res["matched_skills"]
    assert res["match_score"] > 50

def test_experience_mismatch_too_high():
    job = {
        "title": "Senior Software Engineer",
        "description": "Senior role. Must have 8+ years of experience in distributed systems and architecture."
    }
    res = evaluate_job_match(job)
    assert res["experience_match"] is False
    assert res["match_status"] == "EXPERIENCE_TOO_HIGH"
    assert "Requires 8+ years" in res["reasons"][0]

def test_deduplication_and_persistence():
    test_db = "data/seen_jobs_test.json"
    if os.path.exists(test_db):
        os.remove(test_db)
        
    try:
        dedup = JobDeduplicator(filepath=test_db)

        job_1 = {
            "id": "job_123",
            "title": "Backend Engineer",
            "company": "Tech Corp",
            "job_url": "https://example.com/job/123"
        }

        # First discovery
        is_new, key = dedup.process_job(job_1, match_score=80, match_status="MATCH")
        assert is_new is True
        assert key == "job_123"
        assert dedup.is_notified(job_1) is False

        # Mark notified
        dedup.mark_notified(job_1)
        assert dedup.is_notified(job_1) is True

        # Re-process same job
        is_new_again, _ = dedup.process_job(job_1, match_score=80, match_status="MATCH")
        assert is_new_again is False

        # Reload deduplicator from file to verify persistence
        dedup_reloaded = JobDeduplicator(filepath=test_db)
        assert dedup_reloaded.is_notified(job_1) is True
    finally:
        if os.path.exists(test_db):
            os.remove(test_db)
