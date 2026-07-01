# GAMEJOA Preopen News Radar on GitHub Actions

This workflow moves the 06:30 KST `GAMEJOA 장전 핵심 뉴스 레이더` from the local Codex scheduler to an external GitHub Actions runner.

## What It Does

- Runs every day at 06:30 KST (`30 21 * * *` UTC).
- Builds a Korean high-impact preopen news radar.
- Sends a compact Korean-only core radar to Telegram when Telegram secrets are configured.
- Uploads the Markdown/JSON/title outputs as GitHub Actions artifacts.
- Keeps local Codex automation usable as a backup until the GitHub delivery is confirmed.

## Workflow File

`.github/workflows/gamejoa-preopen-news-radar.yml`

## Runner Script

Telegram workflow entrypoint:

`scripts/gamejoa_preopen_news_radar_telegram_runner.py`

Strict local-policy overlay:

`scripts/gamejoa_preopen_news_radar_strict_runner.py`

Base source/selection runner:

`scripts/gamejoa_preopen_news_radar_runner.py`

## Required GitHub Secrets

Go to:

`Settings` -> `Secrets and variables` -> `Actions` -> `Secrets`

Add:

- `GAMEJOA_TELEGRAM_BOT_TOKEN`
- `GAMEJOA_TELEGRAM_CHAT_ID`

Fallbacks, used only when the GAMEJOA-specific secrets are not set:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `KHS_POLICY_TELEGRAM_BOT_TOKEN`
- `KHS_POLICY_TELEGRAM_CHAT_ID`

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

## Telegram Format Contract

The Telegram message should contain only the core news radar:

- no data-processing table;
- no Markdown table separator rows such as `|---|---:|---:|---|`;
- no source-count/debug list;
- no `전체 보고서` action-run suffix;
- Korean display titles for local data-center policy items;
- local data-center policy articles grouped into one readable cluster when the same theme repeats;
- clickable source names via Telegram HTML parse mode instead of raw long URLs.

## Data Center Local Ban Coverage

The radar treats local US data-center restriction stories as a mandatory policy/timeline screen, not as ordinary sentiment news.

Dedicated local data-center policy queries include:

`"data center" ban moratorium city council residents vote zoning power Reuters Bloomberg AP USA Today`

`"data centers" residents vote block construction city council zoning moratorium county township local news`

`"data center" "planning commission" "public hearing" permit ordinance moratorium power local news`

If a fresh regional/local article contains `data center` or `data centers` plus local policy terms such as `ban`, `block`, `moratorium`, `city council`, `residents`, `vote`, `zoning`, `permit`, `ordinance`, `planning commission`, or `public hearing`, the runner:

- accepts it as a trusted local-policy candidate even when it is not from a national outlet;
- classifies it as `데이터센터/전력망/전력기기`;
- maps the impact to `할인율` and `시간표`, not confirmed revenue unless a contract/order is separately confirmed;
- groups repeated local data-center policy articles into one compact Korean cluster in Telegram so the alert stays readable.

This is intended to catch city-council bans, zoning moratoria, and resident vote campaigns that can change AI infrastructure timelines or regulatory discount rates before national policy headlines pick them up.

## Manual Test

1. Open the repository on GitHub.
2. Go to `Actions`.
3. Select `GAMEJOA preopen news radar test send` for a real Telegram test, or `GAMEJOA preopen news radar` for the scheduled workflow.
4. Click `Run workflow`.

## Local Test

PowerShell:

```powershell
$env:TELEGRAM_DRY_RUN='true'
python scripts/gamejoa_preopen_news_radar_runner.py
python scripts/gamejoa_preopen_news_radar_strict_runner.py
python scripts/gamejoa_preopen_news_radar_telegram_runner.py
```

If local `python` is not on PATH, use the Codex bundled Python runtime.
