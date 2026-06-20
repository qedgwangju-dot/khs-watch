# KHS Policy Watch on GitHub Actions

This repository runs the KHS policy/regulatory watch.

## What It Does

- Runs every 15 minutes with GitHub Actions.
- Polls official/trusted public sources first.
- Looks for stage-changing policy, legal, regulatory, presidential action, agency, offshore wind permit, SEC EDGAR, and OpenDART filing events.
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

Use a secret, not a repository variable, because variables can appear in public Actions logs.

### 3. Optional Telegram Alert

Telegram is optional. When configured, the workflow sends a Telegram message only when a new high-impact alert exists. Manual runs can also send a test message with `telegram_test=true`.

#### Create Telegram Bot

1. Open Telegram and search for `@BotFather`.
2. Send `/newbot`.
3. Choose a bot display name.
4. Choose a bot username ending in `bot`.
5. Copy the bot token.

Add the token as a GitHub secret:

`Settings` -> `Secrets and variables` -> `Actions` -> `Secrets` -> `New repository secret`

- Name: `TELEGRAM_BOT_TOKEN`
- Value: the token from `@BotFather`

#### Get Chat ID

For a personal chat:

1. Open the new bot chat in Telegram.
2. Send any message to the bot, such as `test`.
3. Open this URL in a browser, replacing `<TOKEN>` with the bot token:

`https://api.telegram.org/bot<TOKEN>/getUpdates`

4. Find `message.chat.id` in the JSON response.

For a group chat, add the bot to the group, send a group message, then use the same `getUpdates` URL. Group chat IDs are often negative numbers.

Add the chat ID as a GitHub secret:

- Name: `TELEGRAM_CHAT_ID`
- Value: the `message.chat.id` value

#### Test Telegram

1. Go to `Actions`.
2. Choose `KHS policy watch`.
3. Click `Run workflow`.
4. Set `telegram_test` to `true`.
5. Confirm a Telegram message arrives.

### 4. Optional Korean Stock Watchlist

GitHub repo path:

`Settings` -> `Secrets and variables` -> `Actions` -> `Variables` -> `New repository variable`

- Name: `DART_WATCH_STOCK_CODES`
- Value example: `005930,000660,373220,051910,006400,112610,267260,010120,064350,010140,329180`

## Source Layers

### Official Policy / Regulatory Sources

- Federal Register search RSS: energy permits/final rules, semiconductor export controls, tariff/Section 301
- Federal Register Presidential Documents API: executive orders, presidential memoranda, determinations, proclamations, and presidential permits
- White House Presidential Actions pages: Executive Orders, Presidential Memoranda, and policy-relevant Proclamations
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
