#!/usr/bin/env python3
"""
WARD v2 – Web Accessibility Review for civil society organizations
Adapted from ward_v2.py (Ayub & ul Hassan, University of Galway)
for civil society organization website datasets.

Checks WCAG 2.0 AA + 2.1 AA + 2.2 AA criteria via static HTML analysis.
Retry logic with exponential backoff and URL variant rotation.
"""

import csv, json, os, re, sys, time, warnings
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
warnings.filterwarnings('ignore')

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

class WARDCivil:
    def __init__(self, timeout=20, max_retries=3, retry_delay=2.0):
        self.timeout     = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    # ── URL variant generation ────────────────────────────────────────────────
    def _variants(self, url):
        url = url.strip().rstrip('/')
        if not url.startswith('http'):
            url = 'https://' + url
        parsed = urlparse(url)
        host   = parsed.netloc
        rest   = parsed.path or ''
        scheme = parsed.scheme

        variants = [url]
        # swap www
        if host.startswith('www.'):
            alt = url.replace(host, host[4:], 1)
        else:
            alt = url.replace(host, 'www.' + host, 1)
        variants.append(alt)
        # swap scheme
        opp = 'http' if scheme == 'https' else 'https'
        variants.append(url.replace(scheme + '://', opp + '://', 1))
        variants.append(alt.replace(scheme + '://', opp + '://', 1))
        return list(dict.fromkeys(variants))

    # ── Fetch with retry ──────────────────────────────────────────────────────
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
                last_err = 'Timeout'
            except requests.exceptions.SSLError:
                last_err = 'SSL Error'
            except requests.exceptions.ConnectionError as e:
                last_err = f'Connection: {str(e)[:60]}'
            except requests.exceptions.HTTPError as e:
                last_err = f'HTTP {e.response.status_code}'
                if e.response.status_code in (403, 404, 410):
                    break
            except Exception as e:
                last_err = f'Error: {str(e)[:60]}'
            if attempt < self.max_retries - 1:
                time.sleep(self.retry_delay * (2 ** attempt))
        return None, url, last_err

    # ── WCAG 2.0 AA checks ────────────────────────────────────────────────────
    def _check_2_0(self, soup):
        issues = []

        # 1.1.1 Images missing alt (Level A)
        for img in soup.find_all('img'):
            if img.get('alt') is None and img.get('role') != 'presentation':
                issues.append({'criterion':'1.1.1','level':'A',
                               'issue':'Image missing alt attribute'})

        # 1.3.1 Heading hierarchy skips + form labels (Level A)
        headings = soup.find_all(['h1','h2','h3','h4','h5','h6'])
        levels = [int(h.name[1]) for h in headings]
        for i in range(1, len(levels)):
            if levels[i] - levels[i-1] > 1:
                issues.append({'criterion':'1.3.1','level':'A',
                               'issue':f'Heading skip h{levels[i-1]}->h{levels[i]}'})
                break
        for inp in soup.find_all(['input','select','textarea']):
            if inp.get('type','text') in ['hidden','submit','button','image','reset']:
                continue
            iid = inp.get('id')
            labelled = bool(soup.find('label', {'for': iid})) if iid else False
            if not labelled and not inp.get('aria-label') \
                    and not inp.get('aria-labelledby') and not inp.get('title'):
                issues.append({'criterion':'1.3.1','level':'A',
                               'issue':'Form input missing label'})

        # 1.4.1 Color-only links (Level A) – heuristic
        for a in soup.find_all('a'):
            style = a.get('style','')
            if ('text-decoration:none' in style.replace(' ','') or
                    'text-decoration: none' in style) and not a.get('class'):
                issues.append({'criterion':'1.4.1','level':'A',
                               'issue':'Link may rely on color alone'})

        # 1.4.4 Fixed px font size (Level AA)
        for s in soup.find_all('style'):
            if s.string and re.search(r'font-size:\s*\d+px', s.string):
                issues.append({'criterion':'1.4.4','level':'AA',
                               'issue':'Fixed pixel font size detected'})
                break

        # 2.1.1 Keyboard – onclick on non-interactive elements (Level A)
        for el in soup.find_all(attrs={'onclick': True}):
            if el.name not in ['a','button','input','select','textarea']:
                if not el.get('onkeypress') and not el.get('onkeydown') \
                        and not el.get('tabindex'):
                    issues.append({'criterion':'2.1.1','level':'A',
                                   'issue':'onclick without keyboard handler'})

        # 2.4.1 Skip navigation (Level A)
        skip = soup.find('a', href=re.compile(r'^#(main|content|skip)', re.I))
        nav  = soup.find(['nav','main']) or \
               soup.find(attrs={'role': re.compile(r'(navigation|main)', re.I)})
        if not skip and not nav:
            issues.append({'criterion':'2.4.1','level':'A',
                           'issue':'No skip link or landmark regions'})

        # 2.4.2 Page title (Level A)
        title = soup.find('title')
        if not title or not (title.string or '').strip():
            issues.append({'criterion':'2.4.2','level':'A',
                           'issue':'Page title missing or empty'})

        # 2.4.4 Link purpose (Level A)
        for a in soup.find_all('a'):
            txt = a.get_text(strip=True).lower()
            if txt in ['click here','here','read more','more','link','learn more']:
                if not a.get('aria-label') and not a.get('title'):
                    issues.append({'criterion':'2.4.4','level':'A',
                                   'issue':f'Non-descriptive link text: "{txt}"'})

        # 2.4.6 Heading structure (Level AA)
        h1s = soup.find_all('h1')
        if not h1s:
            issues.append({'criterion':'2.4.6','level':'AA',
                           'issue':'No h1 heading found'})
        elif len(h1s) > 1:
            issues.append({'criterion':'2.4.6','level':'AA',
                           'issue':f'Multiple h1 headings ({len(h1s)})'})

        # 3.1.1 Language declaration (Level A)
        html_tag = soup.find('html')
        if html_tag and not html_tag.get('lang'):
            issues.append({'criterion':'3.1.1','level':'A',
                           'issue':'HTML lang attribute missing'})

        # 4.1.1 Duplicate IDs (Level A)
        ids = [el.get('id') for el in soup.find_all(id=True)]
        seen, reported = set(), set()
        for id_val in ids:
            if id_val in seen and id_val not in reported:
                issues.append({'criterion':'4.1.1','level':'A',
                               'issue':f'Duplicate ID: {id_val}'})
                reported.add(id_val)
            seen.add(id_val)

        # 4.1.2 Interactive elements without ARIA (Level A)
        for el in soup.find_all(['div','span'], attrs={'onclick': True}):
            if not el.get('role') and not el.get('tabindex'):
                issues.append({'criterion':'4.1.2','level':'A',
                               'issue':'Interactive element without role/ARIA'})

        return issues

    # ── WCAG 2.1 additional checks ────────────────────────────────────────────
    def _check_2_1(self, soup):
        issues = []

        # 1.3.4 Orientation lock (Level AA)
        meta = soup.find('meta', attrs={'name':'viewport'})
        if meta:
            content = meta.get('content','')
            if 'user-scalable=no' in content or 'user-scalable=0' in content:
                issues.append({'criterion':'1.3.4','level':'AA',
                               'issue':'Viewport locks user scaling'})

        # 1.3.5 Autocomplete on personal data fields (Level AA)
        personal = ['name','email','tel','street-address','postal-code',
                    'country','cc-name','cc-number']
        for inp in soup.find_all('input'):
            name = (inp.get('name','') + inp.get('id','')).lower()
            if any(p in name for p in personal) and not inp.get('autocomplete'):
                issues.append({'criterion':'1.3.5','level':'AA',
                               'issue':'Personal data input missing autocomplete'})

        # 1.4.10 Reflow – horizontal scroll CSS (Level AA)
        style_txt = ' '.join(s.string or '' for s in soup.find_all('style'))
        if 'overflow-x:scroll' in style_txt.replace(' ',''):
            issues.append({'criterion':'1.4.10','level':'AA',
                           'issue':'CSS may force horizontal scrolling'})

        # 1.4.12 Text spacing – !important on line-height or letter-spacing (Level AA)
        if '!important' in style_txt and \
                ('line-height' in style_txt or 'letter-spacing' in style_txt):
            issues.append({'criterion':'1.4.12','level':'AA',
                           'issue':'CSS !important may block text spacing adjustment'})

        # 1.4.13 Content on hover – long title attributes (Level AA)
        for el in soup.find_all(attrs={'title': True}):
            if len(el.get('title','')) > 50:
                issues.append({'criterion':'1.4.13','level':'AA',
                               'issue':'Long title attribute hides content on hover'})

        return issues

    # ── WCAG 2.2 additional checks ────────────────────────────────────────────
    def _check_2_2(self, soup):
        issues = []

        # 2.4.11 Focus not obscured – sticky/fixed elements (Level AA)
        style_txt = ' '.join(s.string or '' for s in soup.find_all('style'))
        if re.search(r'position\s*:\s*(sticky|fixed)', style_txt):
            issues.append({'criterion':'2.4.11','level':'AA',
                           'issue':'Sticky/fixed element may obscure focused component'})

        # 2.4.12 Focus not obscured (enhanced) – modal overlays (Level AAA – noted only)
        # 2.5.3 Label in name – buttons with aria-label that doesn't match visible text
        for btn in soup.find_all(['button','a'], attrs={'aria-label': True}):
            visible = btn.get_text(strip=True).lower()
            aria    = btn.get('aria-label','').lower()
            if visible and aria and visible not in aria and aria not in visible:
                issues.append({'criterion':'2.5.3','level':'AA',
                               'issue':'aria-label does not contain visible button text'})

        # 3.2.6 Consistent help – missing contact/help link heuristic
        help_pattern = re.compile(r'(contact|help|support|faq)', re.I)
        nav_links = [a.get_text(strip=True) for a in soup.find_all('a')]
        if not any(help_pattern.search(t) for t in nav_links):
            issues.append({'criterion':'3.2.6','level':'AA',
                           'issue':'No contact/help link found in navigation'})

        # 3.3.7 Redundant entry – repeated form fields heuristic
        inputs = soup.find_all('input', type='text')
        names = [i.get('name','').lower() for i in inputs]
        if names.count('name') > 1 or names.count('email') > 1:
            issues.append({'criterion':'3.3.7','level':'AA',
                           'issue':'Potential redundant data entry in form'})

        # 3.3.8 Accessible authentication – CAPTCHA without alternative
        captcha_markers = soup.find_all(
            class_=re.compile(r'captcha|recaptcha|hcaptcha', re.I))
        if captcha_markers:
            # Check if there's an alternative (audio, object recognition alt)
            has_audio = bool(soup.find(
                string=re.compile(r'audio.*captcha|listen|sound', re.I)))
            if not has_audio:
                issues.append({'criterion':'3.3.8','level':'AA',
                               'issue':'CAPTCHA with no accessible alternative detected'})

        return issues

    # ── Full site analysis ────────────────────────────────────────────────────
    def analyze(self, url, org_name, country=''):
        html, final_url, error = self.fetch(url)

        result = {
            'organization': org_name,
            'url':          url,
            'final_url':    final_url,
            'country':      country,
            'status':       'error' if error else 'tested',
            'error':        error,
            'issues_2_0':   [],
            'issues_2_1':   [],
            'issues_2_2':   [],
            'count_2_0':    0,
            'count_2_1':    0,
            'count_2_2':    0,
            'accessibility_score': None,
            'compliance_pct':      None,
            'severity_score':      None,
        }

        if error or not html:
            return result

        try:
            soup = BeautifulSoup(html, 'html.parser')
            i_20 = self._check_2_0(soup)
            i_21 = self._check_2_1(soup)
            i_22 = self._check_2_2(soup)

            all_21 = i_20 + i_21          # 2.1 = 2.0 + new 2.1 criteria
            all_22 = all_21 + i_22        # 2.2 = 2.1 + new 2.2 criteria

            result['issues_2_0'] = i_20
            result['issues_2_1'] = all_21
            result['issues_2_2'] = all_22
            result['count_2_0']  = len(i_20)
            result['count_2_1']  = len(all_21)
            result['count_2_2']  = len(all_22)

            # Accessibility score: 100 – (issues/50 × 100), floored at 0
            n = len(all_21)
            result['accessibility_score'] = max(0.0, round(100 - (n / 50) * 100, 1))

            # Compliance %: criteria with zero violations
            CRITERIA_2_1 = {
                '1.1.1','1.3.1','1.4.1','1.4.4','1.4.10','1.4.12','1.4.13',
                '2.1.1','2.4.1','2.4.2','2.4.4','2.4.6','3.1.1',
                '4.1.1','4.1.2','1.3.4','1.3.5'
            }
            violated = {i['criterion'] for i in all_21}
            passed = CRITERIA_2_1 - violated
            result['compliance_pct'] = round(len(passed) / len(CRITERIA_2_1) * 100, 1)

            # Severity score: Level A × 3 + Level AA × 2
            result['severity_score'] = sum(
                3 if i['level'] == 'A' else 2 for i in all_21)

        except Exception as e:
            result['status'] = 'parse_error'
            result['error']  = str(e)[:100]

        return result


# ── Batch runner ──────────────────────────────────────────────────────────────

def run_batch(sites, out_json, delay=1.0, resume=True):
    """Run audit on a list of {name, url} dicts; save JSON incrementally."""
    checker = WARDCivil()
    results = []

    # Resume: load previously saved results and skip already-done URLs
    done_urls = set()
    if resume and os.path.exists(out_json):
        with open(out_json, encoding='utf-8') as f:
            try:
                results = json.load(f)
                done_urls = {r['url'] for r in results}
                print(f"  Resuming from {out_json}: {len(results)} already done")
            except Exception:
                results = []

    todo = [s for s in sites if s['url'] not in done_urls]
    total = len(todo)
    print(f"  Sites to audit: {total}")

    for i, site in enumerate(todo, 1):
        r = checker.analyze(site['url'], site['name'], site.get('country', ''))
        results.append(r)

        # Incremental save every 10 sites
        if i % 10 == 0 or i == total:
            with open(out_json, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2)
            tested  = sum(1 for x in results if x['status'] == 'tested')
            errors  = sum(1 for x in results if x['status'] == 'error')
            print(f"  [{i}/{total}] {site['name'][:40]:40s} "
                  f"status={r['status']:8s} "
                  f"issues={r.get('count_2_1','?'):>3}  "
                  f"score={str(r.get('accessibility_score','?')):>5}  "
                  f"(tested={tested} errors={errors})")
        else:
            print(f"  [{i}/{total}] {site['name'][:40]:40s} "
                  f"status={r['status']:8s} "
                  f"issues={r.get('count_2_1','?'):>3}  "
                  f"score={str(r.get('accessibility_score','?')):>5}")

        time.sleep(delay)

    return results


if __name__ == '__main__':
    # Paths are relative to the folder this script lives in
    HERE     = os.path.dirname(os.path.abspath(__file__))
    # Accept:  python ward_civil.py [csv_file] [batch_size]
    # Defaults: all_countries.csv, all rows
    if len(sys.argv) >= 2 and sys.argv[1].endswith('.csv'):
        IN_CSV  = os.path.join(HERE, sys.argv[1])
        BATCH   = int(sys.argv[2]) if len(sys.argv) >= 3 else 999999
    else:
        IN_CSV  = os.path.join(HERE, 'all_countries.csv')
        BATCH   = int(sys.argv[1]) if len(sys.argv) >= 2 else 999999

    # Output JSON named after the input CSV
    csv_stem = os.path.splitext(os.path.basename(IN_CSV))[0]
    OUT_JSON = os.path.join(HERE, f'results_{csv_stem}.json')

    with open(IN_CSV, encoding='utf-8') as f:
        sites = []
        for r in csv.DictReader(f):
            site = {'name': r['name'], 'url': r['url']}
            if 'country' in r:          # new 4-country format
                site['country'] = r['country']
            elif 'page' in r:           # old directory export format
                site['country'] = 'Ireland'
            else:
                site['country'] = 'Unknown'
            sites.append(site)

    print(f"WARD v2 – Civil Society Pre-Audit")
    print(f"Input : {len(sites)} sites from {IN_CSV}")
    print(f"Batch : first {BATCH} sites")
    print(f"Output: {OUT_JSON}")
    print("="*60)
    print()

    results = run_batch(sites[:BATCH], OUT_JSON, delay=0.8)

    tested = [r for r in results if r['status'] == 'tested']
    errors = [r for r in results if r['status'] != 'tested']
    print(f"\n{'='*60}")
    print(f"Done.  Tested={len(tested)}  Errors={len(errors)}")
    if tested:
        scored = [r for r in tested if r.get('accessibility_score') is not None]
        avg_issues = sum(r['count_2_1'] for r in tested) / len(tested)
        avg_score  = sum(r['accessibility_score'] for r in scored) / len(scored) if scored else 0
        print(f"Avg WCAG 2.1 issues/site : {avg_issues:.1f}")
        print(f"Avg accessibility score  : {avg_score:.1f}/100  ({len(scored)} scored, {len(tested)-len(scored)} unscored)")