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

### Recorded Result: October 5, 2026

- Policy delivery contract passed locally; all 11 radar checks passed locally
  and on Actions. The new readability suite passed 15 tests for the six cases.
- Production change: `d9f85ed2422ef9efdb641c6a21e1fde34e731ddb`.
- Actions run [37267304005](https://github.com/qedgwangju-dot/khs-watch/actions/runs/37267304005)
  completed successfully. Its checkout was `0f05ebc5b3627f041313592484ea03bd4948d184`;
  the intervening changes did not modify the policy renderer or verifier.
- All four remote preview artifacts matched the local previews after newline
  normalization. Remote sidecar: 15 tests, 6 cases, 0 failures, 0 errors,
  `external_delivery=false`, `seen_state_changed=false`.
- Browser-rendered preview checks at 800px and 390px showed no horizontal
  overflow. All three source anchors retained their exact destinations.
- The local official FCC recheck succeeded for both attachment texts. The remote
  suite is fixture replay, not an independent live FCC retrieval.
- Final workflow states: policy watch `disabled_manually`, news radar `active`.
- Radar collection in the dry run still recorded inaccessible Etnews sources
  and body-verification failures. This formatting verification does not certify
  full news-source coverage or repair those separate retrieval failures.

## Completion Boundaries

No six old articles were replayed to Telegram. No seen-history reset was made.
The policy watch must remain `disabled_manually`; the news radar must remain
`active`. Source-backed summaries retain the important article facts, not the
full verbatim article. Tests and source checks are evidence for these regressions,
not a guarantee of perfect future extraction or exactly-once network delivery.
