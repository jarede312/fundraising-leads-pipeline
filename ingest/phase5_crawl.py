"""
Phase 5 full crawl: for every ND public school/district site on file, discover the staff/
directory page(s), extract contacts via the LLM (ingest.extract_contacts), and write them
to `contacts` with source_url provenance.

Scope, stated plainly:
- Only public districts/schools are crawled here. NCES's Private School Universe Survey
  (PSS) - the only source Phase 1 had for ND's 43 private schools - does not publish a
  website field, so every private school's website_url is NULL in this database. There is
  nothing to crawl for them from any source already on file. Not silently absorbed into
  this pass: flagged in the Phase 5 report as a separate, small follow-up (manual lookup or
  an explicitly-scoped search pass), not guessed at here.
- A contact with no role stated on the source page is not written to `contacts` at all -
  the schema's `role` column is NOT NULL with a fixed CHECK list, and inventing a role for
  a bare name would violate the brief's "never invent a contact" rule as much as inventing
  the name itself would. Real, roleless names (Hettinger's prototype pages were all like
  this) are simply not sales-actionable without a role, so they're dropped, not guessed.
- District-level pages (e.g. a superintendent or business-office listing that isn't tied to
  one building) are anchored to the district's largest-enrollment open school as a proxy,
  since `contacts.school_id` is NOT NULL and there's no district-level contact concept in
  the schema. Reversible later via `source_url` if a better anchor is wanted - not a
  structural rebuild.
- No retry/queue infra per the brief: each URL is fetched once. robots.txt is checked
  first and a Crawl-delay (or a 1.5s default) is respected per host between requests.

Run: python -m ingest.phase5_crawl           (full crawl)
     python -m ingest.phase5_crawl 10        (first 10 targets only, for a dry run)
"""
import csv
import re
import sys
import time
import urllib.robotparser
from urllib.parse import urljoin, urlparse

import httpx
from selectolax.parser import HTMLParser

from . import config, db
from .email_pattern import derive_email
from .extract_contacts import SCHEMA_ROLES, extract

# The LLM is allowed to classify a real title into "other" when it doesn't fit (see
# extract_contacts.SYSTEM_PROMPT rule 3) so it isn't forced into a wrong specific role -
# but "other" is a generic catch-all (cooks, librarians, nightwatch, IT staff showed up
# in the dry run) and none of that is a fundraising sales contact. Only the roles below
# get written to `contacts`; "other" people are still real and still logged as found in
# the console/gap accounting, just not persisted. User's explicit call (2026-08-23).
SALES_RELEVANT_ROLES = [r for r in SCHEMA_ROLES if r != "other"]

STAFF_LINK_KEYWORDS = [
    ("staff directory", 10), ("faculty staff", 10), ("faculty and staff", 10),
    ("meet our staff", 9), ("meet the staff", 9), ("meet our teachers", 8),
    ("staff list", 8), ("faculty", 7), ("staff", 6), ("directory", 6),
    ("administration", 5), ("our team", 5), ("personnel", 5),
    ("about us", 3), ("contacts", 3), ("contact us", 2),
]
MAX_CANDIDATES_PER_SITE = 3
REQUEST_TIMEOUT = 20.0
DEFAULT_CRAWL_DELAY = 1.5
MIN_TEXT_LEN = 30

_robots_cache = {}
_last_request = {}


def _host(url):
    return urlparse(url).netloc.lower()


def _get_robots(client, url):
    host = _host(url)
    if host in _robots_cache:
        return _robots_cache[host]
    robots_url = f"{urlparse(url).scheme}://{host}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    try:
        resp = client.get(robots_url, timeout=REQUEST_TIMEOUT)
        rp.parse(resp.text.splitlines() if resp.status_code == 200 else [])
    except httpx.HTTPError:
        rp.parse([])
    _robots_cache[host] = rp
    return rp


def _polite_wait(url):
    host = _host(url)
    delay = DEFAULT_CRAWL_DELAY
    rp = _robots_cache.get(host)
    if rp is not None:
        rd = rp.crawl_delay(config.USER_AGENT)
        if rd:
            delay = max(delay, float(rd))
    wait = delay - (time.monotonic() - _last_request.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    _last_request[host] = time.monotonic()


def fetch(client, url):
    """Return (html, error). error is a short reason string, or None on success.
    Honors robots.txt and per-host rate limiting; never retries."""
    rp = _get_robots(client, url)
    if not rp.can_fetch(config.USER_AGENT, url):
        return None, "robots_disallowed"
    _polite_wait(url)
    try:
        resp = client.get(url, timeout=REQUEST_TIMEOUT, follow_redirects=True)
    except httpx.HTTPError as e:
        return None, f"fetch_error:{type(e).__name__}"
    if resp.status_code == 403 and "just a moment" in resp.text.lower():
        return None, "blocked_challenge"
    if resp.status_code != 200:
        return None, f"http_{resp.status_code}"
    return resp.text, None


def html_to_text(html):
    tree = HTMLParser(html)
    for tag in tree.css("script, style, nav, footer, header"):
        tag.decompose()
    return tree.body.text(separator="\n", strip=True) if tree.body else ""


def discover_candidates(html, base_url):
    tree = HTMLParser(html)
    base_host = _host(base_url)
    scored, seen = [], set()
    for a in tree.css("a[href]"):
        href = a.attributes.get("href") or ""
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        abs_url = urljoin(base_url, href).split("#")[0].rstrip("/")
        if _host(abs_url) != base_host or abs_url in seen:
            continue
        text = (a.text() or "").strip().lower()
        haystack = re.sub(r"[-_/]", " ", f"{text} {href.lower()}")
        score = max((pts for kw, pts in STAFF_LINK_KEYWORDS if kw in haystack), default=0)
        if score > 0:
            scored.append((score, abs_url))
            seen.add(abs_url)
    scored.sort(key=lambda x: -x[0])
    return [url for _, url in scored[:MAX_CANDIDATES_PER_SITE]]


def build_targets(conn):
    """One target per distinct site URL, anchored to the school any extracted contact
    should be written against. Schools' own sites take precedence; a district's site is
    only added as its own target when it isn't already covered by one of its schools."""
    targets = {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, website_url, name FROM schools WHERE status = 'open' AND website_url IS NOT NULL"
        )
        for school_id, school_url, name in cur.fetchall():
            norm = school_url.rstrip("/").lower()
            targets[norm] = {
                "url": school_url, "anchor_school_id": school_id,
                "url_type": "school", "label": name,
            }

        cur.execute(
            """
            SELECT d.website_url, d.name,
                   (SELECT s2.id FROM schools s2 WHERE s2.district_id = d.id AND s2.status = 'open'
                    ORDER BY s2.enrollment DESC NULLS LAST LIMIT 1)
            FROM districts d
            WHERE d.website_url IS NOT NULL
            """
        )
        for district_url, name, anchor_school_id in cur.fetchall():
            if anchor_school_id is None:
                continue
            norm = district_url.rstrip("/").lower()
            if norm in targets:
                continue
            targets[norm] = {
                "url": district_url, "anchor_school_id": anchor_school_id,
                "url_type": "district", "label": name,
            }
    return list(targets.values())


def load_district_email_info(conn):
    info = {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.id, d.email_domain, d.email_pattern, d.email_pattern_confidence,
                   COALESCE((d.email_pattern_evidence ->> 'requires_suffix')::boolean, false)
            FROM schools s JOIN districts d ON d.id = s.district_id
            WHERE s.status = 'open'
            """
        )
        for school_id, domain, pattern, confidence, requires_suffix in cur.fetchall():
            info[school_id] = {
                "domain": domain, "pattern": pattern,
                "confidence": confidence, "requires_suffix": requires_suffix,
            }
    return info


def write_gap_csv(rows, path=None):
    path = path or (config.OUT_DIR / "phase5_gap_list.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["url", "url_type", "label", "reason", "detail"])
        writer.writeheader()
        writer.writerows(rows)
    return path


INSERT_CONTACT_SQL = """
    INSERT INTO contacts (
        school_id, role, role_detail, first_name, last_name,
        email, email_source, email_confidence, phone, source_url, ingest_run_id
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def crawl_site(client, target, email_info):
    """Fetch one site's candidate pages, extract, and dedupe within it. Returns
    (site_contacts, gap_rows, cost_usd). site_contacts is keyed by (first, last, role)
    (lowercased) -> (school_id, role, role_detail, first_name, last_name, email_source,
    email_confidence, phone, page_url, email). Shared by the full crawl (phase5_crawl)
    and the August re-crawl (phase7_sweep) so the fetch/discover/extract/dedupe logic
    exists exactly once."""
    gap_rows = []
    cost_usd = 0.0

    html, err = fetch(client, target["url"])
    if err:
        gap_rows.append({"url": target["url"], "url_type": target["url_type"],
                          "label": target["label"], "reason": err, "detail": ""})
        return {}, gap_rows, cost_usd

    candidates = discover_candidates(html, target["url"]) or [target["url"]]
    found_any = False
    site_contacts = {}
    for page_url in candidates:
        if page_url == target["url"]:
            page_html = html
        else:
            page_html, perr = fetch(client, page_url)
            if perr:
                gap_rows.append({"url": page_url, "url_type": target["url_type"],
                                  "label": target["label"], "reason": perr, "detail": ""})
                continue

        text = html_to_text(page_html)
        if len(text) < MIN_TEXT_LEN:
            continue
        try:
            result = extract(text, page_url)
        except Exception as e:
            gap_rows.append({"url": page_url, "url_type": target["url_type"],
                              "label": target["label"], "reason": "extract_exception",
                              "detail": str(e)[:200]})
            continue

        cost_usd += result["_usage"]["cost_usd"]
        if not result["page_had_staff_content"] or not result["contacts"]:
            continue
        found_any = True

        info = email_info.get(target["anchor_school_id"])
        for c in result["contacts"]:
            role = c["role"] if c["role"] in SALES_RELEVANT_ROLES else None
            if role is None:
                continue

            email = c["email"]
            email_source = "found" if email else "unknown"
            email_confidence = "high" if email else "unknown"
            if not email and c["first_name"] and c["last_name"] and info \
                    and info["pattern"] and info["pattern"] != "custom" \
                    and info["confidence"] in ("high", "medium") \
                    and not info["requires_suffix"]:
                derived = derive_email(c["first_name"], c["last_name"],
                                        info["pattern"], info["domain"])
                if derived:
                    email, email_source, email_confidence = derived, "derived", info["confidence"]

            key = ((c["first_name"] or "").strip().lower(),
                   (c["last_name"] or "").strip().lower(), role)
            existing = site_contacts.get(key)
            # Prefer a version with a real found email over a derived/unknown one
            if existing is None or (existing[5] != "found" and email_source == "found"):
                site_contacts[key] = (
                    target["anchor_school_id"], role, c["role_detail"],
                    c["first_name"], c["last_name"], email_source, email_confidence,
                    c["phone"], page_url, email,
                )

    if not found_any:
        gap_rows.append({"url": target["url"], "url_type": target["url_type"],
                          "label": target["label"], "reason": "no_staff_content_found",
                          "detail": f"{len(candidates)} candidate page(s) checked"})
    return site_contacts, gap_rows, cost_usd


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None

    conn = db.connect()
    targets = build_targets(conn)
    if limit:
        targets = targets[:limit]
    email_info = load_district_email_info(conn)
    print(f"{len(targets)} site targets to crawl.")

    gap_rows = []
    client = httpx.Client(headers={"User-Agent": config.USER_AGENT})

    with db.ingest_run(
        conn, "llm_extract",
        "Full ND public district/school staff-directory crawl, LLM extraction", "ND",
    ) as (run_id, counts):
        with conn.cursor() as cur:
            for i, target in enumerate(targets, 1):
                counts["in"] += 1
                site_contacts, site_gaps, site_cost = crawl_site(client, target, email_info)
                gap_rows.extend(site_gaps)
                counts["cost_usd"] += site_cost

                for (school_id, role, role_detail, first_name, last_name, email_source,
                     email_confidence, phone, page_url, email) in site_contacts.values():
                    cur.execute(
                        INSERT_CONTACT_SQL,
                        (school_id, role, role_detail, first_name, last_name, email,
                         email_source, email_confidence, phone, page_url, run_id),
                    )
                    counts["written"] += cur.rowcount

                # Commit and flush the gap list after every site, not once at the end -
                # a 300+ site crawl run one host at a time takes a while, and losing all
                # of it to a single interruption near the end would waste real API spend.
                conn.commit()
                write_gap_csv(gap_rows)
                if i % 10 == 0 or i == len(targets):
                    print(f"[{i}/{len(targets)}] written={counts['written']} "
                          f"gaps={len(gap_rows)} cost=${counts['cost_usd']:.4f}", flush=True)

    gap_path = write_gap_csv(gap_rows)
    conn.close()
    print(f"Crawled {len(targets)} sites. Wrote {counts['written']} contacts. "
          f"Cost: ${counts['cost_usd']:.4f}. Gaps: {len(gap_rows)} -> {gap_path}")


if __name__ == "__main__":
    main()
