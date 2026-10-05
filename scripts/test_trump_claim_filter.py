#!/usr/bin/env python3
"""Regression guards for Trump portfolio-claim relevance filtering."""
import datetime as dt

from trump_portfolio_claim_watch import is_portfolio_claim_relevant, is_recent_publication


def main():
    dinner = "Trump-Xi dinner had OpenAI, Nvidia, Meta. Anthropic was absent"
    assert not is_portfolio_claim_relevant(dinner), "Dinner/guest-list article must not trigger portfolio alert"


    ebc = "The Trump Trade 2.0: How the US Election and Our New US Stock CFDs Can Rock Your Portfolio"
    assert not is_portfolio_claim_relevant(ebc), "Generic Trump Trade/CFD marketing article must not trigger portfolio alert"

    viral = "Trump's updated portfolio: Nvidia 10%, Tesla 9%, Apple 8.5% are the top holdings"
    assert is_portfolio_claim_relevant(viral), "True portfolio-weight claim must remain eligible"

    oge_trade = "Trump financial disclosure shows Strategy stock purchases"
    assert not is_portfolio_claim_relevant(oge_trade), "OGE transaction story must be routed to OGE watcher"

    benzinga_recap = "트럼프 포트폴리오 관전 포인트···스페이스X 상장 11일 후 매수, 다른 투자 종목은?"
    assert not is_portfolio_claim_relevant(benzinga_recap), "Historical SpaceX buy recap must not trigger portfolio claim alert"

    kb_recap = "트럼프는 무슨 주식을 샀나…6월 포트폴리오에 빅테크·금융·에너지 망라"
    assert not is_portfolio_claim_relevant(kb_recap), "Historical June buy/sell recap must not trigger portfolio claim alert"

    now = dt.datetime(2026, 10, 5, 6, 0, tzinfo=dt.timezone.utc)
    fresh = "Mon, 05 Oct 2026 04:30:00 GMT"
    stale = "Tue, 25 Aug 2026 00:00:00 GMT"
    assert is_recent_publication(fresh, now=now)
    assert not is_recent_publication(stale, now=now), "Old resurfaced articles must be rejected"

    print("Trump claim filter regression checks passed.")


if __name__ == "__main__":
    main()
