# 미 재무부·미 국채 알림 구조

목표: 같은 사건을 여러 감시기가 반복 설명하지 않고, **정책 → 실제 집행 → 실제 현금 이동 → 신규 국채 최종수요 → 시장 포지션 → 해외수요 → 금리 결과** 순으로 단계가 진전될 때만 알림을 보낸다.

## 1) QRA·발행계획
담당: `qra-recurring-telegram-alert.yml`
- 분기 차입계획, 이표채/FRN/Bill/CMB, TGA 목표, 향후 발행 가이던스
- 실제 경매 수요나 CTA 움직임은 여기서 반복 설명하지 않음

## 2) 바이백 정책
담당: `treasury-buyback-policy-telegram-alert.yml`
- 바이백 상한·만기구간·일정·공식 목적 변경
- 실제 매입 결과는 별도 집행 감시가 담당

## 3) 바이백 실제 집행
담당: `treasury-buyback-media-telegram-alert.yml`의 실행 전용 로직
- 총 제시액, 실제 매입액, 상한 소진율, 제시액/상한
- 언론 보도만으로는 알리지 않음

## 4) 신규 장기채 최종수요
담당: `treasury-auction-final-demand-telegram-alert.yml`
- 신규 10Y/20Y/30Y 공식 입찰 결과가 새로 나올 때만
- Bid-to-Cover, Indirect, Direct, Primary Dealer, SOMA
- 직전 및 최근 6회 평균과 비교
- Indirect를 해외수요와 동일시하지 않음
- WI tail/stop-through는 신뢰 가능한 WI 원자료가 있을 때만 표시

## 5) TGA·Bill·SOMA 순유동성
담당: `treasury-net-liquidity-telegram-alert.yml`
- 일별 TGA, 최근 Bill 순발행, Fed Treasury holdings, 은행 준비금, ON RRP
- 서로 다른 빈도의 숫자를 억지로 더해 가짜 정밀 '순유동성 총액'을 만들지 않음
- 유동성 레짐/임계값 변화가 있을 때만 알림
- 바이백 자체는 반복 설명하지 않고 결제 후 현금 이동만 확인

## 6) 해외 최종수요
담당: `treasury-foreign-demand-telegram-alert.yml`
- TIC 국가별 보유, 거래·평가 분해, Fed custody
- 당일 입찰 Indirect와 혼동하지 않음

## 7) CTA 숏 스퀴즈
담당: `treasury-cta-squeeze-telegram-alert.yml`
- 기사 하나나 금리 하락 하나로 알리지 않음
- CTA/DV01, CFTC, ZN/ZB/UB 가격·OI, z-score, repo가 복합 확인될 때만

## 8) 일반 금리 결과
담당: `global-rates-telegram-watch.yml` 및 기존 TIPS 단일 송신자
- 명목·실질금리 및 거시 결과
- 재무부 정책 설명을 중복하지 않음

## 공통 규칙
- 외화 금액은 FRED DEXKOUS 확인값으로 원화 병기. 확인 실패 시 임의 환산 금지.
- 확정 사실 / 보도 / 시나리오를 구분.
- 같은 사건은 단계가 진전될 때만 후속 알림.
- 원문 링크는 텔레그램에서 짧은 클릭형 링크로 표시.
