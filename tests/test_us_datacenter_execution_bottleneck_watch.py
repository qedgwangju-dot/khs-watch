from scripts.us_datacenter_execution_bottleneck_watch import (
    cluster_items,
    direction,
    event_fingerprint,
    source_class,
    stage,
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
