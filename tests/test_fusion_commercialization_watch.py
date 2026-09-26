#!/usr/bin/env python3
from scripts import fusion_commercialization_watch as f

def main():
    official = "House Committee on Science, Space, and Technology"
    assert f.allowed(official)
    assert f.official_publisher(official)
    assert not f.allowed("Heatmap News")

    title = "Lofgren and Obernolte Lead Introduction of American Leadership in Fusion Act"
    summary = "The bipartisan American Leadership in Fusion Act would provide $10 billion in direct investments for fusion commercialization."
    text = f.text_of(title, summary, official)
    stage, score = f.stage(text)
    assert stage == "법안 발의", stage
    assert score >= 80
    assert f.event_key(title, summary, official) == "american-leadership-in-fusion-act:법안 발의"

    hts_title = "Fusion company signs REBCO magnet supply contract"
    hts_summary = "A new HTS magnet procurement contract expands qualification and capacity."
    hts_text = f.text_of(hts_title, hts_summary, "Reuters")
    hts_stage, _ = f.stage(hts_text)
    assert hts_stage == "HTS·초전도 공급망 실행", hts_stage

    print("fusion_commercialization_watch_tests=passed")

if __name__ == "__main__":
    main()
