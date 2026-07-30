from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import gamejoa_preopen_news_radar_full_compact_runner as radar

CASES = (
    ("NAVER, 엔비디아 대상 1조4809억 규모 유상증자 결정", "유상증자", "수급"),
    ("SK하이닉스, 10개사와 LTA 장기공급계약 체결", "lta", "돈 버는 능력"),
    ("코스피, 2거래일 연속 매도 사이드카 발동", "사이드카", "수급"),
    ("코스닥 서킷브레이커 1단계 발동", "서킷브레이커", "수급"),
    ("구마모토 규모 7.1 강진, TSMC 공장 중단", "강진", "돈 버는 능력"),
    ("10년물 미국채 금리 4.7%, 트럼프 2기 최고", "미국채", "할인율"),
    ("삼성전기, 10개 고객과 MLCC 장기공급계약", "mlcc", "돈 버는 능력"),
    ("미국, 외국산 휴머노이드 수입 제한", "수입 제한", "할인율"),
    ("엔비디아, AI 순환금융 우려 재점화", "순환금융", "돈 버는 능력"),
)


def main():
    failures = []
    now = datetime.now().astimezone()
    for index, (title, required_term, required_impact) in enumerate(CASES):
        row = {"title": title, "summary": title, "published": now}
        score, _ = radar.korean_business_detail_priority(row)
        material = [term for term in radar.KOREAN_BUSINESS_MATERIAL_TERMS if radar.korean_business_title_has_material_term(title.lower(), term)]
        impacts = radar.korean_business_impacts(title.lower(), [])
        if score < 10: failures.append(f"case={index} priority={score}")
        if required_term not in material: failures.append(f"case={index} material={required_term}")
        if required_impact not in impacts: failures.append(f"case={index} impact={required_impact}")
    a = {"news": "삼성전기 2분기 영업이익 4404억원, 10개 고객과 MLCC 장기계약", "published": now}
    b = {"news": "삼성전기, 하이퍼스케일러 10여곳과 MLCC LTA 체결", "published": now}
    if radar.alert_dedup_key(a) != radar.alert_dedup_key(b): failures.append("semantic_duplicate=mlcc_lta")
    if failures:
        print("GAMEJOA news coverage contract failed: " + ", ".join(failures))
        return 1
    print(f"GAMEJOA news coverage contract OK: cases={len(CASES)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
