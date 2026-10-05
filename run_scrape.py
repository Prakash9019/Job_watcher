import csv
from jobspy import scrape_jobs

def run_job_search():
    print("Starting JobSpy job scrape...")
    
    jobs = scrape_jobs(
        site_name=["indeed", "linkedin", "zip_recruiter", "google"],
        search_term="software engineer",
        google_search_term="software engineer jobs near San Francisco, CA since yesterday",
        location="San Francisco, CA",
        results_wanted=10,
        hours_old=72,
        country_indeed='USA'
    )
    
    print(f"\nScrape complete! Found {len(jobs)} jobs across specified platforms.\n")
    
    if not jobs.empty:
        print("Sample Results:")
        print(jobs[['site', 'title', 'company', 'location', 'job_url']].head())
        
        output_filename = "jobs.csv"
        jobs.to_csv(output_filename, quoting=csv.QUOTE_NONNUMERIC, escapechar="\\", index=False)
        print(f"\nFull results saved successfully to '{output_filename}' in {output_filename}")
    else:
        print("No jobs found matching the search criteria.")

if __name__ == "__main__":
    run_job_search()
