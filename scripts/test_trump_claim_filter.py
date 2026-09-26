#!/usr/bin/env python3
"""Regression guards for Trump portfolio-claim relevance filtering."""
from trump_portfolio_claim_watch import is_portfolio_claim_relevant


def main():
    dinner = "Trump-Xi dinner had OpenAI, Nvidia, Meta. Anthropic was absent"
    assert not is_portfolio_claim_relevant(dinner), "Dinner/guest-list article must not trigger portfolio alert"

    viral = "Trump's updated portfolio is basically a bet that America wins the AI race."
    assert is_portfolio_claim_relevant(viral), "True portfolio-composition claim must remain eligible"

    oge_trade = "Trump financial disclosure shows Strategy stock purchases"
    assert not is_portfolio_claim_relevant(oge_trade), "OGE transaction story must be routed to OGE watcher"

    print("Trump claim filter regression checks passed.")


if __name__ == "__main__":
    main()
