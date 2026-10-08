#!/usr/bin/env python3
"""Run the canonical crypto liquidity watcher without replacing its ETF parser.

The parser, missing-fund treatment, stale-source protection and rolling windows
must have a single implementation in crypto_liquidity_watch.py.
"""
from scripts import crypto_liquidity_watch as watch


if __name__ == "__main__":
    watch.main()
