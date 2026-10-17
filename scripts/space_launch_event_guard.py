#!/usr/bin/env python3
"""Event-type checks for space-launch monitoring."""
import re

def kind(category, title):
    t=title.lower()
    if category=='rocketlab' and 'neutron' in t and re.search(r'delay|postpon|2027',t):
        return 'development_delay'
    if re.search(r'price target|target price|목표주가',t):
        return 'analyst'
    return 'other'
