"""Test fixture: the REAL event calendar, made current and quiet.

Order-path tests ask "does a clean signal pass when the calendar is readable and nothing is scheduled?". Reading the
hand-maintained docs/architecture/event-calendar.json directly made them time bombs: the day its `snapshot.covers_through`
passed, every one of them failed (correctly, by the fail-safe) for a reason that has nothing to do with what they test.
The expiry itself is covered where it belongs (test_event_risk). This keeps every policy field of the real file and only
moves the coverage past `now` and empties the event list.
"""
import copy
import datetime
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PATH = os.path.join(ROOT, "docs", "architecture", "event-calendar.json")


def fresh(days=30):
    with open(PATH, encoding="utf-8") as fh:
        cal = copy.deepcopy(json.load(fh))
    until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days)
    cal["snapshot"]["covers_through"] = until.strftime("%Y-%m-%dT%H:%M:%SZ")
    cal["snapshot"]["id"] = cal["snapshot"]["id"] + "-test-fresh"
    cal["events"] = []
    return cal


def fresh_load(*_a, **_k):
    """Drop-in for event_risk.load(...) in a test harness."""
    return fresh()
