import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.us_datacenter_execution_bottleneck_watch as dc
from scripts.us_datacenter_execution_bottleneck_watch import (
    EventCluster,
    clean_title,
    cluster_items,
    direction,
    event_fingerprint,
    source_class,
    stage,
    translate_title_to_korean,
    verified,
)


def item(title: str, source: str):
    return {
        "id": title + source,
        "title": title,
        "link": "https://example.com/" + str(abs(hash(title + source))),
        "published": "Mon, 10 Aug 2026 12:00:00 GMT",
        "source": source,
    }


def test_stage_and_direction_forward():
    assert stage("Meta data center permit approved in county")[1] == "인허가"
    assert direction("Meta data center permit approved in county", "인허가") == "전진"


def test_stage_and_direction_backward():
    assert stage("County blocks data center after resident opposition")[1] == "주민 반대"
    assert direction("County blocks data center after resident opposition", "주민 반대") == "후퇴"


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
    assert source_class("Prince William County") == "공식·당사자"


def test_event_fingerprint_is_stable_across_source_order():
    a = item("Meta data center permit approved for new campus", "Reuters")
    b = item("Meta data center permit approved for campus", "Local Business Journal")
    c1 = cluster_items([a, b])[0]
    c2 = cluster_items([b, a])[0]
    assert event_fingerprint(c1) == event_fingerprint(c2)


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


def test_report_uses_korean_title_and_clickable_original_links(monkeypatch):
    monkeypatch.setattr(
        dc,
        "_translate_via_google",
        lambda _text: "도미니언에 데이터센터 송전 비용 일부를 직접 부담시키라는 명령",
    )
    rows = [
        item("Dominion data center transmission agreement approved by regulator - Utility Dive", "Utility Dive"),
        item("Dominion data center transmission agreement approved by regulator - Data Center Dynamics", "Data Center Dynamics"),
    ]
    cluster = EventCluster(rank=2, stage_name="계통접속", direction="전진", items=rows)
    text = dc.report([cluster], False)
    assert "도미니언에 데이터센터 송전 비용 일부를 직접 부담시키라는 명령" in text
    assert "Dominion data center transmission agreement" not in text
    assert text.count(">원문</a>") == 2
    assert '<a href="https://example.com/' in text
    assert " · https://" not in text
