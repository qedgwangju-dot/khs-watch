from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_yahoo_contract_oi_never_enters_cta_gate():
    text = read("scripts/treasury_cta_squeeze_market_watch.py")
    # Root-cause guard: Yahoo may distribute a contract/rolled-contract OI that is
    # not comparable with CFTC whole-market weekly OI. The fallback lane must
    # source OI only from CFTC when CME official OI is unavailable.
    assert 'oi = row.get("openInterest")' not in text
    assert 'oi_scope": "CFTC_TFF_WHOLE_MARKET_WEEKLY"' in text
    assert "CFTC TFF 주간 전체 시장 OI" in text


def test_cta_headline_does_not_present_4_3_as_live_policy_target():
    audited = read("scripts/treasury_cta_squeeze_audited_watch.py")
    assert "4.3% 시나리오가 실제로 작동하는지 판정" not in audited
    assert "장기금리 하락 전환이 실제로 시작됐는지 판정" in audited


def test_cta_scheduled_thresholds_adapt_to_live_yield_regime():
    text = read("scripts/treasury_cta_squeeze_equity_watch.py")
    assert "def _yield_regime_line" in text
    assert "5.25% 이상 초고금리 구간" in text
    assert "5.00~5.25% 고금리 구간" in text
    assert "4.30%는 과거 시장 시나리오의 보조 하단" in text
    assert "10Y 4.50→4.40→4.35→4.30%와 -1σ/-2σ 진입" not in text


def test_buyback_initial_reaction_is_not_presented_as_persistent_effect():
    text = read("scripts/treasury_buyback_policy_watch.py")
    assert "<b>발표 직후 초기 시장 반응</b>" in text
    assert "지속효과 판정은 아래 실제 집행·금리·CTA 체인에서 별도로 확인" in text


def test_bessent_oil_scenario_is_conditional_and_causal_verdict_uses_multi_day_window():
    text = read("scripts/treasury_alert_korean_guard.py")
    assert "UPGRADE_REVISION = 12" in text
    assert "def oil_scenario_block" in text
    assert "def oil_scenario_key" in text
    assert "def _url_bytes" in text
    assert "from datetime import date, datetime, timedelta" in text
    assert "oil_scenario_stable" in text
    assert "bessent_oil_scenario_key" in text
    assert "이란 분쟁 종료 + 공급과잉" in text
    assert "재무부의 공식 가격목표가 아닙니다" in text
    assert "changes_5d" in text
    assert 'regime_changes = changes_5d or changes' in text
    assert 'c = snapshot.get("changes_5d") or snapshot["common_changes"]' in text
    assert "5거래일 공통창" in text
    # This was true only before the first expanded operation; it must never
    # survive as a current statement in a future one-time upgrade.
    assert "아직 확대된 바이백은 집행되지 않았" not in text
    assert "현재 하루 움직임만으로" not in text
    assert "EIA Brent는 Europe 현물 시계열" in text
    assert "ICE Brent 선물과 섞어" in text



def test_buyback_chain_uses_same_multi_day_horizon_as_causal_verdict():
    text = read("scripts/treasury_buyback_chain_enrich.py")
    assert 'changes = snapshot.get("changes_5d") or snapshot.get("common_changes") or {}' in text
    assert '"basis": basis' in text
    assert "금리 반응({causal.get('basis','기준 확인 불가')} {window})" in text
    assert "nom_bp >= 2.0" in text
    assert "nom_bp >= 2.0 and real_bp >= 2.0" in text
    assert "nom_bp > 0" not in text


def test_policy_state_commit_is_race_safe():
    workflow = read(".github/workflows/treasury-buyback-policy-telegram-alert.yml")
    text = read("scripts/treasury_buyback_policy_state_commit.py")
    assert "run: python scripts/treasury_buyback_policy_state_commit.py" in workflow
    assert "git pull --rebase origin main" not in workflow
    assert 'git("fetch", "origin", "main")' in text
    assert "merge_state(remote, local)" in text
    assert 'git("reset", "--hard", "origin/main")' in text
    assert '"HEAD:main"' in text
    assert 'range(1, 6)' in text

def test_yen_verbal_intervention_is_checked_for_persistence_not_hard_peg():
    text = read("scripts/yen_carry_policy_equity_enrich.py")
    assert "특정 USD/JPY 숫자를 공식 방어선으로 선언한 것으로 보지 않습니다" in text
    assert "5영업일·20영업일 지속효과" in text
    assert "발언 이전 약세권으로 복귀하면 구두개입 효과 약화" in text


def test_treasury_compact_alert_uses_data_dates_not_false_latest_causality():
    import sys
    import json
    import importlib
    sys.path.insert(0, str(ROOT / "scripts"))
    guard = importlib.import_module("treasury_alert_korean_guard")
    s = json.loads(read("data/treasury_buyback_policy_state.json"))
    snapshot = dict(s["bessent_causal_snapshot"])
    snapshot["is_lagged"] = True
    snapshot["lag_market_sessions"] = 3
    snapshot["latest_bond_common_date"] = "2026-10-09"
    message = guard.one_time_alert(1341.49, "2026-10-09 ECB 기준", snapshot)
    assert "공통 2026-09-29→2026-10-06" in message
    assert "Brent(EIA) 2026-10-06 vs 국채 2026-10-09" in message
    assert "최신 인과판정 보류" in message
    assert "이란 분쟁 종료 + 공급과잉" in message
    assert "모형 추정치" in message
    assert "새로운 정책 발표가 아닙니다" in message
    assert len(message) < 3300, len(message)


def test_treasury_causal_term_premium_not_mixed_off_date():
    text = read("scripts/treasury_alert_korean_guard.py")
    assert 'term_start in term_map and cur_date in term_map' in text
    assert 'term_d = direction(term_aligned["change_bp"], 2.0)' in text
    assert "lag_market_sessions >= 2" in text
    assert 'verdict_key = "mixed"' in text
