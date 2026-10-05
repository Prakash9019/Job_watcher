import os

def handle_new_job(job_info: dict):
    """
    Modular notification handler for new matching jobs.
    Receives job dictionary enriched with match results.
    """
    match_res = job_info.get("match_result", {})
    
    print("\n" + "="*50)
    print("NEW MATCHING JOB")
    print(f"Title: {job_info.get('title')}")
    print(f"Company: {job_info.get('company')}")
    print(f"Location: {job_info.get('location')}")
    print(f"Match Score: {match_res.get('match_score')}")
    print(f"Experience: {'Match' if match_res.get('experience_match') else 'Mismatch / Too High'}")
    print(f"Matched Skills: {', '.join(match_res.get('matched_skills', []))}")
    print(f"Missing Skills: {', '.join(match_res.get('missing_skills', []))}")
    print(f"URL: {job_info.get('job_url_direct') or job_info.get('job_url')}")
    print("="*50 + "\n")
