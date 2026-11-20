"""Regression for the two title-only decision-timing variants from run 910."""
import unittest

import war_peace_reconstruction_watch_integrity as stage
import war_peace_reconstruction_watch_two_color as presentation


class KoreanDeferredDecisionTests(unittest.TestCase):
    def setUp(self):
        # Headlines only: the run's full retained snapshot remains in the local
        # audit, not in the repository fixture or its git history.
        self.titles = (
            '트럼프 “이란 추가 공습 결정, 새해 이후에 논의…서두르지 않아” - 동아일보',
            '트럼프, 이란 추가 공습 결정 내년으로 미뤄…"시간 있다" - 뉴스1',
        )

    @staticmethod
    def row(title):
        return {'title_original': title, 'title_ko': title,
                'body_verified': False, 'classification_color': 'red',
                'tags': ['확전']}

    def test_both_actual_titles_are_neutral_decision_context(self):
        for title in self.titles:
            with self.subTest(title=title):
                row = self.row(title)
                self.assertTrue(presentation._iran_attack_decision_deferred_ko(stage, row))
                self.assertIsNone(presentation.direction(stage, row))

    def test_independent_attack_or_diplomacy_is_not_hidden(self):
        for suffix in ('…이란 추가 공습 감행', '…이란 미사일 발사', '…사우디 시설 피격',
                       '…이란 제재 강화', '…휴전 협상 재개', '…추가 공습 예고',
                       '; sanctions threatened', '; forces launched an attack'):
            with self.subTest(suffix=suffix):
                row = self.row(self.titles[1] + suffix)
                self.assertFalse(presentation._iran_attack_decision_deferred_ko(stage, row))
        attack = self.row(self.titles[1] + '…이란 추가 공습 감행')
        self.assertEqual(presentation.direction(stage, attack), 'red')

    def test_verified_body_and_non_deferred_decision_keep_existing_path(self):
        verified = self.row(self.titles[0])
        verified['body_verified'] = True
        self.assertFalse(presentation._iran_attack_decision_deferred_ko(stage, verified))
        no_deferral = self.row('트럼프, 이란 추가 공습 결정 발표')
        self.assertFalse(presentation._iran_attack_decision_deferred_ko(stage, no_deferral))


if __name__ == '__main__':
    unittest.main()
