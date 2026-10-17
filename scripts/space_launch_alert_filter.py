#!/usr/bin/env python3
"""Validate and clean space launch alert contents before Telegram sending."""
from __future__ import annotations
import pathlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from space_launch_event_guard import eligible, correction_notices
