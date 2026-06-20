# GAMEJOA Policy Watch on GitHub Actions

This repository runs the first GitHub Actions version of the GAMEJOA policy/regulatory watch.

## What It Does

- Runs every 15 minutes with GitHub Actions.
- Polls official/trusted public sources first.
- Looks for stage-changing policy, legal, regulatory, agency, offshore wind permit, SEC EDGAR, and OpenDART filing events.
- Creates a short Actions summary every run.
- Opens a GitHub issue only when a new high-impact candidate is detected.
- Stores seen fingerprints in `data/gamejoa_policy_watch_seen.json` so repeated items are not alerted again.

## Required Setup

### 1. Add DART API Secret

GitHub repo path:

`Settings` -> `Secrets and variables` -> `Actions` -> `Secrets` -> `New repository secret`

- Name: `DART_API_KEY`
- Value: your OpenDART API key

Without this, DART will show `접근 제한 (DART_API_KEY 미설정)` and the rest of the watcher will still run.

### 2. Add SEC User-Agent Variable

GitHub repo path:

`Settings` -> `Secrets and variables` -> `Actions` -> `Variables` -> `New repository variable`

- Name: `SEC_USER_AGENT`
- Value example: `GAMEJOA-policy-watch your-email@example.com`

SEC requires a real User-Agent/contact string for fair access.

### 3. Optional Korean Stock Watchlist

GitHub repo path:

`Settings` -> `Secrets and variables` -> `Actions` -> `Variables` -> `New repository variable`

- Name: `DART_WATCH_STOCK_CODES`
- Value example: `005930,000660,373220,051910,006400,112610,267260,010120,064350,010140,329180`

Default watchlist:

- Samsung Electronics `005930`
- SK hynix `000660`
- LG Energy Solution `373220`
- LG Chem `051910`
- Samsung SDI `006400`
- CS Wind `112610`
- HD Hyundai Electric `267260`
- LS ELECTRIC `010120`
- Hyundai Rotem `064350`
- Samsung Heavy Industries `010140`
- HD Hyundai Heavy Industries `329180`

## Source Layers

### Official Policy / Regulatory Sources

- Federal Register search RSS: energy permits/final rules, semiconductor export controls, tariff/Section 301
- FERC RSS
- DOE RSS
- USTR RSS
- Commerce RSS
- BIS RSS
- OFAC recent actions RSS
- SEC press releases RSS
- FTC press releases RSS
- FDA press announcements RSS

### SEC EDGAR Company Filings

Uses `https://data.sec.gov/submissions/CIK##########.json`.

Current watchlist:

- NVDA, MU, AVGO, AMD, INTC, TSM, ASML, ARM, AAPL, MSFT, ORCL

Current form filter:

- 8-K, 6-K, 10-Q, 10-K, 20-F, 40-F, S-3, 424B5, SC 13D, SC 13G

### DART / Korea Filings

Uses OpenDART `https://opendart.fss.or.kr/api/list.json`.

The script flags high-impact Korean report names such as:

- supply contracts
- major sales contracts
- paid-in capital increases
- convertible bonds / bonds with warrants
- treasury shares
- mergers / spin-offs
- litigation
- largest-shareholder changes
- investment-decision material disclosures

### KRX KIND

KRX KIND is included as a backup public disclosure page check. It is less stable than OpenDART because the page may be dynamic or rate-limited. Treat DART as the primary Korean disclosure source and KIND as a secondary cross-check.

### BOEM / BSEE Offshore Wind

Added official BOEM/BSEE sources:

- BOEM news RSS
- BSEE official news page
- BSEE official Notice to Lessees page
- CourtListener BOEM/BSEE offshore wind legal search

These are intended to catch wind permitting, lease, construction and operations plan, notice-to-lessee, injunction, appeal, and final-rule changes.

### Court / Legal Watch

Uses CourtListener searches for:

- wind permit appeal injunction order
- BOEM/BSEE offshore wind permit lease order
- export controls semiconductor injunction order

## Alert Threshold

The watch is designed to catch:

- Court orders, appeal withdrawals, injunctions, stays, vacated orders
- Final rules, effective dates, implementation dates
- Permit restart, freeze removal, approval, rejection
- Sanctions, tariffs, export controls, Section 301 actions
- FDA approvals or rejection letters
- FERC, DOE, SEC, USTR, Commerce, BIS, OFAC actions
- Major SEC/DART-style company filings

Low-importance routine items are collected for the run summary but are not opened as alert issues.

## How To Run Manually

1. Open the repository on GitHub.
2. Go to `Actions`.
3. Choose `GAMEJOA policy watch`.
4. Click `Run workflow`.
5. Open the run and read the step summary.
6. If a new high-impact candidate is detected, the workflow creates a GitHub issue.

## Current Limitation

This first version is deterministic source polling, not a full LLM analyst. Treat it as a high-signal tripwire. The 06:30 GAMEJOA radar should still verify the original documents, market reaction, Korean value-chain exposure, and invalidation signals.

## Next Upgrades

- Add exact Korean sector/company watchlists.
- Add BOEM project-page polling for specific offshore wind projects.
- Add OpenAI summary step if an `OPENAI_API_KEY` secret is available.
- Split alerts into `상`, `중`, `하` labels.
