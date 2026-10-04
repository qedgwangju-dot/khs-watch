# GAMEJOA Maintenance Contract

GAMEJOA and KHS monitoring changes are complete only when implementation and
verification are handled as one inseparable unit. A green workflow alone is
not sufficient evidence that the content or Telegram delivery is correct.

## Mandatory Improvement Loop

Every defect or requested change must follow this sequence:

1. **원인 규명**: identify the actual runtime cause, not only the visible symptom.
2. **반영**: change the source, classifier, renderer, workflow, or delivery path
   that owns the behavior.
3. **재발 방지 회귀 테스트**: add or strengthen a durable invariant for the
   newly discovered defect class.
4. **로컬 검증**: run syntax checks, contract checks, and relevant fixtures or
   dry runs.
5. **원격 검증**: push the change and run the production GitHub Actions path.
6. **실제 송출 상태**: inspect the runtime delivery result separately from the
   workflow conclusion.

## Completion Labels

- `반영 완료` means the intended code or contract is committed and pushed.
- `재검증 완료` means the relevant local checks and remote workflow checks
  passed after that exact change.
- `sent` proves Telegram accepted a non-empty alert.
- `skipped_empty` means no Telegram message was sent because no qualifying item
  remained. It is valid runtime behavior, but it is not proof of a successful
  non-empty send.
- If a non-empty alert was not observed, report `실제 신규 알림 송출 미관찰`.

## Non-Negotiable Guards

- The core radar covers domestic and international stock-market-moving news,
  across industries, not only a fixed list of Korean companies or policy topics.
  Evidence may be a company event or a global transmission channel: interest
  rates, inflation/employment, FX/liquidity, trade restrictions, energy/materials,
  transport, geopolitical risk, earnings/investment, or capital flows.
- A foreign event does not need to name a Korean issuer to change the market's
  discount rate, costs, demand or risk premium. The channel must come from the
  source article, never collector query names or generated sector commentary.
- Policy/geopolitical topic flags never remove an item from the live radar on
  the assumption that a separate policy workflow delivered it. Normal source,
  freshness, materiality and duplicate guards still apply.
- Actions 성공만으로 완료 처리하지 않는다.
- Headline, summary, source URL, and source body must describe the same event.
- Verified Korean article titles and bodies are owned by the source-body layer.
  Legacy topic overlays must not replace them from background references. An
  incompatible thematic summary is re-extracted from the article and checked
  again; it is never published by bypassing source alignment. Related-story
  footers are not article evidence.
- Client-rendered News1 articles use only typed text in the linked article's
  `articleView`, bound to its requested URL article ID and aligned title. Empty,
  malformed or mismatched client data cannot fall back to recommendation HTML.
- A funding headline must retain the funding decision or unresolved options,
  not substitute HBM demand from its background. Conditional valuation or IPO
  scenarios do not become secured funding. Earnings forecasts retain their
  forecast attribution and quarter; prior-quarter results cannot own the core.
- An economic-war response needs sourced economic measures, not victory
  rhetoric. A reported review/announcement without specified policy terms stays
  an early signal; it never becomes a confirmed ban or oil-price change.
- Same-country, same-indicator, same-period, same-value macro releases share a
  seen key across publishers, including migrated historical seen entries.
  Revised values, other periods, core versus headline, and explicit month-on-
  month values remain distinct.
- A market event must be the article's foreground change. Consumer promotions,
  humanitarian response, ceremonial politics, regional multiplier studies and
  historical company profiles cannot qualify through incidental economic words.
  Actual outages, deaths, production damage, customer negotiations and early
  policy changes remain eligible when the source establishes the mechanism.
- A source headline consisting only of an issuer name is not a news event.
  Bank support MOUs need concrete size, financing terms or committed execution,
  not a platform-promotion paragraph. National export milestones prioritize the
  observed cumulative total and period over hypothetical required monthly sales.
- Entertainment/private-life articles cannot qualify as customer discussions
  from meeting or social-photo certification words. Apply the same genre and
  foreground check before body retrieval, alert construction and final output.
  Entertainment-section URLs need a headline market event, not a search-query
  AI label or a background company statistic. Actual company results, insider
  share trades and scoped commercial supply discussions remain eligible.
- Dated wire-photo captions are not current operating facts. A commentator's
  hypothetical psychological/logistics intent cannot by itself establish a
  confirmed supply interruption. Actual sourced disruptions remain eligible.
- Public-opinion percentages are not policy execution. Keep actual rule changes
  distinct from opinion polls; yield summaries prefer the observed rate change
  to causal commentary when the source supplies a complete numeric fact.
- Cross-publisher event identities compare actors, action, object, quantities,
  duration and stage. An unchanged statement is not new because its publisher,
  URL tracking parameters or query date changed. Changed terms and execution
  stages must not be suppressed by older coarse title/link keys.
- DRAM market share must retain its source, period and revenue/bit basis.
  CAPEX plans must retain their fiscal period and net/gross basis. A reporter's
  annual extrapolation is not company guidance. A project bill is not a tariff.
- A visible live radar item contains only the heading, `핵심`, and a clickable
  `출처`. Investment commentary, importance/status labels, duplicate query time,
  per-item `기준/시각`, `경로/섹터`, and the disclaimer must not return.
- `핵심` must preserve the article body's material actors, actions, amounts,
  rates, and next step in complete Korean sentences. It must not fall back to a
  50-character clipping or visible ellipsis.
- Every detected foreign-currency amount keeps the original amount and adds a
  same-run KRW estimate with FX source, rate timestamp, and query timestamp.
  When both the primary and fallback FX lookups fail, write
  `원화 환산 확인 불가` instead of omitting or estimating the conversion.
- A newly discovered defect must produce a durable regression check before the
  work is closed.
- Source access failures, delayed data, mismatches, and empty selections must be
  reported explicitly; they must not be rewritten as successful news delivery.
- Successful article-fetch cooldowns are versioned against the selection rules.
  After a rule change, a previously verified unsent candidate is fetched and
  checked once with fresh source evidence. This does not reuse earlier bodies,
  clear seen-state, bypass transport-failure backoff or force a Telegram send.
- An unsent article does not leave the retrieval queue merely because it
  scrolled out of a current RSS page. Resume its metadata within the normal age
  window, fetch a new verified body, require a real publication time and apply
  the same quality and seen checks. Already-sent unchanged links stay excluded.
- The 06:30 preopen digest must not be emptied by the real-time seen-state.
  It may reuse a qualifying overnight item once in the daily digest, then the
  successful digest send must refresh seen-state so later live polls stay quiet.
- Seen-state is lane-aware: a live-only item may appear once in the next 06:30
  digest, while 전날 장전판 항목 재송출 금지 remains a hard invariant.
- Cloudflare owns the 06:30 KST daily dispatch and must use a date-scoped KV
  lock. GitHub's delayed schedule is not an acceptable primary timer.
- Implementation and re-verification results must be reported together with
  exact pass or fail evidence.
