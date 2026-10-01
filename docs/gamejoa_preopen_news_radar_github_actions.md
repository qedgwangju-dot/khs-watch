# GAMEJOA Preopen News Radar on GitHub Actions

This workflow moves the 06:30 KST `GAMEJOA 장전 핵심 뉴스 레이더` from the local Codex scheduler to an external GitHub Actions runner.

## What It Does

- Receives the 06:30 KST preopen dispatch and has a native live fallback at minutes 07, 27 and 47 of every hour (`7,27,47 * * * *` UTC).
- Builds a Korean high-impact preopen news radar.
- Sends a compact Korean-only core radar to Telegram when Telegram secrets are configured.
- Uploads the Markdown/JSON/title outputs as GitHub Actions artifacts.
- Keeps local Codex automation usable as a backup until the GitHub delivery is confirmed.

## Workflow File

`.github/workflows/gamejoa-preopen-news-radar.yml`

## Runner Script

Telegram workflow entrypoint:

`scripts/gamejoa_preopen_news_radar_fda_quality_runner.py`

The entrypoint applies the full compact renderer and its source/stock-market quality gates before the Telegram delivery runner.

Strict local-policy overlay:

`scripts/gamejoa_preopen_news_radar_strict_runner.py`

Base source/selection runner:

`scripts/gamejoa_preopen_news_radar_runner.py`

## Required GitHub Secrets

Go to:

`Settings` -> `Secrets and variables` -> `Actions` -> `Secrets`

Add:

- `KHS_POLICY_TELEGRAM_BOT_TOKEN`
- `KHS_POLICY_TELEGRAM_CHAT_ID`

These are the `@hs8879_bot` destination used for the 실시간 뉴스 정책 bot.

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
- Domestic and international stock-market news across earnings, valuation/discount rates, flows, catalysts/timelines, supply chains and market-wide changes; company-name keywords are not the coverage boundary.
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

## Article Retrieval Progress

- Each collection can verify up to 160 Korean article bodies using 12 workers. Half the slots follow urgency ranking and half follow the oldest waiting/least attempted URLs, so fixed keyword scores cannot permanently starve other articles.
- `data/gamejoa_article_detail_queue.json` stores discovery times, attempts, verification status and retry times only. It contains no article bodies and is independent of delivered/seen state.
- Failed addresses back off for 5, 15, 60 and then 120 minutes. A changed headline/publication fingerprint becomes eligible immediately. Recent unchanged deliveries are skipped for one hour in the live lane; the preopen digest bypasses live retrieval cooldowns.
- Preflight and send may reuse an exact-fingerprint source receipt only within the same `GITHUB_RUN_ID` and for at most 15 minutes. The original article query time remains in the audit; another execution must fetch the source again.
- Retrieval metadata is merged and committed even if a subsequent report/delivery check fails. Sent/seen state still requires successful verified delivery. Manual dry runs do not commit either state.
- A verified `articleBody` region takes precedence over longer navigation/recommended-story nodes. Hidden quote popups, sidebars and footer navigation are not article evidence. Sports-association elections and ceremonial photos without a material corporate event are not market alerts.
- Publisher descriptions stay separate from the verified body. Core sentences exclude image credits and context-only comparisons; decimal values stay intact, and an explicit company statement of non-confirmation is not replaced by market speculation.
- Generated sector labels never establish market relevance. Source headlines and bodies must contain a material market/business event; coverage includes private-company financing, client cooperation, industrial incentives and climate-related supply damage without a fixed company whitelist. Photo credits and obfuscated email addresses are stripped and checked before delivery.
- Article-body requests validate each direct/proxy response before selecting a winner. An HTTP-successful consent page, empty body or mismatched article cannot hide the other route's verified article. Other shared-fetch callers retain the default HTTP-only behavior unless they supply a response validator.
- Validated article requests use an HTML-only Accept header; feed/JSON negotiation remains separate so an HTTP-successful empty alternative representation cannot masquerade as an article response.
- Metadata records the response-validation version. A previous HTTP-only title/body validation failure gets one immediate retry under the corrected route selection; transport failures, subsequent failures and verified/delivered articles keep their ordinary backoff and dedupe behavior.
- `selection_diagnostics.detail_coverage` retains failed/deferred counts, and `detail_queue` records fetches, same-run hits, fair slots and skips. A successful workflow is not proof that every source was accessible or every candidate was examined.
- `verify_gamejoa_article_detail_queue.py` tests progress under continuing urgent arrivals, backoff, updated-story and preopen bypass, same-run expiry, state merging, publisher contamination and non-market false positives.

## Source Materiality Refinement

- Source-verified candidates carry an internal `market_materiality` audit: evidence kind, exact source sentence, early/reported stage, earnings/discount-rate/flow/timeline axes and priority. Generated sectors, watch flags and commentary are not evidence.
- Results, changes in policy scope, market flows, supply damage and execution stages precede general cooperation announcements before the display limit. Within an economic priority, source event focus precedes publication time; generated keyword scores and retrieval time do not decide priority. Priority does not estimate stock-price impact.
- Preliminary negotiations, proposed restrictions, research forecasts, client discussions, technology validation, clinical stages and climate supply risks remain eligible without a signed contract, minimum monetary threshold or issuer whitelist.
- Routine volunteering, awards, promotions, visits and vague cooperation without a new source-grounded business change are excluded. An older revenue figure or another company's background paragraph cannot rescue a promotional headline. Unrecognised events still face the existing broad market/source/summary gates rather than a new whitelist.
- The audit is internal only. Telegram keeps the aligned title, complete compact core and clickable source. No commentary or decision matrix is restored; delivered/seen keys and retrieval state are not reset.
- `verify_gamejoa_market_materiality.py` runs in production and test CI. The generated-report guard recomputes the audit from source text before delivery and rejects missing/stale evidence or routine articles that bypass selection.
- Headline event focus and explicit reporting month now constrain source evidence and compact cores. Related-story sections and publisher UI are removed before assessment. A preceding R&D issuer may qualify the following amount only when the adjacent source sentences establish that relationship.
- Direct financing, contracts, scoped restrictions, supply disruption and rate/macro changes outrank routine index recaps and retrospective features. Proposed policy or financing retains its early stage without automatically being less material than a reported small index move. Price changes alone never prove investor flows.
- Tactical weapon deployment without an economic transmission path is excluded; energy/logistics attacks, Hormuz tanker incidents, sanctions, ceasefire/negotiation developments, procurement and major escalation remain eligible. This is not a geopolitical-source shutdown.
- Saved-run shadow audits are read-only: compare old/new source cores and exclusions without resetting seen state or resending historical Telegram messages. Headline-event/month checks also run in the compact renderer and pre-delivery generated-report guard.
- Loan-solicitation advertorials cannot qualify through an introductory IPO/industry paragraph or investor advice. Genuine margin/loan regulation and corporate financing remain eligible. A prior-session "today's market" preview is stale even within the 24-hour discovery window; overnight global news is not excluded by that rule. Buyback-ending summaries preserve the source issuer, deadline and forecast wording.
- A denial or unconfirmed-investment headline must retain that polarity in its source evidence and compact core. A previous affirmative announcement is background, not a substitute for the new denial; the denying speaker and qualification must remain in the summary.

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
