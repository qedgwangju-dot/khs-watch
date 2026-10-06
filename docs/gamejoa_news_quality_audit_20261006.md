# 2026-10-06 Radar Source and Delivery Audit

## Observed Production Failure

Run 37440806142 checked out version 94 after commit
`4b96d5095218dd6a627662c034aa803e49367e2b`. Telegram acknowledged message
2318, but the job reached its 15-minute timeout before committing sent history.
This is a delivered message with an incomplete workflow, not a quality pass.

The successful receipt allowed recovery of 55 missing keys while preserving all
8072 existing keys. Recovery commit
`ebaf6365adae0df82e8a4cf70d79bf05bc2f55ba` did not call Telegram or reset history.

## Whole-Body Review

All seven delivered article bodies were read and bound to saved source hashes.
They are replay fixtures, not current live source inputs.

| Article | Treatment | Source-bound core requirement |
| --- | --- | --- |
| Hyundai Saudi construction-site response | Keep | Houthi attack claim; Hyundai's current no-damage assessment |
| Samsung DX earnings preview | Keep | IBK and Yuanta segment losses remain Q3 estimates, not actual losses |
| Lotte foreign-sales roundup, Newsis | Same event | Issuer, foreign-customer population, year, amount and disclosure date |
| LG Energy Solution consensus | Keep | FnGuide Q3 revenue/profit forecasts; Q2 comparison; Oct 8 scheduled release |
| Lotte foreign-sales roundup, Etoday | Same event | Date and current period appear after the introductory paragraphs |
| Lotte foreign-sales release, Newsis | Same event | Milestone, not the issuer's promotional quote |
| Bulgwang local demolition notice | Exclude | The only contractor selection was historical, not a new commercial order |

Six eligible articles collapse to four primary events. Revisions of amount,
period or disclosure date retain separate event identities. A temporary
receipt-backed alias replay leaves zero fresh repeats and changes no production
history or Telegram message.

## Version 95 Contract

- Recover the primary milestone from complete issuer-owned source sentences.
- Keep segment and total-company earnings scopes separate.
- Keep consensus attribution, period, values and release stage together.
- Keep a claimed attack separate from an issuer-confirmed damage assessment.
- Reject local announcements that borrow their commercial evidence from old facts.
- Reject anniversary memorials, single-product dessert trend publicity and
  ownership-exit scenarios without a new owner action. Preserve actual earnings,
  source-bound review/negotiation and quantified new contracts.
- A premium AP market forecast cannot use an earlier quarter's global AP share.
  Retain the research provider, premium population, forecast year and competitors.
- Skip ETF-specific body scans for non-ETF articles without changing eligibility.
- Allow 20 minutes for the observed collection path and preserve acknowledged
  receipt history in cleanup even after cancellation. Failed or dry sends cannot
  mark an article as delivered.

Local regression, production execution, article quality, Telegram acceptance and
persisted sent history are separate evidence levels. The new production result
will be recorded after execution. This audit does not claim complete source
coverage or universal future accuracy.

## Follow-Up Whole-Body Review

Run 37444262832 completed and Telegram acknowledged message 2320, but direct
review found three non-catalysts and a population/period mismatch. Its green
workflow is not a content-quality pass. All seven original bodies were read.

The AI listing report, quantified defense-site MOU, early power-contract report
and premium AP forecast remain eligible. The ownership-exit scenario, anniversary
memorial and dessert trend publicity are excluded. The AP core binds the
Counterpoint premium Android AP forecast and forecast year, not the prior
quarter's global Exynos share. Four events remain, with no new actual confirmed
contract or actual earnings claim inferred from a forecast, MOU or source report.
