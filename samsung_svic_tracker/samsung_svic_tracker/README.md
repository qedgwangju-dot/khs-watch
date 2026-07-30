# 삼성전자 SVIC 82호·83호 상시 추적기

종료일 없이 공식 출처의 신규 문서만 탐지하고, SQLite 상태를 이어서 사용하며, 신규 알림 조건에 해당할 때만 알립니다. 수집기가 새 문서를 저장한 실행에서만 선택적으로 OpenAI Responses API 분석을 호출합니다.

## 동작 계약

- KST 06:00·12:00·18:00·23:00에 GitHub Actions가 실행됩니다.
- `last_success_at` 이후 자료를 우선 조회하고 문서 내용 해시로 재확인합니다.
- 문서와 알림 해시는 SQLite UNIQUE 제약으로 중복 차단합니다.
- 일부 수집기가 실패한 실행은 기존 행을 신규 사실로 만들지 않습니다.
- 출처별 연속 실패 횟수를 저장하고 정확히 3회째에만 오류 알림을 냅니다.
- 알림이 없으면 Markdown 알림 보고서도 만들지 않습니다.
- API 키는 GitHub Secrets 또는 로컬 `.env` 환경변수로만 제공합니다.

## 로컬 실행

```powershell
cd C:\dev\tips-yield-telegram-worker\samsung_svic_tracker
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:DART_API_KEY='...'
.\.venv\Scripts\python.exe main.py
```

오프라인 회귀 테스트:

```powershell
python -m unittest discover -s tests -v
python main.py --sample tests/fixtures/new_documents.json
```

선택 환경변수는 `.env.example`을 참고합니다. `ALERT_WEBHOOK_URL`이 없으면 신규 알림은 표준 출력으로만 기록됩니다. `OPENAI_API_KEY`가 없으면 분석 단계만 건너뛰며 수집·저장·중복 제거는 정상 동작합니다.

## GitHub Actions 영구 상태

워크플로는 `svic-tracker-state` 브랜치의 `samsung_svic_tracker/state`와 `outputs`를 복원한 뒤 실행하고 다시 커밋합니다. 최초 실행에는 빈 상태로 시작합니다. 저장소 Settings → Actions → General에서 Workflow permissions를 `Read and write permissions`로 설정하고 다음 Secrets를 등록합니다.

- 필수: `DART_API_KEY`
- 텔레그램: 기존 `TELEGRAM_BOT_TOKEN`, 비공개 SVIC 채널의 `SVIC_TELEGRAM_CHAT_ID`
- 선택: `OPENAI_API_KEY`, `ALERT_WEBHOOK_URL`

`SVIC_TELEGRAM_CHAT_ID`가 등록되면 SVIC 알림은 해당 채널에만
`🔎 [SVIC 82·83 신규 공식자료]` 머리말로 전송됩니다. 기존 뉴스의
`TELEGRAM_CHAT_ID`는 읽지 않으므로 기존 뉴스방과 섞이지 않습니다.

Actions 스케줄은 UTC 기준이며 `21:00, 03:00, 09:00, 14:00`이 각각 KST `06:00, 12:00, 18:00, 23:00`입니다. `concurrency`가 동시 DB 쓰기를 막습니다. 상태 브랜치를 삭제하면 이력이 초기화되므로 보호 규칙 적용을 권장합니다.

## 확정 기준

공식 문서에 `SVIC 82호` 또는 `SVIC 83호`가 명시된 경우만 해당 조합의 확정 투자로 분류합니다. 조합번호 없는 `Samsung Ventures` 투자, 단일 언론 보도, PoC, 인증, 양산, 매출은 서로 대체하지 않습니다.
