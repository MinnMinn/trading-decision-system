"""Experiment IC (Claude discretionary ICT): the harness, the evaluator and the prompt template, on SYNTHETIC data only.

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_claude_ict
(docs/plans/2026-10-04-claude-ict-discretionary-preregistration.md; docs/plans/2026-10-04-claude-ict-implementation.md)

No real model call (a fake `claude` executable answers), no outcome on the real window: the evaluator is exercised on
hand-made bars, and on the temporary repositories only up to its refusals / preconditions.
"""
import contextlib
import datetime
import hashlib
import importlib.util
import io
import json
import os
import random
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts", "research"))
import claude_ict_common as K  # noqa: E402
import claude_ict_harness as H  # noqa: E402
import claude_ict_eval as E  # noqa: E402

TD = datetime.timedelta
D = datetime.date
Z = K.parse_z


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


PG = _load("prereg_guard_test_ic", "scripts/research/prereg_guard.py")


def git(root, *args):
    return subprocess.run(["git", "-C", root, *args], check=True, capture_output=True, text=True)


def bar(t, o, h, l, c):
    return {"time": t, "open": float(o), "high": float(h), "low": float(l), "close": float(c)}


def synth(start, end, seed, base):
    """5m BID bars Mon-Fri with the weekly gap (Fri 17:00 -> Sun 18:00 New York) and the daily break 17:00-18:00 New
    York; a deterministic random walk."""
    rng = random.Random(seed)
    t, stop, px, out = Z(start), Z(end), base, []
    while t < stop:
        et = t.astimezone(K.ET)
        wd = et.weekday()
        closed = wd == 5 or (wd == 4 and et.hour >= 17) or (wd == 6 and et.hour < 18) or et.hour == 17
        if not closed:
            o = px
            c = round(o + rng.uniform(-2, 2), 2)
            out.append(bar(K.iso_z(t), o, round(max(o, c) + rng.uniform(0, 1), 2), round(min(o, c) - rng.uniform(0, 1), 2), c))
            px = c
        t += K.BAR
    return out


def point(sym, kz, day):
    o, e = K.killzone_window(sym, kz, day)
    label = next(lab for k, lab, _a, _b in K.killzones(sym) if k == kz)
    return {"id": K.point_id(sym, kz, day), "instrument": sym, "killzone": kz, "killzone_label": label,
            "date_et": day.isoformat(), "kz_open_utc": K.iso_z(o), "kz_end_utc": K.iso_z(e),
            "time_exit_utc": K.iso_z(K.time_exit(o)[0])}


def user_block():
    with open(os.path.join(ROOT, K.TEMPLATE), encoding="utf-8") as fh:
        return H.split_template(fh.read())[1]


def answer(decision="LONG", order="limit", entry=100.0, stop=99.0, target=102.0, **kw):
    a = {"decision": decision, "order": order, "entry": entry, "stop": stop, "target": target,
         "valid_until": "killzone_end", "htf_bias": "bullish", "draw_on_liquidity": "buyside liquidity above PDH",
         "pd_array": "bullish FVG 10:05-10:15", "invalidation": "body close below the swept low",
         "reasoning": "Sellside liquidity swept, displacement and MSS; entry in the FVG toward buyside liquidity."}
    if decision == "NO_TRADE":
        a.update(order=None, entry=None, stop=None, target=None)
    a.update(kw)
    return a


# ================================================================================================ clock (CLAUDE.md §21)
class Clock(unittest.TestCase):
    def test_killzones_across_the_spring_dst_change(self):
        self.assertEqual(K.killzone_window("XAUUSD", "london", D(2026, 3, 6))[0], Z("2026-03-06T07:00:00Z"))   # EST
        self.assertEqual(K.killzone_window("XAUUSD", "london", D(2026, 3, 9))[0], Z("2026-03-09T06:00:00Z"))   # EDT
        self.assertEqual(K.killzone_window("US500", "ny_am", D(2026, 3, 6)), (Z("2026-03-06T13:30:00Z"), Z("2026-03-06T16:00:00Z")))
        self.assertEqual(K.killzone_window("US500", "ny_am", D(2026, 3, 9)), (Z("2026-03-09T12:30:00Z"), Z("2026-03-09T15:00:00Z")))
        self.assertEqual(K.killzone_window("US500", "ny_pm", D(2026, 3, 9))[1], Z("2026-03-09T20:00:00Z"))

    def test_killzones_across_the_autumn_dst_change(self):
        self.assertEqual(K.killzone_window("XAUUSD", "ny_am", D(2026, 10, 30)), (Z("2026-10-30T11:00:00Z"), Z("2026-10-30T14:00:00Z")))
        self.assertEqual(K.killzone_window("XAUUSD", "ny_am", D(2026, 11, 2)), (Z("2026-11-02T12:00:00Z"), Z("2026-11-02T15:00:00Z")))

    def test_a_wall_time_that_does_not_exist_or_exists_twice_is_refused(self):
        with self.assertRaises(ValueError):
            K.et_instant(D(2026, 3, 8), (2, 30))
        with self.assertRaises(ValueError):
            K.et_instant(D(2026, 11, 1), (1, 30))

    def test_the_server_day_follows_the_ftmo_clock_not_a_fixed_offset(self):
        """The FTMO-Demo server is +2 in US standard time and +3 in US DST (docs/audits/2026-09-29-ftmo-server-timezone.md):
        its midnight is 17:00 New York on both sides of the change. A fixed +3 would put 21:30Z in January on the next day."""
        self.assertEqual(K.server_date(Z("2026-01-15T21:30:00Z")), D(2026, 1, 15))
        self.assertEqual(K.server_date(Z("2026-07-15T21:30:00Z")), D(2026, 7, 16))
        self.assertEqual(K.server_midnight(D(2026, 3, 6)), Z("2026-03-05T22:00:00Z"))
        self.assertEqual(K.server_midnight(D(2026, 3, 10)), Z("2026-03-09T21:00:00Z"))
        for day in (D(2026, 3, 6), D(2026, 3, 10), D(2026, 10, 30), D(2026, 11, 3)):
            self.assertEqual(K.et_label(K.server_midnight(day))[-5:], "17:00")

    def test_the_time_exit_is_16_new_york_before_the_rollover_across_dst(self):
        for day, kz, want_exit, want_roll in ((D(2026, 3, 6), "london", "2026-03-06T21:00:00Z", "2026-03-06T22:00:00Z"),
                                              (D(2026, 3, 9), "london", "2026-03-09T20:00:00Z", "2026-03-09T21:00:00Z"),
                                              (D(2026, 11, 2), "ny_am", "2026-11-02T21:00:00Z", "2026-11-02T22:00:00Z")):
            o, _e = K.killzone_window("XAUUSD", kz, day)
            ex, roll = K.time_exit(o)
            self.assertEqual((ex, roll), (Z(want_exit), Z(want_roll)))

    def test_no_new_fill_between_the_time_exit_and_the_rollover(self):
        self.assertFalse(K.no_fill_after(Z("2026-07-07T19:55:00Z")))       # 15:55 New York
        self.assertTrue(K.no_fill_after(Z("2026-07-07T20:00:00Z")))        # 16:00
        self.assertTrue(K.no_fill_after(Z("2026-07-07T20:55:00Z")))        # 16:55
        self.assertFalse(K.no_fill_after(Z("2026-07-07T21:00:00Z")))       # 17:00 = the next server day


# ================================================================================================ decision points
class DecisionPoints(unittest.TestCase):
    def setUp(self):
        self.times = {s: [b["time"] for b in synth("2026-07-03T00:00:00Z", "2026-07-11T00:00:00Z", 1, 100.0)]
                      for s in K.INSTRUMENTS}

    def test_one_point_per_instrument_killzone_and_weekday_inside_the_window(self):
        pts, skipped = K.decision_points(self.times, Z("2026-07-06T00:00:00Z"), Z("2026-07-11T00:00:00Z"))
        self.assertEqual(len(pts), 5 * 5)                                  # Mon-Fri x (2 + 3) killzones
        self.assertEqual(skipped, [])
        self.assertEqual(pts[0]["id"], "2026-07-06|US500|london")
        self.assertEqual(len({p["id"] for p in pts}), len(pts))
        self.assertTrue(all(D.fromisoformat(p["date_et"]).weekday() < 5 for p in pts))
        self.assertEqual([p["kz_open_utc"] for p in pts], sorted(p["kz_open_utc"] for p in pts))

    def test_a_killzone_without_bars_is_skipped_and_counted(self):
        o, e = K.killzone_window("US500", "ny_pm", D(2026, 7, 8))
        self.times["US500"] = [t for t in self.times["US500"] if not K.iso_z(o) <= t < K.iso_z(e)]
        pts, skipped = K.decision_points(self.times, Z("2026-07-06T00:00:00Z"), Z("2026-07-11T00:00:00Z"))
        self.assertEqual(len(pts), 24)
        self.assertEqual([(s["id"], s["reason"]) for s in skipped], [("2026-07-08|US500|ny_pm", "no_data_in_killzone")])

    def test_a_killzone_cut_by_the_window_is_not_a_point(self):
        pts, _ = K.decision_points(self.times, Z("2026-07-06T06:30:00Z"), Z("2026-07-06T19:00:00Z"))
        self.assertEqual(sorted(p["id"] for p in pts), ["2026-07-06|US500|ny_am", "2026-07-06|XAUUSD|ny_am"])

    def test_the_real_window_is_the_pre_registered_one(self):
        self.assertEqual((K.WINDOW_START, K.WINDOW_LAST_BAR), ("2026-07-01T00:00:00Z", "2026-10-02T20:45:00Z"))
        self.assertEqual(K.window_bounds()[1], Z("2026-10-02T20:50:00Z"))
        self.assertEqual({k: [z[0] for z in v] for k, v in K.KILLZONES.items()},
                         {"forex": ["london", "ny_am"], "indices": ["london", "ny_am", "ny_pm"]})


# ================================================================================================ point in time
class GuardBar(dict):
    """A bar whose prices raise once its time is at / after `cut` -- the harness may read its time, never a price."""
    cut = None

    def __getitem__(self, k):
        if k in ("open", "high", "low", "close", "volume") and dict.__getitem__(self, "time") >= GuardBar.cut:
            raise AssertionError(f"read {k} of a bar at {dict.__getitem__(self, 'time')}, at/after the killzone open")
        return dict.__getitem__(self, k)


class PointInTime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candles = synth("2026-06-01T00:00:00Z", "2026-07-11T00:00:00Z", 7, 2000.0)
        cls.full = H.Bars("XAUUSD", cls.candles)
        cls.ub = user_block()

    def prompt(self, p, bars):
        return H.user_prompt(self.ub, p, bars, K.spread_snapshot(p["instrument"], Z(p["kz_open_utc"])))

    def test_truncation_probe_full_equals_cut_equals_changed_future(self):
        for sym, kz, day in (("XAUUSD", "london", D(2026, 7, 6)), ("XAUUSD", "ny_am", D(2026, 7, 8)),
                             ("US500", "ny_am", D(2026, 7, 7)), ("US500", "ny_pm", D(2026, 7, 10))):
            p = point(sym, kz, day)
            k = H.bisect.bisect_left(self.full.times, p["kz_open_utc"])
            changed = [dict(b, open=b["open"] * 2, high=b["high"] * 3, low=b["low"] / 3, close=b["close"] / 2)
                       for b in self.candles[k:]]
            a = self.prompt(p, H.Bars(sym, self.candles))
            b = self.prompt(p, H.Bars(sym, self.candles[:k]))
            c = self.prompt(p, H.Bars(sym, self.candles[:k] + changed))
            self.assertEqual(a.encode(), b.encode())
            self.assertEqual(a.encode(), c.encode())

    def test_the_harness_never_reads_a_price_at_or_after_the_killzone_open(self):
        p = point("US500", "ny_am", D(2026, 7, 8))
        GuardBar.cut = p["kz_open_utc"]
        guarded = [GuardBar(b) for b in self.candles]
        text = self.prompt(p, H.Bars("US500", guarded))            # raises if any later price is read
        self.assertIn("Decision time = killzone open: 2026-07-08T12:30Z", text)
        with self.assertRaises(AssertionError):                    # the guard itself works
            guarded[-1]["close"]

    def test_higher_timeframes_are_closed_and_on_the_server_clock(self):
        p = point("US500", "ny_am", D(2026, 7, 8))                 # opens 08:30 New York = 12:30Z
        cut = Z(p["kz_open_utc"])
        k0, k = H.market_view(self.full, cut)
        h4 = H.aggregate(self.full, k0, k, 240, cut)
        self.assertEqual(K.short_z(h4[-1][0]), "2026-07-08T05:00Z")      # 05:00-09:00Z closed, 09:00-13:00Z forming
        self.assertTrue({x[0].hour for x in h4} <= {21, 1, 5, 9, 13, 17}) # server 00/04/08/... in US DST (+3)
        self.assertEqual(K.short_z(H.aggregate(self.full, k0, k, 60, cut)[-1][0]), "2026-07-08T11:00Z")
        self.assertEqual(K.short_z(H.aggregate(self.full, k0, k, 15, cut)[-1][0]), "2026-07-08T12:15Z")
        self.assertEqual(K.short_z(H.aggregate(self.full, k0, k, 5, cut)[-1][0]), "2026-07-08T12:25Z")
        vals = H.prompt_values(p, self.full, K.spread_snapshot("US500", cut))
        self.assertEqual((vals["n_4h"], vals["n_1h"], vals["n_15m"], vals["n_5m"]), ("60", "60", "96", "48"))
        winter = synth("2026-01-05T00:00:00Z", "2026-01-21T00:00:00Z", 3, 50.0)
        wb = H.Bars("US500", winter)
        wcut = K.killzone_window("US500", "ny_am", D(2026, 1, 20))[0]   # 08:30 EST = 13:30Z
        w0, w = H.market_view(wb, wcut)
        self.assertTrue({x[0].hour for x in H.aggregate(wb, w0, w, 240, wcut)} <= {22, 2, 6, 10, 14, 18})

    def test_a_4h_bar_is_first_open_max_high_min_low_last_close(self):
        cut = Z("2026-07-08T12:30:00Z")
        k0, k = H.market_view(self.full, cut)
        h4 = H.aggregate(self.full, k0, k, 240, cut)[-1]
        js = [j for j in range(k0, k) if Z("2026-07-08T05:00:00Z") <= self.full.dt[j] < Z("2026-07-08T09:00:00Z")]
        self.assertEqual(len(js), 48)
        self.assertEqual(h4[1:], [self.candles[js[0]]["open"], max(self.candles[j]["high"] for j in js),
                                  min(self.candles[j]["low"] for j in js), self.candles[js[-1]]["close"]])

    def test_reference_levels(self):
        p = point("XAUUSD", "london", D(2026, 7, 6))                # Monday: previous server day = Friday 07-03
        cut = Z(p["kz_open_utc"])
        k0, k = H.market_view(self.full, cut)
        lv = H.reference_levels(self.full, k0, k, cut)
        fri = [b for b in self.candles if K.server_date(Z(b["time"])) == D(2026, 7, 3)]
        self.assertEqual(lv["prev_day"][1:], (max(b["high"] for b in fri), min(b["low"] for b in fri)))
        self.assertIn("2026-07-02 17:00 to 2026-07-03 17:00 New York", lv["prev_day"][0])
        week = [b for b in self.candles if Z("2026-07-05T21:00:00Z") <= Z(b["time"]) < cut]   # Sunday 17:00 NY ->
        self.assertEqual(lv["week"][1:], (max(b["high"] for b in week), min(b["low"] for b in week)))
        asia = [b for b in self.candles if Z("2026-07-06T00:00:00Z") <= Z(b["time"]) < Z("2026-07-06T04:00:00Z")]
        self.assertEqual(lv["asia"][1:], (max(b["high"] for b in asia), min(b["low"] for b in asia)))
        self.assertEqual(lv["asia"][0], "2026-07-05 20:00 to 2026-07-06 00:00 New York")

    def test_a_level_without_bars_is_missing_never_zero(self):
        p = point("XAUUSD", "london", D(2026, 7, 7))
        holes = [b for b in self.candles if not Z("2026-07-07T00:00:00Z") <= Z(b["time"]) < Z("2026-07-07T04:00:00Z")]
        text = self.prompt(p, H.Bars("XAUUSD", holes))
        self.assertIn("- Asia session (2026-07-06 20:00 to 2026-07-07 00:00 New York): MISSING", text)

    def test_probe_command_on_a_synthetic_history(self):
        hist = tempfile.mkdtemp(prefix="ic-hist-")
        self.addCleanup(shutil.rmtree, hist, True)
        for sym in K.INSTRUMENTS:
            with open(os.path.join(hist, f"ohlcv.{sym}.5m.json"), "w") as fh:
                json.dump({"symbol": sym, "timeframe": "5m", "candles": self.candles}, fh)
        ctx = H.Ctx(hist_root=hist, window=(Z("2026-07-06T00:00:00Z"), Z("2026-07-10T21:00:00Z")))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(H.cmd_probe(ctx, n=6), 0)


# ================================================================================================ template
class Template(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, K.TEMPLATE), encoding="utf-8") as fh:
            self.text = fh.read()

    def test_the_blocks_carry_exactly_the_harness_placeholders(self):
        sys_block, usr = H.split_template(self.text)
        self.assertEqual(set(H.PLACEHOLDER.findall(sys_block)), {"KNOWLEDGE_BASE"})
        self.assertEqual(set(H.PLACEHOLDER.findall(usr)), set(H.USER_FIELDS))

    def test_render_refuses_a_missing_or_an_extra_value(self):
        with self.assertRaises(H.TemplateError):
            H.render("a {{x}} b", {})
        with self.assertRaises(H.TemplateError):
            H.render("a {{x}} b", {"x": 1, "y": 2})
        self.assertEqual(H.render("a {{x}} {{x}}", {"x": "{{y}}"}), "a {{y}} {{y}}")       # one pass, no re-expansion

    def test_the_system_prompt_embeds_every_knowledge_file_verbatim_in_order(self):
        sysp = H.system_prompt(ROOT, self.text)
        pos = []
        for rel in K.KB_FILES:
            with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
                body = fh.read()
            self.assertIn(f'<document path="{rel}">\n{body}', sysp)
            pos.append(sysp.index(f'<document path="{rel}">'))
        self.assertEqual(pos, sorted(pos))
        outside = re.sub(r"(?s)<reference_material>.*</reference_material>", "", sysp)
        self.assertNotIn("{{", outside)                                     # every placeholder filled
        self.assertNotIn(K.SYSTEM_BOUNDARY, sysp)
        self.assertEqual(K.kb_glob_matches(ROOT)[0], True)

    def test_the_schema_rules_are_stated(self):
        sys_block, _ = H.split_template(self.text)
        for k in E.KEYS:
            self.assertIn(f'"{k}"', sys_block)
        for phrase in ("killzone_end", "at least 1.0", "stop < entry < target", "target < entry < stop",
                       "Do not give a confidence", "at most 120 words", "counted as NO_TRADE"):
            self.assertIn(phrase, sys_block)

    def test_a_user_prompt_has_no_unfilled_placeholder(self):
        candles = synth("2026-06-15T00:00:00Z", "2026-07-09T00:00:00Z", 11, 5000.0)
        p = point("US500", "ny_pm", D(2026, 7, 8))
        text = H.user_prompt(user_block(), p, H.Bars("US500", candles), K.spread_snapshot("US500", Z(p["kz_open_utc"])))
        self.assertNotIn("{{", text)
        self.assertIn("Spread snapshot: 0.28 (ASK = BID + spread). Commission: 0.", text)   # table bucket 17, 28 points


# ================================================================================================ the answer
class Answers(unittest.TestCase):
    def ok(self, obj):
        dec, why = E.validate(obj)
        self.assertIsNone(why)
        return dec

    def bad(self, obj, reason):
        dec, why = E.validate(obj)
        self.assertIsNone(dec)
        self.assertTrue(why.startswith(reason), why)

    def test_valid_long_short_and_no_trade(self):
        self.ok(answer())
        self.ok(answer("SHORT", "stop", entry=100.0, stop=101.0, target=98.0))
        self.ok(answer("NO_TRADE", htf_bias="neutral", pd_array="none"))
        self.ok(answer(order="market", entry=100, stop=99, target=101))                    # integers, R:R exactly 1

    def test_sides_and_reward_risk(self):
        self.bad(answer(stop=101.0), "long_sides")
        self.bad(answer(target=99.5), "long_sides")
        self.bad(answer("SHORT", entry=100.0, stop=99.0, target=98.0), "short_sides")
        self.bad(answer(entry=100.0, stop=99.0, target=100.99), "reward_risk_below_1")
        self.ok(answer(entry=100.1, stop=100.0, target=100.2))                              # 1.0 up to float error

    def test_schema_violations(self):
        self.bad(dict(answer(), confidence=70), "extra_keys")                              # no confidence %, §18
        a = answer()
        del a["pd_array"]
        self.bad(a, "missing_keys")
        self.bad(dict(answer("NO_TRADE"), entry=100.0), "no_trade_with_order_fields")
        self.bad(answer(entry="100.0"), "price_not_a_positive_number")
        self.bad(answer(entry=True), "price_not_a_positive_number")
        self.bad(answer(valid_until="session_end"), "valid_until")
        self.bad(answer(htf_bias="up"), "htf_bias_value")
        self.bad(answer(order="ioc"), "order_value")
        self.bad(answer(decision="BUY"), "decision_value")
        self.bad(answer(reasoning=" ".join(["w"] * 121)), "reasoning_over_120_words")
        self.ok(answer(reasoning=" ".join(["w"] * 120)))
        self.bad(answer(invalidation="  "), "empty_invalidation")

    def test_extraction_is_robust_but_strict(self):
        js = json.dumps(answer())
        self.assertEqual(K.extract_answer(js)[1], "whole")
        self.assertEqual(K.extract_answer("```json\n" + js + "\n```")[1], "fenced")
        obj, how = K.extract_answer("Here is my decision:\n" + js + "\nGood luck {not json}.")
        self.assertEqual((obj["decision"], how), ("LONG", "embedded"))
        self.assertEqual(K.extract_answer("```\n" + js + "\n```\n" + js)[1], "fenced")       # the same object twice
        self.assertEqual(K.extract_answer(js + "\n" + json.dumps(answer("NO_TRADE"))), (None, "several_objects"))
        self.assertEqual(K.extract_answer(js[:-5]), (None, "no_json_object"))              # truncated
        self.assertEqual(K.extract_answer('{"decision": "LONG", "decision": "SHORT"}'), (None, "duplicate_key"))
        self.assertIsNone(K.extract_answer(js.replace("100.0", "NaN", 1))[0])
        self.assertEqual(K.extract_answer(""), (None, "empty_answer"))
        self.assertEqual(K.extract_answer("[1, 2]"), (None, "not_an_object"))

    def test_judge_counts_a_technical_failure_and_an_unparseable_answer(self):
        self.assertEqual(E.judge({"status": "technical_failure"})[1], "technical_failure")
        self.assertEqual(E.judge({"status": "answered", "answer": "wait"})[1], "unparseable:no_json_object")
        self.assertEqual(E.judge({"status": "answered", "answer": json.dumps(answer(stop=200.0))})[1], "long_sides")


# ================================================================================================ §4 simulator
T0 = "2026-07-07T11:00:00Z"            # XAUUSD New York AM opens 07:00 New York (EDT) = 11:00Z; time exit 20:00Z


def tl(minutes):
    return K.iso_z(Z(T0) + TD(minutes=minutes))


def book(rows):
    return E.Book("XAUUSD", [bar(tl(m), o, h, l, c) for m, o, h, l, c in rows])


def order(side=1, kind="limit", entry=100.0, stop=99.0, target=102.0, spread=0.5, until=180, placed=0):
    return {"side": side, "kind": kind, "entry": entry, "stop": stop, "target": target, "spread": spread,
            "placed_at": Z(tl(placed)), "valid_until": Z(tl(until))}


class Simulator(unittest.TestCase):
    def test_a_buy_limit_fills_on_the_ask_not_the_bid(self):
        b = book([(0, 101, 101.2, 100.8, 101), (5, 101, 101, 99.6, 100.5), (10, 100.5, 100.6, 99.5, 100.2),
                  (15, 100.2, 102.6, 100.1, 102.4)])
        r = E.simulate(b, order())
        self.assertEqual((r["status"], r["fill_time"], r["fill_price"], r["fill_mode"]), ("filled", tl(10), 100.0, "falling"))
        self.assertEqual((r["exit_reason"], r["exit_price"]), ("target", 102.0))
        self.assertAlmostEqual(r["R"], (102.0 - 100.0) / (1.0 + 0.5))                         # R = net / (|e - s| + spread)

    def test_a_sell_limit_fills_on_the_bid(self):
        b = book([(0, 99, 99.2, 98.8, 99), (5, 99, 100.0, 98.9, 99.5), (10, 99.5, 99.6, 97.0, 97.2)])
        r = E.simulate(b, order(side=-1, entry=100.0, stop=101.0, target=98.0))
        self.assertEqual((r["fill_time"], r["fill_price"], r["fill_mode"]), (tl(5), 100.0, "rising"))
        self.assertEqual((r["exit_reason"], r["exit_price"]), ("target", 98.0))              # ASK 97.5 <= 98
        self.assertAlmostEqual(r["R"], 2.0 / 1.5)

    def test_stop_orders_fill_at_the_first_trade_through_including_a_gap(self):
        b = book([(0, 98, 98.5, 97.8, 98.2), (5, 98.2, 99.6, 98.1, 99.4), (10, 99.4, 99.8, 99.3, 99.7)])
        r = E.simulate(b, order(kind="stop", entry=100.0, stop=98.0, target=103.0))
        self.assertEqual((r["fill_time"], r["fill_price"], r["fill_mode"]), (tl(5), 100.0, "rising"))   # ASK 100.1 >= 100
        g = book([(0, 98, 98.5, 97.8, 98.2), (5, 101, 101.5, 100.8, 101.2)])
        r = E.simulate(g, order(kind="stop", entry=100.0, stop=98.0, target=105.0))
        self.assertEqual((r["fill_price"], r["fill_mode"]), (101.5, "open"))                  # gap: the ASK open
        s = book([(0, 102, 102.5, 101.8, 102.2), (5, 99.0, 99.2, 98.5, 98.8)])
        r = E.simulate(s, order(side=-1, kind="stop", entry=100.0, stop=102.0, target=95.0))
        self.assertEqual((r["fill_price"], r["fill_mode"]), (99.0, "open"))                   # gap: the BID open

    def test_a_market_order_fills_at_the_first_killzone_bar_open(self):
        b = book([(0, 100, 100.4, 99.8, 100.2), (5, 100.2, 101.0, 100.1, 100.9)])
        r = E.simulate(b, order(kind="market", entry=100.0, stop=98.0, target=104.0))
        self.assertEqual((r["fill_time"], r["fill_price"], r["fill_mode"]), (tl(0), 100.5, "open"))     # ASK
        r = E.simulate(b, order(side=-1, kind="market", entry=100.0, stop=102.0, target=96.0))
        self.assertEqual(r["fill_price"], 100.0)                                                      # BID

    def test_the_r_unit_is_the_order_price_or_a_market_orders_fill(self):
        b = book([(0, 100, 100.4, 99.8, 100.2), (5, 100.2, 100.3, 98.5, 98.7)])
        m = E.simulate(b, order(kind="market", entry=99.01, stop=99.0, target=104.0))   # the stated entry is ignored
        self.assertEqual((m["fill_price"], m["exit_reason"], m["risk_unit"]), (100.5, "stop", 100.5 - 99.0 + 0.5))
        self.assertAlmostEqual(m["R"], (99.0 - 100.5) / 2.0)
        lim = E.simulate(book([(0, 101, 101.2, 100.8, 101), (5, 101, 101, 98.5, 98.7)]), order())
        self.assertEqual(lim["risk_unit"], 100.0 - 99.0 + 0.5)                         # a limit: its own price

    def test_orders_on_the_wrong_side_of_the_market_are_rejected(self):
        b = book([(0, 100, 100.4, 99.8, 100.2)])
        self.assertEqual(E.simulate(b, order(entry=100.6, stop=99.0, target=103.0))["reason"], "limit_on_wrong_side_of_market")
        self.assertEqual(E.simulate(b, order(kind="stop", entry=100.4, stop=99.0, target=103.0))["reason"],
                         "stop_on_wrong_side_of_market")
        self.assertEqual(E.simulate(b, order(side=-1, entry=99.9, stop=101.0, target=98.0))["reason"],
                         "limit_on_wrong_side_of_market")
        self.assertEqual(E.simulate(b, order(kind="market", entry=101.0, stop=100.2, target=104.0))["reason"],
                         "stops_on_wrong_side_at_fill")                                           # BID 100 <= stop

    def test_an_unfilled_order_expires_at_the_killzone_end(self):
        b = book([(0, 101, 101.2, 100.8, 101), (175, 101, 101.1, 100.9, 101), (180, 101, 101, 98, 98.5)])
        r = E.simulate(b, order())                                  # the 14:00Z touch is at the killzone end: too late
        self.assertEqual((r["status"], r["reason"]), ("unfilled", "expired"))

    def test_stop_first_when_stop_and_target_share_a_bar(self):
        b = book([(0, 101, 101.2, 100.8, 101), (5, 101, 101, 99.5, 100.2), (10, 100.2, 102.5, 98.9, 100)])
        r = E.simulate(b, order())
        self.assertEqual((r["exit_reason"], r["exit_price"], r["exit_time"]), ("stop", 99.0, tl(10)))
        self.assertAlmostEqual(r["R"], -1.0 / 1.5)

    def test_on_the_fill_bar_the_unknown_order_is_resolved_against_the_trade(self):
        """The extreme price travelled to after the fill is known to follow it; the other may precede or follow it. The
        stop is checked on the whole fill bar, the target only on the extreme known to follow the fill."""
        b = book([(0, 101.6, 102.5, 101.5, 102), (5, 102, 102.4, 99.4, 99.6), (10, 99.6, 99.8, 99.5, 99.7),
                  (15, 99.7, 99.8, 98.9, 99.0)])
        r = E.simulate(b, order(target=102.2))       # buy limit fills falling on bar 5: its 102.4 high may precede it
        self.assertEqual((r["fill_time"], r["exit_reason"], r["exit_time"]), (tl(5), "stop", tl(15)))
        r = E.simulate(book([(0, 98, 98.5, 97.8, 98.2), (5, 98.2, 103.5, 98.1, 103.0)]),
                       order(kind="stop", entry=100.0, stop=98.0, target=103.0))
        self.assertEqual((r["fill_time"], r["exit_reason"], r["exit_time"]), (tl(5), "target", tl(5)))   # high follows
        r = E.simulate(book([(0, 101, 101.2, 100.8, 101), (5, 101, 101, 98.5, 98.7)]), order())
        self.assertEqual((r["fill_time"], r["exit_reason"], r["exit_time"]), (tl(5), "stop", tl(5)))     # low follows
        r = E.simulate(book([(0, 98, 98.5, 97.8, 98.2), (5, 98.2, 103.5, 97.9, 103.0)]),
                       order(kind="stop", entry=100.0, stop=98.0, target=103.0))
        self.assertEqual((r["exit_reason"], r["exit_price"], r["exit_time"]), ("stop", 98.0, tl(5)))     # the low may follow
        s = E.simulate(book([(0, 99, 99.2, 98.8, 99), (5, 99.0, 100.6, 97.4, 97.6)]),
                       order(side=-1, entry=100.0, stop=101.0, target=98.0))
        self.assertEqual((s["fill_mode"], s["exit_reason"], s["exit_time"]), ("rising", "stop", tl(5)))  # ASK high 101.1
        s = E.simulate(book([(0, 99, 99.2, 98.8, 99), (5, 99.0, 100.2, 97.0, 97.2), (10, 97.2, 97.4, 96.9, 97.0)]),
                       order(side=-1, entry=100.0, stop=101.0, target=98.0))
        self.assertEqual((s["exit_reason"], s["exit_time"]), ("target", tl(10)))     # a sell limit: low may precede

    def test_a_bar_opening_beyond_the_stop_exits_at_its_open(self):
        b = book([(0, 101, 101.2, 100.8, 101), (5, 101, 101, 99.5, 100.4), (10, 98.2, 98.6, 97.9, 98.3)])
        r = E.simulate(b, order())
        self.assertEqual((r["exit_reason"], r["exit_price"]), ("stop", 98.2))
        self.assertAlmostEqual(r["R"], (98.2 - 100.0) / 1.5)

    def test_time_exit_at_16_new_york_long_at_the_bid_short_at_the_ask(self):
        rows = [(0, 101, 101.2, 100.8, 101), (5, 101, 101, 99.5, 100.4)] + \
               [(m, 100.4, 100.9, 100.1, 100.6) for m in range(10, 545, 5)]      # last bar 19:55Z closes 20:00Z
        r = E.simulate(book(rows), order())
        self.assertEqual((r["exit_reason"], r["exit_time"], r["exit_price"]), ("time", tl(535), 100.6))
        s = E.simulate(book([(0, 99, 99.2, 98.8, 99), (5, 99, 100.0, 98.9, 99.5)] +
                            [(m, 99.5, 99.9, 99.1, 99.4) for m in range(10, 560, 5)]),
                       order(side=-1, entry=100.0, stop=101.0, target=97.0))
        self.assertEqual((s["exit_reason"], s["exit_time"], s["exit_price"]), ("time", tl(535), 99.9))   # ASK close

    def test_a_market_closed_early_exits_at_the_last_close_before_16_new_york(self):
        rows = [(0, 101, 101.2, 100.8, 101), (5, 101, 101, 99.5, 100.4), (10, 100.4, 100.7, 100.3, 100.5),
                (600, 101, 101.2, 100.9, 101.1)]                                  # the next bar is after the time exit
        r = E.simulate(book(rows), order())
        self.assertEqual((r["exit_reason"], r["exit_time"], r["exit_price"]), ("time", tl(10), 100.5))

    def test_no_fill_between_16_and_17_new_york_but_after_the_rollover(self):
        rows = [(0, 101, 101.2, 100.8, 101), (545, 101, 101, 99.0, 99.6),        # 20:05Z = 16:05 New York: no fill
                (610, 99.6, 99.8, 99.2, 99.4), (620, 99.4, 99.9, 99.3, 99.8)]      # 21:10Z: next server day
        r = E.simulate(book(rows), order(until=700))
        self.assertEqual((r["status"], r["fill_time"]), ("filled", tl(610)))
        self.assertEqual(K.iso_z(K.time_exit(Z(r["fill_time"]))[0]), "2026-07-08T20:00:00Z")


# ================================================================================================ R-control
class Control(unittest.TestCase):
    def test_the_same_direction_control_is_the_trade_itself(self):
        rows = [(0, 101, 101.2, 100.8, 101), (5, 101, 101, 99.5, 100.4), (10, 100.4, 101.3, 100.2, 101.1),
                (15, 101.1, 102.3, 101.0, 102.1)]
        for o in (order(), order(kind="market", entry=101.0, stop=99.0, target=104.0),
                  order(side=-1, kind="market", entry=101.0, stop=102.0, target=100.0)):
            b = book(rows)
            r = E.simulate(b, o)
            same, opp = E.control_pair(b, r, o)
            self.assertAlmostEqual(same, r["R"])
            self.assertNotAlmostEqual(opp, r["R"])

    def test_the_opposite_control_mirrors_from_the_bid_at_the_fill(self):
        b = book([(0, 101, 101.2, 100.8, 101), (5, 101, 101, 99.5, 100.4), (10, 99.9, 100.1, 99.3, 99.4)])
        r = E.simulate(b, order(target=102.0))                    # long limit 100 (ASK) fills on bar 5, BID 99.5 there
        _same, opp = E.control_pair(b, r, order(target=102.0))
        # short at BID 99.5, stop 100.5, target 97.5; on the fill bar the ASK high 101.5 may follow the fill -> stopped
        self.assertAlmostEqual(opp, -(100.5 - 99.5) / 1.5)
        quiet = book([(0, 101, 101.2, 100.8, 101), (5, 99.8, 99.9, 99.4, 99.6), (10, 99.6, 99.7, 97.0, 97.1)])
        r = E.simulate(quiet, order(target=102.0))
        _same, opp = E.control_pair(quiet, r, order(target=102.0))
        self.assertAlmostEqual(opp, (99.5 - 97.5) / 1.5)          # ASK low 97.5 on bar 10: the control's target

    def test_the_fill_bar_rule_is_the_same_for_c_and_its_control(self):
        """A trade's R on a fill bar depends on its side and the bar, never on whether it is C or a control: the control
        of a buy stop (short at the same instant) is scored exactly as a sell stop filled there would be."""
        b = book([(0, 98, 98.5, 97.8, 98.2), (5, 98.2, 103.5, 98.1, 103.0), (10, 103, 103.2, 102.8, 103.1)])
        o = order(kind="stop", entry=100.0, stop=98.0, target=103.0)
        r = E.simulate(b, o)
        _same, opp = E.control_pair(b, r, o)
        # short at BID 99.5 (ASK 100), stop 101.5, target 96.5: the ASK high 104 follows the fill -> stopped on bar 5
        self.assertAlmostEqual(opp, -(101.5 - 99.5) / 2.5)
        self.assertAlmostEqual(r["R"], (103.0 - 100.0) / 2.5)

    def test_the_permutation_test_is_seeded_and_reproducible(self):
        rng = random.Random(5)
        dirs = [rng.choice((1, -1)) for _ in range(80)]
        r_c = [rng.uniform(-1, 2) for _ in range(80)]
        r_opp = [rng.uniform(-1, 2) for _ in range(80)]
        a = E.permutation_test(r_c, dirs, r_c, r_opp, n_perm=500)
        b = E.permutation_test(r_c, dirs, r_c, r_opp, n_perm=500)
        self.assertEqual(a, b)
        c = E.permutation_test(r_c, dirs, r_c, r_opp, n_perm=500, tag="another seed")
        self.assertNotEqual(a["control_mean_R"], c["control_mean_R"])
        self.assertEqual(E.permutation_test(r_c, dirs, r_c, r_opp, n_perm=500, signflip=True),
                         E.permutation_test(r_c, dirs, r_c, r_opp, n_perm=500, signflip=True))

    def test_a_right_direction_scores_low_p_and_a_one_sided_book_cannot_pass(self):
        dirs = [1, -1] * 40
        good = E.permutation_test([1.0] * 80, dirs, [1.0] * 80, [-1.0] * 80, n_perm=2000)
        self.assertLess(good["p_one_sided"], 0.01)
        same = E.permutation_test([1.0] * 80, [1] * 80, [1.0] * 80, [-1.0] * 80, n_perm=200)
        self.assertEqual(same["p_one_sided"], 1.0)                 # every shuffle of all-LONG is C itself
        self.assertEqual(E.N_PERM, 2000)

    def test_bootstrap_is_seeded(self):
        xs = [0.5, -1.0, 2.0, -0.7, 1.3, 0.1] * 10
        lo, hi = E.bootstrap_ci(xs, n_boot=2000)
        self.assertEqual((lo, hi), E.bootstrap_ci(xs, n_boot=2000))
        self.assertLess(lo, E.mean(xs))
        self.assertGreater(hi, E.mean(xs))


# ================================================================================================ verdict and metrics
class Verdict(unittest.TestCase):
    def test_the_six_outcomes(self):
        self.assertEqual(E.verdict(59, 0.001, 0.5, True, 0.0), "INSUFFICIENT")
        self.assertEqual(E.verdict(60, 0.05, 0.5, True, 0.0), "FAIL")
        self.assertEqual(E.verdict(60, 0.049, 0.5, True, 0.0, p_mirror=0.01), "PASS")
        self.assertEqual(E.verdict(60, 0.01, -0.1, True, -0.5, p_mirror=0.01), "NOT_PASS")   # mean net R must be > 0
        self.assertEqual(E.verdict(60, 0.01, 0.3, True, 0.4, p_mirror=0.01), "NOT_PASS")     # C must beat M
        self.assertEqual(E.verdict(60, 0.01, 0.3, False, None, p_mirror=0.01), "INCOMPLETE (C vs M not evaluable)")
        self.assertEqual(E.verdict(60, 0.01, -0.3, False, None, p_mirror=0.01), "NOT_PASS")
        self.assertEqual(E.verdict(60, 0.01, 0.5, True, 0.0, p_mirror=0.2), "NOT_PASS")      # amendment 1: the mirror test gates
        self.assertEqual(E.verdict(200, 0.2, 0.3, False, None), "FAIL")

    def test_metrics(self):
        tr = [{"id": str(i), "R": r, "exit_time": f"2026-07-0{i + 1}T10:00:00Z", "fill_time": "x", "exit_reason": "stop"}
              for i, r in enumerate([1.0, -0.5, -0.5, 2.0, -1.0])]
        m = E.metrics(tr)
        self.assertEqual((m["n"], m["win_rate"], m["total_R"]), (5, 0.4, 1.0))
        self.assertAlmostEqual(m["profit_factor"], 3.0 / 2.0)
        self.assertAlmostEqual(m["max_drawdown_R"], 1.0)
        self.assertEqual(E.metrics([]), {"n": 0})


class ArmC(unittest.TestCase):
    def test_every_outcome_of_a_decision_is_counted(self):
        day = D(2026, 7, 7)
        p = point("XAUUSD", "ny_am", day)
        b = book([(0, 101, 101.2, 100.8, 101), (5, 101, 101, 99.5, 100.4), (10, 100.4, 102.5, 100.3, 102.3)])
        pts, final = [], {}
        cases = {"a": json.dumps(answer()), "b": json.dumps(answer("NO_TRADE")), "c": "no idea",
                 "d": json.dumps(answer(entry=101.6, stop=99.0, target=104.2)), "e": None,   # above the 101.5 ASK
                 "f": json.dumps(answer(entry=95.0, stop=94.0, target=97.0))}
        for i, (key, ans) in enumerate(cases.items()):
            pts.append(dict(p, id=f"{p['id']}|{key}", spread={"spread": 0.5}))
            final[f"{p['id']}|{key}"] = ({"status": "answered", "answer": ans} if ans is not None
                                         else {"status": "technical_failure"})
        rows = E.arm_c(pts, final, {"XAUUSD": b})
        self.assertEqual([r["outcome"] for r in rows], ["filled", "no_trade", "invalid", "rejected",
                                                       "technical_failure", "unfilled"])
        c = E.counts(rows)
        self.assertEqual((c["orders"], c["filled"], c["fill_rate"], c["invalid_answers"], c["technical_failures"]),
                         (3, 1, 1 / 3, 1, 1))
        self.assertEqual(c["no_trade_rate_of_valid"], 1 / 4)


# ================================================================================================ the run (fake CLI)
FAKE_CLI = r'''#!/usr/bin/env python3
import hashlib, json, os, sys, time
if "--version" in sys.argv:
    print("9.9.9 (Fake Claude Code)")
    sys.exit(0)
d = os.environ["IC_FAKE_DIR"]
prompt = sys.stdin.buffer.read()
sysfile = sys.argv[sys.argv.index("--system-prompt-file") + 1]
with open(os.path.join(d, "state.json")) as fh:
    st = json.load(fh)
n = st["n"]
st["n"] = n + 1
with open(os.path.join(d, "state.json"), "w") as fh:
    json.dump(st, fh)
with open(sysfile, "rb") as fh:
    sys_sha = hashlib.sha256(fh.read()).hexdigest()
with open(os.path.join(d, "calls.jsonl"), "a") as fh:
    fh.write(json.dumps({"n": n, "argv": sys.argv[1:], "cwd_listing": os.listdir("."), "cwd": os.getcwd(),
                         "prompt_sha256": hashlib.sha256(prompt).hexdigest(), "system_sha256": sys_sha}) + "\n")
with open(os.path.join(d, "scenario.json")) as fh:
    sc = json.load(fh)
beh = sc["calls"][n] if n < len(sc["calls"]) else sc["default"]
time.sleep(beh.get("sleep", 0))
if beh.get("kill"):
    os.kill(os.getpid(), 9)
sys.stdout.write(beh["raw"] if "raw" in beh else json.dumps(beh["env"]))
sys.stderr.write(beh.get("stderr", ""))
sys.exit(beh.get("exit", 0))
'''


def envelope(result, model="claude-opus-5-5", turns=1, denials=None, usage=None, is_error=False, model_usage=True):
    e = {"type": "result", "subtype": "success", "is_error": is_error, "num_turns": turns, "result": result,
         "duration_ms": 10, "total_cost_usd": 0.01, "permission_denials": denials or [], "session_id": "s",
         "usage": usage or {"input_tokens": 10, "output_tokens": 5,
                            "server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0}}}
    if model_usage:
        e["modelUsage"] = {model: {"inputTokens": 10, "outputTokens": 5, "webSearchRequests": 0, "costUSD": 0.01}}
    return e


OK = {"env": envelope(json.dumps(answer("NO_TRADE")))}
WINDOW = (Z("2026-07-07T00:00:00Z"), Z("2026-07-07T20:50:00Z"))         # one Tuesday: 2 + 3 killzones


def agg15(bars):
    """15m bars from 5m bars (buckets on the clock), for the 15m data pin of the synthetic history."""
    out = {}
    for b in bars:
        t = Z(b["time"])
        k = K.iso_z(t - TD(minutes=t.minute % 15))
        if k not in out:
            out[k] = dict(b, time=k)
        else:
            o = out[k]
            o.update(high=max(o["high"], b["high"]), low=min(o["low"], b["low"]), close=b["close"])
    return [out[k] for k in sorted(out)]


class Repo:
    """A temporary git repository holding copies of the experiment's committed inputs, a synthetic history and a fake
    `claude` executable."""

    def __init__(self, case, shadow_subdir=None):
        self.root = tempfile.mkdtemp(prefix="ic-repo-")
        self.hist = tempfile.mkdtemp(prefix="ic-hist-")
        self.fake = tempfile.mkdtemp(prefix="ic-fake-")
        self.shadow = tempfile.mkdtemp(prefix="ic-shadow-")
        for d in (self.root, self.hist, self.fake, self.shadow):
            case.addCleanup(shutil.rmtree, d, True)
        git(self.root, "init", "-q")
        for k, v in (("user.email", "t@example.invalid"), ("user.name", "t"), ("commit.gpgsign", "false"),
                     ("core.excludesFile", os.devnull)):
            git(self.root, "config", k, v)
        for rel in (K.PREREG, K.TEMPLATE, *K.KB_FILES, K.COMMON, K.HARNESS, K.EVALUATOR, *E.ALWAYS_EXECUTED):
            os.makedirs(os.path.dirname(os.path.join(self.root, rel)), exist_ok=True)
            shutil.copyfile(os.path.join(ROOT, rel), os.path.join(self.root, rel))
        for i, sym in enumerate(K.INSTRUMENTS):
            bars = synth("2026-06-01T00:00:00Z", "2026-07-08T00:00:00Z", 20 + i, 100.0 * (i + 1))
            for tf, cs in (("5m", bars), ("15m", agg15(bars))):
                with open(os.path.join(self.hist, f"ohlcv.{sym}.{tf}.json"), "w") as fh:
                    json.dump({"symbol": sym, "timeframe": tf, "candles": cs}, fh)
        cli = os.path.join(self.fake, "claude")
        with open(cli, "w") as fh:
            fh.write(FAKE_CLI)
        os.chmod(cli, os.stat(cli).st_mode | stat.S_IXUSR)
        self.ctx = H.Ctx(root=self.root, hist_root=self.hist, window=WINDOW, claude_bin=cli, timeout_s=20, retry_delay_s=0,
                         shadow_dir=os.path.join(self.shadow, shadow_subdir) if shadow_subdir else self.shadow)
        self.scenario({"calls": [], "default": OK})
        case.addCleanup(os.environ.pop, "IC_FAKE_DIR", None)
        os.environ["IC_FAKE_DIR"] = self.fake

    def scenario(self, sc):
        with open(os.path.join(self.fake, "scenario.json"), "w") as fh:
            json.dump(sc, fh)
        with open(os.path.join(self.fake, "state.json"), "w") as fh:
            json.dump({"n": 0}, fh)
        open(os.path.join(self.fake, "calls.jsonl"), "w").close()

    def calls(self):
        with open(os.path.join(self.fake, "calls.jsonl")) as fh:
            return [json.loads(l) for l in fh if l.strip()]

    def build(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return H.cmd_build(self.ctx)

    def commit(self, msg="c"):
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", msg)

    def init(self, **kw):
        kw.setdefault("selfcheck", False)
        return H.cmd_init(self.ctx, out=lambda *a: None, **kw)

    def start(self):
        """build -> commit -> init -> commit: the state in which `run` may ask decisions."""
        self.build()
        self.commit("inputs")
        self.init()
        self.commit("start event")

    def run(self, **kw):
        kw.setdefault("selfcheck", False)
        return H.cmd_run(self.ctx, concurrency=1, out=lambda *a: None, **kw)

    def ectx(self):
        return E.Ctx(root=self.root, shadow_dir=self.ctx.shadow_dir, hist_root=self.hist)

    def log(self):
        return H.read_log(os.path.join(self.root, K.DECISIONS))

    def events(self):
        return [x["event"] for x in self.log() if x["record"] == "run_event"]

    def manifest(self):
        with open(os.path.join(self.root, K.MANIFEST)) as fh:
            return json.load(fh)

    def shadow_file(self):
        return self.ctx.shadow_path(K.sha256_file(os.path.join(self.root, K.MANIFEST)))


class Run(unittest.TestCase):
    def ready(self, scenario=None):
        r = Repo(self)
        r.start()
        if scenario:
            r.scenario(scenario)
        return r

    def finals(self, r):
        return {x["decision_id"]: x for x in r.log() if x["record"] == "decision"}

    def test_run_refuses_before_the_inputs_are_committed(self):
        r = Repo(self)
        r.build()
        with self.assertRaises(K.Refused):
            r.run()
        r.commit()
        with open(os.path.join(r.root, K.TEMPLATE), "a") as fh:
            fh.write("\nedited after the build\n")
        with self.assertRaises(K.Refused):
            r.run()
        self.assertEqual(r.calls(), [])

    def test_run_refuses_until_the_start_event_is_committed(self):
        r = Repo(self)
        r.build()
        r.commit()
        with self.assertRaises(K.Refused):                          # not started
            r.run()
        r.init()
        with self.assertRaises(K.Refused):                          # started, start event not committed
            r.run()
        with self.assertRaises(K.Refused):                          # the run starts once
            r.init()
        self.assertEqual(r.calls(), [])
        r.commit()
        self.assertEqual(r.run(), 0)
        self.assertEqual(r.events(), ["start", "resume", "stop"])

    def test_init_with_a_failing_selfcheck_writes_nothing(self):
        r = Repo(self)
        r.build()
        r.commit()
        r.scenario({"calls": [{"env": envelope(json.dumps(answer("NO_TRADE")), model="claude-sonnet-5-5")}], "default": OK})
        with self.assertRaises(K.Refused):
            r.init(selfcheck=True)
        self.assertEqual(r.log(), [])
        self.assertEqual(r.init(selfcheck=True), 0)
        self.assertEqual(r.log()[0]["selfcheck"]["served_models"], ["claude-opus-5-5"])

    def test_run_refuses_an_uncommitted_evaluator(self):
        r = self.ready()
        with open(os.path.join(r.root, K.EVALUATOR), "a") as fh:
            fh.write("# edit\n")
        with self.assertRaises(K.Refused):
            r.run()

    def test_a_complete_run_with_the_isolated_command(self):
        r = self.ready()
        PG.trace_start(r.root)
        self.assertEqual(r.run(), 0)
        seen = set(PG._TRACE["seen"])
        PG._TRACE["on"] = False
        self.assertNotIn(K.EVALUATOR, seen)                         # the harness never opens the evaluator
        man = r.manifest()
        fin = self.finals(r)
        self.assertEqual(sorted(fin), sorted(p["id"] for p in man["decision_points"]))
        self.assertEqual(len(fin), 5)
        for rec in fin.values():
            self.assertEqual((rec["status"], rec["served_models"], rec["served_model_unverifiable"], rec["attempt"]),
                             ("answered", ["claude-opus-5-5"], False, 1))
            self.assertEqual(rec["cli_version"], "9.9.9 (Fake Claude Code)")
            self.assertEqual(rec["manifest_sha256"], K.sha256_file(os.path.join(r.root, K.MANIFEST)))
            self.assertEqual(rec["answer_sha256"], hashlib.sha256(rec["answer"].encode()).hexdigest())
        calls = r.calls()
        self.assertEqual(len(calls), 5)
        for c in calls:
            argv = c["argv"]
            self.assertEqual(argv[:9], ["-p", "--safe-mode", "--tools", "", "--strict-mcp-config",
                                        "--no-session-persistence", "--model", "claude-opus-5-5", "--system-prompt-file"])
            self.assertEqual(argv[10:], ["--output-format", "json", "--effort", "high"])   # amendment 1: effort pinned
            self.assertNotIn("--fallback-model", argv)
            self.assertEqual(c["cwd_listing"], [])
            self.assertNotEqual(os.path.realpath(c["cwd"]), os.path.realpath(r.root))
            self.assertEqual(c["system_sha256"], man["system_prompt"]["sha256"])
        self.assertEqual(sorted(c["prompt_sha256"] for c in calls), sorted(p["prompt_sha256"] for p in man["decision_points"]))
        events = [x for x in r.log() if x["record"] == "run_event"]
        self.assertEqual([e["event"] for e in events], ["start", "resume", "stop"])
        self.assertEqual(events[0]["evaluator_blob"], K.git_blob(r.root, K.EVALUATOR))
        self.assertEqual(r.run(), 0)                                # complete: nothing is asked again
        self.assertEqual(len(r.calls()), 5)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            H.cmd_status(r.ctx)
        self.assertIn("complete: True", out.getvalue())

    def test_an_isolation_violation_gets_exactly_one_retry(self):
        r = self.ready({"calls": [{"env": envelope(json.dumps(answer("NO_TRADE")), turns=2)}], "default": OK})
        self.assertEqual(r.run(), 0)
        tf = [x for x in r.log() if x["record"] == "technical_failure"]
        self.assertEqual([(x["kind"], x["counts_toward_retry"]) for x in tf], [("isolation_violation", True)])
        rec = self.finals(r)[tf[0]["decision_id"]]
        self.assertEqual((rec["status"], rec["attempt"], rec["retry"]), ("answered", 2, True))

    def test_permission_denials_and_server_tools_are_violations_and_two_failures_are_final(self):
        bad_usage = {"input_tokens": 1, "server_tool_use": {"web_search_requests": 1}}
        r = self.ready({"calls": [{"env": envelope(json.dumps(answer("NO_TRADE")), denials=[{"tool_name": "WebFetch"}])},
                                  {"env": envelope(json.dumps(answer("NO_TRADE")), usage=bad_usage)}], "default": OK})
        self.assertEqual(r.run(), 0)
        tf = [x for x in r.log() if x["record"] == "technical_failure"]
        self.assertEqual([x["kind"] for x in tf], ["isolation_violation", "isolation_violation"])
        self.assertIn("permission_denials", tf[0]["detail"])
        self.assertIn("server_tool_use.web_search_requests=1", tf[1]["detail"])
        rec = self.finals(r)[tf[0]["decision_id"]]
        self.assertEqual((rec["status"], rec["last_failure_kind"], rec["answer"]), ("technical_failure", "isolation_violation", None))

    def test_timeouts_and_bad_cli_output_are_technical_failures(self):
        r = self.ready({"calls": [{"env": OK["env"], "sleep": 3}, {"raw": "Segmentation fault", "exit": 1},
                                  {"raw": "{not json", "exit": 0}, {"env": envelope("I would wait for the NY open.")}],
                        "default": OK})
        r.ctx.timeout_s = 1
        self.assertEqual(r.run(), 0)
        kinds = [x["kind"] for x in r.log() if x["record"] == "technical_failure"]
        self.assertEqual(kinds, ["timeout", "nonzero_exit", "invalid_cli_json", "no_json_in_answer"])
        self.assertEqual(sum(1 for x in self.finals(r).values() if x["status"] == "technical_failure"), 2)

    def test_a_prose_wrapped_answer_is_stored_for_the_evaluator(self):
        r = self.ready({"calls": [{"env": envelope("My read:\n```json\n" + json.dumps(answer()) + "\n```")}], "default": OK})
        self.assertEqual(r.run(), 0)
        self.assertEqual(sorted(x["kind"] for x in r.log() if x["record"] == "technical_failure"), [])

    def test_a_fallback_model_pauses_the_run_and_is_retried_when_the_pinned_model_serves(self):
        r = self.ready({"calls": [{"env": envelope(json.dumps(answer("NO_TRADE")), model="claude-sonnet-5-5")}],
                        "default": OK})
        self.assertEqual(r.run(), 3)
        tf = [x for x in r.log() if x["record"] == "technical_failure"]
        self.assertEqual([(x["kind"], x["counts_toward_retry"], x["served_models"]) for x in tf],
                         [("model_pin_mismatch", False, ["claude-sonnet-5-5"])])
        self.assertEqual(r.events(), ["start", "resume", "pause"])
        self.assertEqual(self.finals(r), {})
        r.commit("paused")
        self.assertEqual(r.run(), 0)
        self.assertEqual(r.events(), ["start", "resume", "pause", "resume", "stop"])
        rec = self.finals(r)[tf[0]["decision_id"]]
        self.assertEqual((rec["attempt"], rec["retry"], rec["served_models"]), (2, False, ["claude-opus-5-5"]))

    def test_no_model_information_is_recorded_unverifiable(self):
        r = self.ready({"calls": [{"env": envelope(json.dumps(answer("NO_TRADE")), model_usage=False)}], "default": OK})
        self.assertEqual(r.run(), 0)
        flags = sorted(x["served_model_unverifiable"] for x in self.finals(r).values())
        self.assertEqual(flags, [False, False, False, False, True])

    def test_a_usage_limit_only_pauses_and_resume_never_regenerates_a_stored_decision(self):
        r = self.ready({"calls": [OK, {"env": envelope("Claude AI usage limit reached|1791100000", is_error=True),
                                       "exit": 1}], "default": OK})
        self.assertEqual(r.run(), 3)
        first = self.finals(r)
        self.assertEqual(len(first), 1)
        self.assertEqual([x["kind"] for x in r.log() if x["record"] == "interruption"], ["usage_limit"])
        with self.assertRaises(K.Refused):                          # the stored decision must be committed first
            r.run()
        r.commit("paused")
        self.assertEqual(r.run(), 0)
        fin = self.finals(r)
        self.assertEqual(len(fin), 5)
        only = next(iter(first))
        self.assertEqual(fin[only], first[only])
        self.assertEqual(len(r.calls()), 2 + 4)                   # the stored decision was never asked again
        self.assertEqual(sum(1 for x in r.log() if x["record"] == "technical_failure"), 0)

    def test_a_call_killed_from_outside_pauses_without_counting(self):
        r = self.ready({"calls": [{"kill": True}], "default": OK})
        self.assertEqual(r.run(), 3)
        self.assertEqual([(x["kind"], x["exit_code"], x["counts_toward_retry"]) for x in r.log() if x["record"] == "interruption"],
                         [("killed_by_signal", -9, False)])
        r.commit("paused")
        self.assertEqual(r.run(), 0)
        self.assertFalse(any(x["retry"] for x in self.finals(r).values()))

    def test_max_decisions_pauses_and_an_abandoned_attempt_is_logged_not_counted(self):
        r = self.ready()
        self.assertEqual(r.run(max_decisions=2), 3)
        pending = [p["id"] for p in r.manifest()["decision_points"] if p["id"] not in self.finals(r)]
        with open(os.path.join(r.root, K.DECISIONS), "a") as fh:      # a crash left an attempt open
            fh.write(json.dumps({"record": "attempt_start", "decision_id": pending[0], "attempt": 1,
                                 "attempt_uid": "dead", "started_utc": "2026-10-05T00:00:00Z"}) + "\n")
        r.commit("after the crash")
        self.assertEqual(r.run(), 0)
        ab = [x for x in r.log() if x["record"] == "interruption"]
        self.assertEqual([(x["kind"], x["attempt_uid"], x["counts_toward_retry"]) for x in ab],
                         [("abandoned_in_flight", "dead", False)])
        self.assertEqual(self.finals(r)[pending[0]]["attempt"], 2)
        self.assertEqual(r.events(), ["start", "resume", "pause", "resume", "stop"])

    def test_resume_refuses_an_evaluator_changed_after_the_start(self):
        r = self.ready()
        self.assertEqual(r.run(max_decisions=1), 3)
        with open(os.path.join(r.root, K.EVALUATOR), "a") as fh:
            fh.write("# tuned after seeing a decision\n")
        r.commit("evaluator edit")
        with self.assertRaises(K.Refused):
            r.run()

    def test_build_refuses_once_the_run_started(self):
        r = self.ready()
        with self.assertRaises(K.Refused):
            r.build()

    def test_the_isolation_guard_reads_the_cli_json(self):
        self.assertEqual(H.isolation_check(envelope("x")), ([], []))
        self.assertEqual(H.isolation_check(dict(envelope("x"), num_turns=2))[0], ["num_turns=2"])
        self.assertEqual(H.isolation_check({k: v for k, v in envelope("x").items() if k != "num_turns"})[1], ["num_turns"])
        v, _u = H.isolation_check(dict(envelope("x"), modelUsage={"claude-opus-5-5": {"webFetchRequests": 2}}))
        self.assertEqual(v, ["modelUsage.claude-opus-5-5.webFetchRequests=2"])
        self.assertEqual(H.isolation_check(dict(envelope("x"), deferred_tool_use={"name": "Read"}))[0], ["deferred_tool_use"])
        self.assertEqual(H.isolation_check(dict(envelope("x"), permission_denials=None))[1], ["permission_denials"])

    def test_the_circuit_breaker_pauses_a_systematic_fault_before_it_burns_the_run(self):
        bad = {"env": envelope(json.dumps(answer("NO_TRADE")), turns=2)}
        r = self.ready({"calls": [bad, bad, bad], "default": OK})
        ids = [p["id"] for p in r.manifest()["decision_points"]]
        self.assertEqual(r.run(), 3)
        self.assertEqual({k: v["status"] for k, v in self.finals(r).items()}, {ids[0]: "technical_failure"})  # one retry
        self.assertEqual([x for x in r.log() if x["record"] == "run_event"][-1]["reason"],
                         "circuit_breaker:isolation_violation")
        self.assertEqual(len(r.calls()), 3)                         # the second decision's retry waits for the resume
        r.commit("paused")
        self.assertEqual(r.run(), 0)
        fin = self.finals(r)
        self.assertEqual((fin[ids[1]]["attempt"], fin[ids[1]]["retry"], fin[ids[1]]["status"]), (2, True, "answered"))
        self.assertEqual(len(r.calls()), 3 + 4)

    def test_a_rejected_answer_is_kept_by_hash_only(self):
        rejected = json.dumps(answer("LONG", draw_on_liquidity="a phrase only the rejected answer has"))
        r = self.ready({"calls": [{"env": envelope(rejected, model="claude-sonnet-5-5")}], "default": OK})
        self.assertEqual(r.run(), 3)
        self.assertNotIn("a phrase only the rejected answer has", open(os.path.join(r.root, K.DECISIONS)).read())
        tf = [x for x in r.log() if x["record"] == "technical_failure"][0]
        self.assertEqual((tf["answer_sha256"], tf["answer_chars"]), (hashlib.sha256(rejected.encode()).hexdigest(), len(rejected)))

    def test_the_shadow_directory_is_created_by_init(self):
        r = Repo(self, shadow_subdir="not/yet")
        r.start()
        self.assertEqual(r.run(), 0)
        self.assertEqual(K.raw_lines(r.shadow_file()), K.raw_lines(os.path.join(r.root, K.DECISIONS)))

    def test_discarded_uncommitted_decisions_are_detected_by_the_shadow(self):
        r = self.ready()
        self.assertEqual(r.run(max_decisions=2), 3)
        git(r.root, "checkout", "--", K.DECISIONS)                  # back to the committed start event only
        with self.assertRaises(K.Refused):
            r.run()
        os.remove(os.path.join(r.root, K.DECISIONS))
        with self.assertRaises(K.Refused):
            r.run()
        with self.assertRaises(K.Refused):                          # nor can the prompts be rebuilt and asked again
            r.build()

    def test_a_truncated_log_is_refused_and_a_lost_shadow_is_recreated(self):
        r = self.ready()
        self.assertEqual(r.run(max_decisions=2), 3)
        path = os.path.join(r.root, K.DECISIONS)
        lines = open(path).read().splitlines(True)
        open(path, "w").write("".join(lines[:-3]))
        r.commit("truncated")
        with self.assertRaises(K.Refused):                          # the shadow holds the lost records
            r.run()
        open(path, "w").write("".join(lines))
        r.commit("restored")
        os.remove(r.shadow_file())
        self.assertEqual(r.run(), 0)
        events = [x for x in r.log() if x["record"] == "run_event"]
        self.assertEqual([(e["event"], e.get("shadow")) for e in events],
                         [("start", "fresh"), ("resume", "equal"), ("pause", None), ("resume", "recreated"), ("stop", None)])
        self.assertEqual(K.raw_lines(r.shadow_file()), K.raw_lines(path))

    def test_a_committed_log_can_only_grow(self):
        r = self.ready()
        self.assertEqual(r.run(max_decisions=2), 3)
        r.commit("partial decisions")
        path = os.path.join(r.root, K.DECISIONS)
        lines = open(path).read().splitlines(True)
        open(path, "w").write("".join(lines[:3]))                   # the log rewritten AND its shadow:
        open(r.shadow_file(), "w").write("".join(lines[:3]))        # git still holds the committed version
        r.commit("rewritten")
        with self.assertRaises(K.Refused):
            r.run()

    def test_selfcheck_makes_one_isolated_non_market_call(self):
        r = Repo(self)
        self.assertEqual(H.cmd_selfcheck(r.ctx, out=lambda *a: None), 0)
        c = r.calls()[0]
        self.assertEqual(c["argv"][:9], ["-p", "--safe-mode", "--tools", "", "--strict-mcp-config",
                                         "--no-session-persistence", "--model", "claude-opus-5-5", "--system-prompt-file"])
        self.assertEqual((c["cwd_listing"], c["system_sha256"]),
                         ([], hashlib.sha256(H.SELFCHECK_SYSTEM.encode()).hexdigest()))
        self.assertFalse(os.path.exists(os.path.join(r.root, K.DECISIONS)))
        r.scenario({"calls": [{"env": envelope(json.dumps(answer("NO_TRADE")), model="claude-sonnet-5-5")}], "default": OK})
        self.assertEqual(H.cmd_selfcheck(r.ctx, out=lambda *a: None), 1)

    def test_run_starts_with_a_selfcheck_and_refuses_when_it_fails(self):
        r = self.ready({"calls": [{"env": envelope(json.dumps(answer("NO_TRADE")), turns=3)}], "default": OK})
        with self.assertRaises(K.Refused):
            r.run(selfcheck=True)
        self.assertEqual(r.events(), ["start"])                     # no record: no decision was asked
        r.scenario({"calls": [], "default": OK})
        self.assertEqual(r.run(selfcheck=True), 0)
        resume = [x for x in r.log() if x["record"] == "run_event"][1]
        self.assertEqual((resume["selfcheck"]["status"], resume["selfcheck"]["served_models"]), ("ok", ["claude-opus-5-5"]))
        self.assertEqual(len(r.calls()), 1 + 5)

    def test_every_outcome_kind_is_either_retried_once_or_only_pausing(self):
        """classify() maps each kind of call outcome to exactly one of the documented sets RETRYABLE / PAUSING."""
        enc = lambda e: json.dumps(e).encode()                                          # noqa: E731
        cases = [(None, b"", b"", True), (1, b"Segmentation fault", b"", False), (0, b"{not json", b"", False),
                 (1, enc(envelope("x", is_error=True)), b"", False), (0, enc(envelope("")), b"", False),
                 (0, enc(envelope("x", turns=3)), b"", False), (0, enc(envelope("plain prose")), b"", False),
                 (1, b"Claude usage limit reached", b"", False),
                 (0, enc(envelope(json.dumps(answer()), model="claude-sonnet-5-5")), b"", False),
                 (0, enc(envelope(json.dumps(answer()))), b"", False)]
        got = {}
        for c in cases:
            r = H.classify(*c)
            got[r["kind"]] = r["status"]
        self.assertFalse(set(H.RETRYABLE) & set(H.PAUSING))
        for kind, status in got.items():
            self.assertIn(kind, {"retry": H.RETRYABLE, "pause": H.PAUSING, "ok": ("answered",)}[status])
        self.assertEqual(set(got), set(H.RETRYABLE) | {"usage_limit", "model_pin_mismatch", "answered"})

    def test_a_number_in_the_cli_json_is_not_a_rate_limit(self):
        err = dict(envelope("API Error: 500 internal", is_error=True), duration_ms=429, duration_api_ms=529)
        self.assertEqual(H.classify(1, json.dumps(err).encode(), b"", False)["kind"], "cli_error")
        lim = dict(envelope("API Error: 429 rate_limit_error", is_error=True))
        self.assertEqual(H.classify(1, json.dumps(lim).encode(), b"", False)["kind"], "usage_limit")
        self.assertEqual(H.classify(1, b"", b"node:internal/process:429\n    at Object.<anonymous>", False)["kind"],
                         "nonzero_exit")                                    # a stack-trace line number is not a limit
        self.assertEqual(H.classify(1, b"", b"API Error: 529 overloaded", False)["kind"], "usage_limit")

    def test_the_harness_never_imports_the_evaluator(self):
        src = open(os.path.join(ROOT, K.HARNESS), encoding="utf-8").read()
        self.assertIsNone(re.search(r"(import|spec_from_file_location|_load)\b[^\n]*claude_ict_eval", src))
        code = ("import sys; sys.path.insert(0, %r); import claude_ict_harness as H; "
                "assert not [m for m in sys.modules if 'claude_ict_eval' in m]; print('ok')"
                % os.path.join(ROOT, "scripts", "research"))
        self.assertEqual(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout.strip(), "ok")

    def test_build_and_probe_do_not_open_the_evaluator(self):
        r = Repo(self)
        PG.trace_start(r.root)
        r.build()
        seen = set(PG._TRACE["seen"])
        PG._TRACE["on"] = False
        self.assertNotIn(K.EVALUATOR, seen)
        self.assertIn(K.TEMPLATE, seen)                                     # the tracer does see the harness' reads
        self.assertEqual(sorted(r.manifest()["data_pins"]), ["US500|15m", "US500|5m", "XAUUSD|15m", "XAUUSD|5m"])


# ================================================================================================ evaluate refusals
STUBS = {"_engine": lambda hist_root=None: (types.SimpleNamespace(MIN_RR=2.5, resolve_methods=lambda s: ("ict",)),
                                             {"mgmt": "none"}),
         "t_modules": lambda: {},
         "m_scan": lambda *a, **k: ([], {}, {"checked": 0, "failed": 0, "failed_ids": [], "passed": True}),
         "t_scan": lambda *a, **k: {"v3": ([], {}), "v4": ([], {})}}


@contextlib.contextmanager
def stubbed_m_and_t():
    """Arms M and T stubbed: their detectors read the real FTMO history, and no arm's outcome may be computed on the real
    window before the decisions exist (house rule)."""
    with contextlib.ExitStack() as st:
        for name, fn in STUBS.items():
            st.enter_context(mock.patch.object(E, name, fn))
        yield


class Evaluate(unittest.TestCase):
    def done(self, commit=True, scenario=None):
        r = Repo(self)
        r.start()
        if scenario:
            r.scenario(scenario)
        self.assertEqual(r.run(), 0)
        if commit:
            r.commit("decisions")
        return r

    def test_evaluate_refuses_uncommitted_decisions(self):
        r = self.done(commit=False)
        with self.assertRaises(K.Refused):
            E.preconditions(r.ectx())
        with self.assertRaises(K.Refused):
            E.cmd_evaluate(r.ectx(), out=lambda *a: None)

    def test_evaluate_refuses_an_incomplete_run(self):
        r = Repo(self)
        r.start()
        self.assertEqual(r.run(max_decisions=2), 3)
        r.commit("partial decisions")
        with self.assertRaises(K.Refused):
            E.preconditions(r.ectx())

    def test_the_preconditions_hold_on_a_complete_committed_run(self):
        r = self.done()
        man, man_sha, final, events, dec_sha, integ = E.preconditions(r.ectx())
        self.assertEqual(len(final), len(man["decision_points"]))
        self.assertEqual(events[-1]["event"], "stop")
        self.assertEqual(dec_sha, K.sha256_file(os.path.join(r.root, K.DECISIONS)))
        self.assertEqual((integ["shadow"], integ["commits_of_decisions_log_checked"]), ("equal", 2))

    def test_evaluate_runs_once(self):
        r = self.done()
        with open(os.path.join(r.root, K.RESULT), "w") as fh:
            fh.write("{}")
        with self.assertRaises(K.Refused):
            E.preconditions(r.ectx())
        r.commit("a result")
        os.remove(os.path.join(r.root, K.RESULT))
        r.commit("result deleted")
        with self.assertRaises(K.Refused):                             # once committed, never again
            E.preconditions(r.ectx())

    def test_evaluate_refuses_an_evaluator_changed_after_the_run_started(self):
        r = self.done()
        with open(os.path.join(r.root, K.EVALUATOR), "a") as fh:
            fh.write("# changed after the decisions were seen\n")
        r.commit("evaluator edit")
        with self.assertRaises(K.Refused):
            E.preconditions(r.ectx())

    def test_evaluate_refuses_a_decision_log_edited_after_the_run(self):
        r = self.done()
        path = os.path.join(r.root, K.DECISIONS)
        lines = open(path).read().splitlines()
        i = next(n for n, l in enumerate(lines) if json.loads(l)["record"] == "decision")
        rec = json.loads(lines[i])
        rec["prompt_sha256"] = "0" * 64
        lines[i] = json.dumps(rec)
        open(path, "w").write("\n".join(lines) + "\n")
        r.commit("edited")
        with self.assertRaises(K.Refused):
            E.preconditions(r.ectx())

    def test_evaluate_refuses_an_answer_edited_with_its_shadow(self):
        r = self.done(commit=False)
        path = os.path.join(r.root, K.DECISIONS)
        text = open(path).read().replace("NO_TRADE", "LONG")       # the log AND its shadow edited before any commit
        open(path, "w").write(text)
        open(r.shadow_file(), "w").write(text)
        r.commit("decisions")
        with self.assertRaises(K.Refused):
            E.preconditions(r.ectx())

    def test_evaluate_refuses_a_dependency_changed_after_the_start(self):
        r = self.done()
        with open(os.path.join(r.root, "scripts", "real_costs.py"), "a") as fh:
            fh.write("# a cost rule changed after the decisions were seen\n")
        r.commit("cost edit")
        with stubbed_m_and_t(), self.assertRaises(K.Refused):
            E.cmd_evaluate(r.ectx(), out=lambda *a: None)
        self.assertFalse(os.path.exists(os.path.join(r.root, K.RESULT)))

    def test_evaluate_refuses_bars_changed_after_the_build(self):
        r = self.done()
        p = os.path.join(r.hist, "ohlcv.US500.5m.json")
        doc = json.load(open(p))
        doc["candles"][-30]["close"] += 0.01                         # a re-export corrected one bar inside the window
        json.dump(doc, open(p, "w"))
        with stubbed_m_and_t(), self.assertRaises(K.Refused):
            E.cmd_evaluate(r.ectx(), out=lambda *a: None)


class EvaluateEndToEnd(unittest.TestCase):
    def test_a_complete_evaluation_is_written_once(self):
        r = Repo(self)
        r.start()
        r.scenario({"calls": [], "default": {"env": envelope(json.dumps(answer(order="market", entry=100.0, stop=1.0,
                                                                                     target=10000.0)))}})
        self.assertEqual(r.run(), 0)
        r.commit("decisions")
        with stubbed_m_and_t():
            self.assertEqual(E.cmd_evaluate(r.ectx(), out=lambda *a: None), 0)
            with self.assertRaises(K.Refused):
                E.cmd_evaluate(r.ectx(), out=lambda *a: None)
        res = json.load(open(os.path.join(r.root, K.RESULT)))
        self.assertEqual(res["verdict"]["status"], "INSUFFICIENT")
        c = res["arms"]["C"]["counts"]
        self.assertEqual((c["decision_points"], c["orders"], c["filled"], c["invalid_answers"]), (5, 5, 5, 0))
        self.assertEqual(res["arms"]["C"]["metrics"]["exits"], {"time": 5})
        self.assertEqual(c["answer_forms"], {"whole": 5})
        R = res["arms"]["R"]
        self.assertEqual(R["same_direction_differs_from_C"], 0)
        self.assertEqual(R["shuffle_within_instrument"]["p_one_sided"], 1.0)    # all LONG: every shuffle is C itself
        self.assertEqual(R["shuffle_within_instrument"]["strata"], {"US500": 3, "XAUUSD": 2})
        self.assertEqual((R["mirror_order"]["n_orders"], R["mirror_order"]["p_one_sided"]), (5, 1.0))
        self.assertEqual({d["mirror_outcome"] for d in res["arms"]["C"]["decisions"]}, {"filled"})
        self.assertEqual(res["verdict"]["c_beats_m"], "not evaluable")
        self.assertEqual(len(res["sample_10"]), 5)
        self.assertEqual(res["meta"]["log_integrity"]["shadow"], "equal")
        self.assertEqual(res["meta"]["frozen_inputs"]["data_pins"], r.manifest()["data_pins"])
        self.assertEqual(sorted(res["arms"]["C"]["by_killzone"]),
                         ["US500|london", "US500|ny_am", "US500|ny_pm", "XAUUSD|london", "XAUUSD|ny_am"])


class MLeakageProbe(unittest.TestCase):
    """Reviewing session, constraint 3: the arm M probe runs inside `evaluate`; a failed probe excludes M, and "C beats M"
    is `not evaluable`, never passed, so the verdict cannot be PASS."""

    def test_a_failed_m_probe_excludes_m_and_the_verdict_cannot_be_pass(self):
        r = Repo(self)
        r.start()
        r.scenario({"calls": [], "default": {"env": envelope(json.dumps(answer(order="market", entry=100.0, stop=1.0,
                                                                                     target=10000.0)))}})
        self.assertEqual(r.run(), 0)
        r.commit("decisions")
        failing = {"checked": 3, "failed": 1, "failed_ids": ["XAUUSD|long|a|b"], "passed": False}
        with contextlib.ExitStack() as st:
            for name, fn in dict(STUBS, m_scan=lambda *a, **k: ([], {}, dict(failing))).items():
                st.enter_context(mock.patch.object(E, name, fn))
            self.assertEqual(E.cmd_evaluate(r.ectx(), out=lambda *a: None), 0)
        res = json.load(open(os.path.join(r.root, K.RESULT)))
        v = res["verdict"]
        self.assertEqual((v["m_evaluable"], v["c_beats_m"]), (False, "not evaluable"))
        self.assertFalse(v["m_leakage_probe"]["XAUUSD"]["passed"])
        self.assertEqual(res["arms"]["M"]["leakage_probe"]["US500"]["failed_ids"], ["XAUUSD|long|a|b"])
        # every other PASS condition holding, the label is INCOMPLETE; with an evaluable M the same numbers PASS
        self.assertEqual(E.verdict(80, 0.01, 0.3, v["m_evaluable"], None, p_mirror=0.01), "INCOMPLETE (C vs M not evaluable)")
        self.assertEqual(E.verdict(80, 0.01, 0.3, True, 0.1, p_mirror=0.01), "PASS")

    def test_the_probe_redetects_every_intent_on_the_series_cut_after_its_detection_bar(self):
        """m_probe on a stub engine: an intent the cut series reproduces passes; one it does not reproduce (a detection
        that needed a later bar) fails, and so does an edge the cut series already shows as traded."""
        class Cut:
            def __init__(self, found):
                self.found, self.calls = found, []

            def _ict_ctx(self, sym, tf, c, Tm, HZ, H, L, C, methods):
                self.calls.append(len(c))                                # the series it is given ends at the detection bar
                return types.SimpleNamespace(idx_of_time={"m": 1}, K=16, fx_opts={}, n=len(c))

            def _ict_candidate(self, x, i, a):
                return self.found

            fvg_formed_start = staticmethod(lambda su, idx: None)
            OPTS = {}
            lr = types.SimpleNamespace(read_at=lambda c, i, tf, methods, opts=None: {"facts": 1})
            fvg_fill = staticmethod(lambda *a, **k: None)                # the edge is untouched on the cut series

        su = {"side": "long", "sweep": {"time": "s"}, "mss": {"time": "m"}, "entry": 100.0, "stop": 99.0, "target": 103.0,
              "entry_models": {"fill": 99.5}}
        candles = [bar(f"2026-06-10T0{h}:00:00Z", 100, 101, 99, 100) for h in range(6)]
        it = {"id": "X", "_i": 3, "_key": ("long", "s", "m", 100.0, 99.0, 103.0)}
        ok_eng = Cut(su)
        same = E.m_probe(ok_eng, "XAUUSD", candles, 96, [it])
        self.assertEqual((same["checked"], same["failed"], same["passed"]), (1, 0, True))
        self.assertEqual(ok_eng.calls, [4])                               # re-detected on bars[:i + 1] only
        eng = Cut(None)
        gone = E.m_probe(eng, "XAUUSD", candles, 96, [it])
        self.assertEqual((gone["failed"], gone["failed_ids"], gone["passed"]), (1, ["X"], False))
        self.assertEqual(eng.calls, [4])                                  # re-detected on bars[:i + 1] only
        touched = Cut(su)
        touched.fvg_fill = staticmethod(lambda *a, **k: (2, "filled"))    # the edge had already traded by the cut
        self.assertFalse(E.m_probe(touched, "XAUUSD", candles, 96, [it])["passed"])


# ================================================================================================ review fixes
class ReviewFixes(unittest.TestCase):
    def test_a_stop_inside_the_spread_is_hit_at_once_at_the_market(self):
        b = book([(0, 101, 101.2, 100.8, 101), (5, 101, 101, 99.4, 99.6)])
        r = E.simulate(b, order(entry=100.0, stop=99.9, target=101.0))
        self.assertEqual((r["exit_reason"], r["exit_price"], r["exit_time"]), ("stop_inside_spread", 99.5, tl(5)))
        self.assertAlmostEqual(r["R"], (99.5 - 100.0) / 0.6)

    def test_c_needs_a_price_at_the_killzone_open(self):
        b = book([(0, 101, 101.2, 100.8, 101), (10, 101, 101, 99.4, 99.6)])
        o = dict(order(placed=5), bar_at_placement=True)
        self.assertEqual(E.simulate(b, o), {"status": "rejected", "reason": "no_price_at_placement"})
        self.assertEqual(E.simulate(b, order(placed=5))["status"], "filled")    # M / T: placed at the next price

    def test_the_mirror_order_is_the_same_order_on_the_other_side(self):
        m = E.mirror_order(order(entry=100.0, stop=99.0, target=102.0), 101.0)            # ASK 101.5: 1.5 below
        self.assertEqual((m["side"], m["kind"], m["entry"], m["stop"], m["target"]), (-1, "limit", 102.5, 103.5, 100.5))
        s = E.mirror_order(order(side=-1, kind="stop", entry=99.0, stop=100.0, target=97.0), 101.0)  # BID 101: 2 below
        self.assertEqual((s["side"], s["entry"], s["stop"], s["target"]), (1, 103.5, 102.5, 105.5))   # ASK 101.5: 2 above
        mk = E.mirror_order(order(kind="market", entry=90.0, stop=99.0, target=104.0), 101.0)   # C fills at the ASK 101.5
        self.assertEqual((mk["side"], mk["entry"], mk["stop"], mk["target"]), (-1, 101.0, 103.5, 98.5))

    def test_the_mirror_test(self):
        units = [(1, 1.0, -1.0), (-1, 0.5, None), (1, None, 0.2), (-1, 0.8, -0.4)] * 10
        a = E.mirror_test(units, n_perm=400)
        self.assertEqual(a, E.mirror_test(units, n_perm=400))
        self.assertAlmostEqual(a["observed_mean_R_per_order"], (1.0 + 0.5 + 0.0 + 0.8) / 4)
        self.assertLess(a["p_one_sided"], 0.01)
        self.assertEqual(E.mirror_test([(1, 1.0, -1.0)] * 20, n_perm=100)["p_one_sided"], 1.0)    # one side only
        self.assertIsNone(E.mirror_test([]))

    def test_a_per_instrument_static_direction_cannot_pass_the_primary_test(self):
        dirs = [-1] * 35 + [1] * 35
        rng = random.Random(1)
        noise = [rng.gauss(0, 1) for _ in range(70)]
        r_c, r_opp = [0.25 + e for e in noise], [-0.25 - e for e in noise]
        inst = ["XAUUSD"] * 35 + ["US500"] * 35
        self.assertLess(E.permutation_test(r_c, dirs, r_c, r_opp, n_perm=2000, tag="g")["p_one_sided"], 0.05)
        self.assertEqual(E.permutation_test(r_c, dirs, r_c, r_opp, n_perm=500, strata=inst)["p_one_sided"], 1.0)

    def test_the_mirror_test_gates_the_pass_since_amendment_1(self):
        """Amendment 1 (2026-10-05): a PASS needs the mirror-order test as well as the pre-registered primary test."""
        self.assertTrue(E.MIRROR_CONTROL_GATES)
        self.assertEqual(E.verdict(80, 0.01, 0.3, True, 0.1, p_mirror=0.4), "NOT_PASS")
        self.assertEqual(E.verdict(80, 0.01, 0.3, True, 0.1, p_mirror=None), "NOT_PASS")
        self.assertEqual(E.verdict(80, 0.01, 0.3, True, 0.1, p_mirror=0.01), "PASS")
        self.assertEqual(E.verdict(80, 0.2, 0.3, True, 0.1, p_mirror=0.01), "FAIL")           # the primary test still decides FAIL
        self.assertEqual(E.verdict(59, 0.01, 0.3, True, 0.1, p_mirror=0.01), "INSUFFICIENT")
        with mock.patch.object(E, "MIRROR_CONTROL_GATES", False):                              # the pre-registration's own text
            self.assertEqual(E.verdict(80, 0.01, 0.3, True, 0.1, p_mirror=0.4), "PASS")

    def test_calibrate_runs_on_bars_before_the_window_only(self):
        hist = tempfile.mkdtemp(prefix="ic-cal-")
        self.addCleanup(shutil.rmtree, hist, True)
        for i, sym in enumerate(K.INSTRUMENTS):
            with open(os.path.join(hist, f"ohlcv.{sym}.5m.json"), "w") as fh:
                json.dump({"symbol": sym, "timeframe": "5m",
                           "candles": synth("2026-06-01T00:00:00Z", "2026-06-20T00:00:00Z", 5 + i, 100.0 * (i + 1))}, fh)
        res = E.cmd_calibrate(since="2026-06-03T00:00:00Z", until="2026-06-19T00:00:00Z", reps=4, n_trades=10, n_orders=10,
                              n_perm=20, hist_root=hist, out=lambda *a: None)
        self.assertEqual(sorted(res), sorted(f"{s}|{k}" for s in K.INSTRUMENTS for k in ("market", "limit", "stop")))
        self.assertTrue(all(0 <= v["primary_size"] <= 1 and 0 <= v["mirror_size"] <= 1 for v in res.values()))
        with self.assertRaises(K.Refused):
            E.cmd_calibrate(since="2026-06-03T00:00:00Z", until="2026-07-02T00:00:00Z", hist_root=hist)


if __name__ == "__main__":
    unittest.main()
