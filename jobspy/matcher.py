import re
from typing import Dict, List, Any, Optional, Tuple
from jobspy.resume import CANDIDATE_RESUME

def parse_experience_required(text: str) -> Optional[int]:
    """
    Parses minimum required years of experience from job descriptions or titles.
    Examples:
      '2+ years' -> 2
      '5+ years' -> 5
      '8+ years' -> 8
      '3-5 years' -> 3
      'minimum 4 years' -> 4
      'at least 6 yrs' -> 6
    """
    if not text or not isinstance(text, str):
        return None
    
    # Standard patterns
    patterns = [
        r'(\d+)\s*\+\s*(?:years?|yrs?)',                  # 5+ years, 5+ yrs
        r'(\d+)\s*(?:-|to)\s*\d+\s*(?:years?|yrs?)',       # 3-5 years, 3 to 5 yrs
        r'(?:minimum|min|at least)\s*(\d+)\s*(?:years?|yrs?)', # minimum 4 years
        r'(\d+)\s*(?:years?|yrs?)\s*(?:of)?\s*(?:experience|exp)', # 5 years experience
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
            
    return None


def evaluate_job_match(job_dict: Dict[str, Any], candidate_resume: Dict[str, Any] = CANDIDATE_RESUME) -> Dict[str, Any]:
    """
    Evaluates a job dictionary against the candidate's resume.
    Returns:
    {
      "match_score": int,
      "match_status": str,
      "experience_match": bool,
      "matched_skills": list,
      "missing_skills": list,
      "reasons": list
    }
    """
    title = str(job_dict.get("title") or "").strip()
    description = str(job_dict.get("description") or "").strip()
    full_text = f"{title}\n{description}"
    
    candidate_exp = candidate_resume.get("years_of_experience", 2)
    candidate_skills = candidate_resume.get("skills", [])
    target_roles = candidate_resume.get("target_roles", [])
    
    reasons = []
    
    # 1. Experience Check
    req_exp = parse_experience_required(full_text)
    
    experience_match = True
    match_status = "MATCH"
    
    if req_exp is not None:
        if req_exp > candidate_exp + 2:
            # If job requires significantly higher experience (e.g. 8+ when candidate has 2)
            experience_match = False
            match_status = "EXPERIENCE_TOO_HIGH"
            reasons.append(f"Requires {req_exp}+ years of experience; candidate has {candidate_exp} years.")
        elif req_exp > candidate_exp:
            reasons.append(f"Requires {req_exp} years of experience (slightly higher than candidate's {candidate_exp} years).")
        else:
            reasons.append(f"Experience requirement met ({req_exp} years required, candidate has {candidate_exp} years).")
    else:
        reasons.append("No explicit years of experience specified in job post.")

    # Check for senior keywords in title if exp wasn't explicitly parsed as high
    senior_keywords = ["sr.", "senior", "lead", "principal", "staff", "director", "head of", "architect"]
    title_lower = title.lower()
    is_senior_title = any(re.search(rf'\b{re.escape(kw)}\b', title_lower) for kw in senior_keywords)
    if is_senior_title and (req_exp is None or req_exp > 5):
        if match_status != "EXPERIENCE_TOO_HIGH":
            reasons.append("Seniority title mismatch (Senior/Lead role).")
            # Downgrade match status if title is senior and experience is high or unstated
            if req_exp and req_exp >= 5:
                match_status = "EXPERIENCE_TOO_HIGH"
                experience_match = False

    # 2. Skill Matching
    matched_skills = []
    missing_skills = []
    
    # Case-insensitive substring/word-boundary check for candidate skills
    for skill in candidate_skills:
        # Escape special regex chars like C++, .NET, React.js
        pattern = rf'\b{re.escape(skill)}\b'
        if re.search(pattern, full_text, re.IGNORECASE):
            matched_skills.append(skill)
            
    # Calculate score base
    # Skills weight: up to 60 points
    # Title match weight: up to 30 points
    # Experience match weight: up to 10 points
    
    skill_score = 0
    if candidate_skills:
        skill_ratio = len(matched_skills) / min(10, len(candidate_skills))
        skill_score = min(60, int(skill_ratio * 60))
        
    title_score = 0
    for role in target_roles:
        if role.lower() in title_lower or any(word in title_lower for word in role.lower().split()):
            title_score = 30
            break
            
    exp_score = 10 if experience_match else 0
    
    match_score = skill_score + title_score + exp_score
    if match_status == "EXPERIENCE_TOO_HIGH":
        match_score = min(match_score, 45) # Cap score for experience mismatch
        
    if matched_skills:
        reasons.append(f"Matched skills: {', '.join(matched_skills[:5])}")
    else:
        reasons.append("No explicit resume skills matched in job description.")
        
    return {
        "match_score": match_score,
        "match_status": match_status,
        "experience_match": experience_match,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "reasons": reasons
    }
