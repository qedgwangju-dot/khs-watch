# 글로벌 금리·엔캐리 Telegram 감시 설정

## GitHub Actions Secrets

Repository → Settings → Secrets and variables → Actions → New repository secret 에 아래 두 값을 등록한다.

- `GLOBAL_RATES_TELEGRAM_BOT_TOKEN`: 새 Telegram BotFather 토큰
- `GLOBAL_RATES_TELEGRAM_CHAT_ID`: 새 Telegram 대상 chat_id

토큰과 chat_id는 코드/커밋/Issue에 직접 적지 않는다.

## 테스트

Actions → `Global Rates & Yen Carry Telegram Watch` → Run workflow → `force_test` 체크 → Run workflow.

전송 성공 시 Actions 로그와 artifact에 `global_rates_watch_telegram_confirmed.json`이 생성된다.

## 자동 감시

15분마다 공식 소스를 재조회한다.

- 일본 재무성: JGB 2년·10년 공식 일일 금리
- 미국 재무부: 미국 국채 2년·10년·30년 공식 일일 금리
- Federal Reserve/FRED: USD/JPY 일일 환율

변화가 없으면 Telegram을 보내지 않는다. 새 임계값 진입/해제 때만 전송한다.

## 임계값

- 일본 10년 JGB: 3.00% 이상
- 미국 10년: 4.50%, 4.70%, 4.75% 이상
- 미국 30년: 5.00%, 5.30% 이상
- USD/JPY: 155 이하
- USD/JPY 일일 변화: -2% 이하
- 미·일 2년 금리차: 2.00%p 이하

## 해석 잠금

- 일본 10년 3.0%는 엔캐리 자동 청산선이나 BOJ 공식 방어선이 아니다. FY2026 일본 정부 예산의 국채 이자비용 계산 가정금리와 겹치는 재정 경계선으로 분류한다.
- 미국 10년 4.7%는 공식 TACO선이 아니다. 4.5% 및 미국 30년 5.0% 부근은 과거 시장이 주목한 경험적 고통구간으로만 취급한다.
- 엔캐리 청산은 JGB 3% 하나로 판정하지 않고 USD/JPY 급락과 미·일 단기금리차 축소가 같이 나타나는지 본다.

## 주의

공식 JGB 금리는 일본 시장 15시 마감 기준 값을 다음 영업일 09:30에 공표하므로 실시간 시세가 아니다. 미국 재무부와 FRED 값도 공식 일일 데이터다. 장중 임계값 즉시 알림이 필요하면 별도의 실시간 시장 데이터 소스를 추가해야 한다.
