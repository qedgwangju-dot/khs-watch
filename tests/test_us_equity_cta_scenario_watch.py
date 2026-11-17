from __future__ import annotations
import datetime as dt,json,sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import us_equity_cta_scenario_watch as cta
NOTE="""11월 17일 골드만삭스가 발간한 Eq Positioning and Key Levels에 따르면 CTA의 수급 전환 가능성을 제기했다.
향후 1주일 CTA 수급 전망: 상승할 경우 글로벌 주식 기준 약 308억 달러, 미국 주식에서는 약 161억 달러 매수.
횡보하는 상황에서도 글로벌 주식 약 230억 달러, 미국 주식 약 99억 달러 매수.
하락 시나리오에서는 글로벌 주식 약 61억 달러, 미국 주식 약 52억 달러 매도.
향후 1개월 시나리오: 주가 상승 시 글로벌 주식 약 891억 달러 매수,
하락 시에는 약 1,230억 달러 매도."""
PUB=dt.date(2026,11,17)

def test_model_and_periods_are_separate():
    x=cta.parse_note(NOTE,PUB)
    assert x["report"]=="2026-11-17"
    assert x["week"]=={"up":[30.8,16.1],"flat":[23.0,9.9],"down":[-6.1,-5.2]}
    assert x["month"]=={"up_global":89.1,"down_global":-123.0}

def test_dated_and_complete_fail_closed():
    assert cta.parse_note(NOTE,dt.date(2026,10,17)) is None
    assert cta.parse_note(NOTE.replace("11월 17일 골드만삭스","금융사"),PUB) is None
    assert cta.parse_note(NOTE.replace("99억 달러","미확인"),PUB) is None

def inputs(agree=True,verbatim=False):
    news=[("https://reuters.com/a",PUB,"Goldman CTA"),
          ("https://marketwatch.com/b",PUB,"CTA Goldman")]
    def fetch(url,timeout=9):
        body=NOTE
        if "marketwatch.com" in url:
            body=NOTE+("" if verbatim else " 별도 취재의 추가 설명.")
            if not agree:body=body.replace("161억","162억")
        return url,"<article>"+body+"</article>"
    return lambda:news,fetch

def test_two_independent_publishers_same_observation_only():
    news,read=inputs()
    found=cta.collect(today=PUB,discovery=news,reader=read)
    assert found["status"]=="verified_secondary"
    assert found["note"]["week"]["flat"][1]==9.9
    assert cta.collect(today=PUB,discovery=lambda:news()[:1],reader=read)["status"]=="withheld"
    news,read=inputs(agree=False)
    assert cta.collect(today=PUB,discovery=news,reader=read)["status"]=="withheld"
    news,read=inputs(verbatim=True)
    assert cta.collect(today=PUB,discovery=news,reader=read)["status"]=="withheld"

def test_report_and_krw_are_explicitly_estimates():
    n,r=inputs()
    found=cta.collect(today=PUB,discovery=n,reader=r)
    text=cta.render(found,"1335.00","2026-11-17")
    assert "99억달러(약 13조 2,165억원)" in text
    assert "52억달러(약 6조 9,420억원)" in text
    assert "실제 체결된 CTA" in text
    assert "CFTC Leveraged Funds" in text

def test_validate_only_preserves_delivery_and_duplicate_keys():
    n,r=inputs()
    with TemporaryDirectory() as tmp:
        state=Path(tmp)/"cta.json"
        sender=Mock(return_value={"message_id":991,"chat_id_returned":True,"chat_id_match":True})
        fx=lambda _day:("1335.00","2026-11-17")
        a=cta.run(validate_only=True,today=PUB,discovery=n,reader=r,
                  state_path=state,sender=sender,fx_reader=fx)
        assert a["status"]=="alert_due"
        assert sender.call_count==0 and not state.exists()
        b=cta.run(validate_only=False,today=PUB,discovery=n,reader=r,
                  state_path=state,sender=sender,fx_reader=fx)
        assert b["telegram_sent"] and sender.call_count==1
        state.write_text(cta.PENDING.read_text())
        c=cta.run(validate_only=False,today=PUB,discovery=n,reader=r,
                  state_path=state,sender=sender,fx_reader=fx)
        assert c["status"]=="duplicate_suppressed" and sender.call_count==1
