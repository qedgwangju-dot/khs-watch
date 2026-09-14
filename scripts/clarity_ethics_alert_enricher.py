#!/usr/bin/env python3
import html
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out"
ALERT_JSON = OUT_DIR / "clarity_watch_alert.json"
OUT_HTML = OUT_DIR / "clarity_watch_alert.html"
OUT_CHUNKS = OUT_DIR / "clarity_watch_telegram_chunks.json"

GENERIC_EASY = (
    "실제 표결이나 법률 효력이 생긴 것은 아니지만, 대통령·재무장관·백악관 같은 최고위 당사자가 공개적으로 처리를 압박하면 "
    "상원 의원들의 협상 비용과 표결 시간표가 바뀔 수 있습니다. 따라서 ‘입법 절차 변화’와 별도로 통과 확률을 움직이는 정책 압력 신호로 봅니다."
)
PRECISE_EASY = (
    "이번 변화의 핵심은 단순한 ‘통과 촉구’가 아니라, 60표 확보의 가장 큰 걸림돌 중 하나였던 윤리 조항에서 Trump 대통령이 "
    "Tillis–Gallego 절충안의 약 80%를 수용했다는 점입니다. 특히 주 검찰총장 집행권까지 받아들였다는 보도는 협상 간극이 실제로 줄었다는 뜻입니다. "
    "다만 아직 백악관의 공개 확인과 개정 법안 원문이 없으므로 ‘윤리 조항 최종 합의’나 ‘법안 통과 확정’으로 보면 안 됩니다."
)
GENERIC_INVEST = (
    "- 돈 버는 능력: 공개 촉구만으로 Coinbase·Circle의 현재 실적은 바뀌지 않습니다.\n"
    "- 할인율: 행정부의 우선순위 재확인은 규제 불확실성 완화 기대에 긍정적이지만 실제 표결 전까지 확정 효과는 아닙니다.\n"
    "- 수급: 정책 기대 수급은 COIN·CRCL에 상대적으로 더 직접적이고 BTC에는 간접적입니다.\n"
    "- 시간표: 이번 사건에서 가장 직접적으로 바뀐 축은 상원에 대한 정치적 압박입니다. 실제 일정·표결 결과를 다음으로 확인합니다."
)
PRECISE_INVEST = (
    "- 돈 버는 능력: 아직 법안 통과 전이므로 Coinbase·Circle의 현재 매출·마진은 바뀌지 않았습니다. 다만 윤리 협상 진전은 향후 미국 내 거래·수탁·스테이블코인·토큰화 사업의 규제 가시성을 높이는 방향입니다.\n"
    "- 할인율: 가장 큰 정치적 규제 리스크 하나가 완화되는 방향이라 COIN·CRCL의 규제 위험 프리미엄에는 긍정적입니다. 다만 공식 문안과 실제 표결 전까지는 기대 효과입니다.\n"
    "- 수급: COIN·CRCL에는 통과 확률 상승 기대가 상대적으로 직접적이고 BTC에는 간접적입니다. 실제 가격 반응은 금리·달러·Nasdaq과 분리해 확인해야 합니다.\n"
    "- 시간표: 가장 크게 바뀐 축입니다. 윤리 조항은 60표 확보의 핵심 장애물이었고, 이번 합의 진전은 9월 15일 절차표결의 상방 요인입니다. 다만 stablecoin rewards·불법금융·은행권 반대·공화당 이탈표는 여전히 남아 있습니다."
)
GENERIC_CORE = (
    "행정부·핵심 당사자의 통과 촉구로 실제 바뀐 축은 시간표와 규제 할인율 기대이며 Coinbase·Circle에는 긍정적이지만 현재 실적은 그대로이고, "
    "상원 60표 미확보·추가 수정·일정 지연이 최대 실패 경로입니다."
)
PRECISE_CORE = (
    "Trump가 Tillis–Gallego 윤리안의 약 80%와 주 검찰총장 집행권을 수용했다는 AP 보도로 실제 개선된 축은 시간표·규제 할인율이며 COIN·CRCL에는 호재 방향이지만, "
    "백악관 공개 확인·개정 원문·9월 15일 60표가 아직 남아 있어 현재 실적 효과는 미확정이고 stablecoin rewards·불법금융·공화당 이탈표가 핵심 실패 경로입니다."
)


def is_ethics_breakthrough(event):
    return "윤리 합의 진전" in str(event.get("event_type", ""))


def enrich_text(text):
    text = text.replace(html.escape(GENERIC_EASY), html.escape(PRECISE_EASY))
    text = text.replace(html.escape(GENERIC_INVEST), html.escape(PRECISE_INVEST))
    text = text.replace(html.escape(GENERIC_CORE), html.escape(PRECISE_CORE))
    return text


def main():
    if not ALERT_JSON.exists() or not OUT_CHUNKS.exists():
        print("clarity_ethics_enrichment=false reason=no_formatted_alert")
        return
    events = json.loads(ALERT_JSON.read_text(encoding="utf-8"))
    if not events or not is_ethics_breakthrough(events[0]):
        print("clarity_ethics_enrichment=false reason=ethics_not_primary")
        return
    chunks = json.loads(OUT_CHUNKS.read_text(encoding="utf-8"))
    chunks = [enrich_text(chunk) for chunk in chunks]
    OUT_CHUNKS.write_text(json.dumps(chunks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUT_HTML.write_text("\n\n".join(chunks) + "\n", encoding="utf-8")
    print(f"clarity_ethics_enrichment=true chunks={len(chunks)}")


if __name__ == "__main__":
    main()
