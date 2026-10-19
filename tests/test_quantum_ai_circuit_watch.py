import datetime as dt
import json
import unittest
from zoneinfo import ZoneInfo
import quantum_ai_circuit_watch as q

class QuantumCircuitMilestoneTests(unittest.TestCase):
    def setUp(self):
        self.now=dt.datetime(2026,10,19,9,53,tzinfo=ZoneInfo("Asia/Seoul"))

    def atom(self,version=1):
        return ('<feed xmlns="http://www.w3.org/2005/Atom">'
            '<entry><id>http://arxiv.org/abs/2610.22367v'+str(version)+'</id>'
            '<title>Discovering state-of-the-art quantum circuits with large language models</title>'
            '<updated>2026-10-18T12:00:00Z</updated></entry></feed>')

    def test_separate_original_benchmarks(self):
        self.assertAlmostEqual(5100000/440000,11.5909090909)
        self.assertAlmostEqual((1938-1837)/1938*100,5.2115583,places=4)
        self.assertTrue(q.baseline_event(q.ANTHROPIC_ORIGINAL))
        self.assertTrue(q.baseline_event(q.QUERA_ORIGINAL))

    def test_stage_classifier(self):
        checks=[
            ("Claude demonstrates quantum circuit optimization cutting Toffoli gates",
                "Claude and Harvard verified 440000 Toffoli gates from 5100000, improved qubits",
                "AI 양자회로 자원 절감 후속 실증"),
            ("QuEra demonstrates AI quantum hardware control",
                "Claude AI agent validated operating real quantum hardware", "실물 양자 하드웨어 적용·자동화"),
            ("Independent replication of Claude quantum circuits",
                "Other researchers reproduce Anthropic large language model quantum circuits", "독립 재현·검증"),
            ("Claude quantum circuit compiler commercial customer contract",
                "Anthropic has a paid license for this quantum compiler", "양자 설계·제어 유료 계약 또는 상용 채택"),
            ("Correction: Anthropic quantum circuits", "Claude quantum Toffoli estimates were corrected", "논문·결과 정정 또는 재현 실패"),
            ("Claude may reduce quantum circuit Toffoli costs",
                "Claude predicts 440000 Toffoli gate improvement",None),
            ("Google quantum chip has fewer errors","Willow reduced errors 40x",None),
            ("Anthropic quantum circuits","Claude has 5100000 Toffoli gates and 440000 optimized",None),
        ]
        for title,body,expect in checks:
            with self.subTest(title=title):
                self.assertEqual(q.stage(title,body),expect)

    def test_official_url_filter(self):
        self.assertEqual(q.official_url("/research/new-quantum-result","https://www.anthropic.com/research"),"https://www.anthropic.com/research/new-quantum-result")
        self.assertEqual(q.official_url("https://anthropic.com.evil.test/research/fake"),"")
        self.assertEqual(q.official_url("http://www.anthropic.com/research/fake"),"")
        self.assertEqual(q.official_url("https://www.anthropic.com/account"),"")
    
    def test_published_date_not_navigation(self):
        self.assertEqual(q.published_date('<meta property="article:published_time" content="2026-10-18T17:00:00Z"/>'),dt.date(2026,10,19))
        self.assertIsNone(q.published_date("<h1>Quantum circuits</h1>"))
    
    def test_baseline_does_not_resend(self):
        page='<a href="'+q.ANTHROPIC_ORIGINAL+'">Claude designs more efficient quantum circuits</a>'
        original='<meta property="article:published_time" content="2026-10-16"/><h1>Claude quantum circuits</h1>5100000 gates'
        def source(url):
            if url in (x[1] for x in q.INDEXES): return page
            if url==q.ARXIV: return self.atom(1)
            if url==q.CODE_RELEASES: return "[]"
            if url==q.ANTHROPIC_ORIGINAL: return original
            raise KeyError(url)
        results,notes,healthy=q.collect(self.now,getter=source)
        self.assertEqual(results,[])
        self.assertEqual(healthy,5)
    
    def test_new_official_after_baseline(self):
        next_url="https://www.anthropic.com/research/new-quantum-gate-test"
        page='<a href="'+next_url+'">Claude demonstrates quantum circuit optimization cutting Toffoli gates</a>'
        detail=('<meta property="article:published_time" content="2026-10-18T10:00:00Z"/>'
                '<article>Claude and Harvard verified 440000 Toffoli gates from 5100000 '
                'and improved qubit utilization in quantum circuits</article>')
        def source(url):
            if url in (x[1] for x in q.INDEXES): return page
            if url==next_url: return detail
            if url==q.ARXIV: return self.atom(1)
            if url==q.CODE_RELEASES: return "[]"
            raise KeyError(url)
        found,notes,healthy=q.collect(self.now,getter=source)
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]["stage"],"AI 양자회로 자원 절감 후속 실증")
        self.assertEqual(found[0]["date"],"2026-10-18")
        self.assertEqual(healthy,5)

    def test_arxiv_revision_and_code_release(self):
        release={"name":"v2 validated quantum circuit benchmark","body":"Reproduced exact Toffoli cost with proof",
                 "tag_name":"v2","published_at":"2026-10-18T02:00:00Z",
                 "html_url":"https://github.com/andigu/uncompute/releases/tag/v2"}
        def source(url):
            if url in (x[1] for x in q.INDEXES): return ""
            if url==q.ARXIV: return self.atom(2)
            if url==q.CODE_RELEASES: return json.dumps([release])
            raise KeyError(url)
        found,notes,healthy=q.collect(self.now,getter=source)
        self.assertEqual(len(found),2)
        self.assertEqual(set(x["stage"] for x in found),
                         {"논문 개정판 공개(개선·정정 내용 별도 검증 필요)","연구자 검증코드 정식 릴리스(성능 개선 여부 별도 확인)"})

    def test_official_partial_failure_and_total_failure(self):
        def partial(url):
            if url==q.CODE_RELEASES: return "[]"
            raise OSError("source blocked")
        found,notes,healthy=q.collect(self.now,getter=partial)
        self.assertEqual(healthy,1)
        self.assertTrue(any("실패" in note for note in notes))
        with self.assertRaisesRegex(RuntimeError,"모든 공식 원천 조회 실패"):
            q.collect(self.now,getter=lambda _: (_ for _ in ()).throw(OSError("fail")))

    def test_alert_text_factual_boundaries(self):
        event={"title":"Independent replication of Claude quantum circuits",
               "stage":"독립 재현·검증","date":"2026-10-18",
               "url":"https://www.anthropic.com/research/replication",
               "evidence":"공식 기업·연구기관 발표"}
        body=q.render([event],self.now)
        self.assertIn("타원곡선 재설계",body)
        self.assertIn("실제 하드웨어 적용, 유료 고객·매출을 구분",body)
        self.assertNotIn("<script",body)

if __name__=="__main__":
    unittest.main()
