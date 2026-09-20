import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "clarity_alert_readability", ROOT / "scripts" / "clarity_alert_readability.py"
)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class ClarityAlertReadabilityTest(unittest.TestCase):
    def test_ethics_alert_is_scannable_without_losing_detail(self):
        event = {
            "source": "Associated Press 윤리합의 검증",
            "event_type": "행정부·핵심 당사자 통과 촉구 — 윤리 합의 진전",
            "event_subtype": "tillis_gallego_ethics_compromise",
            "title": "Trump 대통령, Tillis–Gallego 윤리안 핵심 조항 수용 — 공식 문안 확인 대기",
            "url": "https://apnews.com/article/521fd5986eb107413064018f7a468c51",
            "date": "",
            "detail": (
                "Associated Press가 고위 공화당 보좌관을 인용해 Trump 대통령이 Tillis–Gallego 양당 윤리 절충안의 약 80%를 수용했다고 보도했습니다. "
                "주 검찰총장 집행 권한도 포함된 것으로 전해졌습니다. 개정안 원문은 아직 공개 전입니다."
            ),
            "verification_status": "보좌관·신뢰매체 확인 / 백악관 공개 확인 및 개정 원문 대기",
            "evidence_sources": ["Associated Press", "Reuters"],
            "reported_title": "Trump agrees to new bipartisan ethics provision in massive crypto bill",
        }
        rendered = "\n".join(MOD.build_readable([event]))
        self.assertIn("<b>한눈에 보기</b>", rendered)
        self.assertIn("<b>🧭 무엇이 달라졌나</b>", rendered)
        self.assertIn("<b>📍 현재 판정</b>", rendered)
        self.assertIn("<b>💰 투자 의미</b>", rendered)
        self.assertIn("<b>✅ 확인된 사실</b>", rendered)
        self.assertIn("<b>⚠️ 아직 미확정</b>", rendered)
        self.assertIn("<b>⏱ 다음 확인</b>", rendered)
        self.assertIn("<b>🔎 근거</b>", rendered)
        self.assertIn("약 80%", rendered)
        self.assertIn("주 검찰총장 집행 권한", rendered)
        self.assertIn("Associated Press · Reuters", rendered)
        self.assertIn('<a href="https://apnews.com/article/521fd5986eb107413064018f7a468c51">원문</a>', rendered)
        self.assertNotIn("Trump agrees to new bipartisan ethics provision in massive crypto bill", rendered)
        self.assertLessEqual(max(map(len, MOD.build_readable([event]))), 3900)

    def test_oira_prerule_starts_with_easy_real_world_meaning(self):
        event = {
            "source": "OIRA/RegInfo — CFTC",
            "event_type": "CFTC OIRA 규제검토 — Prerule",
            "title": "Regulation Crypto Asset Transactions and Regulation Crypto Asset Markets",
            "url": "https://www.reginfo.gov/public/do/eoReviewSearch?agencyCode=3038",
            "date": "09/17/2026",
            "detail": "RIN 3038-AF80 | Status: Pending Review | Stage: Prerule | Economically Significant: No | Legal Deadline: None",
        }
        rendered = "\n".join(MOD.build_readable([event]))
        self.assertIn("<b>🧩 한마디로</b>", rendered)
        self.assertIn("CLARITY가 의회에서 막혀도 CFTC가 기다리지 않고", rendered)
        self.assertIn("레버리지·마진 거래", rendered)
        self.assertIn("사전규칙 단계", rendered)
        self.assertIn("아직 미확정", rendered)
        self.assertIn("OIRA 검토 종료", rendered)
        self.assertLessEqual(max(map(len, MOD.build_readable([event]))), 3900)

    def test_article_is_evidence_not_monitoring_unit(self):
        event = {
            "source": "Bloomberg Law 발언 검증",
            "event_type": "행정부·핵심 당사자 통과 촉구",
            "event_subtype": "national_security_pressure",
            "title": "Bessent 재무장관, 상원에 CLARITY 법안 절차 진행을 촉구",
            "url": "https://example.com/source",
            "date": "Thu, 10 Sep 2026 04:18:00 +0000",
            "detail": "Bessent 재무장관이 상원에 절차 진행을 촉구했습니다. 국가안보 논리도 강조했습니다.",
            "policy_actor": "Bessent 재무장관",
            "evidence_sources": ["Bloomberg Law", "CoinDesk"],
            "monitoring_unit": "event_state_change",
            "reported_title": "A publisher-specific headline that should never become the alert identity",
        }
        rendered = "\n".join(MOD.build_readable([event]))
        self.assertIn("Bessent 재무장관", rendered)
        self.assertIn("Bloomberg Law · CoinDesk", rendered)
        self.assertNotIn("publisher-specific headline", rendered)
        self.assertIn("시간표 ↑", rendered)

    def test_media_first_draft_release_is_clear_and_not_called_official_yet(self):
        event = {
            "source": "The Block 문안 공개 검증",
            "event_type": "법안 문안 공개·핵심 수정 — 신뢰매체 확인",
            "event_subtype": "senate_revised_draft_release",
            "title": "상원 공화당, CLARITY 최신 초안 공개 — 공식 원문 재확인 중",
            "url": "https://example.com/draft-report",
            "date": "Mon, 14 Sep 2026 00:24:37 -0400",
            "detail": (
                "The Block가 상원 공화당이 CLARITY 최신 초안을 공개했다고 보도했습니다. "
                "법안 문안 자체가 바뀐 상태 변화입니다. 공식 원문으로 조항을 확인해야 합니다."
            ),
            "verification_status": "신뢰매체 문안 공개 확인 / Senate Banking·GovInfo·Congress.gov 공식 원문 재확인 대기",
            "evidence_sources": ["The Block"],
            "monitoring_unit": "event_state_change",
            "text_release": True,
        }
        rendered = "\n".join(MOD.build_readable([event]))
        self.assertIn("문안 변화 확인", rendered)
        self.assertIn("신뢰매체", rendered)
        self.assertIn("공식 Senate Banking·GovInfo·Congress.gov 원문", rendered)
        self.assertIn("법안 문안 자체가 바뀐 상태 변화", rendered)
        self.assertIn("돈 버는 능력 → 아직 직접 변화 없음", rendered)
        self.assertIn("시간표 ↑", rendered)
        self.assertIn("공식 개정 법안 PDF·텍스트 확보", rendered)
        self.assertNotIn("Trump 대통령, CLARITY 법안 처리·통과를 의회에 촉구", rendered)
        self.assertLessEqual(max(map(len, MOD.build_readable([event]))), 3900)


if __name__ == "__main__":
    unittest.main()
