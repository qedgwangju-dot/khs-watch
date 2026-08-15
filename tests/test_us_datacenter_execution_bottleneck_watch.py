import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.us_datacenter_execution_bottleneck_watch as dc
from scripts.us_datacenter_execution_bottleneck_watch import (
    EventCluster,
    clean_title,
    cluster_items,
    direction,
    event_fingerprint,
    fresh_for_alert,
    select_factual_sentences,
    source_class,
    stage,
    translate_title_to_korean,
    verified,
)


def item(title: str, source: str, published: str = "Fri, 14 Aug 2026 12:00:00 GMT"):
    return {
        "id": title + source,
        "title": title,
        "link": "https://example.com/" + str(abs(hash(title + source))),
        "published": published,
        "source": source,
    }


def test_stage_and_direction_forward():
    assert stage("Meta data center permit approved in county")[1] == "인허가"
    assert direction("Meta data center permit approved in county", "인허가") == "전진"


def test_moratorium_is_permitting_backward_not_resident_opposition():
    rank, name = stage("New York imposes one-year data center moratorium")
    assert rank == 3
    assert name == "인허가"
    assert direction("New York imposes one-year data center moratorium", name) == "후퇴"


def test_stage_and_direction_resident_opposition():
    assert stage("Residents oppose county data center and file lawsuit")[1] == "주민 반대"
    assert direction("Residents oppose county data center and file lawsuit", "주민 반대") == "후퇴"


def test_single_source_is_not_verified():
    clusters = cluster_items([
        item("Meta data center permit approved for new campus", "Reuters"),
    ])
    assert len(clusters) == 1
    assert verified(clusters[0]) is False


def test_two_independent_sources_with_reputable_source_are_verified():
    rows = [
        item("Meta data center permit approved for new campus", "Reuters"),
        item("Meta data center permit approved for campus", "Local Business Journal"),
    ]
    clusters = cluster_items(rows)
    assert len(clusters) == 1
    assert verified(clusters[0]) is True


def test_same_source_republication_does_not_count_as_two_sources():
    rows = [
        item("Meta data center permit approved for new campus", "Reuters"),
        item("Meta data center permit approved for campus", "Reuters"),
    ]
    clusters = cluster_items(rows)
    assert len(clusters) == 1
    assert verified(clusters[0]) is False


def test_source_classification():
    assert source_class("Reuters") == "신뢰보도"
    assert source_class("The Washington Post") == "신뢰보도"
    assert source_class("Prince William County") == "공식·당사자"


def test_event_fingerprint_is_stable_across_source_order():
    a = item("Meta data center permit approved for new campus", "Reuters")
    b = item("Meta data center permit approved for campus", "Local Business Journal")
    c1 = cluster_items([a, b])[0]
    c2 = cluster_items([b, a])[0]
    assert event_fingerprint(c1) == event_fingerprint(c2)


def test_old_event_is_not_fresh_for_alert():
    cluster = EventCluster(
        rank=3,
        stage_name="인허가",
        direction="후퇴",
        items=[item(
            "New York imposes one-year data center moratorium",
            "Reuters",
            "Tue, 14 Jul 2026 09:05:20 GMT",
        )],
    )
    now = datetime(2026, 8, 15, 0, 0, tzinfo=timezone.utc)
    assert fresh_for_alert(cluster, now=now) is False


def test_recent_event_is_fresh_for_alert():
    cluster = EventCluster(
        rank=3,
        stage_name="인허가",
        direction="후퇴",
        items=[item(
            "New York imposes new data center moratorium",
            "Reuters",
            "Fri, 14 Aug 2026 09:05:20 GMT",
        )],
    )
    now = datetime(2026, 8, 15, 0, 0, tzinfo=timezone.utc)
    assert fresh_for_alert(cluster, now=now) is True


def test_factual_summary_selection_keeps_scope_duration_and_permits():
    body = (
        "New York became the first U.S. state to halt construction of large new data centers. "
        "The one-year construction ban applies to data centers that use 50 megawatts or more of power. "
        "During the moratorium the Department of Environmental Conservation will not issue discretionary permits not already deemed complete. "
        "Officials will prepare a generic environmental impact statement and the ban will be lifted once those standards are finalized. "
        "Several companies declined to comment."
    )
    selected = select_factual_sentences(body, "인허가")
    assert "50 megawatts" in selected
    assert "one-year" in selected
    assert "discretionary permits" in selected


def test_clean_title_removes_publisher_suffix():
    assert clean_title(
        "Dominion ordered to directly assign some transmission costs to data centers - Utility Dive",
        "Utility Dive",
    ) == "Dominion ordered to directly assign some transmission costs to data centers"


def test_translate_title_outputs_korean(monkeypatch):
    monkeypatch.setattr(
        dc,
        "_translate_via_google",
        lambda _text: "도미니언에 데이터센터 송전 비용 일부를 직접 부담시키라는 명령",
    )
    translated, status = translate_title_to_korean(
        "Dominion ordered to directly assign some transmission costs to data centers - Utility Dive",
        "Utility Dive",
        "계통접속",
        "변화",
        [],
    )
    assert status == "자동번역"
    assert re.search(r"[가-힣]", translated)
    assert "ordered to directly" not in translated


def test_translation_failure_never_leaks_english_headline(monkeypatch):
    def fail(_text):
        raise RuntimeError("translation unavailable")

    monkeypatch.setattr(dc, "_translate_via_google", fail)
    translated, status = translate_title_to_korean(
        "Dominion ordered to directly assign some transmission costs to data centers - Utility Dive",
        "Utility Dive",
        "계통접속",
        "변화",
        [],
    )
    assert status == "한국어 대체문구"
    assert re.search(r"[가-힣]", translated)
    assert "Dominion ordered" not in translated


def test_hydrate_summary_requires_article_body_and_translates(monkeypatch):
    rows = [
        item("New York data center moratorium blocks permits - Reuters", "Reuters"),
        item("New York data center moratorium blocks permits - The Washington Post", "The Washington Post"),
    ]
    cluster = EventCluster(rank=3, stage_name="인허가", direction="후퇴", items=rows)
    article = (
        "New York became the first U.S. state to halt construction of large new data centers. "
        "The one-year construction ban applies to data centers that use 50 megawatts or more of power. "
        "During the moratorium the state will not issue discretionary permits not already deemed complete. "
        "The ban will be lifted once environmental standards are finalized."
    )
    monkeypatch.setattr(dc, "resolve_publisher_url", lambda url: url.replace("example.com", "reuters.com"))
    monkeypatch.setattr(dc, "extract_article_text", lambda _session, _url: article)
    monkeypatch.setattr(
        dc,
        "_translate_via_google",
        lambda text: "뉴욕주는 50메가와트 이상 신규 대형 데이터센터에 대해 1년간 건설을 중단하고, 완료로 인정되지 않은 재량 인허가를 내주지 않는다. 환경 기준이 확정되면 유예를 해제한다." if "50 megawatts" in text else "뉴욕주 데이터센터 인허가 유예",
    )
    assert dc.hydrate_cluster_summary(cluster, object()) is True
    assert "50메가와트" in cluster.summary_ko
    assert "1년" in cluster.summary_ko
    assert cluster.summary_source == "Reuters"


def test_report_uses_exact_summary_korean_title_and_clickable_links(monkeypatch):
    monkeypatch.setattr(
        dc,
        "_translate_via_google",
        lambda _text: "도미니언에 데이터센터 송전 비용 일부를 직접 부담시키라는 명령",
    )
    rows = [
        item("Dominion data center transmission agreement approved by regulator - Utility Dive", "Utility Dive"),
        item("Dominion data center transmission agreement approved by regulator - Data Center Dynamics", "Data Center Dynamics"),
    ]
    cluster = EventCluster(
        rank=2,
        stage_name="계통접속",
        direction="전진",
        items=rows,
        summary_ko="규제기관은 데이터센터 계통접속에 필요한 송전 비용 일부를 해당 대형 전력수요자에게 직접 배분하도록 했다.",
        summary_source="Utility Dive",
        resolved_urls={row["id"]: row["link"] for row in rows},
    )
    text = dc.report([cluster], False)
    assert "정확한 내용 요약:" in text
    assert "송전 비용 일부" in text
    assert "도미니언에 데이터센터 송전 비용 일부를 직접 부담시키라는 명령" in text
    assert "Dominion data center transmission agreement" not in text
    assert text.count(">원문</a>") == 2
    assert '<a href="https://example.com/' in text
    assert " · https://" not in text
