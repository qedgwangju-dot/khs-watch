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
    assert f.alertable_stage(hts_stage)

    generic_title = "Office of Fusion - Department of Energy (.gov)"
    generic_summary = "Office of Fusion"
    generic_text = f.text_of(generic_title, generic_summary, "Department of Energy (.gov)")
    generic_stage, _ = f.stage(generic_text)
    assert generic_stage == "기타 핵융합 변화", generic_stage
    assert not f.alertable_stage(generic_stage)
    assert not any(term in generic_text for term in f.HARD)

    office_change = "DOE established the Office of Fusion to coordinate fusion commercialization activities."
    office_stage, _ = f.stage(office_change.lower())
    assert office_stage == "DOE 전담조직 제도화", office_stage
    assert f.alertable_stage(office_stage)

    print("fusion_commercialization_watch_tests=passed")

if __name__ == "__main__":
    main()
