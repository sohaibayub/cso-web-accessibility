# cso-web-accessibility

Data, results and code for the paper

**Digital Barriers in Low-Resource Advocacy: A Systematic Accessibility Assessment of Civil Society Organization Websites**
Muhammad Sohaib Ayub, Umair ul Hassan, Iftikhar Azim Niaz and Imdad Ullah Khan. Submitted to Universal Access in the Information Society, 2026.

Archived on Zenodo: this version at https://doi.org/10.5281/zenodo.23529469, all versions at https://doi.org/10.5281/zenodo.23529468.

The study audited the homepages of 161,220 civil society organizations with recorded websites in the United Kingdom, Australia, the United States, New Zealand and Ireland against WCAG 2.0, 2.1 and 2.2 success criteria using WARD (Web Accessibility Review tool for resource-constrained Domains), a static-analysis tool written in Python. A browser-based audit of a stratified 500-site subsample with axe-core validated the instrument. The audit ran between June and July 2026.

## Layout

```
frame/        the evaluation frame, one CSV per country, plus the merged workbook
results/      per-site audit results (gzipped JSON), a per-site CSV for the UK, and one Excel report per country
validation/   the 500-site validation subsample, the axe-core results and the comparison scripts
ward/         the WARD toolkit, the register collection scripts and the UK chunked pipeline
```

## frame/

| File | Rows | Source |
|---|---|---|
| uk_orgs.csv | 80,978 | Charity Commission for England and Wales, full register download, charities with a recorded website |
| aus_orgs.csv | 36,500 | Australian Charities and Not-for-profits Commission register via data.gov.au |
| usa_orgs.csv | 25,504 | Wikidata, organizations typed as nonprofit with an official website, collected by SPARQL (24,174), plus the public member list of the Minnesota Council of Nonprofits (1,330 further organizations); the source column says which |
| nz_orgs.csv | 16,184 | Charities Services New Zealand register via its OData API |
| irl_orgs.csv | 2,057 | member directory of the national association of community and voluntary organizations |

Columns are `name`, `url`, `country` and `source`. The paper deduplicates each frame by exact URL within country before reporting counts, which is why Ireland's 2,057 rows become 2,054 in the paper. `civil_society_websites_all_countries.xlsx` is the merged frame as collected; the US sheet there predates the addition of the Minnesota list.

## results/

`results_<country>_orgs.json.gz` holds one record per organization in the frame. Decompress with `gunzip` or read directly with Python's `gzip` module. The Irish file combines two runs of the same frame (June and July 2026): for each URL it keeps the July record if that fetch succeeded, otherwise the June record if that one succeeded, otherwise the July error record. Each record has these fields:

| Field | Meaning |
|---|---|
| organization, url, country | from the frame |
| final_url | the URL that answered after variant rotation |
| status | `tested` or `error` |
| error | failure cause for unreachable sites (connection, timeout, HTTP status, TLS) |
| count_2_0, count_2_1, count_2_2 | violation counts under the WCAG 2.0 subset, the WCAG 2.1 AA set and the strict WCAG 2.2 set |
| issues_2_0, issues_2_1, issues_2_2 | the itemized violations, each with criterion, conformance level and description |
| compliance_pct | share of evaluated criteria with no violation |
| accessibility_score, severity_score | the severity-weighted score and its raw form (not used in the paper) |

The `level` field in the issue records is the tool's own label. The paper applies the official W3C conformance level of each criterion instead (2.5.3, 3.2.6 and 3.3.7 are Level A), as `replicate_tables.py` does.

`results_uk_orgs.csv` is a flat per-site summary of the UK file. `WARD_Report_<country>_orgs.xlsx` are the Excel reports produced by `ward/generate_ward_report.py`, with summary, violation ranking, per-site results, worst and best sites, and error sheets. The reports total the tool's `count_2_1` field, which covers 17 criteria; the paper's tables use the itemized lists as described below, so the two sets of totals differ slightly.

## validation/

| File | What it is |
|---|---|
| validation_sample.csv | 500 sites, 100 per country, stratified across five violation-count quintiles, fixed seed |
| ward_criteria_sample.csv | WARD's flagged criteria for those sites, taken from the census results |
| axe_results.jsonl | the axe-core 4.9.1 run over the 500 sites in headless Chromium, one record per site; 463 completed and the rest carry the failure reason |
| validation_summary.csv | per-criterion agreement between WARD and axe-core on the subsample |
| run_axe_validation.py | runs the browser audit (Playwright, resume-safe); downloads axe-core 4.9.1 on first run |
| compare_ward_axe.py | computes site-level agreement, per-criterion agreement and the rank correlation |

## ward/

| Script | Purpose |
|---|---|
| ward_civil.py | the audit tool. `python ward_civil.py <frame.csv> [batch_size]` writes `results_<stem>.json` incrementally and resumes if interrupted |
| ward_civil_chunk_json.py, run_all_chunks_json.py, split_csv.py, prepare_resume.py, merge_detailed_results.py | the chunked pipeline used for the UK register (3,000-site chunks, JSONL output per chunk, merged afterwards) |
| ward_civil_chunk.py, run_all_chunks.py, run_all_chunks.sh | the earlier counts-only pass over the same chunks |
| generate_ward_report.py | `python generate_ward_report.py results_<country>_orgs.json` produces the Excel report |
| scrape_four_countries.py | collection of the UK frame from the Charity Commission bulk download (also contains earlier collectors for the other countries) |
| scrape_aus.py, parse_aus_csv.py | ACNC register collection and parsing |
| scrape_nz_final.py | Charities Services NZ OData collection |
| scrape_usa_all.py | Wikidata SPARQL collection for the United States (the ProPublica and IRS sources in the script were not used in the paper) |
| scrape_irl_directory.py | collection of the Irish member directory, URLs only |

## Reproducing the paper's tables

```
python replicate_tables.py
```

The script reads the five results files and recomputes every figure in the paper: the reachability breakdown, the headline conformance numbers, Tables 2 to 4, the values plotted in Figures 1 to 3, the WCAG 2.2 transition figures and the most frequent defect texts. It prints each value next to the one printed in the paper and ends with a line saying whether all of them match. It needs only the Python standard library.

The definitions it applies are the ones the paper uses. The frame is deduplicated by exact URL within each country. Audited sites are those with status `tested`. The itemized list `issues_2_2` is the extended evaluation; the WCAG 2.1 AA set is that list without the four criteria WCAG 2.2 introduced (2.4.11, 3.2.6, 3.3.7, 3.3.8), the strict WCAG 2.2 set is that list without 4.1.1, and the WCAG 2.0 subset is `issues_2_0`.

## Reproducing the audit

```
pip install -r requirements.txt
python ward/ward_civil.py frame/nz_orgs.csv
python ward/generate_ward_report.py results_nz_orgs.json
```

Runtime is about 0.8 seconds per site on one machine, so New Zealand takes a few hours and the UK register a few days, or less with the chunked pipeline. For the validation study:

```
pip install playwright pandas scipy
playwright install chromium
python validation/run_axe_validation.py
python validation/compare_ward_axe.py
```

Websites change, so a re-run will not reproduce the counts exactly. The results files in this repository are the ones the paper reports.

## What WARD evaluates

WCAG 2.0 criteria 1.1.1, 1.3.1, 1.4.1, 1.4.4, 2.1.1, 2.4.1, 2.4.2, 2.4.4, 2.4.6, 3.1.1, 4.1.1 and 4.1.2; the WCAG 2.1 additions 1.3.4, 1.3.5, 1.4.10, 1.4.12, 1.4.13 and 2.5.3; and the WCAG 2.2 additions 2.4.11, 3.2.6, 3.3.7 and 3.3.8. Strict WCAG 2.2 totals exclude 4.1.1, which WCAG 2.2 removed. WARD evaluates the parsed HTML of the homepage without executing JavaScript, so every count is a lower bound; the validation folder quantifies the gap.

## Licence

The code is released under the MIT License (see LICENSE). The frame and the results are released under the Creative Commons Attribution 4.0 International licence (CC BY 4.0). The register data in `frame/` derives from open registers published by the Charity Commission for England and Wales, the Australian Charities and Not-for-profits Commission, Charities Services New Zealand and Wikidata, each under its own open licence.

## Contact

Muhammad Sohaib Ayub, Institute for Data and AI Research, University of Galway
muhammadsohaib.ayub@universityofgalway.ie
