#!/usr/bin/env python3
"""K-defense overlay for the GAMEJOA preopen news radar."""

from __future__ import annotations

import gamejoa_preopen_news_radar_full_compact_runner as runner


base = runner.base
contract = runner.contract
telegram = runner.telegram

K_DEFENSE_DART_CODES = {"012450", "079550", "047810", "064350", "272210"}
K_DEFENSE_SECTOR = "K-방산/항공우주"
K_DEFENSE_CHECK = "계약금액·기간·상대국/상대방·공시 여부·양산/인도 일정·수출허가 확인"
K_DEFENSE_COMMON_RISK = "트럼프 행정부 압박: 방위비 분담금 증액·주한미군 재조정은 전 종목 지정학/할인율 리스크"
K_DEFENSE_POLAND_RISK = "단일 고객 의존도: 폴란드향 수출 50%+ 노출 여부와 정권 교체·예산 재검토는 현대로템·한화에어로 수주잔고 리스크"
K_DEFENSE_CONTRACT_DELAY_RISK = "수주 계약 지연: 폴란드·사우디 대형 계약이 정치적 사유로 지연되면 현대로템·LIG넥스원 단기 주가 조정 리스크"
K_DEFENSE_SIGNING_CATALYST = "분수령: 사우디 천궁Ⅱ 또는 K2 폴란드 2차 계약이 실제 서명으로 이어지면 수주 가시성 재평가"
K_DEFENSE_DRONE_SECTOR = "K-방산/대드론·무인기"
K_DEFENSE_DRONE_CHECK = "탐지 레이더·지휘통제·무인기 플랫폼·레이저/HPM 중 어느 층위가 시험평가·도입 언어로 넘어갔는지 확인"
K_DEFENSE_DRONE_COUNTER = "KADIZ 진입은 지정학성 경보일 수 있고, KS 제정·정부 구상이 예산·시험평가·조달 일정·기업별 역할로 연결되지 않으면 테마성 반응에 그칠 수 있습니다."
K_DEFENSE_COMPANY_TERMS = [
    "hanwha aerospace", "한화에어로스페이스",
    "lig nex1", "lig넥스원", "lig 넥스원",
    "korea aerospace industries", "한국항공우주", "kai",
    "hyundai rotem", "현대로템",
    "hanwha systems", "한화시스템",
]
K_DEFENSE_SYSTEM_TERMS = [
    "k9", "k9 thunder", "k9 자주포", "chunmoo", "천무", "redback", "레드백",
    "cheongung", "cheongung ii", "km-sam", "천궁", "천궁Ⅱ", "천궁ii", "천궁2",
    "hyungung", "현궁", "guided missile", "유도무기", "fa-50", "kf-21",
    "surion", "수리온", "k2 tank", "k2 전차", "wheeled armored vehicle",
    "차륜형장갑차", "radar", "레이더", "satellite", "위성", "electronic warfare", "전자전",
]
K_DEFENSE_EVENT_TERMS = [
    "arms export", "contract", "defense contract", "defense order", "delivery",
    "export", "loi", "mass production", "mou", "order", "procurement",
    "selected", "supply agreement", "tender", "wins",
    "계약", "공급계약", "도입", "무기체계", "방산", "수주", "수출", "양산",
    "유도무기", "입찰", "전력화", "조달", "체결",
]
K_DEFENSE_KOREA_RISK_TERMS = [
    "burden sharing", "defense cost sharing", "special measures agreement", "sma",
    "troop realignment", "u.s. forces korea", "usfk",
    "방위비 분담금", "방위비분담금", "주한미군", "미군 재조정", "한미 방위비",
]
K_DEFENSE_POLAND_RISK_TERMS = [
    "poland", "polish", "폴란드", "government change", "election", "defense budget",
    "budget review", "cancel", "delay", "renegotiate", "정권 교체", "예산", "재검토", "취소", "지연",
]
K_DEFENSE_POLAND_STRESS_TERMS = [
    "government change", "election", "defense budget", "budget review", "cancel",
    "delay", "renegotiate", "정권 교체", "예산", "재검토", "취소", "지연",
]
K_DEFENSE_DELAY_MARKET_TERMS = [
    "poland", "polish", "폴란드", "saudi", "saudi arabia", "사우디", "사우디아라비아",
]
K_DEFENSE_DELAY_STRESS_TERMS = [
    "approval", "budget", "contract delay", "delay", "delayed",
    "negotiation", "political", "politically", "postpone", "postponed", "review",
    "승인", "예산", "계약 지연", "본계약", "협상", "정치", "정치적", "지연", "연기", "재검토",
]
K_DEFENSE_DELAY_HARD_TERMS = [
    "contract delay", "delay", "delayed", "political", "politically", "postpone",
    "postponed", "review", "계약 지연", "정치", "정치적", "지연", "연기", "재검토",
]
K_DEFENSE_DELAY_EXPOSURE_TERMS = [
    "hyundai rotem", "현대로템", "k2 tank", "k2 전차", "wheeled armored vehicle", "차륜형장갑차",
    "lig nex1", "lig넥스원", "lig 넥스원", "cheongung", "cheongung ii", "km-sam",
    "천궁", "천궁Ⅱ", "천궁2", "hyungung", "현궁", "guided missile", "유도무기",
]
K_DEFENSE_SIGNING_MARKET_TERMS = [
    "saudi", "saudi arabia", "사우디", "사우디아라비아", "poland", "polish", "폴란드",
]
K_DEFENSE_SIGNING_TERMS = [
    "contract signed", "contract signing", "final contract", "second contract", "signed",
    "signs", "2nd contract", "actual signing",
    "계약 서명", "실제 서명", "본계약 체결", "최종 계약", "2차 계약", "서명", "체결",
]
K_DEFENSE_SIGNING_EXPOSURE_TERMS = [
    "cheongung", "cheongung ii", "km-sam", "천궁", "천궁Ⅱ", "천궁2",
    "k2 tank", "k2 전차", "hyundai rotem", "현대로템", "lig nex1", "lig넥스원", "lig 넥스원",
]
K_DEFENSE_DRONE_AIRSPACE_TERMS = [
    "kadiz", "k-adiz", "korea air defense identification zone",
    "air defense identification zone", "방공식별구역", "카디즈",
]
K_DEFENSE_DRONE_SYSTEM_TERMS = [
    "anti-drone", "counter drone", "counter-drone", "counter-uas", "c-uas", "cuas",
    "drone", "drone defense", "uas", "uav", "unmanned aerial vehicle",
    "대드론", "드론", "무인기", "무인항공기", "드론 대응",
    "low altitude", "low-altitude", "small target", "저고도", "소형 표적", "소형표적",
    "radar", "레이더", "command and control", "c2", "지휘통제",
    "ai swarm", "swarm", "swarming", "군집", "군집체계",
    "laser", "directed energy", "high-power microwave", "hpm", "microwave",
    "레이저", "고출력 마이크로파", "마이크로파",
]
K_DEFENSE_DRONE_CATALYST_TERMS = [
    "acquisition", "adoption", "evaluation", "kats", "korean agency for technology and standards",
    "korean standard", "ks", "procurement", "program", "standard", "standardization",
    "test", "testing", "국가기술표준원", "규격", "도입", "방위사업청", "성능시험",
    "시험", "시험평가", "정부", "제정", "조달", "표준", "표준화", "평가",
    "low cost", "low-cost", "mass drone", "mass-produced", "cheap drone",
    "저가", "대량", "대량 드론",
]
K_DEFENSE_QUERIES = [
    (
        "K-방산 수출/수주",
        "Hanwha Aerospace K9 Thunder Chunmoo Redback LIG Nex1 Cheongung II KM-SAM Hyungung KAI FA-50 KF-21 Surion Hyundai Rotem K2 tank Hanwha Systems radar satellite electronic warfare defense contract order export Reuters Bloomberg Yonhap DART",
    ),
    (
        "K-방산 무기체계",
        "한화에어로스페이스 K9 자주포 천무 레드백 LIG넥스원 천궁Ⅱ 현궁 유도무기 한국항공우주 FA-50 KF-21 수리온 현대로템 K2 전차 차륜형장갑차 한화시스템 레이더 위성 전자전 수주 계약 수출 공시",
    ),
    (
        "K-방산 한반도 리스크",
        "Trump South Korea defense cost sharing burden sharing USFK troop realignment special measures agreement Reuters Bloomberg Yonhap",
    ),
    (
        "K-방산 폴란드 의존도",
        "Poland Korean defense imports K9 Chunmoo K2 Hanwha Aerospace Hyundai Rotem government change election defense budget review Reuters Bloomberg Yonhap",
    ),
    (
        "K-방산 대형계약 지연",
        "Poland Saudi Arabia Korean defense contract delay political approval budget Hyundai Rotem K2 LIG Nex1 Cheongung II KM-SAM Reuters Bloomberg Yonhap",
    ),
    (
        "K-방산 분수령 계약서명",
        "Saudi Arabia Cheongung II KM-SAM final contract signed LIG Nex1 Poland second contract K2 tank Hyundai Rotem actual signing Reuters Bloomberg Yonhap",
    ),
    (
        "K-방산 대드론/무인기 체계",
        "KADIZ counter drone counter-UAS anti-drone low altitude small target radar command control UAV unmanned aerial vehicle AI swarm laser high-power microwave HPM Korean Standard KS procurement Reuters Yonhap DAPA KATS",
    ),
]


def append_unique(seq: list, values: list) -> None:
    for value in values:
        if value not in seq:
            seq.append(value)


def has_any(text: str, terms: list[str]) -> bool:
    return any(base.has(text, term) for term in terms)


def has_drone_air_defense_watch(text: str) -> bool:
    has_airspace = has_any(text, K_DEFENSE_DRONE_AIRSPACE_TERMS)
    has_system = has_any(text, K_DEFENSE_DRONE_SYSTEM_TERMS)
    has_catalyst = has_any(text, K_DEFENSE_DRONE_CATALYST_TERMS)
    has_layered_program = has_any(text, ["low cost", "low-cost", "cheap drone", "mass drone", "저가", "대량"]) and has_any(text, ["swarm", "군집", "laser", "hpm", "microwave", "레이저", "마이크로파"])
    return (has_airspace and has_system) or (has_system and has_catalyst) or has_layered_program


def k_defense_title(text: str) -> str:
    if has_drone_air_defense_watch(text):
        return "KADIZ·대드론 체계: 저고도 표적 감시/즉응·KS 시험평가 전환 체크"
    if has_any(text, K_DEFENSE_KOREA_RISK_TERMS):
        return "트럼프 행정부 방위비·주한미군 압박 리스크 체크"
    if has_any(text, K_DEFENSE_SIGNING_MARKET_TERMS) and has_any(text, K_DEFENSE_SIGNING_TERMS) and has_any(text, K_DEFENSE_SIGNING_EXPOSURE_TERMS):
        return "사우디 천궁Ⅱ·K2 폴란드 2차 계약 실제 서명 분수령 체크"
    if has_any(text, K_DEFENSE_DELAY_MARKET_TERMS) and has_any(text, K_DEFENSE_DELAY_HARD_TERMS) and has_any(text, K_DEFENSE_DELAY_EXPOSURE_TERMS):
        return "폴란드·사우디 K-방산 대형계약 지연 리스크 체크"
    if has_any(text, ["poland", "polish", "폴란드"]) and has_any(text, K_DEFENSE_POLAND_STRESS_TERMS) and has_any(text, ["hanwha aerospace", "한화에어로스페이스", "hyundai rotem", "현대로템", "k9", "chunmoo", "천무", "k2 tank", "k2 전차"]):
        return "폴란드 K-방산 의존도·정권 교체 리스크 체크"
    if has_any(text, ["hanwha aerospace", "한화에어로스페이스", "k9", "k9 thunder", "k9 자주포", "chunmoo", "천무", "redback", "레드백"]):
        return "한화에어로스페이스 K9·천무·레드백 수출/수주 체크"
    if has_any(text, ["lig nex1", "lig넥스원", "lig 넥스원", "cheongung", "cheongung ii", "km-sam", "천궁", "천궁Ⅱ", "천궁2", "hyungung", "현궁", "guided missile", "유도무기"]):
        return "LIG넥스원 천궁Ⅱ·현궁·유도무기 수출/수주 체크"
    if has_any(text, ["korea aerospace industries", "한국항공우주", "kai", "fa-50", "kf-21", "surion", "수리온"]):
        return "한국항공우주 FA-50·KF-21·수리온 수출/수주 체크"
    if has_any(text, ["hyundai rotem", "현대로템", "k2 tank", "k2 전차", "wheeled armored vehicle", "차륜형장갑차"]):
        return "현대로템 K2 전차·차륜형장갑차 수출/수주 체크"
    if has_any(text, ["hanwha systems", "한화시스템", "radar", "레이더", "satellite", "위성", "electronic warfare", "전자전"]):
        return "한화시스템 레이더·위성·전자전 수주/정책 체크"
    return "K-방산 무기체계 수출/수주 체크"


def k_defense_risk_check(text: str) -> str:
    risks = [K_DEFENSE_COMMON_RISK]
    has_poland_exposure = has_any(
        text,
        ["poland", "polish", "폴란드", "hanwha aerospace", "한화에어로스페이스", "hyundai rotem", "현대로템", "k9", "chunmoo", "천무", "redback", "레드백", "k2 tank", "k2 전차"],
    )
    if has_poland_exposure:
        risks.append(K_DEFENSE_POLAND_RISK)
    has_delay_exposure = has_any(text, K_DEFENSE_DELAY_MARKET_TERMS) and has_any(text, K_DEFENSE_DELAY_HARD_TERMS) and has_any(text, K_DEFENSE_DELAY_EXPOSURE_TERMS)
    if has_delay_exposure:
        risks.append(K_DEFENSE_CONTRACT_DELAY_RISK)
    has_signing_exposure = has_any(text, K_DEFENSE_SIGNING_MARKET_TERMS) and has_any(text, K_DEFENSE_SIGNING_TERMS) and has_any(text, K_DEFENSE_SIGNING_EXPOSURE_TERMS)
    if has_signing_exposure:
        risks.append(K_DEFENSE_SIGNING_CATALYST)
    return " / ".join(risks)


def enforce_k_defense_watch() -> None:
    append_unique(base.QUERIES, K_DEFENSE_QUERIES)
    append_unique(
        base.TERMS,
        K_DEFENSE_COMPANY_TERMS
        + K_DEFENSE_SYSTEM_TERMS
        + K_DEFENSE_EVENT_TERMS
        + K_DEFENSE_KOREA_RISK_TERMS
        + K_DEFENSE_POLAND_RISK_TERMS
        + K_DEFENSE_DELAY_MARKET_TERMS
        + K_DEFENSE_DELAY_STRESS_TERMS
        + K_DEFENSE_DELAY_HARD_TERMS
        + K_DEFENSE_DELAY_EXPOSURE_TERMS
        + K_DEFENSE_SIGNING_MARKET_TERMS
        + K_DEFENSE_SIGNING_TERMS
        + K_DEFENSE_SIGNING_EXPOSURE_TERMS
        + K_DEFENSE_DRONE_AIRSPACE_TERMS
        + K_DEFENSE_DRONE_SYSTEM_TERMS
        + K_DEFENSE_DRONE_CATALYST_TERMS,
    )
    append_unique(base.TRUSTED, ["yonhap", "yna", "korea herald", "korea joongang daily", "opendart", "dart", "dapa", "mnd", "kats"])
    if hasattr(base, "DART_WATCH_STOCK_CODES"):
        base.DART_WATCH_STOCK_CODES.update(K_DEFENSE_DART_CODES)
    if not any(label == K_DEFENSE_SECTOR for label, _ in base.SECTORS):
        base.SECTORS.append((K_DEFENSE_SECTOR, K_DEFENSE_COMPANY_TERMS + K_DEFENSE_SYSTEM_TERMS))
    if not any(label == K_DEFENSE_DRONE_SECTOR for label, _ in base.SECTORS):
        base.SECTORS.append((K_DEFENSE_DRONE_SECTOR, K_DEFENSE_DRONE_AIRSPACE_TERMS + K_DEFENSE_DRONE_SYSTEM_TERMS + K_DEFENSE_DRONE_CATALYST_TERMS))

    original_classify = contract.strict.classify

    def classify(row: dict, now):
        text = base.norm(f"{row.get('title')} {row.get('summary')} {row.get('publisher')} {row.get('source')}")
        has_k_defense = has_any(text, K_DEFENSE_COMPANY_TERMS + K_DEFENSE_SYSTEM_TERMS)
        has_event = has_any(text, K_DEFENSE_EVENT_TERMS)
        has_drone_watch = has_drone_air_defense_watch(text)
        has_korea_risk = has_any(text, K_DEFENSE_KOREA_RISK_TERMS)
        has_poland_risk = has_any(text, ["poland", "polish", "폴란드"]) and has_any(text, K_DEFENSE_POLAND_STRESS_TERMS) and has_any(text, ["hanwha aerospace", "한화에어로스페이스", "hyundai rotem", "현대로템", "k9", "chunmoo", "천무", "k2 tank", "k2 전차"])
        has_signing_catalyst = has_any(text, K_DEFENSE_SIGNING_MARKET_TERMS) and has_any(text, K_DEFENSE_SIGNING_TERMS) and has_any(text, K_DEFENSE_SIGNING_EXPOSURE_TERMS)
        has_contract_delay_risk = has_any(text, K_DEFENSE_DELAY_MARKET_TERMS) and has_any(text, K_DEFENSE_DELAY_HARD_TERMS) and has_any(text, K_DEFENSE_DELAY_EXPOSURE_TERMS)
        alert = original_classify(row, now)
        if not (has_k_defense or has_drone_watch or has_korea_risk or has_poland_risk or has_signing_catalyst or has_contract_delay_risk) or (not has_event and not has_drone_watch and not has_korea_risk and not has_poland_risk and not has_signing_catalyst and not has_contract_delay_risk and not alert):
            return alert

        is_soft_deal = has_any(text, ["mou", "loi", "양해각서"])
        hard_contract = has_any(text, ["contract", "defense contract", "order", "procurement", "supply agreement", "계약", "공급계약", "수주", "수출", "조달", "체결"]) and not is_soft_deal
        drone_revenue_event = has_any(text, ["awarded", "contract", "defense contract", "order", "supply agreement", "wins", "계약", "공급계약", "수주", "체결"]) and not is_soft_deal
        age = base.age_hours(row, now)
        status = "확정" if row.get("layer") == "official" else "공식 확인 전"
        if has_drone_watch:
            impacts = ["돈 버는 능력", "수급", "시간표"] if drone_revenue_event else ["시간표", "수급"]
            paths = ["계약 가시성", "밸류체인", "정책 타임라인"] if drone_revenue_event else ["정책 타임라인", "테마 수급"]
        elif has_korea_risk:
            impacts = ["할인율", "수급", "시간표"]
            paths = ["지정학 리스크", "테마 수급", "정책 타임라인"]
        elif has_signing_catalyst:
            impacts = ["돈 버는 능력", "수급", "시간표"]
            paths = ["계약 가시성", "수급", "정책 타임라인"]
        elif has_contract_delay_risk:
            impacts = ["돈 버는 능력", "수급", "시간표"]
            paths = ["계약 가시성", "수급", "정책 타임라인"]
        elif has_poland_risk and not hard_contract:
            impacts = ["돈 버는 능력", "수급", "시간표"]
            paths = ["계약 가시성", "수급", "정책 타임라인"]
        else:
            impacts = ["시간표", "수급"] if is_soft_deal else ["돈 버는 능력", "수급", "시간표"]
            paths = ["계약 가시성", "공급·수요", "정책 타임라인"] if not is_soft_deal else ["정책 타임라인", "테마 수급"]
        title = k_defense_title(text)

        if not alert:
            score = 112 if has_signing_catalyst else 106 if hard_contract else 106 if has_drone_watch else 104 if (has_korea_risk or has_poland_risk or has_contract_delay_risk) else 88
            if age is not None and age <= 12:
                score += 8
            alert = {
                "score": score,
                "importance": "상" if score >= 100 else "중",
                "status": status,
                "news": title,
                "original_news": row.get("title") or title,
                "publisher": row.get("publisher") or row.get("source"),
                "source": row.get("source"),
                "link": row.get("link") or "",
                "published": row["published"].isoformat(timespec="minutes") if row.get("published") else "확인 불가",
                "impacts": impacts[:],
                "paths": paths[:],
                "sectors": [K_DEFENSE_DRONE_SECTOR, K_DEFENSE_SECTOR, "한국 직접 영향"] if has_drone_watch else [K_DEFENSE_SECTOR],
                "matched": [],
                "reflection": "낮음" if age is not None and age <= 6 else "중간",
                "counter": K_DEFENSE_DRONE_COUNTER if has_drone_watch else "방위비·주한미군 이슈는 협상용 발언일 수 있고, 실제 분담금·배치 변경 확정 전까지 직접 실적 영향은 제한적입니다." if has_korea_risk else "실제 서명 뉴스도 계약금액·납기·수출허가·상대국 예산 집행 조건 확인 전까지 매출 인식 시차가 있습니다." if has_signing_catalyst else "계약 지연 뉴스는 협상 과정의 노이즈일 수 있어 공식 본계약 일정·상대국 예산·정치 이벤트 확인이 필요합니다." if has_contract_delay_risk else "MOU/LOI는 확정 매출이 아니며 본계약·금액·인도 일정·수출허가 확인 전 과대해석 가능" if is_soft_deal else "계약금액, 기간, 상대국 예산, 수출허가, 양산·인도 일정 확인 전까지 실제 매출 인식에는 시차가 있습니다.",
                "interpretation": "KADIZ 진입과 대드론 KS 제정은 전시회 시연이 아니라 상시 감시·즉응·시험평가·도입 언어로 넘어가는 신호입니다. 완제품 한 종목보다 탐지 레이더-지휘통제-무인기 플랫폼-레이저/HPM 대응수단 중 어느 층위가 움직이는지 봐야 합니다." if has_drone_watch else "방위비 분담금·주한미군 재조정 압박은 K-방산 전 종목의 한반도 지정학 프리미엄과 수급 심리를 흔들 수 있습니다." if has_korea_risk else "사우디 천궁Ⅱ 또는 K2 폴란드 2차 계약의 실제 서명은 기대감이 수주 가시성으로 바뀌는 분수령입니다." if has_signing_catalyst else "폴란드·사우디 대형계약 지연은 현대로템·LIG넥스원의 수주 가시성과 단기 수급을 흔드는 리스크입니다." if has_contract_delay_risk else "폴란드 의존도와 정권·예산 변화는 현대로템·한화에어로 수주잔고 가시성을 흔드는 리스크입니다." if has_poland_risk and not hard_contract else "K-방산 무기체계 수주·수출은 국내 방산주의 수주잔고와 밸류체인 수급을 바로 흔들 수 있는 재료입니다.",
                "failed_signal": "KS·국방부/방사청 후속 공고, 예산, 시험평가 일정, 조달/전력화 계획, 기업별 레이어 확인이 없으면 방산 전반 테마로 약화" if has_drone_watch else "공식 협정·국방부 발표·의회 예산·병력배치 후속 문서가 없으면 협상성 헤드라인으로 약화" if has_korea_risk else "서명 원문·공시·상대국 예산 집행·계약금액/납기 확인이 없으면 기대감 재료로 후퇴" if has_signing_catalyst else "본계약 체결 일정이 유지되거나 상대국 예산·승인이 확인되면 계약 지연 리스크는 약화" if has_contract_delay_risk else "폴란드 예산·정권 리스크가 실제 계약 취소·지연·재협상으로 연결되지 않으면 영향 제한" if has_poland_risk and not hard_contract else "공시·공식 발표·상대국 예산·수출허가·납기 확인이 뒤따르지 않으면 테마성 반응으로 약화",
                "korea_basis": "예고된 이벤트의 공식화" if status == "확정" else "외신 확산",
            }
        else:
            alert["score"] = max(int(alert.get("score", 0)), 112 if has_signing_catalyst else 106 if hard_contract else 106 if has_drone_watch else 104 if (has_korea_risk or has_poland_risk or has_contract_delay_risk) else 88)
            alert["importance"] = "상" if int(alert["score"]) >= 100 else "중"
            alert["status"] = alert.get("status") or status
            alert["news"] = title
            alert["original_news"] = alert.get("original_news") or row.get("title") or title
            if has_drone_watch:
                alert["impacts"] = impacts[:]
                alert["paths"] = paths[:]
                alert["sectors"] = [K_DEFENSE_DRONE_SECTOR, K_DEFENSE_SECTOR, "한국 직접 영향"]
            else:
                append_unique(alert.setdefault("impacts", []), impacts)
                append_unique(alert.setdefault("paths", []), paths)
                append_unique(alert.setdefault("sectors", []), [K_DEFENSE_SECTOR])
            if len(alert["impacts"]) > 1:
                alert["impacts"] = [impact for impact in alert["impacts"] if impact != "의사결정 영향 제한적"]
            if len(alert["paths"]) > 1:
                alert["paths"] = [path for path in alert["paths"] if path != "의사결정 영향 제한적"]
            alert["counter"] = K_DEFENSE_DRONE_COUNTER if has_drone_watch else "방위비·주한미군 이슈는 협상용 발언일 수 있고, 실제 분담금·배치 변경 확정 전까지 직접 실적 영향은 제한적입니다." if has_korea_risk else "실제 서명 뉴스도 계약금액·납기·수출허가·상대국 예산 집행 조건 확인 전까지 매출 인식 시차가 있습니다." if has_signing_catalyst else "계약 지연 뉴스는 협상 과정의 노이즈일 수 있어 공식 본계약 일정·상대국 예산·정치 이벤트 확인이 필요합니다." if has_contract_delay_risk else "MOU/LOI는 확정 매출이 아니며 본계약·금액·인도 일정·수출허가 확인 전 과대해석 가능" if is_soft_deal else "계약금액, 기간, 상대국 예산, 수출허가, 양산·인도 일정 확인 전까지 실제 매출 인식에는 시차가 있습니다."
            alert["interpretation"] = "KADIZ 진입과 대드론 KS 제정은 전시회 시연이 아니라 상시 감시·즉응·시험평가·도입 언어로 넘어가는 신호입니다. 완제품 한 종목보다 탐지 레이더-지휘통제-무인기 플랫폼-레이저/HPM 대응수단 중 어느 층위가 움직이는지 봐야 합니다." if has_drone_watch else "방위비 분담금·주한미군 재조정 압박은 K-방산 전 종목의 한반도 지정학 프리미엄과 수급 심리를 흔들 수 있습니다." if has_korea_risk else "사우디 천궁Ⅱ 또는 K2 폴란드 2차 계약의 실제 서명은 기대감이 수주 가시성으로 바뀌는 분수령입니다." if has_signing_catalyst else "폴란드·사우디 대형계약 지연은 현대로템·LIG넥스원의 수주 가시성과 단기 수급을 흔드는 리스크입니다." if has_contract_delay_risk else "폴란드 의존도와 정권·예산 변화는 현대로템·한화에어로 수주잔고 가시성을 흔드는 리스크입니다." if has_poland_risk and not hard_contract else "K-방산 무기체계 수주·수출은 국내 방산주의 수주잔고와 밸류체인 수급을 바로 흔들 수 있는 재료입니다."
            alert["failed_signal"] = "KS·국방부/방사청 후속 공고, 예산, 시험평가 일정, 조달/전력화 계획, 기업별 레이어 확인이 없으면 방산 전반 테마로 약화" if has_drone_watch else "공식 협정·국방부 발표·의회 예산·병력배치 후속 문서가 없으면 협상성 헤드라인으로 약화" if has_korea_risk else "서명 원문·공시·상대국 예산 집행·계약금액/납기 확인이 없으면 기대감 재료로 후퇴" if has_signing_catalyst else "본계약 체결 일정이 유지되거나 상대국 예산·승인이 확인되면 계약 지연 리스크는 약화" if has_contract_delay_risk else "폴란드 예산·정권 리스크가 실제 계약 취소·지연·재협상으로 연결되지 않으면 영향 제한" if has_poland_risk and not hard_contract else "공시·공식 발표·상대국 예산·수출허가·납기 확인이 뒤따르지 않으면 테마성 반응으로 약화"

        alert["k_defense_watch"] = True
        alert["k_drone_air_defense_watch"] = has_drone_watch
        alert["k_defense_check"] = K_DEFENSE_DRONE_CHECK if has_drone_watch else K_DEFENSE_CHECK
        alert["k_defense_risk_check"] = "" if has_drone_watch else k_defense_risk_check(text)
        return alert

    contract.strict.classify = classify


ORIGINAL_KOREAN_TITLE = telegram.korean_title
ORIGINAL_COMPACT_ALERT = runner.compact_alert
ORIGINAL_RELATED_TEXT = runner.related_text


def korean_title(alert: dict) -> str:
    sectors = alert.get("sectors") or []
    if alert.get("k_defense_watch") or K_DEFENSE_SECTOR in sectors:
        return alert.get("news") or k_defense_title(base.norm(alert.get("original_news") or ""))
    return ORIGINAL_KOREAN_TITLE(alert)


def compact_alert(alert: dict, idx: int, now, fred: dict, te: dict) -> str:
    text = ORIGINAL_COMPACT_ALERT(alert, idx, now, fred, te)
    if alert.get("k_defense_watch") and "K-방산 체크:" not in text:
        marker = "\n- 실패 신호:"
        label = "대드론 체계 체크" if alert.get("k_drone_air_defense_watch") else "K-방산 체크"
        check = f"\n- {label}: {alert.get('k_defense_check') or K_DEFENSE_CHECK}"
        risk = alert.get("k_defense_risk_check")
        if risk:
            check += f"\n- K-방산 리스크: {risk}"
        return text.replace(marker, check + marker, 1)
    return text


def related_text(alert: dict, fred: dict, te: dict) -> str:
    text = ORIGINAL_RELATED_TEXT(alert, fred, te)
    if alert.get("k_drone_air_defense_watch") or K_DEFENSE_DRONE_SECTOR in alert.get("sectors", []):
        extra = [
            "272210.KS 한화시스템", "079550.KS LIG넥스원", "047810.KS 한국항공우주",
            "012450.KS 한화에어로스페이스", "탐지 레이더", "지휘통제/C2",
            "무인기 플랫폼", "레이저/HPM", "KS 시험평가/조달",
        ]
        empty_markers = {"확인 가능한 직접 티커 없음", "확인 가능한 직접 지표 없음"}
        parts = [] if text in empty_markers else [part.strip() for part in text.split(",") if part.strip() and part.strip() not in empty_markers]
        return ", ".join(dict.fromkeys(parts + extra))
    return text


enforce_k_defense_watch()
telegram.korean_title = korean_title
runner.compact_alert = compact_alert
runner.related_text = related_text


if __name__ == "__main__":
    raise SystemExit(telegram.main())
