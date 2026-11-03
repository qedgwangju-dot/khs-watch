import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import korail_hangsin_solar_watch as w

KST = timezone(timedelta(hours=9))


def row(title, summary="", at="2026-11-04T10:00:00+09:00", official=False):
    return {
        "title": title, "summary": summary,
        "url": "https://example.com/story", "source": "테스트",
        "published": datetime.fromisoformat(at), "official": official,
    }


def test_original_negotiation_does_not_notify():
    title = "한수원, 지투파워·신한자산운용과 손잡고 철도 태양광 공략"
    body = (
        "행신역 20.1MW 태양광 사업을 위해 출자 방안을 마련했다. "
        "한수원 49%, 신한자산운용 10%, 지투파워 41%로 구상하지만 확정되지 않았다. "
        "오는 11월 24일 공모 마감일까지 사업제안서를 제출할 예정이다. "
        "우선협상대상자로 선정돼 약 1년 인허가를 마치면 운영에 돌입한다."
    )
    assert w.detect_events(title, body) == set()


def test_actual_proposal_submission_is_new_stage():
    assert w.detect_events(
        "한수원·지투파워, 행신역 태양광 사업제안서 제출 완료",
        "한국철도공사 수도권철도차량정비단 20.1MW 공모에 제안서를 제출했다.",
    ) == {"proposal_submitted"}


def test_future_submission_is_not_actual_stage():
    assert not w.detect_events(
        "한수원·지투파워, 행신역 태양광 사업제안서 제출 예정",
        "마감일 24일까지 제출할 계획이다.",
    )


def test_preferred_bidder_is_selected_only_when_consortium_named():
    assert w.detect_events(
        "한수원·지투파워, 행신역 태양광 우선협상대상자 선정",
        "한국철도공사가 선정 결과를 발표했다.",
        True,
    ) == {"preferred_selected"}
    assert not w.detect_events(
        "한국철도공사, 행신역 태양광 우선협상대상자 선정하면 건설 추진",
        "한수원은 선정되면 출자를 검토한다.",
    )


def test_agreement_and_equity_are_distinct():
    assert w.detect_events(
        "한수원·지투파워, 행신역 태양광 사업협약 체결 완료",
        "",
    ) == {"agreement_signed"}
    assert w.detect_events(
        "한수원, 행신역 태양광 특수목적법인 출자 확정",
        "",
    ) == {"equity_approved"}


def test_competitor_selected_does_not_mean_khnp_won():
    events = w.detect_events(
        "한수원 컨소시엄 탈락, 행신역 태양광 다른 사업자가 우선협상대상자로 선정됐다",
        "",
    )
    assert "other_selected" in events
    assert "preferred_selected" not in events


def test_other_rail_maintenance_contract_is_irrelevant():
    assert not w.detect_events(
        "수도권철도차량정비단 건축물 자동제어설비 개량 및 기타공사 낙찰",
        "2026년 11월 개찰 결과",
    )
    assert not w.detect_events(
        "부산 철도차량기지 16개소 태양광 발전사업",
        "한국철도공사 시범사업",
    )


def test_stale_and_duplicate_alerts_are_suppressed():
    s = w.initial_state()
    now = datetime(2026, 11, 25, 9, 0, tzinfo=KST)
    title = "한수원·지투파워, 행신역 태양광 사업제안서 제출 완료"
    rows = [
        row(title, "한국철도공사 공모 신청 완료", at="2026-11-24T17:00:00+09:00"),
        row(title, "한국철도공사 공모 신청 완료", at="2026-11-24T18:00:00+09:00"),
        row("한수원·지투파워 행신역 태양광 착공했다", "", at="2026-11-02T10:00:00+09:00"),
    ]
    selected = w.select_events(rows, s, now)
    assert len(selected) == 1
    assert selected[0]["event_type"] == "proposal_submitted"
    s["seen_event_types"].append("proposal_submitted")
    assert w.select_events(rows, s, now) == []


def test_article_and_official_sources_are_not_automatically_same():
    fake_xml = """
    <rss><channel><item><title>한수원 지투파워 행신역 태양광 사업제안서 제출 완료</title>
    <description>한국철도공사 입찰에 사업제안서 제출 완료</description>
    <link>https://news.google.com/story</link>
    <pubDate>Tue, 24 Nov 2026 05:00:00 GMT</pubDate></item></channel></rss>
    """
    parsed = w.rss_rows(fake_xml, "Google 뉴스 RSS")
    assert len(parsed) == 1
    assert parsed[0]["official"] is False


def test_deadline_change_and_spc_are_not_confused_with_plans():
    assert w.detect_events(
        "행신역 태양광 공모 접수 마감일 변경",
        "한국철도공사 11월 24일 마감에서 12월 1일로 변경 확정",
        True,
    ) == {"deadline_changed"}
    assert not w.detect_events(
        "지투파워·한수원, 행신역 태양광 SPC 설립 방안 마련",
        "신한자산운용과 아직 협의 중",
    )
