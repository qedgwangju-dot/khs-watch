#!/usr/bin/env python3
"""Run explicitly selected unittest modules with in-process outbound IO blocked."""
import socket
import sys
import unittest
import urllib.request
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch


def deny_network(*args, **kwargs):
    raise AssertionError("Network prohibited in no-send regression suite")


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Pass explicit unittest module paths; implicit full discovery is disabled")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    with ExitStack() as guards:
        # Guard discovery/import time too. Tests may mock urlopen with a local
        # fixture, but lower-level DNS and sockets remain blocked throughout.
        guards.enter_context(patch.object(socket, "socket", side_effect=deny_network))
        guards.enter_context(patch.object(socket, "create_connection", side_effect=deny_network))
        guards.enter_context(patch.object(socket, "getaddrinfo", side_effect=deny_network))
        guards.enter_context(patch.object(urllib.request, "urlopen", side_effect=deny_network))
        program = unittest.main(module=None, argv=sys.argv, exit=False)
    return 0 if program.result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
