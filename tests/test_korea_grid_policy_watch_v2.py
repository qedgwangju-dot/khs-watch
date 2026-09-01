import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.korea_grid_policy_watch_v2 import (
    canonical_title,
    collapse_events,
    extract_official_date,
    render_report,
)


def test_canonical_title_removes_official_search_suffix():
    assert canonical_title(
        "송전용 에너지저장장치에 전력망의 안정성을 높이는 그리드포밍 기술 도입 - 기후에너지환경부"
    ) == canonical_title(
        "송전용 에너지저장장치에 전력망의 안정성을 높이는 그리드포밍 기술 도입"
    )


def test_direct_official_item_wins_over_google_news_duplicate():
    items = [
        {
            "title": "그리드포밍 기술 도입 - 기후에너지환경부",
            "source": "기후에너지환경부 공식 검색",
            "url": "https://news.google.com/rss/articles/x",
            "published": "Tue, 01 Sep 2026 07:00:00 GMT",
            "category": "전력망 정책",
            "stage": 1,
        },
        {
            "title": "그리드포밍 기술 도입",
            "source": "기후에너지환경부",
            "url": "https://www.mcee.go.kr/home/web/newsRead.do?boardId=1",
            "published": "2026-06-24",
            "category": "전력망 정책",
            "stage": 1,
        },
    ]
    collapsed = collapse_events(items)
    assert len(collapsed) == 1
    assert collapsed[0]["source"] == "기후에너지환경부"
    assert collapsed[0]["published"] == "2026-06-24"


def test_extract_official_date_prefers_labeled_date():
    html = "<div>작성일 2026-06-24 조회수 9100 다른 날짜 2026-09-01</div>"
    assert extract_official_date(html) == "2026-06-24"


def test_gfm_alert_contains_readable_core_numbers_and_risk():
    item = {
        "title": "송전용 에너지저장장치에 전력망의 안정성을 높이는 그리드포밍 기술 도입",
        "source": "기후에너지환경부",
        "url": "https://www.mcee.go.kr/example",
        "published": "2026-06-24",
        "category": "전력망 정책",
        "stage": 1,
        "article_text": (
            "2027년 12월부터 장주기 BESS에 적용한다. "
            "2027년 540MW, 2028년 540MW, 2029년 600MW를 도입한다."
        ),
    }
    report = render_report([item], [])
    assert "1.68GW" in report
    assert "쉽게 풀면" in report
    assert "PCS·인버터" in report
    assert "개별 PCS·인버터 공급사는 이번 공식자료에서 공개되지 않음" in report
    assert "숨은 역풍" in report
    assert "2026년 6월 24일" in report
