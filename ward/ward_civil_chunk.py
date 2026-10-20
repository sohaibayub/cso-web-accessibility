#!/usr/bin/env python3
"""
WARD v2 (chunked, concurrent edition) - for large-scale runs like the UK 800,000-site list.

Same WCAG 2.0/2.1/2.2 checks as ward_civil.py, with two changes needed at this scale:

1. Concurrency. Sequential requests with a 0.8s delay would take roughly 18 days
   for 800,000 sites. This version fires requests with a thread pool (the work is
   I/O-bound - waiting on network responses - so threads help a lot here).

2. Append-only CSV output instead of full-file JSON rewrite. The original script
   re-saves the entire JSON results list every 10 sites. That's fine for a few
   hundred sites, but at hundreds of thousands of rows each save re-writes a
   growing file from scratch, which gets slower and slower. This version appends
   one row per site directly to a CSV, so save time stays constant regardless of
   how far into the run you are.

Meant to be run one chunk file at a time (see split_csv.py to create chunks).

Usage:
    python ward_civil_chunk.py chunks/uk_all_chunk_0001.csv --workers 15
    python ward_civil_chunk.py chunks/uk_all_chunk_0001.csv --workers 15 --delay 0.2

Output:
    chunks/uk_all_chunk_0001_results.csv

Resuming: if you stop and re-run on the same chunk file, it reads the existing
_results.csv, skips URLs already present, and continues.
"""

import argparse
import csv
import os
import re
import sys
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

warnings.filterwarnings("ignore")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

FIELDNAMES = [
    "organization", "url", "final_url", "country", "status", "error",
    "count_2_0", "count_2_1", "count_2_2",
    "accessibility_score", "compliance_pct", "severity_score",
]


class WARDCivil:
    def __init__(self, timeout=20, max_retries=3, retry_delay=2.0):
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def _variants(self, url):
        url = url.strip().rstrip("/")
        if not url.startswith("http"):
            url = "https://" + url
        parsed = urlparse(url)
        host = parsed.netloc
        scheme = parsed.scheme

        variants = [url]
        if host.startswith("www."):
            alt = url.replace(host, host[4:], 1)
        else:
            alt = url.replace(host, "www." + host, 1)
        variants.append(alt)
        opp = "http" if scheme == "https" else "https"
        variants.append(url.replace(scheme + "://", opp + "://", 1))
        variants.append(alt.replace(scheme + "://", opp + "://", 1))
        return list(dict.fromkeys(variants))

    def fetch(self, url):
        variants = self._variants(url)
        last_err = None
        for attempt in range(self.max_retries):
            target = variants[attempt % len(variants)]
            headers = {"User-Agent": USER_AGENTS[attempt % len(USER_AGENTS)]}
            try:
                r = requests.get(target, headers=headers, timeout=self.timeout,
                                  verify=False, allow_redirects=True)
                r.raise_for_status()
                return r.text, r.url, None
            except requests.exceptions.Timeout:
                last_err = "Timeout"
            except requests.exceptions.SSLError:
                last_err = "SSL Error"
            except requests.exceptions.ConnectionError as e:
                last_err = f"Connection: {str(e)[:60]}"
            except requests.exceptions.HTTPError as e:
                last_err = f"HTTP {e.response.status_code}"
                if e.response.status_code in (403, 404, 410):
                    break
            except Exception as e:
                last_err = f"Error: {str(e)[:60]}"
            if attempt < self.max_retries - 1:
                time.sleep(self.retry_delay * (2 ** attempt))
        return None, url, last_err

    def _check_2_0(self, soup):
        issues = []
        for img in soup.find_all("img"):
            if img.get("alt") is None and img.get("role") != "presentation":
                issues.append({"criterion": "1.1.1", "level": "A", "issue": "Image missing alt attribute"})

        headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
        levels = [int(h.name[1]) for h in headings]
        for i in range(1, len(levels)):
            if levels[i] - levels[i - 1] > 1:
                issues.append({"criterion": "1.3.1", "level": "A", "issue": f"Heading skip h{levels[i-1]}->h{levels[i]}"})
                break
        for inp in soup.find_all(["input", "select", "textarea"]):
            if inp.get("type", "text") in ["hidden", "submit", "button", "image", "reset"]:
                continue
            iid = inp.get("id")
            labelled = bool(soup.find("label", {"for": iid})) if iid else False
            if not labelled and not inp.get("aria-label") and not inp.get("aria-labelledby") and not inp.get("title"):
                issues.append({"criterion": "1.3.1", "level": "A", "issue": "Form input missing label"})

        for a in soup.find_all("a"):
            style = a.get("style", "")
            if ("text-decoration:none" in style.replace(" ", "") or "text-decoration: none" in style) and not a.get("class"):
                issues.append({"criterion": "1.4.1", "level": "A", "issue": "Link may rely on color alone"})

        for s in soup.find_all("style"):
            if s.string and re.search(r"font-size:\s*\d+px", s.string):
                issues.append({"criterion": "1.4.4", "level": "AA", "issue": "Fixed pixel font size detected"})
                break

        for el in soup.find_all(attrs={"onclick": True}):
            if el.name not in ["a", "button", "input", "select", "textarea"]:
                if not el.get("onkeypress") and not el.get("onkeydown") and not el.get("tabindex"):
                    issues.append({"criterion": "2.1.1", "level": "A", "issue": "onclick without keyboard handler"})

        skip = soup.find("a", href=re.compile(r"^#(main|content|skip)", re.I))
        nav = soup.find(["nav", "main"]) or soup.find(attrs={"role": re.compile(r"(navigation|main)", re.I)})
        if not skip and not nav:
            issues.append({"criterion": "2.4.1", "level": "A", "issue": "No skip link or landmark regions"})

        title = soup.find("title")
        if not title or not (title.string or "").strip():
            issues.append({"criterion": "2.4.2", "level": "A", "issue": "Page title missing or empty"})

        for a in soup.find_all("a"):
            txt = a.get_text(strip=True).lower()
            if txt in ["click here", "here", "read more", "more", "link", "learn more"]:
                if not a.get("aria-label") and not a.get("title"):
                    issues.append({"criterion": "2.4.4", "level": "A", "issue": f'Non-descriptive link text: "{txt}"'})

        h1s = soup.find_all("h1")
        if not h1s:
            issues.append({"criterion": "2.4.6", "level": "AA", "issue": "No h1 heading found"})
        elif len(h1s) > 1:
            issues.append({"criterion": "2.4.6", "level": "AA", "issue": f"Multiple h1 headings ({len(h1s)})"})

        html_tag = soup.find("html")
        if html_tag and not html_tag.get("lang"):
            issues.append({"criterion": "3.1.1", "level": "A", "issue": "HTML lang attribute missing"})

        ids = [el.get("id") for el in soup.find_all(id=True)]
        seen, reported = set(), set()
        for id_val in ids:
            if id_val in seen and id_val not in reported:
                issues.append({"criterion": "4.1.1", "level": "A", "issue": f"Duplicate ID: {id_val}"})
                reported.add(id_val)
            seen.add(id_val)

        for el in soup.find_all(["div", "span"], attrs={"onclick": True}):
            if not el.get("role") and not el.get("tabindex"):
                issues.append({"criterion": "4.1.2", "level": "A", "issue": "Interactive element without role/ARIA"})

        return issues

    def _check_2_1(self, soup):
        issues = []
        meta = soup.find("meta", attrs={"name": "viewport"})
        if meta:
            content = meta.get("content", "")
            if "user-scalable=no" in content or "user-scalable=0" in content:
                issues.append({"criterion": "1.3.4", "level": "AA", "issue": "Viewport locks user scaling"})

        personal = ["name", "email", "tel", "street-address", "postal-code", "country", "cc-name", "cc-number"]
        for inp in soup.find_all("input"):
            name = (inp.get("name", "") + inp.get("id", "")).lower()
            if any(p in name for p in personal) and not inp.get("autocomplete"):
                issues.append({"criterion": "1.3.5", "level": "AA", "issue": "Personal data input missing autocomplete"})

        style_txt = " ".join(s.string or "" for s in soup.find_all("style"))
        if "overflow-x:scroll" in style_txt.replace(" ", ""):
            issues.append({"criterion": "1.4.10", "level": "AA", "issue": "CSS may force horizontal scrolling"})

        if "!important" in style_txt and ("line-height" in style_txt or "letter-spacing" in style_txt):
            issues.append({"criterion": "1.4.12", "level": "AA", "issue": "CSS !important may block text spacing adjustment"})

        for el in soup.find_all(attrs={"title": True}):
            if len(el.get("title", "")) > 50:
                issues.append({"criterion": "1.4.13", "level": "AA", "issue": "Long title attribute hides content on hover"})

        return issues

    def _check_2_2(self, soup):
        issues = []
        style_txt = " ".join(s.string or "" for s in soup.find_all("style"))
        if re.search(r"position\s*:\s*(sticky|fixed)", style_txt):
            issues.append({"criterion": "2.4.11", "level": "AA", "issue": "Sticky/fixed element may obscure focused component"})

        for btn in soup.find_all(["button", "a"], attrs={"aria-label": True}):
            visible = btn.get_text(strip=True).lower()
            aria = btn.get("aria-label", "").lower()
            if visible and aria and visible not in aria and aria not in visible:
                issues.append({"criterion": "2.5.3", "level": "AA", "issue": "aria-label does not contain visible button text"})

        help_pattern = re.compile(r"(contact|help|support|faq)", re.I)
        nav_links = [a.get_text(strip=True) for a in soup.find_all("a")]
        if not any(help_pattern.search(t) for t in nav_links):
            issues.append({"criterion": "3.2.6", "level": "AA", "issue": "No contact/help link found in navigation"})

        inputs = soup.find_all("input", type="text")
        names = [i.get("name", "").lower() for i in inputs]
        if names.count("name") > 1 or names.count("email") > 1:
            issues.append({"criterion": "3.3.7", "level": "AA", "issue": "Potential redundant data entry in form"})

        captcha_markers = soup.find_all(class_=re.compile(r"captcha|recaptcha|hcaptcha", re.I))
        if captcha_markers:
            has_audio = bool(soup.find(string=re.compile(r"audio.*captcha|listen|sound", re.I)))
            if not has_audio:
                issues.append({"criterion": "3.3.8", "level": "AA", "issue": "CAPTCHA with no accessible alternative detected"})

        return issues

    def analyze(self, url, org_name, country=""):
        html, final_url, error = self.fetch(url)

        result = {
            "organization": org_name, "url": url, "final_url": final_url, "country": country,
            "status": "error" if error else "tested", "error": error,
            "count_2_0": 0, "count_2_1": 0, "count_2_2": 0,
            "accessibility_score": None, "compliance_pct": None, "severity_score": None,
        }

        if error or not html:
            return result

        try:
            soup = BeautifulSoup(html, "html.parser")
            i_20 = self._check_2_0(soup)
            i_21 = self._check_2_1(soup)
            i_22 = self._check_2_2(soup)

            all_21 = i_20 + i_21
            all_22 = all_21 + i_22

            result["count_2_0"] = len(i_20)
            result["count_2_1"] = len(all_21)
            result["count_2_2"] = len(all_22)

            n = len(all_21)
            result["accessibility_score"] = max(0.0, round(100 - (n / 50) * 100, 1))

            CRITERIA_2_1 = {
                "1.1.1", "1.3.1", "1.4.1", "1.4.4", "1.4.10", "1.4.12", "1.4.13",
                "2.1.1", "2.4.1", "2.4.2", "2.4.4", "2.4.6", "3.1.1",
                "4.1.1", "4.1.2", "1.3.4", "1.3.5",
            }
            violated = {i["criterion"] for i in all_21}
            passed = CRITERIA_2_1 - violated
            result["compliance_pct"] = round(len(passed) / len(CRITERIA_2_1) * 100, 1)

            result["severity_score"] = sum(3 if i["level"] == "A" else 2 for i in all_21)

        except Exception as e:
            result["status"] = "parse_error"
            result["error"] = str(e)[:100]

        return result


_write_lock = threading.Lock()


def load_done_urls(out_csv):
    done = set()
    if os.path.exists(out_csv):
        with open(out_csv, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("url"):
                    done.add(row["url"])
    return done


def append_result(out_csv, flat_result):
    with _write_lock:
        write_header = not os.path.exists(out_csv) or os.path.getsize(out_csv) == 0
        with open(out_csv, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
            if write_header:
                w.writeheader()
            w.writerow(flat_result)


def run_chunk(in_csv, workers=15, delay=0.1, timeout=20):
    checker = WARDCivil(timeout=timeout)
    out_csv = os.path.splitext(in_csv)[0] + "_results.csv"

    with open(in_csv, encoding="utf-8") as f:
        sites = []
        for r in csv.DictReader(f):
            name = r.get("name") or r.get("Organization") or r.get("organization") or ""
            url = r.get("url") or r.get("Website") or r.get("website") or ""
            country = r.get("country") or r.get("Country") or "United Kingdom"
            if url.strip():
                sites.append({"name": name, "url": url, "country": country})

    done_urls = load_done_urls(out_csv)
    todo = [s for s in sites if s["url"] not in done_urls]
    print(f"{os.path.basename(in_csv)}: {len(sites)} total, {len(done_urls)} already done, {len(todo)} remaining")
    if not todo:
        print("Nothing to do.")
        return

    def work(site):
        r = checker.analyze(site["url"], site["name"], site.get("country", ""))
        flat = {k: r.get(k, "") for k in FIELDNAMES}
        flat["error"] = flat["error"] or ""
        append_result(out_csv, flat)
        if delay:
            time.sleep(delay)
        return r["status"]

    done_count = 0
    tested = errors = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(work, s): s for s in todo}
        for fut in as_completed(futures):
            status = fut.result()
            if status == "tested":
                tested += 1
            else:
                errors += 1
            done_count += 1
            if done_count % 50 == 0 or done_count == len(todo):
                elapsed = time.time() - t0
                rate = done_count / elapsed if elapsed else 0
                remaining = (len(todo) - done_count) / rate if rate else float("inf")
                print(f"  [{done_count}/{len(todo)}] tested={tested} errors={errors} "
                      f"rate={rate:.2f}/s  est. remaining={remaining/60:.1f} min")

    print(f"Chunk complete: {in_csv} -> {out_csv}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_file", help="Chunk CSV with name/url (or Organization/Website) columns")
    ap.add_argument("--workers", type=int, default=15, help="Concurrent requests (default 15)")
    ap.add_argument("--delay", type=float, default=0.1, help="Small per-request delay, seconds (default 0.1)")
    ap.add_argument("--timeout", type=int, default=20, help="Per-request timeout, seconds (default 20)")
    args = ap.parse_args()
    run_chunk(args.csv_file, workers=args.workers, delay=args.delay, timeout=args.timeout)
