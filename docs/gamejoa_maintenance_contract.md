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

- Actions 성공만으로 완료 처리하지 않는다.
- Headline, summary, source URL, and source body must describe the same event.
- A newly discovered defect must produce a durable regression check before the
  work is closed.
- Source access failures, delayed data, mismatches, and empty selections must be
  reported explicitly; they must not be rewritten as successful news delivery.
- The 06:30 preopen digest must not be emptied by the real-time seen-state.
  It may reuse a qualifying overnight item once in the daily digest, then the
  successful digest send must refresh seen-state so later live polls stay quiet.
- Seen-state is lane-aware: a live-only item may appear once in the next 06:30
  digest, while 전날 장전판 항목 재송출 금지 remains a hard invariant.
- Cloudflare owns the 06:30 KST daily dispatch and must use a date-scoped KV
  lock. GitHub's delayed schedule is not an acceptable primary timer.
- Implementation and re-verification results must be reported together with
  exact pass or fail evidence.
