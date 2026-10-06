import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.korea_energy_mix_watch_runner as energy_runner

from scripts.korea_energy_mix_watch import (
    classify,
    collapse_events,
    event_key,
    event_level,
    korean_date,
    display_title,
    plan_stage,
    parse_rss,
    render,
    topic_match,
)
from scripts.korea_energy_mix_watch_runner import headline_match, interpret_article_body, semantic_event_key, semantic_event_level


def test_topic_match_all_power_plan_mentions():
    assert topic_match("제12차 전기본 재생에너지 2040년 220GW 전망") is True
    assert topic_match("제12차 전기본 총괄위원회 회의") is True
    assert topic_match("제12차 전력수급기본계획 정부안 확정") is True
    assert topic_match("일반 태양광 기업 신제품 출시") is False


def test_classifies_renewable_and_nuclear():
    assert classify("12차 전기본 재생에너지 220GW")[0] == "재생에너지·전원믹스"
    assert classify("12차 전기본 신규 원전 논의")[0] == "원전·전원믹스"


def test_rss_trusted_media_filter_and_korean_date():
    xml = """
    <rss><channel><item>
      <title>제12차 전력수급기본계획 재생에너지 220GW 전망</title>
      <source>연합뉴스</source>
      <link>https://example.com/story</link>
      <guid>story-1</guid>
      <pubDate>Wed, 26 Aug 2026 07:00:00 GMT</pubDate>
    </item></channel></rss>
    """
    rows = parse_rss(xml, "국내 주요 언론", False)
    assert len(rows) == 1
    assert korean_date(rows[0]["published"]) == "2026년 8월 26일"


def test_render_is_readable_and_ranks_2040_capacity():
    body = render([
        {
            "title": "2040년 재생에너지 220GW 보급…태양광 155GW·풍력 61GW - 뉴시스",
            "publisher": "뉴시스",
            "source": "국내 주요 언론",
            "official": False,
            "url": "https://example.com/story",
            "published": "Wed, 26 Aug 2026 07:00:00 GMT",
            "category": "재생에너지·전원믹스",
            "plan_stage": "전망·잠정안",
            "stage": 6,
            "id": "x",
        }
    ])
    assert "#" not in body
    assert "2026년 8월 26일" in body
    assert "<b>한눈에 보기</b>" in body
    assert "<b>현재 단계</b>" in body
    assert "<b>핵심 분야</b>" in body
    assert "<b>지금 의미</b>" in body
    assert "<b>다음 변곡점</b>" in body
    assert "<b>2040년 보급량 순위</b>" in body
    assert "1위  태양광  <b>155GW</b>" in body
    assert "2위  해상풍력  <b>45GW</b>" in body
    assert "3위  육상풍력  <b>16GW</b>" in body
    assert "자가용 태양광 포함 전체  <b>약 236GW</b>" in body
    assert "해상풍력 0.4 → 45GW  <b>112.5배</b>" in body
    assert "<b>투자 판단 포인트</b>" in body
    assert "기사 제목 자체가 아니라 전기본의 <b>숫자·정책 단계·공식화 여부가 실제로 바뀌었는지</b>를 추적" in body
    assert '<a href="https://example.com/story"><b>기사 원문 보기</b></a>' in body


def _row(title: str, publisher: str, item_id: str, official: bool = False):
    return {
        "title": title,
        "publisher": publisher,
        "source": "기후에너지환경부 공식" if official else "국내 주요 언론",
        "official": official,
        "url": f"https://example.com/{item_id}",
        "published": "Wed, 26 Aug 2026 07:00:00 GMT",
        "category": "재생에너지·전원믹스",
        "plan_stage": "전망·잠정안",
        "stage": 6,
        "id": item_id,
    }


def test_same_renewable_event_has_same_semantic_key():
    rows = [
        _row('"15년 뒤 재생에너지 설비 용량, 현재의 5.6배로 증가 전망" - 연합뉴스', "연합뉴스", "a"),
        _row("2040년 재생에너지 6배 확대…태양광 155GW·육해상풍력 61GW - 머니투데이", "머니투데이", "b"),
        _row("2040년 재생E 220GW…기후부, 12차 전기본 토론회 - 뉴스1", "뉴스1", "c"),
    ]
    keys = {event_key(row) for row in rows}
    assert len(keys) == 1


def test_collapse_events_keeps_only_one_media_item():
    rows = [
        _row('"15년 뒤 재생에너지 설비 용량, 현재의 5.6배로 증가 전망" - 연합뉴스', "연합뉴스", "a"),
        _row("2040년 재생E 220GW…기후부, 12차 전기본 토론회 - 뉴스1", "뉴스1", "b"),
        _row("2040년 재생E 220GW…기후부, 12차 전기본 토론회 - 뉴스1", "뉴스1", "c"),
    ]
    collapsed = collapse_events(rows)
    assert len(collapsed) == 1
    assert len(collapsed[0]["members"]) == 3
    assert collapsed[0]["publisher"] == "연합뉴스"


def test_official_source_is_a_material_upgrade():
    media = _row("2040년 재생에너지 220GW 전망 - 연합뉴스", "연합뉴스", "a")
    official = _row("제12차 전기본 재생에너지 2040년 220GW 전망", "기후에너지환경부", "b", official=True)
    assert event_level(media) == 1
    assert event_level(official) == 2
    collapsed = collapse_events([media, official])
    assert len(collapsed) == 1
    assert collapsed[0]["official"] is True


def test_nuclear_coal_lng_article_gets_real_body_interpretation():
    article_body = """
    정부와 제12차 전력수급기본계획 수립 총괄위원회는 다음 달부터 신규 원전 확대 여부와 2040년 석탄발전 폐지 등을 주제로 공청회를 개최할 예정이다.
    제11차 전기본에 반영된 대형원전 2기와 소형모듈원전(SMR) 1기는 확정됐고 대형원전은 경북 영덕군, SMR은 부산 기장군으로 부지가 정해졌다. SMR은 2035년, 대형원전은 2037년과 2038년 준공이 예상된다.
    김성환 장관은 호남 반도체 산단이 당초 팹 4기보다 커질 경우 원전을 더 지어야 할지 추가 대책을 찾아야 한다고 말했다. 한빛 원전은 현재 6개이고 2개를 더 지을 부지가 있다고 언급했다. 업계에서는 최대 9기의 팹 가능성이 제기된다.
    정부는 2040년 석탄발전 폐지 로드맵을 논의하고 있으며 발전 공백과 정의로운 전환을 함께 고민하고 있다. 발전공기업 5사 재편과 1사 통합안도 연구용역 권고 단계다.
    LNG 발전은 재생에너지 간헐성을 보완하고 원전보다 건설기간이 짧아 대안으로 거론된다. 호남 반도체 산단은 열 스팀 수요 때문에 LNG 발전소 가능성도 열어뒀다.
    정부는 다음 달부터 토론회를 열고 10월 정부안을 낸 뒤 연내 제12차 전기본을 확정할 방침이다.
    """
    result = interpret_article_body(
        {"title": "전력수요 폭증에 2040 석탄폐지까지…신규 원전 공론화 개시"},
        article_body,
        "",
    )
    assert "추가 원전" in result
    assert "확정 계획" in result
    assert "검토 가능성" in result
    assert "LNG" in result
    assert "10월 정부안" in result
    assert "임의 해석은 생략" not in result


def test_generic_article_sentence_parser_handles_korean_and_ascii_boundaries():
    article_body = (
        "정부는 전력시장 제도 개선안을 검토하고 있으며 계통 투자 확대도 함께 논의한다. "
        "송변전 설비 준공 일정은 지역별 인허가 상황에 따라 달라질 수 있다. "
        "ESS 확충 계획은 아직 세부 용량이 확정되지 않았다."
    )
    result = interpret_article_body(
        {"title": "전력시장·계통 투자 논의 확대"},
        article_body,
        "",
    )
    assert "원문에서 확인되는 핵심" in result
    assert "전력시장" in result
    assert "계통 투자" in result
    assert "임의로 추가하지 않음" in result


def test_nuclear_deliberation_is_one_policy_event_across_article_dates():
    official = {
        "title": "미래 전력수급에서 원전의 역할, 국민과 함께 논의한다",
        "publisher": "기후에너지환경부",
        "official": True,
        "published": "Tue, 22 Sep 2026 04:00:00 GMT",
    }
    followup = {
        "title": "국민 10명 중 8명 신규 원전 필요하다는데…정부는 ‘3개월 숙의’ 돌입[Pick코노미] - 서울경제",
        "publisher": "서울경제",
        "official": False,
        "published": "Fri, 25 Sep 2026 03:00:00 GMT",
    }
    # 공식 9/22 계획과 9/25 후속 기사는 '원전 공론화'라는 같은 정책 사건이다.
    # 후속 기사 날짜가 달라졌다는 이유만으로 새 알림이 되면 안 된다.
    assert semantic_event_key(official) == "12th-plan|nuclear-deliberation"
    assert semantic_event_key(followup) == "12th-plan|nuclear-deliberation"


def test_nuclear_deliberation_interpretation_separates_poll_from_policy_change():
    article_body = """
    정부는 원전의 역할을 두고 약 3개월간 공론화를 진행한다.
    시민참여단 숙의토론과 공개토론회, 온라인 의견수렴을 병행하고 12월 권고안을 도출한다.
    당초 10월로 예상됐던 제12차 전력수급기본계획 정부안 일정은 뒤로 미뤄진다.
    별도 국민인식 조사에서는 신규 원전 반영 필요 82.9%, 신규 원전 건설 필요 79.2%, 계속운전 필요 86.5%, SMR 필요 86.8%로 조사됐다.
    """
    result = interpret_article_body(
        {"title": "국민 10명 중 8명 신규 원전 필요…정부 3개월 숙의"},
        article_body,
        "",
    )
    assert "약 3개월간 공론화" in result
    assert "10월" in result
    assert "여론조사 숫자는 별도 구분" in result
    assert "재알림 사유로 보지 않음" in result


def test_article_only_nuclear_commentary_is_suppressed():
    row = {
        "title": "단순 찬반 아닌 전력충당 위한 원전 논의 - 헤럴드경제",
        "publisher": "헤럴드경제",
        "official": False,
        "published": "Tue, 22 Sep 2026 01:00:00 GMT",
        "plan_stage": "전기본 관련",
    }
    assert semantic_event_key(row) == "12th-plan|nuclear-deliberation"
    assert semantic_event_level(row) == 1


def test_poll_only_nuclear_article_does_not_trigger():
    row = {
        "title": "국민 10명 중 8명 신규 원전 필요…찬성률 79.2%",
        "publisher": "서울경제",
        "official": False,
        "published": "Fri, 25 Sep 2026 01:00:00 GMT",
        "plan_stage": "전기본 관련",
    }
    assert semantic_event_key(row) == "12th-plan|nuclear-opinion"
    assert semantic_event_level(row) == 0


def test_lng_capacity_market_not_misclassified_as_nuclear_event():
    row = {
        "title": "원전 1기급 LNG 용량시장 다시 연다",
        "publisher": "매일경제",
        "official": False,
        "published": "Sun, 13 Sep 2026 01:00:00 GMT",
        "plan_stage": "전기본 관련",
    }
    assert semantic_event_key(row).startswith("12th-plan|lng-capacity-market|")


def test_grid_innovation_policy_is_distinct_from_old_100gw_target():
    row = {
        "title": "2030년까지 재생에너지 100GW 달성…정부, 전력망 혁신대책 발표",
        "publisher": "연합뉴스TV",
        "official": False,
        "published": "Tue, 29 Sep 2026 04:00:00 GMT",
        "plan_stage": "발표·공개",
    }
    assert headline_match(row["title"]) is True
    assert semantic_event_key(row) == "12th-plan|grid-innovation|policy-announcement"
    assert semantic_event_level(row) == 1


def test_plain_renewable_100gw_target_rehash_is_suppressed():
    row = {
        "title": "정부, 2030년 재생에너지 100GW 목표 재확인",
        "publisher": "연합뉴스",
        "official": False,
        "published": "Tue, 29 Sep 2026 04:00:00 GMT",
        "plan_stage": "발표·공개",
    }
    assert semantic_event_key(row).startswith("12th-plan|renewable-capacity|")
    assert semantic_event_level(row) == 0


def test_grid_execution_subevents_have_stable_keys():
    release = {
        "title": "10월 1일부터 호남권 계통관리변전소 지정 해제",
        "publisher": "연합뉴스",
        "official": False,
        "published": "Tue, 29 Sep 2026 04:00:00 GMT",
        "plan_stage": "발표·공개",
    }
    rights = {
        "title": "호남 장기 지연 재생에너지 접속권 10GW 이상 회수",
        "publisher": "연합뉴스",
        "official": False,
        "published": "Tue, 29 Sep 2026 04:00:00 GMT",
        "plan_stage": "발표·공개",
    }
    assert headline_match(release["title"]) is True
    assert headline_match(rights["title"]) is True
    assert semantic_event_key(release) == "12th-plan|grid-innovation|management-substation-release"
    assert semantic_event_key(rights) == "12th-plan|grid-innovation|access-right-recovery"


def test_grid_innovation_body_interpretation_separates_target_from_execution():
    article_body = """
    정부는 2030년까지 재생에너지 100GW 이상 보급을 위해 전력망 혁신대책을 발표했다.
    다음달 1일부터 호남권 계통관리변전소 지정을 해제한다.
    환경영향평가가 완료되지 않은 장기 지연사업의 접속권을 회수해 호남에서만 2030년까지 10GW 이상의 접속권을 회수한다.
    ESS를 활용한 비증설 대안을 추진하고 전국 수용량을 최대 171GW로 확대한다.
    """
    result = interpret_article_body(
        {"title": "2030년까지 재생에너지 100GW 달성…정부, 전력망 혁신대책 발표", "category": "전력망·계통 수용력"},
        article_body,
        "",
    )
    assert "100GW 목표 자체가 새로 생긴 것이 아니라" in result
    assert "10월 1일부터 호남권 계통관리변전소 지정 해제" in result
    assert "10GW 이상" in result
    assert "최대 171GW" in result
    assert "비증설 대안" in result


def test_grid_actual_execution_upgrades_event_level():
    announced = {
        "title": "10월 1일부터 호남권 계통관리변전소 지정 해제 예정",
        "publisher": "연합뉴스",
        "official": False,
        "published": "Tue, 29 Sep 2026 04:00:00 GMT",
        "plan_stage": "발표·공개",
    }
    effective = {
        "title": "호남권 계통관리변전소 지정 해제 완료…제도 시행 시작",
        "publisher": "연합뉴스",
        "official": False,
        "published": "Thu, 01 Oct 2026 01:00:00 GMT",
        "plan_stage": "발표·공개",
    }
    assert semantic_event_key(announced) == semantic_event_key(effective)
    assert semantic_event_level(announced) == 1
    assert semantic_event_level(effective) == 3


def test_grid_policy_headlines_collapse_to_same_event():
    a = {
        "title": "2030년까지 재생에너지 100GW 달성…정부, 전력망 혁신대책 발표 - 연합뉴스TV",
        "publisher": "연합뉴스TV",
        "official": False,
        "published": "Tue, 29 Sep 2026 04:00:00 GMT",
        "plan_stage": "발표·공개",
    }
    b = {
        "title": "2030년 재생에너지 수용능력 52GW 늘린다…기존 전력망 최대 활용 - 뉴스1",
        "publisher": "뉴스1",
        "official": False,
        "published": "Tue, 29 Sep 2026 04:00:00 GMT",
        "plan_stage": "전기본 관련",
    }
    assert semantic_event_key(a) == "12th-plan|grid-innovation|policy-announcement"
    assert semantic_event_key(b) == "12th-plan|grid-innovation|policy-announcement"


def test_multirow_render_has_one_article_interpretation_per_row(monkeypatch):
    monkeypatch.setattr(
        energy_runner,
        "fetch_article_body",
        lambda url: (url, "", "본문 추출량 부족"),
    )
    rows = [
        {
            "title": "2030년까지 재생에너지 100GW 달성…정부, 전력망 혁신대책 발표 - 연합뉴스TV",
            "publisher": "연합뉴스TV",
            "official": False,
            "url": "https://example.com/a",
            "published": "Tue, 29 Sep 2026 04:00:00 GMT",
            "category": "전력망·계통 수용력",
            "plan_stage": "발표·공개",
            "stage": 6,
            "id": "a",
        },
        {
            "title": "2030년 재생에너지 수용능력 52GW 늘린다…기존 전력망 최대 활용 - 뉴스1",
            "publisher": "뉴스1",
            "official": False,
            "url": "https://example.com/b",
            "published": "Tue, 29 Sep 2026 04:00:00 GMT",
            "category": "전력망·계통 수용력",
            "plan_stage": "발표·공개",
            "stage": 6,
            "id": "b",
        },
    ]
    body = energy_runner.render_with_linked_source(rows)
    assert body.count("<b>원문 본문 해석</b>") == 2
    first_start = body.index("<b>1.")
    second_start = body.index("<b>2.")
    first_section = body[first_start:second_start]
    second_section = body[second_start:]
    assert first_section.count("<b>원문 본문 해석</b>") == 1
    assert second_section.count("<b>원문 본문 해석</b>") == 1


def test_committee_disclosure_dispute_is_one_suppressed_event():
    rows = [
        {
            "title": '"전기본 위원 명단 왜 공개 안하나" 야당 집중 공세…기후장관 "민원 때문"',
            "publisher": "머니투데이",
            "official": False,
            "published": "Tue, 06 Oct 2026 02:59:00 GMT",
            "plan_stage": "발표·공개",
        },
        {
            "title": '"전기본 위원 공개하라"·"尹정부도 안해"…국힘·김성환 충돌',
            "publisher": "연합뉴스",
            "official": False,
            "published": "Tue, 06 Oct 2026 03:00:00 GMT",
            "plan_stage": "발표·공개",
        },
        {
            "title": '김성환 "전기본 위원 비공개, 외부 잡음 때문…주요 쟁점은 공개"',
            "publisher": "뉴시스",
            "official": False,
            "published": "Tue, 06 Oct 2026 03:01:00 GMT",
            "plan_stage": "발표·공개",
        },
    ]
    assert {semantic_event_key(row) for row in rows} == {"12th-plan|committee-governance|member-disclosure"}
    assert all(semantic_event_level(row) == 0 for row in rows)


def test_honam_four_fab_supply_and_nine_fab_grid_review_are_distinct_events():
    expansion = {
        "title": '김성환 "호남 반도체 팹 9기면 14GW 필요…전력망 계획 원점 점검"(종합) - 뉴시스',
        "publisher": "뉴시스",
        "official": False,
        "published": "Tue, 06 Oct 2026 08:14:00 GMT",
        "plan_stage": "장관 국감 발언",
        "category": "전력수요·산단 인프라",
        "stage": 6,
        "id": "honam-a",
        "url": "https://example.com/a",
    }
    baseline = {
        "title": '기후장관 "호남 반도체산단에 전기 6.3GW·용수 65만t 공급가능" - 연합뉴스',
        "publisher": "연합뉴스",
        "official": False,
        "published": "Tue, 06 Oct 2026 06:01:00 GMT",
        "plan_stage": "장관 국감 발언",
        "category": "전력수요·산단 인프라",
        "stage": 6,
        "id": "honam-b",
        "url": "https://example.com/b",
    }
    assert semantic_event_key(expansion) == "12th-plan|honam-semiconductor|nine-fab-14gw-grid-review"
    assert semantic_event_key(baseline) == "12th-plan|honam-semiconductor|four-fab-6.3gw-water65-supply"
    assert semantic_event_key(expansion) != semantic_event_key(baseline)
    assert semantic_event_level(expansion) == 1
    assert semantic_event_level(baseline) == 1

    original_key = energy_runner.watch.event_key
    original_level = energy_runner.watch.event_level
    try:
        energy_runner.watch.event_key = semantic_event_key
        energy_runner.watch.event_level = semantic_event_level
        collapsed = collapse_events([expansion, baseline])
    finally:
        energy_runner.watch.event_key = original_key
        energy_runner.watch.event_level = original_level

    assert len(collapsed) == 2


def test_power_plan_delay_is_distinct_material_schedule_event():
    row = {
        "title": "[2026 국감] 12차 전기본 지연…'원전공론화 3개월' 놓고 여야 공방",
        "publisher": "전자신문",
        "official": False,
        "published": "Tue, 06 Oct 2026 08:01:00 GMT",
        "plan_stage": "일정 변경",
    }
    assert semantic_event_key(row) == "12th-plan|schedule|government-draft-delay"
    assert semantic_event_level(row) == 1


def test_duplicate_publisher_suffix_is_removed():
    assert display_title(
        '"전기본 위원 명단 왜 공개 안하나" - 머니투데이 - 머니투데이',
        "머니투데이",
    ) == '"전기본 위원 명단 왜 공개 안하나"'


def test_google_news_decoder_import_is_available():
    from googlenewsdecoder import gnewsdecoder
    assert callable(gnewsdecoder)


def test_government_draft_is_not_final_plan():
    assert plan_stage("12차 전기본 정부안 공개") == "정부안 공개"
    assert classify("12차 전기본 정부안 공개")[0] == "전기본 정부안"
    assert plan_stage("12차 전기본 최종안 의결") == "확정·의결"


def test_datacenter_overestimate_has_stable_material_key():
    row = {
        "title": '데이터센터 전력수요 급증 전망에 기후장관 "과잉된 면 있어"',
        "publisher": "연합뉴스",
        "official": False,
        "published": "Tue, 06 Oct 2026 08:10:00 GMT",
        "plan_stage": "전망·잠정안",
    }
    assert semantic_event_key(row) == "12th-plan|demand|datacenter-overestimate"
    assert semantic_event_level(row) == 1


def test_generic_power_plan_political_commentary_is_suppressed():
    row = {
        "title": "12차 전기본 놓고 여야 책임 공방 격화",
        "publisher": "테스트뉴스",
        "official": False,
        "published": "Tue, 06 Oct 2026 08:30:00 GMT",
        "plan_stage": "전기본 관련",
    }
    assert semantic_event_key(row).startswith("12th-plan|fact|")
    assert semantic_event_level(row) == 0


def test_datacenter_body_interpretation_surfaces_realization_gap():
    body = """
    제12차 전력수급기본계획 수요전망소위는 2040년 최대 전력수요를 158.4~165.0GW로 전망했다.
    AI 데이터센터 최대 전력수요는 4.0GW에서 11.9GW로 7.9GW 늘었다.
    전력계통영향평가를 통과한 데이터센터 96건 가운데 실제 전기를 받는 곳은 4곳이며 56건은 전기 사용 신청조차 하지 않았다.
    데이터센터 전력사용효율 PUE는 1.64를 가정했지만 실측 평균은 1.60, 세계 평균은 1.58이라는 지적이 나왔다.
    김성환 장관은 데이터센터 수요 전망에 과잉된 측면이 있다며 불확실성을 반영해 다시 보겠다고 답했다.
    """
    result = energy_runner.interpret_article_body(
        {"title": '데이터센터 전력수요 급증 전망에 기후장관 "과잉된 면 있어"', "category": "전력수요 전망"},
        body,
        "",
    )
    assert "158.4~165.0GW" in result
    assert "4.0GW → 11.9GW" in result
    assert "96건" in result and "4곳" in result
    assert "56건" in result
    assert "PUE" in result

# live-regression-20261006-v2


def test_committee_disclosure_never_notifies_even_when_unseen():
    row = {
        "title": '"전기본 위원 공개하라"·"尹정부도 안해"…국힘·김성환 충돌 - 연합뉴스',
        "publisher": "연합뉴스",
        "official": False,
        "published": "Tue, 06 Oct 2026 02:51:00 GMT",
        "plan_stage": "발표·공개",
    }
    assert semantic_event_key(row) == "12th-plan|committee-governance|member-disclosure"
    assert semantic_event_level(row) == 0
