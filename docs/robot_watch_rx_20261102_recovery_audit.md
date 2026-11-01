# 로봇 감시 [로봇 6] 연속성·복구 감사 기록 (2026-11-02 KST)

## 복원 범위와 한계
- 사용자 제공 캡처 1장, GitHub main의 코드·커밋·중복 방지 상태, GitHub Actions 실행·작업 로그·발송 산출물로 확인한 내용이다.
- 이전 [로봇 6] 대화 본문 전체에는 접근하지 못했다. 따라서 전체 사용자 승인·취소 이력의 복원은 **불완전**하다. 과거 assistant의 완료 주장은 실제 실행 증거와 구분한다.

## 보존한 운영 구조
- 저장소: `qedgwangju-dot/khs-watch`, 브랜치: `main`.
- 워크플로: `.github/workflows/robotis-physical-ai-telegram-watch.yml` (변경하지 않음).
- 기존 예약: UTC 매시 11분과 41분; 동시 실행 시 이전 실행 취소 설정 유지.
- 실행: `scripts/physical_ai_watch_airan_guard.py`; 검증: `scripts/physical_ai_watch_regression_check.py`.
- 상태: `data/robotis_physical_ai_watch_state.json`. 과거 성공 중복 키 초기화·삭제 없음.
- 기존 Telegram bot/token·수신처는 GitHub secrets 참조를 그대로 유지했다. 수신처는 **숫자형 채팅 ID**이고 실제 숫자·토큰은 비공개다.
- `.github/robotis-physical-ai-trigger.txt`의 `force_summary=0` 및 `reactivate_khs_policy=0` 유지; 타 감시 재활성화·임의 수정 없음.

## 실제 10월 27일 누락 확인
- 머니투데이 2026-10-21 **방문 예정**과 연합뉴스·전자신문 2026-10-27 **방문 완료 보도**는 다른 사건이다.
- 연합뉴스 원문: https://www.yna.co.kr/view/AKR20261027124351003
- 전자신문: https://m.etnews.com/20261027000345
- 10/27 Actions `40488869508` 원본 발송 산출물에는 손가락 10개 대 Atlas 8개 비교가 포함되고 실제 RX 현장 방문은 빠져 있다.
- 해당 실행의 Telegram 응답 `message_id=288`, `289` 모두 실제 전송 성공·설정된 숫자형 수신처 확인·상태 저장 확인.
- 구 코드에서는 일반 언론의 방문 완료를 예정 단계 점수 0으로 낮춰 탈락시킬 수 있었다.
- `40467353596` (10/27) 및 `41326088761` (11/02) 등의 실패 실행은 회귀검증 단계에서 중단돼 원천 수집·Telegram 송출을 생략했다. 이 실패는 정상 무발송과 구분한다.

## 최소 수정 내역 — 기존 경로만
- `c84ea51df4370d69e736af6bb3ba5a39cc793fae`: 신뢰 언론 방문 완료 보도 `reported_visit_done` 신설·기존 삼성 공식 `official_visit_done`과 분리, 검색어 및 의미별 중복키 개선.
- `f7ffe8b64ab48688ca92f072a390204594469c3b`: '방문해 ... 점검할 계획'은 방문 완료로 승격하지 않도록 정규식 조정.
- `739ee5ab90b42675e4bce18e931de7d99e1a2a68`: 실제/예정/비신뢰 출처/공식 단계 및 중복 회귀검증 추가.
- 첫 무강제 확인 실행 `41344669683` 성공, Telegram `message_id=313`. 당시 일반 수집은 RX 누락 기사를 되찾지 못해 RX 송출은 안 됐다.
- `01b2fcba609932318860b5f6fd823f2a28238741`: 확인된 10/27 RX 방문을 **한 번만** 소급 포착할 수 있는 원문 기반 언론보도 등급의 임시 검색 대상 등록, 2026-11-05 이후 자동 종료.
- `ee0ad161e60ca2f79042268e6685b8be3fdb35b3`: 소급 대상의 확정 단계·중복키·기간 만료 회귀검증 추가.
- 운영 확인 트리거 `3f59e2b1b1a5c37c1b0987981119921fbb9e8605`: 강제요약·무관 정책 재활성화 모두 0.

## 최종 일곱 단계 — GitHub 실행 41345137462 / 2026-11-02 05:11 KST
1. 실제 코드 반영: **완료**, `scripts/physical_ai_watch_airan_guard.py` main blob SHA `54e7614fdc6076447cdf4bf996697241fe8231b8`.
2. main 커밋 반영: **완료**, 위 코드·회귀검증 두 커밋 및 확인 트리거.
3. 해당 커밋 Actions 실행: **완료**, 실행번호 844, ID `41345137462`, 최종 success.
4. Python 자료 수집·판정: **완료**, 전체 371/371 검색 성공·신규 알림 1건, 회귀검증 PASS; RX 완료 언론 보도.
5. Telegram API 실제 전송: **완료**, GitHub 로그 `Telegram sent: message_id=314` (2026-11-02 05:11:21 KST), 발송 파일의 해당 RX 단일 건 확인.
6. Telegram 수신처·메시지: **완료**, 응답 숫자형 `chat.id` 설정값 일치, `message_id=314`. **기기 알림 표시·수신자 열람은 미확인**.
7. 운영 상태 파일 갱신: **완료**, `data/robotis_physical_ai_watch_state.json` main blob SHA `56344806f4b5756513f63114128c9184330917d2`, seen=812. RX 키 `eb2946f457ef1c86b5938c6f02e4cbb2a20682a140d8971c7ceb1d0511c33a53` 및 기존 삼성 손 사건 키 유지.

## 후속 점검
- 소급 뉴스는 11/05 이후 신규 조회 대상에서 자동 제거된다. 이미 정상 발송된 사건은 성공 중복 키로 재발송 억제.
- GitHub 예약 지연·cancel-in-progress는 기존 설계상 남아 있고, 외부 소스 오류·기한부 회귀 테스트는 향후 별도 장애의 가능성이 있다. 새로운 실패 시 **회귀검증 → 실제 수집 → 후보 선별 → 발송 API → 상태 저장**을 로그로 구분.
- 채팅 원문 전체가 없으므로 모든 관련 감시의 사용자 승인·취소 이력을 완전 복원했다고 주장하지 않는다. 이 문서는 운영 실적을 대체하지 않으며, 향후 현재 main과 Actions 실제 기록을 반드시 재대조할 것.
