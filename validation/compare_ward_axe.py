#!/usr/bin/env python3
"""
Compare WARD (static) against axe-core (browser) on the validation sample.
Run after run_axe_validation.py completes:

    python compare_ward_axe.py

Prints the numbers to paste into both papers, and writes validation_summary.csv.
"""
import json, os
import pandas as pd
from scipy.stats import spearmanr

HERE = os.path.dirname(os.path.abspath(__file__))
COMPARABLE = ['1.1.1', '1.3.1', '1.3.5', '2.4.1', '2.4.2', '2.4.4', '2.5.3',
              '3.1.1', '4.1.1', '4.1.2']
# Criteria both instruments can evaluate. Axe-only criteria (e.g. 1.4.3 contrast)
# are reported separately as "beyond static reach".

ward = pd.read_csv(os.path.join(HERE, 'ward_criteria_sample.csv'))
ward['ward_set'] = ward.ward_criteria.fillna('').apply(lambda s: set(x for x in s.split(';') if x))

axe = []
with open(os.path.join(HERE, 'axe_results.jsonl'), encoding='utf-8') as f:
    for line in f:
        axe.append(json.loads(line))
axe = pd.DataFrame(axe)
tested = axe[axe.status == 'tested'].copy()
tested['axe_set'] = tested.criteria.apply(set)
print(f'axe tested {len(tested)} / {len(axe)} sampled sites')

m = ward.merge(tested[['url', 'axe_set']], on='url', how='inner')
print(f'joined records: {len(m)}')

rows = []
for c in COMPARABLE:
    w = m.ward_set.apply(lambda s: c in s)
    a = m.axe_set.apply(lambda s: c in s)
    both, ward_only, axe_only, neither = (w & a).sum(), (w & ~a).sum(), (~w & a).sum(), (~w & ~a).sum()
    n = len(m)
    agree = (both + neither) / n * 100
    # treating axe as reference:
    prec = both / max(1, both + ward_only) * 100
    rec = both / max(1, both + axe_only) * 100
    rows.append(dict(criterion=c, both=both, ward_only=ward_only, axe_only=axe_only,
                     agreement_pct=round(agree, 1), precision_vs_axe=round(prec, 1),
                     recall_vs_axe=round(rec, 1)))
summary = pd.DataFrame(rows)
summary.to_csv(os.path.join(HERE, 'validation_summary.csv'), index=False)
print(summary.to_string(index=False))

wc = m.ward_set.apply(lambda s: len(s & set(COMPARABLE)))
ac = m.axe_set.apply(lambda s: len(s & set(COMPARABLE)))
rho, p = spearmanr(wc, ac)
print(f'\nSpearman rank correlation of per-site counts on comparable criteria: '
      f'rho = {rho:.3f} (p = {p:.2g}, n = {len(m)})')

extra = {}
for s in m.axe_set:
    for c in s:
        if c not in COMPARABLE:
            extra[c] = extra.get(c, 0) + 1
print('\nAxe-only criteria (beyond static reach), sites affected:')
for c, n in sorted(extra.items(), key=lambda x: -x[1])[:8]:
    print(f'  {c}: {n} sites ({n/len(m)*100:.0f}%)')

mean_agree = summary.agreement_pct.mean()
print(f'\nPaste-ready sentence:\n'
      f'On a stratified subsample of {len(m)} sites audited with browser-based axe-core, '
      f'per-criterion site-level agreement with WARD averaged {mean_agree:.0f} percent across the '
      f'{len(COMPARABLE)} criteria both instruments evaluate, and per-site violation-criterion counts '
      f'correlated at rho = {rho:.2f} (Spearman).')
