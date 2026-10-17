import datetime as dt
import email.utils
import unittest
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo
import google_quantum_magic_watch as q

class GoogleQuantumMagicTests(unittest.TestCase):
    def test_initial_duplicate_and_scenarios(self):
        self.assertIsNone(q.stage("Google magic state cultivation reports 40-fold error reduction at 99.99% logical fidelity",""))
        self.assertIsNone(q.stage("Google plans to demonstrate distance-7 cultivation",""))
        self.assertIsNone(q.stage("Google quantum chip 105 physical qubits",""))
        self.assertIsNone(q.stage("Google will implement a logical T-gate",""))
        self.assertIsNone(q.stage("Google magic state cultivation reports 8% retention",""))
    def test_real_completed_science_milestones(self):
        examples={
            "Google demonstrates distance-7 cultivation on Willow":"오류정정 코드 확장 실증",
            "Google reports cultivation with 60 physical qubits":"매직 상태 공정 물리 큐비트 확대",
            "Google reports cultivation state retention 22%":"후선택 통과율 개선 실증",
            "Google reports magic state fidelity 99.999%":"논리적 T-상태 충실도 개선 실증",
            "Google demonstrates real-time logical T-gate in cultivation":"논리적 T 게이트 실제 연산 적용",
            "Google demonstrates magic state cultivation with leakage removed":"큐비트 누설 억제 실증",
            "Google retracts magic-state cultivation paper":"과학적 정정·재현성 변화",
        }
        for title,expect in examples.items():
            with self.subTest(title=title):
                self.assertEqual(q.stage(title,""),expect)
    def test_rss_duplicates_untrusted_and_old_article(self):
        now=dt.datetime(2026,10,17,19,0,tzinfo=ZoneInfo("Asia/Seoul"))
        root=ET.Element("rss");chan=ET.SubElement(root,"channel")
        def add(title,url):
            e=ET.SubElement(chan,"item")
            ET.SubElement(e,"title").text=title
            ET.SubElement(e,"link").text=url
            ET.SubElement(e,"pubDate").text=email.utils.format_datetime(now)
            ET.SubElement(e,"description").text="Willow cultivation experiment"
        add("Google demonstrates distance-7 cultivation","https://blog.google/innovation-and-ai/models-and-research/quantum-computing/distance7/")
        add("Google demonstrates distance-7 cultivation","https://malicious.google.attacker.test/report")
        add("Google magic state cultivation reports 40-fold error reduction at 99.99% logical fidelity",q.BASE_URL)
        feed=ET.tostring(root,encoding="unicode")
        def getter(url):
            if url in [p[1] for p in q.FEEDS]: return feed
            return "<article>Real quantum cultivation Willow experiment</article>"
        news,notes=q.collect(now,getter=getter)
        self.assertEqual(len(news),1)
        self.assertEqual(news[0]["stage"],"오류정정 코드 확장 실증")
        self.assertEqual(len(notes),3)
    def test_atom_and_domain(self):
        feed='<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Google reports magic state retention 24%</title><link href="https://research.google/blog/quantum-test/"/><published>2026-10-17T12:00:00Z</published></entry></feed>'
        self.assertEqual(len(q.parse_feed(feed)),1)
        self.assertEqual(q.canonical("https://google.evil.example/"),"")
    def test_source_failure_not_silent(self):
        now=dt.datetime(2026,10,17,12,0,tzinfo=dt.timezone.utc)
        def broken(_): raise OSError("unavailable")
        with self.assertRaisesRegex(RuntimeError,"All Google official feeds failed"):
            q.collect(now,getter=broken)
    def test_message_is_not_repeated_old_news(self):
        now=q.now_kst()
        text=q.render([{"stage":"후선택 통과율 개선 실증","url":"https://blog.google/quantum/new/","published_kst":now.isoformat()}],now)
        self.assertIn("후선택 유지율 8%",text)
        self.assertIn("양산·상용계약·실제 매출은 구분",text)
        self.assertNotIn("<script",text)

if __name__=="__main__": unittest.main()
