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
- A policy maintenance push must not enable a user-paused workflow or dispatch a
  live Telegram send. Readability verification uses dry-run previews and leaves
  sent-event identities and policy-watch activation unchanged.
- Policy prose retains complete sourced actions, quantities, conditions and
  stages. Never crop at 50 characters and append a copula. Render concise cores
  followed by factual bullets, stage/date/timeline, scope caveats and clickable
  sources in a deterministic order. Label-based layout must not move a statement
  into a risk/company section because of incidental words. Oversized bundles
  split at article/field boundaries with all source content retained.
- Headline, summary, source URL, and source body must describe the same event.
- Verified Korean article titles and bodies are owned by the source-body layer.
  Legacy topic overlays must not replace them from background references. An
  incompatible thematic summary is re-extracted from the article and checked
  again; it is never published by bypassing source alignment. Related-story
  footers are not article evidence.
- Separately labelled leading AI commentary cards are not the reported event.
  Select the sourced issuer action, counterparty, amount, observation period and
  execution stage first. Concise radar cores allow up to 180 characters so an
  actual event is not displaced by a shorter background sentence. Inline KRW
  conversions and complete-prose/source-alignment guards still apply. Do not
  change legacy body receipts just because the summary input is cleaned.
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
- Source accuracy alone is not a publication-quality pass. The live radar is
  for domestic/international stock-market catalysts, not a quota of true business
  facts. A strategy overview cannot qualify solely through a long-term roadmap;
  a business-vision interview cannot qualify through a secondary listing detail;
  a generic call for investigation/damage prevention cannot republish its incident
  background without a new scoped regulatory or operational action. Keep concrete
  investment decisions, customer contracts, headline listing events, actual damage,
  emergency regulator meetings and enacted/proposed rule changes. Do not require
  an observed share-price response or a named Korean issuer before an early global
  rate, trade, energy or supply-chain catalyst can qualify. Publication limits are
  ceilings, never minimums to fill with lower-quality articles.
- A source headline consisting only of an issuer name is not a news event.
  Bank support MOUs need concrete size, financing terms or committed execution,
  not a platform-promotion paragraph. National export milestones prioritize the
  observed cumulative total and period over hypothetical required monthly sales.
- Institutional role/program series cannot qualify on an expansion subheading
  or a rationale for government intervention. Require a new scoped legal
  instrument, budget or procurement commitment; retain actual new instruments
  even when the source also describes the agency's existing mission.
- A technology/industrial trend sentence such as "verification activity is
  continuing" is not a concrete milestone without a measured result or a
  specific commitment. Weekly coverage is still eligible on a source-bound new
  commercial fact; its genre does not bypass the evidence requirement.
- Korean submission words cannot match shipments. Exhibition attendance cannot
  republish background CAPEX, and personal-finance instructions are not new
  market flows. Preserve scoped new construction and real shipment changes.
- Analyst FX outlooks retain the named source, target and horizon. Operating
  asset financing retains the asset, amount and proposed transfer structure;
  SPV discussions do not become completed chip sales or secured borrowing.
- Conditional factory tariffs retain the construction condition, cited rate
  and any source-provided grace period. A previous LNG statement cannot own
  that headline; a campaign statement does not become an enacted tariff rule.
  Cross-publisher receipts use the verified condition, rate and grace period,
  not a dated country-wide trade label. Changed terms remain separate.
  A generic campaign headline can share that identity only when the verified
  article lead binds the US investment context and its current direct quote.
  The core must retain the quoted terms, not a general investment boast.
  Background quotes and articles foregrounding other actions remain distinct.
- A contract paragraph beginning with "after launch" must retain its supplier
  from verified nearby product context. Do not publish an anonymous contract
  core or invent an issuer when the article has no explicit subject. Preserve
  the source customer and execution stage when adding that subject.
- A cyber incident headline must summarize the reported incident and current
  response, not background AI or network-separation policy. Bind disclosed
  record counts to the named institution and retain scheduled versus completed
  meetings. Prevention drills and defended attempts are not actual breaches;
  do not infer an institution from an anonymous or ambiguous count paragraph.
  Named multiple victims retain their separate populations and estimated versus
  confirmed counts. Loan-broker disclosures are not customer disclosures;
  uncertainty about AI use stays attributed to the affected institution.
- Semiconductor capacity outlooks retain the investment fiscal period and the
  separately attributed production-effect horizon. Market-breadth comparisons
  retain the index, constituent population and high/year-start comparison basis;
  a background Treasury yield cannot replace the headline's actual dispersion.
  Verified numeric index/constituent observations do not imply investor flows.
- A forum's agenda, keynote theme and discussion of expanding supply are not
  new rules or new capacity. A sourced new instrument or quantified committed
  budget remains eligible even when announced at a forum.
- An investment sum in a headline cannot hide exhibition attendance in the
  source lead. Existing project budgets in the exhibition's background are not
  a new investment announcement. Retain new executed construction or contracts
  when the headline or lead actually foregrounds that change.
- National export evidence must bind an observed current-period total. Historical
  milestone paragraphs and conditional amounts needed to meet a future target
  are not a current statistical release. Preserve the observed period and total
  in the core and check them again before delivery.
- Same-run KRW conversion annotations cannot change a source event's original
  foreign amount, observed period or stage, or make its correct core fail the
  headline gate. Explicit unresolved conversion annotations are not estimates.
- Compensation-cost earnings reports retain the CFO's company, fiscal quarter,
  combined cost components, additional cost forecast and profitability outlook.
  A combined bonus/startup cost is not a bonus-only amount. Repeated page heading
  and subheading blocks are not source economic-change evidence.
- A financial-company interview retains its named speaker, scoped business
  statement, regulatory preconditions and first-trade date when actually sourced.
  Digital-asset treasury business is not a US Treasury macro release. A listed
  company description is not a new price/flow event, and a SPAC route overview is
  not fresh financing. First-trade plans remain plans, not completed trading.
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
- Unmodelled events additionally store verified source-action aliases. Suppress
  a shorter cross-publisher copy only when all its material facts were sent;
  matching one shared fact must not hide a new amount, party, period, budget or
  execution stage. Keep legacy exact URL/title receipts and preopen/live lane
  semantics, and record aliases only after acknowledged delivery. Do not use
  collector timestamps, industry keywords or broad fuzzy title similarity as
  proof of a new or duplicate event.
- A possible future CEO visit/meeting cannot qualify through either discussion
  or incidental supply/technology rules. Preserve actual named ongoing supply
  negotiations and confirmed contracts. Columns, consumer accessory launches,
  training plans and strategy case studies need a foreground new sourced
  execution or quantified economic change, not old CAPEX or background demand.
- A regulatory expansion core retains its scheduled selection date, eligibility
  and maximum scope; background breach counts cannot replace the policy change.
  A president's supply instruction is not completed housing purchases. Keep
  other concrete housing rules and actual cyber incidents independently eligible.
- Every supplied article is included in the regression audit: raw article count,
  unique linked articles, unique events, per-article disposition/reason and core
  checks. The October 5 ten-article replay runs in production CI before sending;
  it is a test corpus, never a live alert injection or a seen-state reset.
- A flow core preserves the investor population, named securities, observation
  period and separate amounts. It cannot substitute whole-market foreign-plus-
  institutional turnover for a foreign investor's net sales of two issuers.
  Routine retail foreign-stock popularity rankings need a new direct business
  or policy change to qualify; an old company fact is not that change.
- A technical standard core retains its issuing organization, standard code,
  publication stage and scope. Capacity words such as `고용량` are not employment
  data. An import-share observation retains its cumulative period and decimal
  comparison, not merely a headline's threshold crossing.
- A single-quarter operating result cannot be replaced by a year-to-date
  quarter range. Preserve the issuer, delivery-versus-accounting basis and
  actual quantity/growth. A minimum-lot trading exception retains its lot size,
  disposal mechanism, proposal stage and announcement plan instead of quoting
  an existing product's unit price or generic investability.
- A selection-rule upgrade or known URL tracking parameter is not a new event.
  Successful delivery receipts retain a classification-independent digest of
  the verified article body, excluding rotating recommendation sections. A
  changed sourced amount, counterparty, period or new fact remains eligible.
  Old fact receipts without a body digest conservatively protect the same
  canonical source URL; they cannot prove that an in-place revision is new.
  A new follow-up source URL is not blocked by that legacy fallback alone.
- Named exclusive-license copies compare issuer, counterparty, candidate asset,
  geographic scope, signed stage, upfront payment and conditional milestones.
  Korean money-unit spellings must parse exactly, not by fuzzy title matching.
  A new amount, asset, scope, royalty rate or cash-runway year remains new.
  Single-stock leveraged-product odd-lot rules normalize shares/units only for
  that regulatory action and retain minimum lot, disposal mode, review/confirmed
  stage and any explicit disposal date. Do not use another policy action's date.
  Historical event aliases require a matching existing successful receipt plus
  audited full-body hash, publication time, run ID and Telegram message ID.
- A maritime-attack headline must lead with reported attacks or actual shipping
  disruption and its attribution/observation window, not hypothetical oil-price
  effects. A notice date is not an undisclosed incident-occurrence date.
- A production-target decision leads with the acting producer group, affected
  month and decision, not earlier oil-price or stockpile background. A facility
  approval leads with regulator, product, facility, supply scope and any sourced
  capacity change, not an analyst's unrelated annual revenue forecast.
- An issuer's NAV estimate retains its observation date, comparison date,
  forecast status and unaudited limitation. A weekly outlook may qualify through
  a source-bound quantitative consensus revision, but company-name overlap and
  generic optimism cannot substitute for that revision. Broker consensus is not
  company guidance. A historical unlisted-business survey and policy advice need
  new execution to qualify.
- Acquisition-agreement synopsis and full-report copies compare sourced buyer,
  target, currency, complete original consideration amount and announced stage.
  Preserve explicit revised terms as new facts. Do not split dotted issuer names
  into sentences or treat negotiations as signed agreements. Receipt migration
  uses only audited already-sent articles, never a theme-wide suppression list.
- Buyer- and target-perspective reports of the same acquisition use one event
  identity. Total deal consideration must not be replaced by a per-share price
  merely because the per-share amount appears first in the source lead.
- Consumer fashion publicity, municipal student-welfare notices and startup
  profiles without new execution are not equity catalysts. Actual issuer
  earnings, signed supply contracts, factory permits and quantified customer
  validation remain eligible under the source guards. Productivity services
  are not industrial production capacity; reused commercialization history is
  not a newly validated cooling technology.
- Copies of the same broker earnings report compare the sourced broker,
  complete issuer name, report date, fiscal year/quarter, revenue/profit
  forecasts, annual forecasts and current target price. Changed amounts,
  periods, broker, issuer or explicit corrections remain distinct. Abbreviated
  company titles must not identify a generic word such as growth as the issuer.
  A source-stated fiscal year is not replaced by its publication year; an
  unknown year stays unknown. Summaries name the broker and retain forecast
  status instead of promoting estimates into company-reported results.
- An explicit primary analyst target-price change outranks a subsidiary
  forecast or generic revenue outlook. A primary reported-period earnings
  headline is not overridden by a secondary target-price mention. Name the broker and issuer,
  preserve both previous and current target prices, and keep it an analyst
  revision rather than company guidance. Identical dated broker revisions
  across publishers share an event; changed targets or brokers do not. Foreign
  target revisions retain their sourced original currency before FX display.
- Signed industrial cooperation summaries retain counterparties and actual
  study scope. A joint route/feasibility MOU is not a vessel order, regulatory
  approval or operating launch. A possible future signing is not a signed MOU.
- Same signed route studies compare issuer, partner, technology, vessel, route,
  announcement date, stated amounts and revisions across headline variants.
  Existing successful receipts must be present before historical aliases apply.
- Quantity-based data-center supply summaries retain the contract counterparty,
  project capacity and supply stage. Historical half-year order totals must not
  replace the newly reported agreement, and discussions are not booked orders.
- Small service promotions and student rental notices are not equity catalysts
  merely because they say supply, policy, production or nationwide. Separate
  verified industrial contracts and national housing underwriting stay eligible.
- Disclosed equipment orders compare issuer, customer, product, disclosure
  date, exact original amount, period and explicit revisions. Never merge
  different amounts using a general rounding tolerance. Rounded historical
  copies require an individually audited full-source/successful-receipt alias.
- A six-digit stock code after an issuer or customer does not create a new
  equipment order. Conditional index reports compare broker, report date,
  threshold, target range and stated conditions; they are forecasts, not closes.
- A tiny cryptocurrency spot recap, municipal robot demonstration, vendor
  self-test without measured external validation, retail menu publicity and
  existing-policy explanation are not new equity catalysts. Actual measured
  industry changes, new customer contracts and formal policy actions survive.
- Quantified intraday stock summaries retain each issuer, quote time, price,
  percentage and previous-session basis. Computer-equipment investment is not
  relabelled as all AI CAPEX. Shipping summaries keep maximum per-voyage costs
  separate from daily charter rates, with source attribution and period.
- The issuer may precede or follow the quote time. An omitted subject requires
  an explicit stock code and trading day in the adjacent lead. Do not replace
  the current quote with a session high or the previous day's contract.
- Modest intraday ticks share an event only within the same issuer, sourced
  trading date, direction and five-percentage-point magnitude band. A new day,
  reversal, larger band, primary contract or target revision remains distinct.
- Individual consumer SKU sales or a single-store ranking, historical franchise
  surveys/project inventories, retrospective deal rankings, routine retail
  fund launches and automated stock streaks are not new equity catalysts.
  Company financial results, current national observations, new capital flows
  and formal execution announcements remain eligible.
- Housing demand summaries retain the provider, release day, original
  announcement window, national first-priority population and same-period
  comparison. A local 100-to-1 outcome is not the national competition ratio.
- Deployment agreements/plans are not completed deployments. Keep announced
  support and undisclosed force/mission scope separate. Contracted electrical
  capacity is not operating capacity; preserve approval, build schedule and
  conditional supply year instead of dropping them to fit the summary limit.
- A model-specific industrial delivery shares an event only when the source
  supplier, customer, named model, product and announcement date agree. New
  model/customer/product/date or revised delivery terms must survive dedupe.
- Marketing agreements retain their end year and maximum forecast volume.
  Earlier sample shipments or sales do not replace the current agreement;
  marketing volumes are not automatically guaranteed purchase orders.
- Airline capacity changes retain the effective day, routes and before/after
  frequencies. A generic sentence about expanding supply is insufficient.
- Unquantified single-campus software deployments, used-equipment distribution
  frameworks and prior-week ETF return tables are not publication priorities.
  Quantified signed orders and genuine new fund flows remain eligible.
- Annual crypto adoption/transaction-size surveys without an equity catalyst,
  national-hearing repetitions of prior policy plans, and local farming grants
  without business procurement or a supply shock are not publication priorities.
  New ETF flows, regulatory instruments, company orders and climate-related
  operational losses remain eligible.
- A national research-project award must not be relabelled as company revenue.
  Keep the whole-project R&D budget, government share and actual selection
  stage separate. A signed supply order must not absorb a future expansion
  target as its current contract amount.
- Equipment-adoption summaries retain the current product, production site
  and the stage stated by their own source. Do not replace these with supplier
  profiles, old customer references or planned factory output. Anonymous
  customers are not merged by sector alone; exact full-body receipt evidence
  may reconcile audited copies of one announcement, not later changed terms.
- Public deliberation polls are not employment statistics or enacted policy.
  Actual nonfarm jobs retain their reported period, amount and forecast basis.
  Hearing repetitions of prior roadmaps require new committed terms to qualify.
- Smart-office MOU partner roles are not actual customer orders. Historical
  outage-budget audits are not current supply disruptions; current physical
  outages and losses remain eligible.
- Broker backlog summaries retain the broker, issuer, observation period,
  business, backlog amount and regional share. Peer margin estimates do not
  replace the issuer's current backlog or become reported company earnings.
- Signed development MOUs compare source parties, development purpose,
  disclosure day and revision terms. They are not commercial orders or
  completed production. Different purposes, parties and dates stay distinct.
- R&D-award headline variants retain the same project identity only when the
  issuer, tasks, count, total budget, government share and disclosure date
  agree. An operational-development headline is not a new award by itself.
- Construction summaries retain the client, work package, total project cost,
  issuer's share and duration. National R&D participation retains the whole
  program, public share, subproject budget, participant role and end year;
  none of these budgets becomes the participant's standalone revenue.
- Interviews reinterpreting previously announced clinical results do not
  become fresh trial releases. Newly released results, approvals, licensing
  contracts and actual trial-stage changes remain eligible.
- Public compute allocation summaries name the data provider and original
  application round, requested/allocated units and denominator. Different
  application rounds are not combined and an advocate's request for increased
  spending is not a committed new budget.
- Shareholding summaries retain owner, issuer, previous/current share counts
  and stake percentages. A prior purchase is not the new disclosed change.
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
- A quoted award name, reporter name, or an English model translation is not
  a new customer/model. Model-specific supply announcements are compared by
  supplier, customer, Korean model name, product, disclosed date and stage.
  A separately dated completion or revised order must remain a new event.
- Anonymous orders need matching supplier, customer label/region/industry,
  equipment, end markets, actual contract amount status, expansion target,
  announcement date and stage before being equated. A label such as A alone
  is insufficient, and an expansion target is not the signed order amount.
- New bill summaries must retain the introducing actor, actual bill and
  introduced/submitted/passed stage. Earlier speeches cannot stand in for
  the new clauses. Regulatory implementation dates must remain in the core.
- National-hearing aspirations without a new instrument or committed terms,
  and precommercial validation MOUs without market execution, are not primary
  radar items. New budget revisions, customer contracts, measured independent
  validation and actual commercial deployment must still be evaluated.
- Construction reprints require the same issuer, client, named work package,
  exact project budget, company share, duration and disclosure date. Korean
  numeric spelling is normalized, but nearby rounded values are never merged.
  New lots, terms, counterparties or execution stages remain distinct.
- Regulation packages compare the named measure, affected import item,
  instrument, planned/issued stage, implementation dates and restricted PPA or
  trade-secret scope. A shared word such as regulation is not an event identity.
- Political approval polls must not qualify through old inflation, energy or
  campaign-payout context. Current policy execution and real economic data
  remain eligible through their own source-authored, foreground evidence.
- Industrial model announcements must retain the new model, quantified claims
  and separate completed versus pending certification. Vendor performance
  claims are attributed, not upgraded to independent validation. Cost-sharing
  policy reviews retain who pays, eligible supply horizon and current deadline.
- Clinical pre-submission recommendations retain material failed endpoints
  and are not regulatory approval or successful phase-three efficacy results.
- Photo captions can share a DOM row with the first news sentence. Strip only
  the credited caption boundary and preserve the following article text.
- Named bills compare actor, law, submission date and actual stage across
  publishers. Capacity supply contracts compare issuer, named customer, product,
  region, exact quantity, disclosure date and signed versus discussion scope.
  Whole-body audited historical receipts may equate specific reprints, but an
  unproved title, changed body or changed terms must not inherit that alias.
- Quantified volume cores retain period, population, reported growth and a
  material regional decline. Vessel delivery retains partial adoption and
  attributes capacity claims. CMBS special management is not delinquency.
- Scholarly policy advice without new legislative, budgetary or implementation
  action is not a primary radar item. Actual current bill execution is checked
  independently rather than excluded by a discussion-oriented title.
- A historical shared SNS statement is not current selling-price or earnings
  evidence. A popup exceeding its own sales target is not issuer earnings.
  New disclosed investment, earnings or binding commercial terms remain eligible.
- Split filing fields retain named counterparty, exact amount, contract period
  and revenue share. Rounded nearby amounts cannot create automatic equivalence.
  Contract amount and cumulative LTA bookings are different quantities.
  The cumulative start period must come from the source, never a fixed month.
- Data-center policy cores prefer verified stop orders and permitting reasons
  over generic expert commentary. Trial-result cores retain duration, comparator
  and reported measurements without claiming approval or inferring medical units.
- Executive visits need current sourced business execution or scoped discussions;
  old MOUs plus curiosity about future cooperation are not a new contract event.
  Embedded interrogatives such as whether cooperation will widen do not prove
  execution, while an actual current signed contract remains separately eligible.
- Hearing responsibility disputes and apologies are not new market instruments.
  Real new deposit/trading rules, budgets and execution terms must remain eligible.
  Conditional payment plans retain legal prerequisites and unresolved recovery;
  energy work-plan targets are not installed capacity or already enacted budgets.
- MLCC reprints compare issuer, customer, disclosure date, exact reported amount,
  revenue share and annual term. Source-hash and successful-receipt proof may
  upgrade an existing matching receipt only. Nearby rounded values never create
  automatic equivalence; changed terms and additional execution remain distinct.
  Reporter-footer recommendations cannot become current contract execution.
- A signed tax-scope executive order is summarized by its instrument and affected
  use, not generic war or price background. Project cash remittance is distinct
  from a still-unexecuted power purchase contract or conditional later payment.
- Headline sales milestones retain issuer, population and cumulative period.
  Industry monthly releases using three-month moving averages retain that basis;
  they are not single-month sales. Contract disclosures keep term and revenue share.
  Multiple reporter names are removed without removing the source actor.
- Regional hearing advocacy about an existing investment plan is not a new CAPEX
  commitment. Current sourced budget confirmation or implementation is separate.
