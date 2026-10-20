"""
US Civil Society Organizations — Multi-source collector
Sources:
  1. Wikidata SPARQL (verified orgs with official website URLs)
  2. ProPublica Nonprofit Explorer (EINs + names across all 50 states)
  3. IRS EO BMF (supplementary coverage)
Output: usa_orgs_all.csv
"""
import urllib.request, urllib.parse, json, csv, time, re, os, sys

OUT = "usa_orgs_all.csv"
seen_urls = set()
orgs = []

def add(name, url, state="US", source=""):
    url = url.strip().rstrip('/')
    if not url or url in seen_urls: return
    if not re.match(r'https?://', url): return
    seen_urls.add(url)
    orgs.append({"Name": name.strip(), "URL": url, "State": state, "Source": source})

def save():
    with open(OUT, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=["Name","URL","State","Source"])
        w.writeheader(); w.writerows(orgs)
    print(f"  Saved {len(orgs):,} orgs → {OUT}")

# ── 1. WIKIDATA — paginate through all US nonprofits with websites ──────────
print("=== SOURCE 1: Wikidata ===")
wikidata_types = [
    "wd:Q163740",   # non-profit organization
    "wd:Q157031",   # foundation
    "wd:Q48204",    # non-governmental organization
    "wd:Q4611891",  # charitable organization
    "wd:Q1058914",  # civil society organization
]

for wtype in wikidata_types:
    offset = 0
    batch_size = 500
    while True:
        sparql = f"""
SELECT DISTINCT ?orgLabel ?website WHERE {{
  ?org wdt:P31/wdt:P279* {wtype} .
  ?org wdt:P17 wd:Q30 .
  ?org wdt:P856 ?website .
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
}}
LIMIT {batch_size} OFFSET {offset}
"""
        params = urllib.parse.urlencode({"query": sparql, "format": "json"})
        url = f"https://query.wikidata.org/sparql?{params}"
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "AccessibilityResearch/1.0",
                "Accept": "application/sparql-results+json"
            })
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read())
            bindings = data.get('results', {}).get('bindings', [])
            before = len(orgs)
            for b in bindings:
                name = b.get('orgLabel', {}).get('value', '')
                web  = b.get('website',  {}).get('value', '')
                if name and web:
                    add(name, web, "US", f"Wikidata:{wtype}")
            after = len(orgs)
            print(f"  {wtype} offset={offset}: +{after-before} new (total {after})")
            if len(bindings) < batch_size:
                break
            offset += batch_size
            time.sleep(2)
        except Exception as e:
            print(f"  Wikidata error at offset {offset}: {e}")
            time.sleep(5)
            break

save()
print(f"After Wikidata: {len(orgs):,} unique orgs\n")

# ── 2. PROPUBLICA — all 50 states, paginate ─────────────────────────────────
print("=== SOURCE 2: ProPublica search (names+EINs only, state coverage check) ===")
ALL_STATES = ["AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID",
              "IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS",
              "MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK",
              "OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","DC"]

pp_orgs = {}  # ein -> {name, state}
for state in ALL_STATES:
    for page in range(0, 4):  # 0-3 = up to 100 results (25/page) per state
        url = f"https://projects.propublica.org/nonprofits/api/v2/search.json?q=&state[id]={state}&page={page}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
            batch = data.get('organizations', [])
            for o in batch:
                ein = str(o.get('ein',''))
                if ein and ein not in pp_orgs:
                    pp_orgs[ein] = {'name': o.get('name',''), 'state': state}
            if len(batch) < 25:
                break
            time.sleep(0.3)
        except Exception as e:
            time.sleep(1); break

print(f"  ProPublica EINs collected: {len(pp_orgs):,}")
print(f"  (Website URLs not available from ProPublica — EINs logged for reference)\n")
save()

# ── 3. IRS EO BMF — download all 4 region files ─────────────────────────────
print("=== SOURCE 3: IRS EO BMF (names + states, no URLs) ===")
eo_files = ["eo1","eo2","eo3","eo4"]
eo_orgs = {}
for fname in eo_files:
    url = f"https://www.irs.gov/pub/irs-soi/{fname}.csv"
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            content = r.read().decode('latin-1', errors='ignore')
        import io
        reader = csv.DictReader(io.StringIO(content))
        count = 0
        for row in reader:
            sub = row.get('SUBSECTION','').strip()
            state = row.get('STATE','').strip()
            name = row.get('NAME','').strip()
            ein = row.get('EIN','').strip()
            # 501(c)(3) public charities only
            if sub == '03' and state and name and ein:
                eo_orgs[ein] = {'name': name, 'state': state}
                count += 1
        print(f"  {fname}: {count:,} 501(c)(3) charities")
    except Exception as e:
        print(f"  {fname} error: {e}")

print(f"  Total IRS 501(c)(3) orgs: {len(eo_orgs):,}")

# Save final combined (Wikidata orgs have URLs; EO/PP logged separately)
save()

# Also save IRS org list separately for reference
irs_out = "usa_irs_orgs.csv"
with open(irs_out, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=["EIN","Name","State"])
    w.writeheader()
    for ein, d in list(eo_orgs.items())[:50000]:  # save first 50k
        w.writerow({"EIN": ein, "Name": d['name'], "State": d['state']})
print(f"\nIRS orgs (name+state, no URL) saved: {irs_out}")
print(f"\nFINAL with URLs: {len(orgs):,} US civil society orgs")
