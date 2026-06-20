# KHS Policy Watch on GitHub Actions

This repository runs the KHS policy/regulatory watch.

## What It Does

- Runs every 15 minutes with GitHub Actions.
- Polls official/trusted public sources first.
- Looks for stage-changing policy, legal, regulatory, agency, offshore wind permit, SEC EDGAR, and OpenDART filing events.
- Creates a short Actions summary every run.
- Opens a GitHub issue only when a new high-impact candidate is detected.
- Stores seen fingerprints in `data/khs_policy_watch_seen.json` so repeated items are not alerted again.

## Required Setup

### 1. Add DART API Secret

GitHub repo path:

`Settings` -> `Secrets and variables` -> `Actions` -> `Secrets` -> `New repository secret`

- Name: `DART_API_KEY`
- Value: your OpenDART API key

### 2. Add SEC User-Agent

Recommended repo path:

`Settings` -> `Secrets and variables` -> `Actions` -> `Secrets` -> `New repository secret`

- Name: `SEC_USER_AGENT`
- Value example: `KHS-policy-watch your-email@example.com`

A repository variable named `SEC_USER_AGENT` also works, but a secret is better for public repositories because variables can appear in Actions logs.

### 3. Optional Korean Stock Watchlist

GitHub repo path:

`Settings` -> `Secrets and variables` -> `Actions` -> `Variables` -> `New repository variable`

- Name: `DART_WATCH_STOCK_CODES`
- Value example: `005930,000660,373220,051910,006400,112610,267260,010120,064350,010140,329180`

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

### DART / Korea Filings

Uses OpenDART `https://opendart.fss.or.kr/api/list.json`.

The script flags high-impact Korean report names such as supply contracts, major sales contracts, paid-in capital increases, convertible bonds, treasury shares, mergers, spin-offs, litigation, largest-shareholder changes, and investment-decision material disclosures.

### BOEM / BSEE Offshore Wind

Added official BOEM/BSEE sources:

- BOEM news RSS
- BSEE official news page
- BSEE official Notice to Lessees page
- CourtListener BOEM/BSEE offshore wind legal search

BSEE HTML pages are filtered more strictly so static explanation pages do not become high-impact alerts.

## How To Run Manually

1. Open the repository on GitHub.
2. Go to `Actions`.
3. Choose `KHS policy watch`.
4. Click `Run workflow`.
5. Open the run and read the step summary.
6. If a new high-impact candidate is detected, the workflow creates a GitHub issue.

## Current Limitation

This first version is deterministic source polling, not a full analyst. Treat it as a high-signal tripwire. The KHS morning radar should still verify original documents, market reaction, Korean value-chain exposure, and invalidation signals.
