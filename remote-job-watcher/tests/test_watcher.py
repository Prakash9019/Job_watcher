import json
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest
import requests

import config
import filters
import http_client
import job_watcher
import output
from models import canonical_url, job_key, make_job, parse_datetime
from sources import (greenhouse_source, himalayas_source, hn_source, jobicy_source, lever_source,
                     linkedin_source, remoteok_source, remotive_source, wwr_source, yc_source)
from state_store import StateStore

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


from sources import Context

_CTX = Context(state=None, log=lambda m: None)


def job(title="React Developer", source="Remote OK", url="https://x.io/jobs/1", posted=None, **kw):
    kw.setdefault("is_remote", True)
    return make_job(source, title, kw.pop("company", "Acme"), url, posted=posted, **kw)


def ago(**kw):
    return (NOW - timedelta(**kw)).isoformat()


# ---------- URL / model ----------
def test_canonical_url():
    assert canonical_url("HTTPS://Example.com/jobs/1/#frag") == "https://example.com/jobs/1"
    assert canonical_url("https://e.com/j?id=5&utm_source=x&ref=y") == "https://e.com/j?id=5"
    assert canonical_url("https://e.com/j?id=5") != canonical_url("https://e.com/j?id=6")  # keep meaningful params
    assert canonical_url("/relative") == ""


def test_make_job_requires_direct_url():
    assert make_job("S", "T", "C", "") is None
    assert make_job("S", "T", "C", "not-a-url") is None
    j = make_job("S", "T", "C", "https://a.b/c/", posted="2026-10-03T10:00:00Z", external_id=7)
    assert j["url"] == "https://a.b/c" and j["external_id"] == "7" and j["date_status"] == "known"


def test_parse_datetime_formats():
    assert parse_datetime(1790000000)[0].year == 2026
    assert parse_datetime("Sat, 03 Oct 2026 10:00:00 +0000")[0].hour == 10
    assert parse_datetime("2026-10-03 10:00:00")[0].tzinfo is not None
    assert parse_datetime("2026-10-03") [1] is True
    assert parse_datetime("garbage") == (None, False)
    assert parse_datetime(float("nan")) == (None, False)


# ---------- filters ----------
def test_keyword_matching(settings):
    assert filters.keyword_match(job("Python Engineer"), settings)
    assert filters.keyword_match(job("Designer", description="we use React Native"), settings)
    assert filters.keyword_match(job("Cook", tags=["django"]), settings)
    assert not filters.keyword_match(job("Account Executive"), settings)
    assert not filters.keyword_match(job("Reactor Technician"), settings)  # whole-word only


def test_title_exclusion(settings):
    for t in ["Senior Engineer", "Sr. Developer", "Engineering Manager", "Software Intern", "Tech Lead"]:
        assert filters.title_excluded(t, settings), t
    assert not filters.title_excluded("Internal Tools Engineer", settings)
    assert not filters.title_excluded("International Software Engineer", settings)
    assert filters.company_excluded("ScoutIT Inc", settings)


def test_location_rule(settings):
    assert filters.location_ok(job(location="Worldwide"), settings)
    assert filters.location_ok(job(location="India"), settings)
    assert not filters.location_ok(job(location="USA only"), settings)
    assert filters.location_ok(job(location=""), settings)  # remote board, no restriction
    assert not filters.location_ok(job(source="Hacker News", location="", is_remote=False), settings)
    assert filters.location_ok(job(source="LinkedIn", location="Pune"), settings)  # server-side location


def test_freshness(settings):
    settings.freshness_minutes = 60
    assert filters.freshness(job(posted=ago(minutes=30)), settings, NOW) == "fresh"
    assert filters.freshness(job(posted=ago(minutes=90)), settings, NOW) == "old"
    assert filters.freshness(job(posted=None), settings, NOW) == "unknown"
    settings.freshness_minutes = 1440
    assert filters.freshness(job(posted="2026-10-03"), settings, NOW) == "fresh"  # day precision
    assert filters.freshness(job(posted="2026-09-30"), settings, NOW) == "old"


def test_missing_timestamp_behaviour(settings):
    j = job(posted=None)
    assert j["date_status"] == "unknown" and j["posted_at"] is None  # never invented
    assert filters.evaluate(j, settings, NOW) == "ok"
    settings.print_unknown_date = False
    assert filters.evaluate(j, settings, NOW) == "unknown_date"
    settings.strict_freshness = False
    assert filters.evaluate(j, settings, NOW) == "ok"
    assert filters.evaluate(job(posted=ago(days=30)), settings, NOW) == "ok"  # freshness disabled


# ---------- state / dedup ----------
def test_job_keys():
    assert job_key(job(external_id=5)) == "remoteok:id:5"
    assert job_key(job(url="https://x.io/a/#f")) == "remoteok:url:https://x.io/a"
    assert job_key(job(title="Same", url="https://x.io/a")) != job_key(job(title="Same", url="https://x.io/b"))
    assert job_key(job(external_id=5)) != job_key(job(source="Remotive", external_id=5))


def test_state_persistence_and_duplicate_note(tmp_path):
    path = tmp_path / "state" / "s.json"
    st = StateStore(path)
    a = job(external_id=1)
    assert not st.is_seen(a)
    st.mark_seen(a)
    st.save()
    st2 = StateStore(path)
    assert st2.is_seen(a)
    rec = json.loads(path.read_text())["remoteok:id:1"]
    assert rec["first_seen_at"] and rec["url"] == a["url"]
    other = job(source="Remotive", url="https://r.com/9")
    assert st2.possible_duplicate_of(other) == "Remote OK"
    assert not st2.is_seen(other)  # not hidden across sources


def test_corrupt_state_recovers(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{not json")
    assert StateStore(p).records == {}


# ---------- cycle pipeline ----------
def fetchers_for(jobs_by_source):
    def mk(items):
        def f(settings, ctx):
            if isinstance(items, Exception):
                raise items
            return items
        return f
    return {k: mk(v) for k, v in jobs_by_source.items()}


def run(settings, fetchers, names=None, state=None):
    state = state or StateStore(settings.state_file)
    return job_watcher.run_cycle(settings, state, fetchers, names or list(fetchers), now=NOW)


def test_new_then_seen(settings, capsys):
    fetchers = fetchers_for({"a": [job(posted=ago(minutes=5), external_id=1)]})
    s1 = run(settings, fetchers)
    out = capsys.readouterr().out
    assert s1["new"] == 1 and "NEW JOB FOUND" in out and "URL: https://x.io/jobs/1" in out
    s2 = run(settings, fetchers)
    assert s2["new"] == 0 and s2["seen"] == 1
    assert settings.log_file.read_text().count("https://x.io/jobs/1") == 1


def test_counters(settings):
    jobs = [job(posted=ago(minutes=5), external_id=1),
            job("React Dev 2", posted=ago(days=3), url="https://x.io/2", external_id=2),
            job("Cook", posted=ago(minutes=5), url="https://x.io/3", external_id=3),
            job("Senior React Dev", posted=ago(minutes=5), url="https://x.io/4", external_id=4)]
    s = run(settings, fetchers_for({"a": jobs}))
    assert (s["raw"], s["matching"], s["new"], s["old"], s["filtered"]) == (4, 1, 1, 1, 2)


def test_one_source_failing_others_continue(settings, capsys):
    fetchers = fetchers_for({"a": requests.HTTPError("500 Server Error"), "b": [job(posted=ago(minutes=1))]})
    s = run(settings, fetchers)
    assert s["failed"] == ["a"] and s["new"] == 1 and s["queried"] == 2
    assert "a FAILED" in capsys.readouterr().out


def test_no_new_jobs_message(settings, capsys):
    s = run(settings, fetchers_for({"a": []}))
    job_watcher.output.print_summary(s)
    assert "No new matching jobs found." in capsys.readouterr().out


# ---------- CLI ----------
def cli(settings, argv, fetchers):
    return job_watcher.main(argv + ["--no-notification"], fetchers=fetchers, settings=settings, sleep=lambda s: None)


def test_cli_once_and_reset(settings, capsys):
    calls = []
    fetchers = {"linkedin": lambda s, c: calls.append("li") or [job("React Dev", "LinkedIn", posted=ago(minutes=2), external_id=9)],
                "remoteok": lambda s, c: calls.append("ro") or []}
    assert cli(settings, ["--once", "--sources", "linkedin"], fetchers) == 0
    assert calls == ["li"]  # only the selected source was queried
    capsys.readouterr()
    cli(settings, ["--once", "--sources", "linkedin"], fetchers)
    assert "No new matching jobs found." in capsys.readouterr().out
    cli(settings, ["--once", "--sources", "linkedin", "--reset-state"], fetchers)
    assert "NEW JOB FOUND" in capsys.readouterr().out  # reset -> printed again


def test_cli_unknown_source(settings):
    with pytest.raises(SystemExit):
        cli(settings, ["--once", "--sources", "bogus"], {})


def test_cli_freshness_override(settings, capsys):
    fetchers = {"remoteok": lambda s, c: [job(posted=ago(hours=3))]}
    s = settings.with_(freshness_minutes=1440)
    job_watcher.main(["--once", "--freshness", "60", "--no-notification", "--sources", "remoteok"],
                     fetchers=fetchers, settings=s)
    assert "NEW JOB FOUND" not in capsys.readouterr().out and s.freshness_minutes == 60


def test_continuous_loop_polls_and_stops_on_ctrl_c(settings):
    n = {"cycles": 0}

    def f(s, c):
        n["cycles"] += 1
        return []
    ticks = {"n": 0}

    def fake_sleep(_):
        ticks["n"] += 1
        if n["cycles"] >= 2:
            raise KeyboardInterrupt
    settings.poll_interval, settings.poll_jitter = 30, 0
    assert job_watcher.main(["--sources", "a", "--no-notification"], fetchers={"a": f}, settings=settings, sleep=fake_sleep) == 0
    assert n["cycles"] == 2


# ---------- HTTP retry ----------
def _resp(code):
    r = requests.Response()
    r.status_code = code
    r._content = b"{}"
    return r


def test_http_retries_5xx_then_raises(settings):
    with mock.patch.object(http_client._SESSION, "get", return_value=_resp(500)) as g, mock.patch("http_client.time.sleep"):
        with pytest.raises(requests.HTTPError):
            http_client.get("https://x", settings, log=lambda m: None)
    assert g.call_count == settings.max_retries


def test_http_no_retry_on_404(settings):
    with mock.patch.object(http_client._SESSION, "get", return_value=_resp(404)) as g:
        with pytest.raises(requests.HTTPError):
            http_client.get("https://x", settings)
    assert g.call_count == 1


# ---------- adapters with mocked payloads ----------
def test_remoteok_parse():
    data = [{"legal": "notice"}, {"id": "11", "position": "React Dev", "company": "Co", "url": "https://remoteok.com/remote-jobs/11",
                                   "date": "2026-10-03T10:00:00+00:00", "tags": ["react"]}]
    (j,) = remoteok_source.parse(data)
    assert j["external_id"] == "11" and j["tags"] == ["react"] and j["date_status"] == "known"


def test_remotive_himalayas_jobicy_parse():
    (r,) = remotive_source.parse({"jobs": [{"id": 1, "title": "Py Dev", "company_name": "C", "url": "https://remotive.com/j/1",
                                            "publication_date": "2026-10-03T09:00:00", "candidate_required_location": "Worldwide"}]})
    assert r["location"] == "Worldwide"
    (h,) = himalayas_source.parse({"jobs": [{"title": "Dev", "companyName": "C", "applicationLink": "https://himalayas.app/j/1",
                                             "pubDate": 1790000000, "locationRestrictions": ["India", "UAE"]}]})
    assert h["location"] == "India, UAE" and h["date_status"] == "known"
    (jc,) = jobicy_source.parse({"jobs": [{"id": 5, "jobTitle": "Dev", "companyName": "C", "url": "https://jobicy.com/jobs/5",
                                           "pubDate": "2026-10-03 08:00:00", "jobGeo": "Anywhere", "jobIndustry": ["Engineering"]}]})
    assert jc["tags"] == ["Engineering"]


def test_wwr_parse():
    xml = """<rss><channel><item><title>Acme: Backend Engineer</title><link>https://weworkremotely.com/remote-jobs/acme-be</link>
    <pubDate>Sat, 03 Oct 2026 10:00:00 +0000</pubDate><region>Anywhere in the World</region></item></channel></rss>"""
    (j,) = wwr_source.parse(xml)
    assert j["company"] == "Acme" and j["title"] == "Backend Engineer" and j["date_status"] == "known"


def test_yc_parse_and_no_date():
    import html as h
    page = {"props": {"jobPostings": [{"id": 1, "title": "Full Stack Engineer", "url": "/companies/x/jobs/abc", "companyName": "X",
                                       "location": "Remote (US)", "skills": ["React"], "minExperience": "1+ years"}, {"id": 2, "title": "No url"}]}}
    html = f'<div data-page="{h.escape(json.dumps(page))}"></div>'
    (j,) = yc_source.parse_page(html)
    assert j["url"] == "https://www.ycombinator.com/companies/x/jobs/abc" and j["date_status"] == "unknown"
    with pytest.raises(ValueError):
        yc_source.parse_page("<html></html>")


def test_hn_parse():
    data = {"hits": [{"objectID": "5", "parent_id": 1, "created_at_i": 1790000000,
                      "comment_text": "Acme | Backend Engineer | Remote (India) | Full-time<p>We use Python"},
                     {"objectID": "6", "parent_id": 5, "comment_text": "a reply"}]}
    (j,) = hn_source.parse(data, 1)
    assert j["company"] == "Acme" and j["title"] == "Backend Engineer" and "India" in j["location"]
    assert j["url"].endswith("item?id=5")


LI_HTML = """<li><div class="base-card" data-entity-urn="urn:li:jobPosting:123">
<a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/react-dev-123?trk=x"></a>
<h3 class="base-search-card__title">
 React Developer </h3><h4 class="base-search-card__subtitle"><a class="hidden-nested-link" href="#"> Acme </a></h4>
<span class="job-search-card__location"> Pune, India </span><time class="job-search-card__listdate" datetime="2026-10-03">1 hour ago</time></div></li>
<li><div data-entity-urn="urn:li:jobPosting:456"><h3 class="base-search-card__title">Senior Engineer</h3>
<h4 class="base-search-card__subtitle"><a>Big Co</a></h4></div></li>"""


def test_linkedin_parse_and_experience():
    jobs = linkedin_source.parse_jobs(LI_HTML)
    assert [j["external_id"] for j in jobs] == ["123", "456"]
    assert jobs[0]["title"] == "React Developer" and jobs[0]["company"] == "Acme"
    assert jobs[0]["url"] == "https://www.linkedin.com/jobs/view/123" and jobs[0]["date_status"] == "date_only"
    assert linkedin_source.description_requires_more_experience("needs 5+ years", 2)
    assert not linkedin_source.description_requires_more_experience("1-3 years", 2)
    assert not linkedin_source.description_requires_more_experience("2 years", 2)


def test_linkedin_fetch_skips_excluded_and_seen(settings):
    from sources import Context
    state = StateStore(settings.state_file)
    settings.desc_fetch_delay = (0, 0)
    settings.linkedin_max_pages = 1
    detail_calls = []

    def fake_get_text(url, s, **kw):
        if "seeMoreJobPostings" in url:
            return LI_HTML
        detail_calls.append(url)
        return "<p>2+ years</p>"
    with mock.patch("sources.linkedin_source.http_client.get_text", side_effect=fake_get_text):
        out = linkedin_source.fetch(settings, Context(state=state, log=lambda m: None))
    assert [j["external_id"] for j in out] == ["123"]
    assert detail_calls == ["https://www.linkedin.com/jobs/view/123"]  # excluded "Senior" job never fetched
    assert state.is_seen(linkedin_source.parse_jobs(LI_HTML)[1])  # recorded so it is not retried


# ---------- remote-eligibility exclusions ----------
@pytest.mark.parametrize("loc", [
    "Remote (US only)", "United States only", "USA only", "Must be based in US",
    "Remote - North America only", "Canada only", "UK only", "Europe only",
    "EU only", "Germany only", "Australia only",
])
def test_explicit_region_lockout_rejected(settings, loc):
    j = job(title="Python Engineer", location=loc, posted=ago(minutes=5))
    assert filters.location_ineligible(j, settings)
    assert not filters.location_ok(j, settings)          # beats the 'remote' mention
    assert filters.evaluate(j, settings, NOW) == "excluded"


def test_eu_only_in_tags_rejected(settings):
    j = job(title="Python Engineer", location="Remote", tags=["EU only"], posted=ago(minutes=5))
    assert filters.evaluate(j, settings, NOW) == "excluded"


@pytest.mark.parametrize("loc", ["India", "Worldwide", "Global", "Anywhere", "Remote, India"])
def test_india_global_accepted(settings, loc):
    j = job(title="Python Engineer", location=loc, posted=ago(minutes=5))
    assert not filters.location_ineligible(j, settings)
    assert filters.location_ok(j, settings)
    assert filters.evaluate(j, settings, NOW) == "ok"


def test_us_without_only_is_not_locked_out(settings):
    # 'US' alone (e.g. 'Remote (US)') is not an explicit lock-out phrase
    assert not filters.location_ineligible(job(location="Remote (US)"), settings)


# ---------- scoring ----------
def test_score_calculation(settings):
    settings.freshness_minutes = 1440
    title_india_fresh = job(title="Python Developer", location="India", posted=ago(minutes=5))
    assert filters.score_job(title_india_fresh, settings, NOW) == 50 + 15 + 15

    body_only = job(title="Operations Specialist", description="we use django and react", location="", posted=None)
    assert filters.score_job(body_only, settings, NOW) == 20          # keyword in body only, no bonuses

    li = job(title="ASP.NET Developer", source="LinkedIn", location="Pune", posted=ago(minutes=5))
    assert filters.score_job(li, settings, NOW) == 20 + 15            # server-filtered baseline + fresh


def test_min_match_score_gate(settings, capsys):
    settings.min_match_score = 100                                    # nothing can reach this
    s = run(settings, fetchers_for({"a": [job(title="Python Developer", location="India", posted=ago(minutes=5))]}))
    assert s["new"] == 0 and s["matching"] == 0 and s["filtered"] == 1
    settings.min_match_score = 10
    s = run(settings, fetchers_for({"a": [job(title="Python Developer", location="India", posted=ago(minutes=5), external_id=2)]}))
    assert s["new"] == 1


def test_cli_min_score_override(settings, capsys):
    fetchers = {"remoteok": lambda s, c: [job(title="Python Developer", location="India", posted=ago(minutes=5))]}
    job_watcher.main(["--once", "--min-score", "999", "--no-notification", "--sources", "remoteok"],
                     fetchers=fetchers, settings=settings)
    assert "NEW JOB FOUND" not in capsys.readouterr().out and settings.min_match_score == 999


# ---------- first-seen output ----------
def test_now_ist_offset():
    assert output.now_ist().endswith("+05:30")


def test_first_seen_distinct_from_posted(settings, capsys):
    j = job(title="Python Developer", location="India", posted=ago(hours=2))
    j["match_score"] = 80
    block = output.format_job(j, first_seen="2026-10-03T17:30:00+05:30")
    assert "First seen by watcher: 2026-10-03T17:30:00+05:30 (Asia/Kolkata)" in block
    assert "Match score: 80" in block
    assert "Posted:" in block and j["posted_at"] not in "2026-10-03T17:30:00+05:30"  # posted != first_seen


def test_emit_logs_first_seen_and_score(settings):
    j = job(title="Python Developer", location="India", posted=ago(minutes=5))
    j["match_score"] = 65
    output.emit_job(j, settings, discovered_at="2026-10-03T17:30:00+05:30")
    logged = settings.log_file.read_text(encoding="utf-8")
    assert "first_seen=2026-10-03T17:30:00+05:30" in logged and "score=65" in logged


# ---------- Greenhouse / Lever parsers ----------
def test_greenhouse_parse():
    data = {"jobs": [{
        "id": 42, "title": "Software Engineer", "absolute_url": "https://boards.greenhouse.io/acme/jobs/42",
        "updated_at": "2026-10-03T10:00:00-04:00", "location": {"name": "Remote - India"},
        "departments": [{"name": "Engineering"}], "content": "&lt;p&gt;Build things with Python&lt;/p&gt;",
        "company_name": "Acme"}]}
    (j,) = greenhouse_source.parse(data, "acme")
    assert j["source"] == "Greenhouse" and j["company"] == "Acme" and j["external_id"] == "42"
    assert j["url"] == "https://boards.greenhouse.io/acme/jobs/42" and j["tags"] == ["Engineering"]
    assert j["date_status"] == "known" and "Python" in j["description"]  # HTML unescaped + stripped


def test_greenhouse_parse_company_falls_back_to_token():
    data = {"jobs": [{"id": 1, "title": "Dev", "absolute_url": "https://boards.greenhouse.io/x/jobs/1"}]}
    (j,) = greenhouse_source.parse(data, "x-corp")
    assert j["company"] == "x-corp" and j["date_status"] == "unknown"


def test_lever_parse():
    data = [{
        "id": "uuid-1", "text": "Backend Engineer", "hostedUrl": "https://jobs.lever.co/acme/uuid-1",
        "applyUrl": "https://jobs.lever.co/acme/uuid-1/apply", "createdAt": 1790000000000,
        "categories": {"location": "Remote (India)", "team": "Core", "department": "Engineering", "commitment": "Full-time"},
        "descriptionPlain": "We use Node.js"}]
    (j,) = lever_source.parse(data, "acme")
    assert j["source"] == "Lever" and j["company"] == "acme" and j["external_id"] == "uuid-1"
    assert j["url"] == "https://jobs.lever.co/acme/uuid-1"       # hostedUrl preferred over applyUrl
    assert j["tags"] == ["Core", "Engineering", "Full-time"] and j["date_status"] == "known"


def _boards_file(tmp_path, data):
    p = tmp_path / "config" / "company_boards.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_company_sources_noop_without_config(settings):
    settings.company_boards_file = settings.state_file.parent / "missing.json"
    assert greenhouse_source.fetch(settings, _CTX) == []
    assert lever_source.fetch(settings, _CTX) == []


def test_greenhouse_one_board_fails_others_continue(settings, tmp_path):
    settings.company_boards_file = _boards_file(tmp_path, {"greenhouse": ["good", "bad"]})

    def fake(url, s, **kw):
        if "/good/" in url:
            return {"jobs": [{"id": 1, "title": "Dev", "absolute_url": "https://boards.greenhouse.io/good/jobs/1"}]}
        raise requests.HTTPError("500")
    with mock.patch("sources.greenhouse_source.http_client.get_json", side_effect=fake):
        out = greenhouse_source.fetch(settings, _CTX)
    assert [j["external_id"] for j in out] == ["1"]                 # bad board skipped, good board kept


def test_greenhouse_all_boards_fail_raises(settings, tmp_path):
    settings.company_boards_file = _boards_file(tmp_path, {"greenhouse": ["bad"]})
    with mock.patch("sources.greenhouse_source.http_client.get_json", side_effect=requests.HTTPError("500")):
        with pytest.raises(requests.HTTPError):
            greenhouse_source.fetch(settings, _CTX)


def test_lever_site_failure_isolated_by_watcher(settings, capsys):
    fetchers = fetchers_for({"lever": requests.HTTPError("503"), "remoteok": [job(posted=ago(minutes=1))]})
    s = run(settings, fetchers)
    assert s["failed"] == ["lever"] and s["new"] == 1               # watcher keeps other sources running
