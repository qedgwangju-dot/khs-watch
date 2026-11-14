#!/usr/bin/env python3
"""Offline tests for source-graded Hungarian battery and SNE alert gates."""
import datetime as dt
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import physical_ai_watch_airan_guard as watcher
from robot_watch_hungary_battery_risk import BACKFILL, HUNGARY, SNE_MARKET, DELAYED_SHUTDOWN_KEY
base=watcher.base

def item(title, desc="", source="Telex", published="2026-11-14T00:00:00+00:00"):
    return {"title":title,"description":desc,"source":source,"link":"https://example.org/article","published":published}

def audit(row):
    text=" ".join(str(row.get(k) or "") for k in ("title","description","source"))
    g=base.topic_group(text)
    return g,base.score(row),base.key(row),base.category(text,g) if g else ""

original_now=base.NOW
try:
    base.NOW=dt.datetime(2026,11,14,14,30,tzinfo=dt.timezone.utc)
    source=base.query_news(BACKFILL)
    assert len(source)==1 and source[0].get("hungary_authority_backfill")
    g,s,k,c=audit(source[0])
    assert g==HUNGARY and s>=11 and k==hashlib.sha256(DELAYED_SHUTDOWN_KEY.encode()).hexdigest()
    assert "101" in source[0]["description"] and "201" in source[0]["description"]
    assert "미확인" in source[0]["description"]
    past=item("Volta Energy Solutions Hungary 101 production suspension","헝가리 11월 4일 가동 중단, 법정 최대 과태료 50억포린트","더투데이")
    assert audit(past)[0]==HUNGARY and audit(past)[1]==0,"Old shutdown retell must not be sent as fresh"
    law=item("헝가리 280/2026 법정 최대 50억포린트 과태료 상한","솔루스첨단소재 헝가리 공장 우려","Reuters")
    assert audit(law)[1]==0,"Legal cap is not actual company fine"
    new_fine=item("SK On Iváncsa environmental fine imposed for new contamination","actual order issued by authority","Kormányhivatalok","2026-11-21T00:00:00+00:00")
    assert audit(new_fine)[0]==HUNGARY and audit(new_fine)[1]>=11
    press_fine=item(new_fine["title"],new_fine["description"],"Telex",new_fine["published"])
    assert audit(press_fine)[1]==0,"Unconfirmed press report cannot become official penalty"
    reopen=item("Volta Energy Solutions Hungary production resumed in Környe hall 101","Independent experts verified repair","Kormányhivatalok","2026-11-23T00:00:00+00:00")
    assert audit(reopen)[0]==HUNGARY and audit(reopen)[1]>=11 and audit(reopen)[2]!=k
    sne=item("Jan-Sep 2026 Global (Excl. China) EV Battery Usage at 426.7GWh","SNE Research ex-China EV battery market share","SNE Research","2026-11-04T00:00:00+00:00")
    assert audit(sne)[0]==SNE_MARKET and audit(sne)[1]==0,"Sep official baseline must not replay"
    october=item("Jan-Oct 2026 Global (Excl. China) EV Battery Usage","SNE Research battery usage and market share","SNE Research","2026-12-04T00:00:00+00:00")
    oct_reprint=item("2026년 1~10월 중국 제외 전기차 배터리 점유율","SNE리서치 비중국 시장 배터리 사용량 GWh","SNE리서치","2026-12-05T00:00:00+00:00")
    assert audit(october)[1]>=11 and audit(october)[2]==audit(oct_reprint)[2],"Monthly source rewrites must dedup by period"
    generic=item("CATL 2026 Debrecen Hungary trial cell production","First two lines start trial","CATL","2026-09-22T00:00:00+00:00")
    assert audit(generic)[0]!=HUNGARY,"Existing CATL capacity lane stays intact"
    base.NOW=dt.datetime(2026,11,19,0,0,tzinfo=dt.timezone.utc)
    assert base.query_news(BACKFILL)==[],"One-off recovery must expire"
finally:
    base.NOW=original_now
print("Hungary battery compliance and SNE source-grade offline regressions: PASS")
