from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_required_treasury_workflows_exist():
    required = [
        ".github/workflows/qra-recurring-telegram-alert.yml",
        ".github/workflows/treasury-buyback-policy-telegram-alert.yml",
        ".github/workflows/treasury-buyback-media-telegram-alert.yml",
        ".github/workflows/treasury-auction-final-demand-telegram-alert.yml",
        ".github/workflows/treasury-net-liquidity-telegram-alert.yml",
        ".github/workflows/treasury-foreign-demand-telegram-alert.yml",
        ".github/workflows/treasury-cta-squeeze-telegram-alert.yml",
        ".github/workflows/global-rates-telegram-watch.yml",
    ]
    missing = [p for p in required if not (ROOT / p).exists()]
    assert not missing, f"missing Treasury alert workflows: {missing}"


def test_new_watchers_compile_source_present():
    for p in [
        "scripts/treasury_auction_final_demand_watch.py",
        "scripts/treasury_net_liquidity_watch.py",
    ]:
        text = (ROOT / p).read_text(encoding="utf-8")
        compile(text, p, "exec")
