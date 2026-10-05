# Policy Alert Readability Verification

## Request and Scope

The user supplied six FCC/Army policy alerts with incomplete core sentences and
disordered explanatory sections. Keep all material source-backed facts visible,
use complete Korean sentences, and make the original link clickable. A formatting
change does not authorize restarting the separately paused policy watch.

## Changes

- Removed the delivery-time 50-character crop and forced copula suffix. Existing
  shared short-summary helpers outside policy delivery are unchanged.
- Render core, factual bullets, policy stage, dates/timeline, scope, and source in
  a stable label-based order. Do not classify incidental words into decorative
  company/risk sections.
- Separate the FCC's adopted 1,050 MHz opening from the additional Ku/Ka 1,450 MHz
  and D-band consultation. The 138.25 GHz value is aggregate candidate bandwidth,
  not a single center frequency or a finalized allocation.
- Distinguish September 30 adoption, October 1 FCC release, October 1 FASCOM memo
  signature, and October 2 Army publication. A date-only source does not acquire
  an invented midnight publication time.
- Preserve foreign-currency amounts with parenthesized rounded KRW equivalents,
  plus the original amount roles and action. Escape HTML attributes exactly once.
- Split oversized bundles at article/field boundaries instead of truncating
  facts. Persist acknowledged part receipts so an interrupted retry resumes the
  unsent parts. Partial receipts do not finalize unsent news-event histories.
- A maintenance push no longer enables the user-paused policy workflow or starts
  a live Telegram dispatch. Existing sent-event state is not cleared.

## Primary-Source Recheck

- FCC 26-64: official attachment text read successfully; limited NEPA scope and
  retained antenna-structure/FAA obligations checked.
- FCC 26-65: official attachment text read successfully; 550 MHz + 500 MHz,
  gateway/feeder-link conditions, split filing freeze, and further notice checked.
- Army FASCOM article: October 1 signed memo, six formation areas, FY2028 priority,
  acquisition executive, 15X and 390A checked against the October 2 publication.
- Army State of the Force article and MITRE Project Meridian page: announced
  four-star command versus existing activation, Agincourt responsibilities,
  research scope, and current co-director names checked.
- Project Meridian commissioning PDF returned HTTP 403. Its 120-day submission
  requirement was not reverified. The initial research alert explicitly retains
  this unresolved status instead of presenting January 28 as a confirmed deadline.

## Verification

`verify_khs_policy_readability.py --write-previews --check-live-sources` generates
two preview bundles and a sidecar with test counts, source hashes, and timestamps.
The suite covers the six supplied cases, real final-delivery guard, complete text
through splitting, balanced/clickable HTML, currency role preservation, repeat
formatting, date precision, workflow Python syntax, partial-send retry, and
maintenance pause preservation.

Also run the existing policy delivery contract and all 11 radar regression
commands. Remote validation must use a dry run, check the actual checkout SHA,
and inspect saved preview artifacts. Dry-run success is not Telegram delivery.

## Completion Boundaries

No six old articles were replayed to Telegram. No seen-history reset was made.
The policy watch must remain `disabled_manually`; the news radar must remain
`active`. Source-backed summaries retain the important article facts, not the
full verbatim article. Tests and source checks are evidence for these regressions,
not a guarantee of perfect future extraction or exactly-once network delivery.
