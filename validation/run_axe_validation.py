#!/usr/bin/env python3
"""
Browser-based axe-core validation run for the WARD census.
Run on your own machine (needs internet access to the sampled sites).

Setup (once):
    pip install playwright pandas requests
    playwright install chromium

Run:
    python run_axe_validation.py
Resume-safe: re-running skips URLs already in axe_results.jsonl.
Expected runtime: 500 sites, roughly 60-90 minutes.
"""
import json, os, re, sys, time
import requests
import pandas as pd
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, 'validation_sample.csv')
OUT = os.path.join(HERE, 'axe_results.jsonl')
AXE_JS = os.path.join(HERE, 'axe.min.js')
AXE_URL = 'https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.9.1/axe.min.js'
# 4.9.x still includes the duplicate-id rules needed to compare criterion 4.1.1.

def ensure_axe():
    if not os.path.exists(AXE_JS):
        print('downloading axe-core 4.9.1 ...')
        r = requests.get(AXE_URL, timeout=60)
        r.raise_for_status()
        open(AXE_JS, 'w', encoding='utf-8').write(r.text)

def wcag_criteria_from_tags(tags):
    crits = set()
    for t in tags:
        m = re.fullmatch(r'wcag(\d)(\d)(\d\d?)', t)
        if m:
            crits.add(f'{m.group(1)}.{m.group(2)}.{int(m.group(3))}')
    return sorted(crits)

def main():
    ensure_axe()
    axe_src = open(AXE_JS, encoding='utf-8').read()
    df = pd.read_csv(SAMPLE)
    done = set()
    if os.path.exists(OUT):
        with open(OUT, encoding='utf-8') as f:
            for line in f:
                try: done.add(json.loads(line)['url'])
                except Exception: pass
        print(f'resuming: {len(done)} already done')

    todo = [r for _, r in df.iterrows() if r.url not in done]
    print(f'{len(todo)} sites to audit')

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1366, 'height': 900},
                                  user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                             'AppleWebKit/537.36 Chrome/124 Safari/537.36')
        out = open(OUT, 'a', encoding='utf-8')
        for k, row in enumerate(todo, 1):
            url = row.url
            rec = {'url': url, 'country': row.country, 'status': 'error', 'error': None,
                   'violations': [], 'criteria': [], 'rule_ids': []}
            page = ctx.new_page()
            try:
                page.goto(url, timeout=45000, wait_until='domcontentloaded')
                page.wait_for_timeout(3000)  # let client-side rendering settle
                page.add_script_tag(content=axe_src)
                result = page.evaluate('async () => await axe.run(document, '
                                       '{runOnly: {type: "tag", values: ["wcag2a","wcag2aa","wcag21a","wcag21aa","wcag22aa"]}})')
                crits = set()
                for v in result.get('violations', []):
                    cs = wcag_criteria_from_tags(v.get('tags', []))
                    crits.update(cs)
                    rec['violations'].append({'id': v['id'], 'impact': v.get('impact'),
                                              'criteria': cs, 'nodes': len(v.get('nodes', []))})
                    rec['rule_ids'].append(v['id'])
                rec['criteria'] = sorted(crits)
                rec['status'] = 'tested'
            except Exception as e:
                rec['error'] = str(e)[:200]
            finally:
                page.close()
            out.write(json.dumps(rec) + '\n'); out.flush()
            print(f'[{k}/{len(todo)}] {url[:60]:60s} {rec["status"]:7s} '
                  f'criteria={len(rec["criteria"])}')
            time.sleep(1.0)
        browser.close()
    print('done ->', OUT)

if __name__ == '__main__':
    main()
