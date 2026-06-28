# GAMEJOA Preopen News Radar on GitHub Actions

This workflow moves the 06:30 KST `GAMEJOA 장전 핵심 뉴스 레이더` from the local Codex scheduler to an external GitHub Actions runner.

## What It Does

- Runs every day at 06:30 KST (`30 21 * * *` UTC).
- Builds a Korean high-impact preopen news radar.
- Sends the report to Telegram when Telegram secrets are configured.
- Uploads the full Markdown/JSON report as a GitHub Actions artifact.
- Keeps local Codex automation usable as a backup until the GitHub delivery is confirmed.

## Workflow File

`.github/workflows/gamejoa-preopen-news-radar.yml`

## Runner Script

`scripts/gamejoa_preopen_news_radar_runner.py`

## Required GitHub Secrets

Go to:

`Settings` -> `Secrets and variables` -> `Actions` -> `Secrets`

Add:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Strongly Recommended Secrets

- `SEC_USER_AGENT`
  - Example: `GAMEJOA-preopen-radar your-email@example.com`
  - SEC EDGAR can rate-limit generic clients.
- `DART_API_KEY`
  - Enables OpenDART Korean disclosure checks.
- `FRED_API_KEY`
  - Optional but recommended. If absent, the workflow falls back to the public FRED CSV endpoint for `DFII10`.

## Optional GitHub Variables

Go to:

`Settings` -> `Secrets and variables` -> `Actions` -> `Variables`

Optional:

- `DART_WATCH_STOCK_CODES`
  - Default: `005930,000660,373220,051910,006400,112610,267260,010120,064350,010140,329180`

## Source Coverage

The workflow checks:

- Official sources: FERC, DOE, USTR, Commerce, BIS, OFAC, SEC, FTC, FDA, Federal Register
- Company filings: SEC EDGAR watchlist and OpenDART when configured
- Trusted news RSS via Google News: Reuters/Bloomberg/AP/CNBC/MarketWatch and selected USA Today network local-policy sources
- Discount-rate cross-check: FRED `DFII10` and Trading Economics `United States 10 Year TIPS Yield`

## Data Center Local Ban Coverage

The radar includes a dedicated local data-center policy query:

`"data center" ban moratorium city council residents vote zoning power Reuters Bloomberg AP USA Today`

This is intended to catch city-council bans, zoning moratoria, and resident vote campaigns that can change AI infrastructure timelines or regulatory discount rates before national policy headlines pick them up.

## Manual Test

1. Open the repository on GitHub.
2. Go to `Actions`.
3. Select `GAMEJOA preopen news radar`.
4. Click `Run workflow`.
5. Use `telegram_dry_run=false` to send Telegram, or `true` to only build the report.

## Local Test

PowerShell:

```powershell
$env:TELEGRAM_DRY_RUN='true'
python scripts/gamejoa_preopen_news_radar_runner.py
```

If local `python` is not on PATH, use the Codex bundled Python runtime.
