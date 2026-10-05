#!/usr/bin/env python3
"""Prompt harness of experiment IC, "can Claude trade ICT discretionarily with an edge?"
(docs/plans/2026-10-04-claude-ict-discretionary-preregistration.md §3; implementation note
docs/plans/2026-10-04-claude-ict-implementation.md). RESEARCH ONLY: no account, no order path.

    python3 scripts/research/claude_ict_harness.py points                 # decision points + skips (bar times only)
    python3 scripts/research/claude_ict_harness.py build [--out-dir DIR]  # every prompt + the manifest, no model call
    python3 scripts/research/claude_ict_harness.py probe [--n 12]         # truncation probe on real data, no model call
    python3 scripts/research/claude_ict_harness.py selfcheck              # ONE call, fixed non-market prompt: CLI JSON check
    python3 scripts/research/claude_ict_harness.py init                   # the `start` event only, no decision; commit it
    python3 scripts/research/claude_ict_harness.py run [--concurrency 4] [--max-decisions N]   # the ONE run, resumable
    python3 scripts/research/claude_ict_harness.py status

Point in time. A prompt is built from the closed 5m BID bars whose open time is strictly before the killzone open (every
killzone opens on a 5m boundary, so each such bar has closed by then), at most 30 days back: 4H / 1H the last 60 closed
bars, 15m the last 96, 5m the last 48, the higher timeframes built here from those 5m bars on the broker's clock; the
previous server day's high / low, the server week-to-date high / low and the Asia session (20:00-00:00 New York) high /
low; the spread snapshot of the killzone-open hour. `probe` and the unit tests prove it: the prompt built from the full
series, from the series cut at the killzone open, and from a series whose every later bar is changed, are byte-identical.

Isolation (`run`). Each decision is one fresh process, prompt on stdin, cwd an empty temporary directory:
    claude -p --safe-mode --tools "" --strict-mcp-config --no-session-persistence --model claude-opus-5-5
           --system-prompt-file <file> --output-format json
No tool exists in that process (no file read, no web fetch / search, no MCP server). An answer whose CLI JSON shows
num_turns > 1, a permission denial, a deferred tool use or any server-side tool counter > 0 is a technical failure.
The served model(s) are read from `modelUsage`; a set other than exactly {claude-opus-5-5} is logged as a technical
failure and the run PAUSES (retried when the pinned model is served again; --fallback-model is never passed); no model
information at all is recorded as `served_model_unverifiable`. A technical failure (timeout, non-zero exit, invalid CLI
JSON, CLI error, empty answer, no JSON object in the answer, isolation violation) gets exactly ONE retry, logged; a
usage-limit / overload / operator interruption only pauses the run (not counted). BREAKER consecutive counted failures
of one kind (any decisions) pause the run before another call, so a systematic fault cannot burn the single run; the
deferred retries run on resume. `init` writes the run's `start` event and asks nothing; `run` refuses until that event is
committed, and later refuses any uncommitted record, so every record of one invocation is in git before the next one asks
anything. `run` resumes with the same committed inputs and never regenerates a stored decision.
It refuses unless the template, the knowledge files, this harness, the shared module, the evaluator, the manifest and
every prompt file are committed and unchanged (sha256 = manifest). Every record is also appended to a shadow copy
outside the repository (IC_SHADOW_DIR, default ~/.local/state/trading-decision-system/claude-ict/); `run` refuses when
decisions.jsonl lost records the shadow holds, or when a committed version of decisions.jsonl is not a prefix of it.

This module never imports or opens scripts/research/claude_ict_eval.py; `run` asks git (a subprocess) whether that file
is committed and records its blob id, so the evaluator is frozen before the first decision exists.
"""
import argparse
import bisect
import concurrent.futures
import datetime
import fcntl
import hashlib
import json
import os
import random
import re
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import threading
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts", "research"))
import claude_ict_common as K  # noqa: E402

TD = datetime.timedelta
TAIL = TD(days=30)                    # the oldest 5m bar a prompt may read, before the killzone open
LOOKBACK = (("4H", 240, 60), ("1H", 60, 60), ("15m", 15, 96), ("5m", 5, 48))   # (name, minutes, bars) -- §3
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
SYSTEM_MARKERS = ("<!-- BEGIN SYSTEM -->", "<!-- END SYSTEM -->")
USER_MARKERS = ("<!-- BEGIN USER -->", "<!-- END USER -->")
KB_PLACEHOLDER = "KNOWLEDGE_BASE"
PLACEHOLDER = re.compile(r"\{\{([A-Za-z0-9_]+)\}\}")
USER_FIELDS = ("instrument", "instrument_note", "digits", "killzone_label", "killzone_et", "killzone_set", "weekday",
               "date_et", "kz_open_utc", "et_utc_offset", "kz_end_utc", "time_exit_utc", "last_bar_utc", "last_close",
               "spread", "commission", "prev_day_span", "prev_day_levels", "week_span", "week_levels", "asia_span",
               "asia_levels", "n_4h", "bars_4h", "n_1h", "bars_1h", "n_15m", "bars_15m", "n_5m", "bars_5m")
CHARS_PER_TOKEN = 3.5                 # estimate only (no tokenizer call: no model / API call is made by build)

CALL_TIMEOUT_S = 900                  # one decision; a timeout is a technical failure
RETRY_DELAY_S = 30                    # before the one retry of a technical failure
MAX_CONCURRENCY = 4
BREAKER = 3                           # consecutive counted technical failures of one kind -> pause before another call
SELFCHECK_SYSTEM = "You reply with exactly one JSON object and nothing else."
SELFCHECK_USER = 'Reply with exactly this JSON object and nothing else: {"decision": "NO_TRADE", "selfcheck": true}'
RETRYABLE = ("timeout", "nonzero_exit", "invalid_cli_json", "cli_error", "empty_result", "isolation_violation",
             "no_json_in_answer")
PAUSING = ("usage_limit", "model_pin_mismatch", "killed_by_signal", "operator_interrupt")   # not counted
LIMIT_RE = re.compile(r"usage limit|limit reached|hit your limit|rate.?limit|too many requests|overloaded|"
                      r"(?:\bHTTP[ /0-9.]*|\bstatus[ :=]*|\berror[ :]*|\bcode[ :=]*)(?:429|529)\b|credit balance|"
                      r"out of (?:extra )?usage|resets? (?:at|in)\b|quota", re.I)
SERVER_TOOL_KEY = re.compile(r"web_?search|web_?fetch|server_?tool|code_?execution", re.I)
ENVELOPE_KEYS = ("type", "subtype", "is_error", "api_error_status", "num_turns", "duration_ms", "duration_api_ms",
                 "total_cost_usd", "usage", "modelUsage", "permission_denials", "stop_reason", "terminal_reason",
                 "session_id", "uuid", "errors")


class TemplateError(ValueError):
    pass


def cli_command(claude_bin, system_file):
    """The isolated call, exactly as agreed with the reviewing session (implementation note §3). Never --fallback-model."""
    return [claude_bin, "-p", "--safe-mode", "--tools", "", "--strict-mcp-config", "--no-session-persistence",
            "--model", K.MODEL_ID, "--system-prompt-file", system_file, "--output-format", "json",
            "--effort", K.EFFORT]


class Ctx:
    """Where a command reads and writes. The CLI uses the repository defaults; the tests point it at a temporary git
    repository and a synthetic history (`root`, `hist_root`, `window`, `claude_bin`)."""

    def __init__(self, root=None, hist_root=None, exp_dir=None, window=None, instruments=K.INSTRUMENTS,
                 claude_bin=None, timeout_s=CALL_TIMEOUT_S, retry_delay_s=RETRY_DELAY_S, shadow_dir=None):
        self.root = root or K.ROOT
        self.shadow_dir = K.shadow_dir(shadow_dir)
        self.hist_root = hist_root or K.HIST_ROOT
        self.exp_dir = exp_dir or K.EXP_DIR            # relative to root, or absolute (a scratch build)
        self.window = window or K.window_bounds()
        self.instruments = tuple(instruments)
        self.claude_bin = claude_bin or os.environ.get("IC_CLAUDE_BIN") or shutil.which("claude")
        self.timeout_s = timeout_s
        self.retry_delay_s = retry_delay_s

    def path(self, rel):
        return rel if os.path.isabs(rel) else os.path.join(self.root, rel)

    def exp(self, *parts):
        return os.path.join(self.exp_dir, *parts)

    @property
    def manifest_rel(self):
        return self.exp("manifest.json")

    @property
    def prompts_rel(self):
        return self.exp("prompts")

    @property
    def decisions_rel(self):
        return self.exp("decisions.jsonl")

    def shadow_path(self, manifest_sha):
        return K.shadow_path(manifest_sha, self.shadow_dir)


# ------------------------------------------------------------------------------------------------ template
def split_template(text):
    """(system block, user block): the text between each BEGIN / END marker pair, which must each occur once."""
    def block(a, b):
        if text.count(a) != 1 or text.count(b) != 1:
            raise TemplateError(f"the template must hold exactly one {a!r} and one {b!r}")
        i, j = text.index(a) + len(a), text.index(b)
        if j < i:
            raise TemplateError(f"{b!r} comes before {a!r}")
        body = text[i:j]
        body = body[1:] if body.startswith("\n") else body
        return body[:-1] if body.endswith("\n") else body
    return block(*SYSTEM_MARKERS), block(*USER_MARKERS)


def render(block, values):
    """Fill every {{name}} of `block` in one pass. Refuses a placeholder without a value and a value without a
    placeholder, so the template and the harness cannot drift apart silently."""
    names = set(PLACEHOLDER.findall(block))
    missing, extra = sorted(names - set(values)), sorted(set(values) - names)
    if missing or extra:
        raise TemplateError(f"placeholders without a value: {missing}; values without a placeholder: {extra}")
    return PLACEHOLDER.sub(lambda m: str(values[m.group(1)]), block)


def knowledge_base_text(root):
    parts = []
    for rel in K.KB_FILES:
        with open(os.path.join(root, rel), encoding="utf-8") as fh:
            body = fh.read()
        parts.append(f'<document path="{rel}">\n{body if body.endswith(chr(10)) else body + chr(10)}</document>')
    return "\n\n".join(parts)


def system_prompt(root, template_text):
    sys_block, _ = split_template(template_text)
    if set(PLACEHOLDER.findall(sys_block)) != {KB_PLACEHOLDER}:
        raise TemplateError(f"the system block must carry exactly {{{{{KB_PLACEHOLDER}}}}}")
    out = render(sys_block, {KB_PLACEHOLDER: knowledge_base_text(root)})
    if K.SYSTEM_BOUNDARY in out:
        raise TemplateError(f"{K.SYSTEM_BOUNDARY} in the system prompt would make the CLI split it")
    return out


# ------------------------------------------------------------------------------------------------ point-in-time view
class Bars:
    """One instrument's 5m BID bars plus the clock fields a prompt needs. The clock fields come from the bar TIMES
    only; a price is read only through `prompt_values`, and only for bars before the killzone open."""

    def __init__(self, sym, candles):
        self.sym = sym
        self.c = candles
        self.times = [b["time"] for b in candles]
        zone = K.server_zone()
        self.dt = [K.parse_z(t) for t in self.times]
        local = [d.astimezone(zone) for d in self.dt]
        self.srv_date = [x.date() for x in local]
        self.srv_min = [x.hour * 60 + x.minute for x in local]


def market_view(bars, cut):
    """(k0, k): bars[k0:k] are the bars a prompt for a killzone opening at `cut` may read -- open time strictly before
    `cut` (so closed by `cut`) and not older than TAIL. Bisects on the time labels; reads no price."""
    if cut.second or cut.microsecond or cut.minute % 5:
        raise ValueError(f"killzone open {cut} is not on a 5m boundary")
    return bisect.bisect_left(bars.times, K.iso_z(cut - TAIL)), bisect.bisect_left(bars.times, K.iso_z(cut))


def aggregate(bars, k0, k, minutes, cut):
    """[[start, open, high, low, close], ...]: `minutes` bars built from bars[k0:k] on the broker clock (buckets are
    multiples of `minutes` from the server midnight -- the 4H bars FTMO's MT5 draws), each kept only when the bucket
    ENDS at or before `cut` (a closed bar)."""
    out, cur = [], None
    for j in range(k0, k):
        start = bars.dt[j] - TD(minutes=bars.srv_min[j] % minutes)
        b = bars.c[j]
        if cur is None or start != cur[0]:
            if cur is not None:
                out.append(cur)
            cur = [start, b["open"], b["high"], b["low"], b["close"]]
        else:
            cur[2] = max(cur[2], b["high"])
            cur[3] = min(cur[3], b["low"])
            cur[4] = b["close"]
    if cur is not None:
        out.append(cur)
    return [x for x in out if x[0] + TD(minutes=minutes) <= cut]


def _hl(bars, js):
    hi = lo = None
    for j in js:
        b = bars.c[j]
        hi = b["high"] if hi is None else max(hi, b["high"])
        lo = b["low"] if lo is None else min(lo, b["low"])
    return hi, lo


def reference_levels(bars, k0, k, cut):
    """{name: (span label, high, low)} -- high / low None = MISSING. Day = the FTMO server day (server midnight =
    17:00 New York, the broker's daily bar; knowledge/ict/core-a.md §6 adaptation notes: one fixed boundary per
    instrument); previous day = the latest server day before the killzone's that has bars. Week = the server week
    (Monday 00:00 server = Sunday 17:00 New York) up to the killzone open. Asia = 20:00 -> 00:00 New York ending on
    the killzone's New York date."""
    d_now = K.server_date(cut)
    j = k - 1
    while j >= k0 and bars.srv_date[j] >= d_now:
        j -= 1
    prev = (f"no earlier server day in the last {TAIL.days} days", None, None)
    if j >= k0:
        d_prev = bars.srv_date[j]
        js = []
        while j >= k0 and bars.srv_date[j] == d_prev:
            js.append(j)
            j -= 1
        span = (f"FTMO server day {d_prev}: {K.et_label(K.server_midnight(d_prev))} to "
                f"{K.et_label(K.server_midnight(d_prev + TD(days=1)))} New York")
        complete = j >= k0 or (k0 > 0 and bars.srv_date[k0 - 1] != d_prev) or k0 == 0
        prev = (span, *_hl(bars, js)) if complete else (span + ", cut by the 30-day limit", None, None)
    wk = d_now - TD(days=d_now.weekday())
    js = []
    j = k - 1
    while j >= k0 and bars.srv_date[j] >= wk:
        js.append(j)
        j -= 1
    week = (f"since {K.et_label(K.server_midnight(wk))} New York, the start of the FTMO server week", *_hl(bars, js))
    d_et = cut.astimezone(K.ET).date()
    a0, a1 = K.et_instant(d_et - TD(days=1), K.ASIA_ET[0]), K.et_instant(d_et, K.ASIA_ET[1])
    ia = max(k0, bisect.bisect_left(bars.times, K.iso_z(a0)))
    ib = min(k, bisect.bisect_left(bars.times, K.iso_z(a1)))
    asia = (f"{K.et_label(a0)} to {K.et_label(a1)} New York", *_hl(bars, range(ia, ib)))
    return {"prev_day": prev, "week": week, "asia": asia}


def _fmt(x, d):
    return f"{x:.{d}f}"


def _rows(rows, d):
    return "\n".join(f"{K.short_z(r[0])},{_fmt(r[1], d)},{_fmt(r[2], d)},{_fmt(r[3], d)},{_fmt(r[4], d)}" for r in rows)


def prompt_values(point, bars, spread):
    """Every {{placeholder}} of the user block for one decision point, from bars[k0:k] only (see market_view)."""
    sym = point["instrument"]
    cut, end, texit = (K.parse_z(point[k]) for k in ("kz_open_utc", "kz_end_utc", "time_exit_utc"))
    k0, k = market_view(bars, cut)
    if k <= k0:
        raise K.Refused(f"refused: {point['id']}: no closed 5m bar in the {TAIL.days} days before the killzone open")
    d = spread["digits"]
    lv = reference_levels(bars, k0, k, cut)
    a, b = next((a, b) for kid, _l, a, b in K.killzones(sym) if kid == point["killzone"])
    vals = {"instrument": sym, "instrument_note": K.INSTRUMENT_NOTE[sym], "digits": str(d),
            "killzone_label": point["killzone_label"], "killzone_et": f"{a[0]:02d}:{a[1]:02d}-{b[0]:02d}:{b[1]:02d}",
            "killzone_set": K.KILLZONE_SET[sym], "weekday": WEEKDAYS[datetime.date.fromisoformat(point["date_et"]).weekday()],
            "date_et": point["date_et"], "kz_open_utc": K.short_z(cut), "et_utc_offset": K.et_offset_label(cut),
            "kz_end_utc": K.short_z(end), "time_exit_utc": K.short_z(texit),
            "last_bar_utc": K.short_z(bars.dt[k - 1]), "last_close": _fmt(bars.c[k - 1]["close"], d),
            "spread": _fmt(spread["spread"], d), "commission": _fmt(spread["commission"], 0)}
    for name in ("prev_day", "week", "asia"):
        span, hi, lo = lv[name]
        vals[f"{name}_span"] = span
        vals[f"{name}_levels"] = "MISSING" if hi is None else f"high {_fmt(hi, d)}, low {_fmt(lo, d)}"
    for name, minutes, n in LOOKBACK:
        rows = aggregate(bars, k0, k, minutes, cut)[-n:]
        key = name.lower()
        vals[f"n_{key}"] = str(len(rows))
        vals[f"bars_{key}"] = _rows(rows, d)
    return vals


def user_prompt(user_block, point, bars, spread):
    return render(user_block, prompt_values(point, bars, spread))


def est_tokens(chars):
    return int(round(chars / CHARS_PER_TOKEN))


# ------------------------------------------------------------------------------------------------ points / build / probe
def load_all(ctx):
    since = ctx.window[0] - TAIL - TD(days=7)
    return {sym: Bars(sym, K.load_bars(sym, ctx.hist_root, since=since, until=ctx.window[1])) for sym in ctx.instruments}


def enumerate_points(ctx, bars_by):
    return K.decision_points({s: b.times for s, b in bars_by.items()}, ctx.window[0], ctx.window[1],
                             instruments=ctx.instruments)


def cmd_points(ctx):
    bars_by = load_all(ctx)
    points, skipped = enumerate_points(ctx, bars_by)
    print(f"window {K.iso_z(ctx.window[0])} -> {K.iso_z(ctx.window[1])} (end = close of the last bar)")
    for sym in ctx.instruments:
        for kid, label, _a, _b in K.killzones(sym):
            n = sum(1 for p in points if p["instrument"] == sym and p["killzone"] == kid)
            s = [p["date_et"] for p in skipped if p["instrument"] == sym and p["killzone"] == kid]
            print(f"  {sym:7s} {label:12s} decision points {n:4d}  skipped {len(s)} {s}")
    print(f"decision points: {len(points)}; skipped (no 5m bar in the killzone): {len(skipped)}")
    return points, skipped


def decisions_started(ctx):
    """True when decisions.jsonl holds any record or was ever committed (then no prompt may change, §7)."""
    p = ctx.path(ctx.decisions_rel)
    if os.path.exists(p) and os.path.getsize(p) > 0:
        return True
    return not os.path.isabs(ctx.exp_dir) and K.ever_committed(ctx.root, ctx.decisions_rel)


def cmd_build(ctx):
    if decisions_started(ctx):
        raise K.Refused(f"refused: {ctx.decisions_rel} exists or was committed -- no prompt may change after the first "
                        f"decision is generated (pre-registration §7)")
    if not os.path.isabs(ctx.exp_dir) and K.shadows_with_records(ctx.shadow_dir):
        raise K.Refused(f"refused: a shadow decision log holds records ({K.shadows_with_records(ctx.shadow_dir)}) -- "
                        f"decisions were already generated; no prompt may change (pre-registration §7)")
    ok, found = K.kb_glob_matches(ctx.root)
    if not ok:
        raise K.Refused(f"refused: knowledge/ict/*.md is {found}, KB_FILES embeds {list(K.KB_FILES)} -- decide first")
    with open(ctx.path(K.TEMPLATE), encoding="utf-8") as fh:
        template_text = fh.read()
    system = system_prompt(ctx.root, template_text)
    _, user_block = split_template(template_text)
    if set(PLACEHOLDER.findall(user_block)) != set(USER_FIELDS):
        raise TemplateError(f"the user block's placeholders {sorted(set(PLACEHOLDER.findall(user_block)))} are not "
                            f"the harness fields {sorted(USER_FIELDS)}")
    bars_by = load_all(ctx)
    points, skipped = enumerate_points(ctx, bars_by)
    pdir = ctx.path(ctx.prompts_rel)
    os.makedirs(pdir, exist_ok=True)
    for f in os.listdir(pdir):                       # only this harness's own files
        if f == K.SYSTEM_PROMPT_NAME or re.match(r"^\d{4}-\d{2}-\d{2}_[A-Z0-9]+_[a-z_]+\.txt$", f):
            os.remove(os.path.join(pdir, f))
    sys_bytes = system.encode("utf-8")
    with open(os.path.join(pdir, K.SYSTEM_PROMPT_NAME), "wb") as fh:
        fh.write(sys_bytes)
    rows, sizes = [], []
    for p in points:
        spread = K.spread_snapshot(p["instrument"], K.parse_z(p["kz_open_utc"]))
        text = user_prompt(user_block, p, bars_by[p["instrument"]], spread)
        data = text.encode("utf-8")
        name = K.prompt_name(p["id"])
        with open(os.path.join(pdir, name), "wb") as fh:
            fh.write(data)
        sizes.append(len(text))
        rows.append(dict(p, prompt_file=name, prompt_sha256=K.sha256_bytes(data), prompt_chars=len(text),
                         prompt_est_tokens=est_tokens(len(text)), spread=spread))
    libs = {rel: K.sha256_file(os.path.join(K.ROOT, rel)) for rel in K.BUILD_LIBS}
    man = {
        "experiment": K.EXPERIMENT, "preregistration": K.PREREG, "implementation_note": K.IMPL_NOTE,
        "built_at_utc": K.iso_z(K.utc_now()),
        "window": {"start": K.iso_z(ctx.window[0]), "end_close_of_last_bar": K.iso_z(ctx.window[1])},
        "instruments": {s: {"killzone_set": K.KILLZONE_SET[s],
                            "killzones": [[kid, lab, f"{a[0]:02d}:{a[1]:02d}", f"{b[0]:02d}:{b[1]:02d}"]
                                          for kid, lab, a, b in K.killzones(s)]} for s in ctx.instruments},
        "lookback": {name: n for name, _m, n in LOOKBACK}, "tail_days": TAIL.days,
        "model": K.MODEL_ID, "cli_args": cli_command("claude", "<system prompt file>")[1:],
        "template": {"path": K.TEMPLATE, "sha256": K.sha256_file(ctx.path(K.TEMPLATE))},
        "knowledge_base": [{"path": rel, "sha256": K.sha256_file(ctx.path(rel))} for rel in K.KB_FILES],
        "code": {rel: K.sha256_file(ctx.path(rel)) for rel in (K.COMMON, K.HARNESS)},
        "build_libraries": libs,
        "dataset": {s: K.dataset_snapshot(s, ctx.hist_root) for s in ctx.instruments},
        "data_pins": K.data_pins(ctx.window, ctx.hist_root, ctx.instruments),
        "cost": {"profile": K.COST_PROFILE, "stat": K.SPREAD_STAT,
                 "snapshot": K.RC.profile_snapshot(K.COST_PROFILE, list(ctx.instruments))},
        "system_prompt": {"file": K.SYSTEM_PROMPT_NAME, "sha256": K.sha256_bytes(sys_bytes), "chars": len(system),
                          "est_tokens": est_tokens(len(system))},
        "decision_points": rows, "skipped": skipped,
        "counts": {"decision_points": len(rows), "skipped": len(skipped),
                   "by_instrument_killzone": {f"{s}|{kid}": sum(1 for r in rows if r["instrument"] == s and r["killzone"] == kid)
                                              for s in ctx.instruments for kid, *_x in K.killzones(s)}},
    }
    with open(ctx.path(ctx.manifest_rel), "w", encoding="utf-8") as fh:
        json.dump(man, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"built {len(rows)} prompts (+ {K.SYSTEM_PROMPT_NAME}) in {pdir}; skipped {len(skipped)}")
    if sizes:
        q = statistics.quantiles(sizes, n=20) if len(sizes) > 1 else [sizes[0]] * 19
        print(f"system prompt: {len(system)} chars ~ {est_tokens(len(system))} tokens (est. {CHARS_PER_TOKEN} chars/token)")
        print(f"user prompts: min {min(sizes)} / median {int(statistics.median(sizes))} / p95 {int(q[18])} / max "
              f"{max(sizes)} chars ~ {est_tokens(min(sizes))} / {est_tokens(statistics.median(sizes))} / "
              f"{est_tokens(max(sizes))} tokens")
        print(f"per call ~ {est_tokens(len(system) + statistics.median(sizes))} input tokens; all calls ~ "
              f"{est_tokens(len(system) * len(sizes) + sum(sizes))} input tokens before caching")
    return man


def cmd_probe(ctx, n=12, seed="IC|harness-probe|v1"):
    """Truncation probe on the real history (no model call, no outcome): for a seeded sample of decision points the
    prompt built from (a) the full series, (b) the series cut at the killzone open and (c) the series with every bar
    at / after the open changed must be byte-identical."""
    with open(ctx.path(K.TEMPLATE), encoding="utf-8") as fh:
        _, user_block = split_template(fh.read())
    bars_by = load_all(ctx)
    points, _ = enumerate_points(ctx, bars_by)
    rng = random.Random(int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8], "big"))
    order = list(range(len(points)))
    for i in range(len(order) - 1, 0, -1):          # Fisher-Yates on random() only (stable across Python versions)
        j = int(rng.random() * (i + 1))
        order[i], order[j] = order[j], order[i]
    picked = [points[i] for i in sorted(order[:n])]
    bad = 0
    for p in picked:
        full = bars_by[p["instrument"]]
        k = bisect.bisect_left(full.times, p["kz_open_utc"])
        changed = [dict(b, open=b["open"] * 1.37, high=b["high"] * 1.5, low=b["low"] * 0.5, close=b["close"] * 0.71)
                   for b in full.c[k:]]
        spread = K.spread_snapshot(p["instrument"], K.parse_z(p["kz_open_utc"]))
        texts = [user_prompt(user_block, p, b, spread) for b in
                 (full, Bars(p["instrument"], full.c[:k]), Bars(p["instrument"], full.c[:k] + changed))]
        same = texts[0] == texts[1] == texts[2]
        bad += not same
        print(f"  {p['id']:28s} later bars {len(full.c) - k:6d}  identical: {same}  sha256 {K.sha256_bytes(texts[0].encode())[:16]}")
    print(f"truncation probe: {len(picked) - bad}/{len(picked)} identical")
    return 0 if bad == 0 else 1


# ------------------------------------------------------------------------------------------------ the log
def read_log(path):
    """Every record of decisions.jsonl, in order. Refuses a line that is not a JSON object with a `record` field."""
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except ValueError as e:
                raise K.Refused(f"refused: {path}:{n} is not JSON ({e})")
            if not isinstance(rec, dict) or "record" not in rec:
                raise K.Refused(f"refused: {path}:{n} is not a record")
            out.append(rec)
    return out


class LogState:
    def __init__(self, records):
        self.records = records
        self.final = {}                 # decision id -> its one final `decision` record
        self.counted = {}               # decision id -> technical failures that count toward the one retry
        self.attempts = {}              # decision id -> attempts started
        self.events = [r for r in records if r["record"] == "run_event"]
        ended = set()
        for r in records:
            kind = r["record"]
            if kind == "decision":
                if r["decision_id"] in self.final:
                    raise K.Refused(f"refused: decision {r['decision_id']} is stored twice in the log")
                self.final[r["decision_id"]] = r
            elif kind == "technical_failure" and r.get("counts_toward_retry"):
                self.counted[r["decision_id"]] = self.counted.get(r["decision_id"], 0) + 1
            elif kind == "attempt_start":
                self.attempts[r["decision_id"]] = self.attempts.get(r["decision_id"], 0) + 1
            if kind in ("decision", "technical_failure", "interruption") and r.get("attempt_uid"):
                ended.add(r["attempt_uid"])
        self.open_attempts = [r for r in records if r["record"] == "attempt_start" and r["attempt_uid"] not in ended]

    @property
    def start_event(self):
        return next((e for e in self.events if e["event"] == "start"), None)


# ------------------------------------------------------------------------------------------------ one call
def _walk_numbers(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_numbers(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_numbers(v, f"{path}[{i}]")
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        yield path, obj


def isolation_check(env):
    """(violations, unverifiable) of one CLI result envelope (implementation note §3)."""
    violations, unverifiable = [], []
    nt = env.get("num_turns")
    if not isinstance(nt, int) or isinstance(nt, bool):
        unverifiable.append("num_turns")
    elif nt > 1:                                       # the reviewing session's rule: a tool round trip adds a turn
        violations.append(f"num_turns={nt}")
    pd_ = env.get("permission_denials")
    if pd_ is None:
        unverifiable.append("permission_denials")
    elif pd_:
        violations.append(f"permission_denials={pd_!r}"[:300])
    if env.get("deferred_tool_use"):
        violations.append("deferred_tool_use")
    for path, v in _walk_numbers({"usage": env.get("usage"), "modelUsage": env.get("modelUsage")}):
        leaf = path.rsplit(".", 1)[-1]
        if (SERVER_TOOL_KEY.search(leaf) or ".server_tool_use." in path) and v:
            violations.append(f"{path}={v}")
    return violations, unverifiable


def served_models(env):
    """(sorted model ids that served the call, unverifiable) from the envelope's `modelUsage` keys."""
    mu = env.get("modelUsage")
    if isinstance(mu, dict) and mu:
        return sorted(mu), False
    return [], True


def classify(exit_code, stdout, stderr, timed_out):
    """One attempt's outcome: dict(status in {"ok", "retry", "pause"}, kind, detail, env, answer, served, ...)."""
    out = stdout.decode("utf-8", "replace") if isinstance(stdout, bytes) else (stdout or "")
    err = stderr.decode("utf-8", "replace") if isinstance(stderr, bytes) else (stderr or "")
    if timed_out:
        return {"status": "retry", "kind": "timeout", "detail": "the call exceeded the timeout"}
    env = None
    for cand in (out.strip(), (out.strip().splitlines() or [""])[-1]):
        try:
            env = json.loads(cand)
            break
        except ValueError:
            continue
    if not isinstance(env, dict):
        if LIMIT_RE.search(out + "\n" + err):
            return {"status": "pause", "kind": "usage_limit", "detail": (out + err)[-400:]}
        return {"status": "retry", "kind": "nonzero_exit" if exit_code else "invalid_cli_json",
                "detail": f"exit {exit_code}; stdout is not a JSON object"}
    if env.get("type") != "result":
        return {"status": "retry", "kind": "invalid_cli_json", "detail": f"type {env.get('type')!r}", "env": env}
    if exit_code != 0 or env.get("is_error") or env.get("subtype") != "success":
        # the error TEXT only (never the numeric fields: a duration of 429 ms is not a rate limit)
        text = " ".join(str(x) for x in [env.get("result"), *(env.get("errors") or []), env.get("terminal_reason"),
                                         env.get("stop_reason")] if x) + "\n" + err
        if env.get("api_error_status") in (429, 529) or LIMIT_RE.search(text):
            return {"status": "pause", "kind": "usage_limit", "detail": text[-400:], "env": env}
        return {"status": "retry", "kind": "cli_error", "detail": f"exit {exit_code}, subtype {env.get('subtype')!r}, "
                                                                   f"is_error {env.get('is_error')!r}", "env": env}
    answer = env.get("result")
    if not isinstance(answer, str) or not answer.strip():
        return {"status": "retry", "kind": "empty_result", "detail": "no answer text", "env": env}
    violations, unverifiable = isolation_check(env)
    served, model_unverifiable = served_models(env)
    common = {"env": env, "answer": answer, "served": served, "served_model_unverifiable": model_unverifiable,
              "isolation_unverifiable": unverifiable}
    if violations:
        return dict(common, status="retry", kind="isolation_violation", detail="; ".join(violations))
    if not model_unverifiable and served != [K.MODEL_ID]:
        return dict(common, status="pause", kind="model_pin_mismatch",
                    detail=f"served by {served}, pinned {K.MODEL_ID}")
    obj, why = K.extract_answer(answer)
    if obj is None:
        return dict(common, status="retry", kind="no_json_in_answer", detail=why)
    return dict(common, status="ok", kind="answered", detail="")


# ------------------------------------------------------------------------------------------------ run
def call_cli(claude_bin, system_path, prompt_bytes, timeout_s):
    """One isolated process (implementation note §3): the agreed command, a fresh empty working directory, the prompt
    on stdin, its own process group (a terminal Ctrl-C does not reach it; a timeout kills the whole group).
    (exit code or None on timeout, stdout, stderr, timed_out)."""
    cwd = tempfile.mkdtemp(prefix="ic-call-")
    try:
        if os.listdir(cwd):
            raise RuntimeError(f"the call directory {cwd} is not empty")
        p = subprocess.Popen(cli_command(claude_bin, system_path), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, cwd=cwd, start_new_session=True)
        try:
            so, se = p.communicate(prompt_bytes, timeout=timeout_s)
            return p.returncode, so, se, False
        except subprocess.TimeoutExpired:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            so, se = p.communicate()
            return None, so or b"", se or b"", True
    finally:
        shutil.rmtree(cwd, ignore_errors=True)


def selfcheck_call(ctx):
    """One call through the exact isolated command with a fixed, non-market prompt -- no decision point, nothing written
    to the repository: (ok, summary). ok = answered with a JSON object, inside the isolation guard, served by exactly the
    pinned model. A field the CLI does not emit is reported (unverifiable), as every decision would then record it."""
    d = tempfile.mkdtemp(prefix="ic-selfcheck-")
    try:
        sp = os.path.join(d, K.SYSTEM_PROMPT_NAME)
        with open(sp, "w", encoding="utf-8") as fh:
            fh.write(SELFCHECK_SYSTEM)
        started = K.utc_now()
        code, so, se, timed_out = call_cli(ctx.claude_bin, sp, SELFCHECK_USER.encode("utf-8"), min(ctx.timeout_s, 300))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    res = classify(code, so, se, timed_out)
    env = res.get("env") or {}
    return res["status"] == "ok", {
        "at_utc": K.iso_z(started), "status": res["status"], "kind": res["kind"], "detail": res.get("detail", "")[:300],
        "exit_code": code, "num_turns": env.get("num_turns"), "served_models": res.get("served"),
        "served_model_unverifiable": res.get("served_model_unverifiable"),
        "isolation_unverifiable": res.get("isolation_unverifiable"),
        "permission_denials": env.get("permission_denials"), "total_cost_usd": env.get("total_cost_usd")}


class Runner:
    def __init__(self, ctx, manifest, man_sha, system_path, cli_version, out=print):
        self.ctx, self.man, self.man_sha = ctx, manifest, man_sha
        self.system_path, self.cli_version, self.out = system_path, cli_version, out
        self.log_path = ctx.path(ctx.decisions_rel)
        self.shadow = ctx.shadow_path(man_sha)
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.pause_reasons = []
        self.recent = []
        self.new_final = 0

    def log(self, rec):
        """Append one record to decisions.jsonl and to its shadow (same bytes, each fsync'd)."""
        rec = dict(rec, logged_utc=K.iso_z(K.utc_now()))
        data = (json.dumps(rec, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        with self.lock:
            for path in (self.log_path, self.shadow):
                with open(path, "ab") as fh:
                    fh.write(data)
                    fh.flush()
                    os.fsync(fh.fileno())

    def pause(self, reason):
        with self.lock:
            if reason not in self.pause_reasons:
                self.pause_reasons.append(reason)
        self.stop.set()

    def note(self, outcome):
        """Record one attempt's outcome ('ok' or a counted failure kind). The circuit breaker: when the last BREAKER
        outcomes are one failure kind, no further call starts (a systematic fault must not burn the single run); the
        retries it defers happen on resume. Returns True when it trips."""
        with self.lock:
            self.recent.append(outcome)
            tail = self.recent[-BREAKER:]
            tripped = len(tail) == BREAKER and tail[0] != "ok" and len(set(tail)) == 1
        if tripped:
            self.pause(f"circuit_breaker:{outcome}")
        return tripped

    def process(self, point, attempts_started, counted):
        pid = point["id"]
        with open(os.path.join(self.ctx.path(self.ctx.prompts_rel), point["prompt_file"]), "rb") as fh:
            prompt = fh.read()
        if K.sha256_bytes(prompt) != point["prompt_sha256"]:
            raise K.Refused(f"refused: {point['prompt_file']} changed since the build")
        attempt = attempts_started
        while True:
            if self.stop.is_set():
                return "stopped"
            attempt += 1
            uid = uuid.uuid4().hex
            started = K.utc_now()
            self.log({"record": "attempt_start", "decision_id": pid, "attempt": attempt, "attempt_uid": uid,
                      "started_utc": K.iso_z(started)})
            code, so, se, timed_out = call_cli(self.ctx.claude_bin, self.system_path, prompt, self.ctx.timeout_s)
            ended = K.utc_now()
            base = {"decision_id": pid, "attempt": attempt, "attempt_uid": uid, "started_utc": K.iso_z(started),
                    "ended_utc": K.iso_z(ended), "exit_code": code, "timed_out": timed_out,
                    "cli_stdout_sha256": K.sha256_bytes(so or b"")}
            if code is not None and code < 0:
                self.log(dict(base, record="interruption", kind="killed_by_signal", counts_toward_retry=False,
                              detail=f"the call process was killed by signal {-code} from outside the harness; not "
                                     f"counted, asked again on resume"))
                return "pause:killed_by_signal"
            res = classify(code, so, se, timed_out)
            env = res.get("env") or {}
            envelope = {k: env.get(k) for k in ENVELOPE_KEYS if k in env}
            if res["status"] == "ok":
                self.note("ok")
                answer = res["answer"]
                self.log(dict(base, record="decision", status="answered", instrument=point["instrument"],
                              killzone=point["killzone"], date_et=point["date_et"], kz_open_utc=point["kz_open_utc"],
                              kz_end_utc=point["kz_end_utc"], retry=counted > 0,
                              prompt_file=point["prompt_file"], prompt_sha256=point["prompt_sha256"],
                              system_prompt_sha256=self.man["system_prompt"]["sha256"],
                              template_sha256=self.man["template"]["sha256"], manifest_sha256=self.man_sha,
                              model_pinned=K.MODEL_ID, served_models=res["served"],
                              served_model_unverifiable=res["served_model_unverifiable"],
                              isolation_unverifiable=res["isolation_unverifiable"],
                              cli_version=self.cli_version, cli_args=cli_command("claude", "<system prompt file>")[1:],
                              answer=answer, answer_sha256=K.sha256_bytes(answer.encode("utf-8")),
                              cli_result=envelope))
                return "final"
            # a failed attempt keeps the evidence of WHY, never a usable answer: the answer text of a rejected call
            # (wrong model, isolation violation, no JSON) is recorded by its sha256 and length only
            failure = dict(base, kind=res["kind"], detail=res.get("detail", "")[:2000], cli_result=envelope,
                           served_models=res.get("served"), stderr_head=(se or b"")[:2000].decode("utf-8", "replace"))
            if res.get("answer") is not None:
                failure.update(answer_sha256=K.sha256_bytes(res["answer"].encode("utf-8")), answer_chars=len(res["answer"]))
            if not env:
                failure["stdout_head"] = (so or b"")[:2000].decode("utf-8", "replace")
            if res["status"] == "pause":
                self.log(dict(failure, record="technical_failure" if res["kind"] == "model_pin_mismatch" else "interruption",
                              counts_toward_retry=False))
                return "pause:" + res["kind"]
            counted += 1
            tripped = self.note(res["kind"])
            self.log(dict(failure, record="technical_failure", counts_toward_retry=True, failure_no=counted))
            if counted >= 2:
                self.log(dict(base, record="decision", status="technical_failure", instrument=point["instrument"],
                              killzone=point["killzone"], date_et=point["date_et"], kz_open_utc=point["kz_open_utc"],
                              kz_end_utc=point["kz_end_utc"], prompt_file=point["prompt_file"],
                              prompt_sha256=point["prompt_sha256"], manifest_sha256=self.man_sha,
                              model_pinned=K.MODEL_ID, last_failure_kind=res["kind"], answer=None))
                return "final"
            if tripped or self.stop.wait(self.ctx.retry_delay_s):
                return "stopped"


def _run_checks(ctx):
    """Every refusal `run` makes before its first call. Returns (manifest, manifest sha256, system prompt bytes)."""
    man_path = ctx.path(ctx.manifest_rel)
    if not os.path.exists(man_path):
        raise K.Refused(f"refused: no {ctx.manifest_rel}; run `build` and commit its output first")
    with open(man_path, "rb") as fh:
        man_bytes = fh.read()
    man = json.loads(man_bytes)
    prompt_files = [os.path.join(ctx.prompts_rel, K.SYSTEM_PROMPT_NAME)] + \
                   [os.path.join(ctx.prompts_rel, p["prompt_file"]) for p in man["decision_points"]]
    K.require_clean(ctx.root, [K.PREREG, K.TEMPLATE, *K.KB_FILES, K.COMMON, K.HARNESS, K.EVALUATOR, ctx.manifest_rel],
                    "input")
    K.require_clean(ctx.root, prompt_files, "prompt file")
    if man.get("model") != K.MODEL_ID:
        raise K.Refused(f"refused: the manifest pins {man.get('model')!r}, this harness pins {K.MODEL_ID!r}")
    want = {K.TEMPLATE: man["template"]["sha256"], **{r["path"]: r["sha256"] for r in man["knowledge_base"]},
            **man["code"]}
    if sorted(r["path"] for r in man["knowledge_base"]) != sorted(K.KB_FILES):
        raise K.Refused("refused: the manifest's knowledge files are not KB_FILES")
    for rel, sha in sorted(want.items()):
        got = K.sha256_file(ctx.path(rel))
        if got != sha:
            raise K.Refused(f"refused: {rel} sha256 {got[:12]} != manifest {sha[:12]} -- rebuild and recommit")
    with open(ctx.path(K.TEMPLATE), encoding="utf-8") as fh:
        system = system_prompt(ctx.root, fh.read()).encode("utf-8")
    with open(ctx.path(prompt_files[0]), "rb") as fh:
        committed_system = fh.read()
    if not (K.sha256_bytes(system) == K.sha256_bytes(committed_system) == man["system_prompt"]["sha256"]):
        raise K.Refused("refused: the system prompt rendered from the committed template and knowledge files is not the "
                        "committed system.txt / the manifest's")
    for p in man["decision_points"]:
        if K.sha256_file(ctx.path(os.path.join(ctx.prompts_rel, p["prompt_file"]))) != p["prompt_sha256"]:
            raise K.Refused(f"refused: {p['prompt_file']} does not match the manifest")
    ids = [p["id"] for p in man["decision_points"]]
    if len(ids) != len(set(ids)):
        raise K.Refused("refused: the manifest lists a decision point twice")
    return man, K.sha256_bytes(man_bytes), committed_system


def log_integrity(ctx, man_sha, repair=False):
    """The decision log against its git history and its shadow (implementation note §4 item 29). Refuses when a
    committed version is not a prefix of the current log, when the log lost records its shadow holds, when the two
    differ, or when a shadow of ANOTHER build holds records (the experiment already ran from other prompts). With
    `repair`, a missing shadow is recreated from the log and a shadow behind the log (a crash between the two writes)
    is completed. Returns the shadow state: fresh / equal / repo_ahead / recreated / repaired."""
    path = ctx.path(ctx.decisions_rel)
    data = open(path, "rb").read() if os.path.exists(path) else b""
    K.require_append_only(ctx.root, ctx.decisions_rel, data)
    others = K.shadows_with_records(ctx.shadow_dir, exclude_sha=man_sha)
    if others:
        raise K.Refused(f"refused: shadow log(s) of another build hold decisions: {others} -- the single run already "
                        f"started from other prompts")
    repo = K.raw_lines(path)
    shadow = ctx.shadow_path(man_sha)
    if not os.path.exists(shadow):
        if not repo:
            return "fresh"
        if repair:
            os.makedirs(os.path.dirname(shadow), exist_ok=True)
            with open(shadow, "wb") as fh:
                fh.write(b"".join(ln + b"\n" for ln in repo))
            return "recreated"
        return "absent"
    lines = K.raw_lines(shadow)
    state = K.compare_shadow(repo, lines, shadow)
    if state == "repo_ahead" and repair:
        with open(shadow, "ab") as fh:
            fh.write(b"".join(ln + b"\n" for ln in repo[len(lines):]))
        return "repaired"
    return state


def _fingerprint(ctx, man, man_sha):
    """What the single run must keep from its start to its end (pre-registration §3, §7)."""
    return {"manifest_sha256": man_sha, "template_sha256": man["template"]["sha256"],
            "system_prompt_sha256": man["system_prompt"]["sha256"], "evaluator_blob": K.git_blob(ctx.root, K.EVALUATOR),
            "harness_sha256": man["code"][K.HARNESS], "common_sha256": man["code"][K.COMMON]}


def _cli_version(ctx):
    if not ctx.claude_bin:
        raise K.Refused("refused: no `claude` executable on PATH (or IC_CLAUDE_BIN)")
    try:
        v = subprocess.run([ctx.claude_bin, "--version"], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise K.Refused(f"refused: `{ctx.claude_bin} --version` failed: {e}")
    if v.returncode != 0 or not v.stdout.strip():
        raise K.Refused(f"refused: `{ctx.claude_bin} --version` failed: {v.stderr.strip()[:200]}")
    return v.stdout.strip()


def cmd_init(ctx, selfcheck=True, out=print):
    """Starts the single run WITHOUT asking any decision: the same input checks as `run`, the selfcheck call, then ONE
    record -- the `start` event with the inputs' fingerprint -- in decisions.jsonl and its shadow. Commit decisions.jsonl
    before `run`: `run` refuses an uncommitted log, so every record is in git before a later invocation asks anything
    (implementation note §4 item 29)."""
    man, man_sha, _system = _run_checks(ctx)
    if K.raw_lines(ctx.path(ctx.decisions_rel)) or K.ever_committed(ctx.root, ctx.decisions_rel):
        raise K.Refused(f"refused: {ctx.decisions_rel} exists or was committed -- the single run was already started")
    if K.shadows_with_records(ctx.shadow_dir):
        raise K.Refused(f"refused: a shadow decision log holds records ({K.shadows_with_records(ctx.shadow_dir)}) -- "
                        f"the single run was already started")
    cli_version = _cli_version(ctx)
    sc = None
    if selfcheck:
        ok, sc = selfcheck_call(ctx)
        if not ok:
            raise K.Refused(f"refused: the selfcheck call failed ({sc['kind']}: {sc['detail']}) -- fix the cause first")
    os.makedirs(ctx.shadow_dir, exist_ok=True)
    runner = Runner(ctx, man, man_sha, None, cli_version, out)
    runner.log(dict(_fingerprint(ctx, man, man_sha), record="run_event", event="start", at_utc=K.iso_z(K.utc_now()),
                    git_head=K.git_head(ctx.root), cli_bin=ctx.claude_bin, cli_version=cli_version,
                    cli_args=cli_command("claude", "<system prompt file>")[1:], model_pinned=K.MODEL_ID, selfcheck=sc,
                    shadow="fresh", shadow_path=runner.shadow, decision_points=len(man["decision_points"]),
                    python=sys.version.split()[0]))
    out(f"run started, no decision asked yet: commit {ctx.decisions_rel} (git add -f), then `run`")
    return 0


def cmd_run(ctx, concurrency=MAX_CONCURRENCY, max_decisions=None, selfcheck=True, out=print):
    if not 1 <= concurrency <= MAX_CONCURRENCY:
        raise K.Refused(f"refused: concurrency {concurrency} is outside 1..{MAX_CONCURRENCY}")
    man, man_sha, system_bytes = _run_checks(ctx)
    shadow_state = log_integrity(ctx, man_sha)
    state = LogState(read_log(ctx.path(ctx.decisions_rel)))
    unknown = sorted(set(state.final) - {p["id"] for p in man["decision_points"]})
    if unknown:
        raise K.Refused(f"refused: the log stores decisions the manifest does not list, e.g. {unknown[:3]}")
    fingerprint = _fingerprint(ctx, man, man_sha)
    start = state.start_event
    if start is None:
        raise K.Refused(f"refused: the run has not been started -- `init`, then commit {ctx.decisions_rel}")
    changed = sorted(k for k, v in fingerprint.items() if start.get(k) != v)
    if changed:
        raise K.Refused(f"refused: {changed} differ from the run's start event -- the single run must finish with "
                        f"the inputs it started with (pre-registration §3, §7)")
    pending = [p for p in man["decision_points"] if p["id"] not in state.final]
    if not pending:
        if not any(e["event"] == "stop" for e in state.events):
            os.makedirs(ctx.shadow_dir, exist_ok=True)
            log_integrity(ctx, man_sha, repair=True)
            Runner(ctx, man, man_sha, None, None, out).log(
                {"record": "run_event", "event": "stop", "reason": "complete", "at_utc": K.iso_z(K.utc_now()),
                 "final": len(state.final), "pending": 0})
        out(f"run complete: {len(state.final)} decisions stored; nothing to do")
        return 0
    try:
        K.require_clean(ctx.root, [ctx.decisions_rel], "decision log")
    except K.Refused as e:
        raise K.Refused(f"{e} -- commit it first (git add -f {ctx.decisions_rel} && git commit): every record of an "
                        f"earlier invocation is in git before another decision is asked")
    cli_version = _cli_version(ctx)
    lock_path = os.path.join(tempfile.gettempdir(), "ic-claude-ict-" + K.sha256_bytes(ctx.root.encode())[:12] + ".lock")
    lock_fh = open(lock_path, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_fh.close()
        raise K.Refused("refused: another `run` holds the lock for this repository")
    sysdir = tempfile.mkdtemp(prefix="ic-system-")
    old_handler = None
    try:
        sc = None
        if selfcheck:
            ok, sc = selfcheck_call(ctx)
            out(f"selfcheck: {sc['status']} ({sc['kind']}); num_turns {sc['num_turns']}; served {sc['served_models']}; "
                f"unverifiable {sc['isolation_unverifiable'] or []}{' + model' if sc['served_model_unverifiable'] else ''}")
            if not ok:
                raise K.Refused(f"refused: the selfcheck call failed ({sc['kind']}: {sc['detail']}) -- no decision was "
                                f"asked; fix the cause, then `run` again")
        os.makedirs(ctx.shadow_dir, exist_ok=True)
        shadow_state = log_integrity(ctx, man_sha, repair=True)
        system_path = os.path.join(sysdir, K.SYSTEM_PROMPT_NAME)
        with open(system_path, "wb") as fh:
            fh.write(system_bytes)
        runner = Runner(ctx, man, man_sha, system_path, cli_version, out)
        for r in state.open_attempts:
            runner.log({"record": "interruption", "kind": "abandoned_in_flight", "decision_id": r["decision_id"],
                        "attempt": r.get("attempt"), "attempt_uid": r["attempt_uid"], "counts_toward_retry": False,
                        "detail": "an attempt started by an earlier invocation never ended (process stopped); "
                                  "its answer, if any, was never stored or seen"})
        runner.log(dict(fingerprint, record="run_event", event="resume",
                        at_utc=K.iso_z(K.utc_now()), git_head=K.git_head(ctx.root), cli_bin=ctx.claude_bin,
                        cli_version=cli_version, cli_args=cli_command("claude", "<system prompt file>")[1:],
                        model_pinned=K.MODEL_ID, concurrency=concurrency, timeout_s=ctx.timeout_s,
                        retry_policy=f"one retry per technical failure; usage limit / model pin / signal / operator only "
                                     f"pause; {BREAKER} consecutive failures of one kind pause",
                        selfcheck=sc, shadow=shadow_state, shadow_path=runner.shadow,
                        final=len(state.final), pending=len(pending), python=sys.version.split()[0]))
        it = iter(pending)

        def on_sigint(_signum, _frame):
            """Ctrl-C: no new call; the calls in flight finish and are stored; then the run pauses."""
            runner.pause("operator_interrupt")
        if threading.current_thread() is threading.main_thread():
            old_handler = signal.signal(signal.SIGINT, on_sigint)
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
            futs = {}

            def submit():
                if runner.stop.is_set():
                    return
                if max_decisions is not None and runner.new_final + len(futs) >= max_decisions:
                    return
                p = next(it, None)
                if p is not None:
                    futs[ex.submit(runner.process, p, state.attempts.get(p["id"], 0), state.counted.get(p["id"], 0))] = p

            for _ in range(concurrency):
                submit()
            while futs:
                done, _ = concurrent.futures.wait(list(futs), return_when=concurrent.futures.FIRST_COMPLETED)
                for f in done:
                    p = futs.pop(f)
                    res = f.result()
                    if res == "final":
                        runner.new_final += 1
                        out(f"  stored {p['id']}")
                    elif res.startswith("pause:"):
                        runner.pause(res.split(":", 1)[1])
                    submit()
        final_now = LogState(read_log(runner.log_path)).final
        left = [p["id"] for p in man["decision_points"] if p["id"] not in final_now]
        if not left:
            runner.log({"record": "run_event", "event": "stop", "reason": "complete", "at_utc": K.iso_z(K.utc_now()),
                        "final": len(final_now), "pending": 0})
            out(f"run complete: {len(final_now)} decisions stored")
            return 0
        reason = sorted(runner.pause_reasons) or (["max_decisions"] if max_decisions is not None else ["stopped"])
        runner.log({"record": "run_event", "event": "pause", "reason": ",".join(reason), "at_utc": K.iso_z(K.utc_now()),
                    "final": len(final_now), "pending": len(left)})
        out(f"run paused ({', '.join(reason)}): {len(final_now)} stored, {len(left)} pending -- commit decisions.jsonl, "
            f"fix any cause, then `run` again to resume")
        return 3
    finally:
        if old_handler is not None:
            signal.signal(signal.SIGINT, old_handler)
        shutil.rmtree(sysdir, ignore_errors=True)
        fcntl.flock(lock_fh, fcntl.LOCK_UN)
        lock_fh.close()


def cmd_selfcheck(ctx, out=print):
    """One isolated call with a fixed non-market prompt (no decision point, nothing written): checks the CLI JSON the
    guard reads -- num_turns, permission denials, server-tool counters, the served model set -- before the run."""
    if not ctx.claude_bin:
        raise K.Refused("refused: no `claude` executable on PATH (or IC_CLAUDE_BIN)")
    ok, sc = selfcheck_call(ctx)
    for k, v in sc.items():
        out(f"  {k}: {v}")
    out(f"selfcheck {'passed' if ok else 'FAILED'}")
    return 0 if ok else 1


def cmd_status(ctx, out=print):
    man_path = ctx.path(ctx.manifest_rel)
    man_bytes = open(man_path, "rb").read() if os.path.exists(man_path) else None
    man = json.loads(man_bytes) if man_bytes else None
    st = LogState(read_log(ctx.path(ctx.decisions_rel)))
    n = len(man["decision_points"]) if man else None
    kinds = {}
    for r in st.records:
        if r["record"] in ("technical_failure", "interruption"):
            kinds[(r["record"], r["kind"])] = kinds.get((r["record"], r["kind"]), 0) + 1
    answered = [r for r in st.final.values() if r.get("status") == "answered"]
    cost = sum((r.get("cli_result") or {}).get("total_cost_usd") or 0 for r in answered)
    out(f"manifest decision points: {n}; stored decisions: {len(st.final)} (answered {len(answered)}, technical "
        f"failure {len(st.final) - len(answered)}); pending: {None if n is None else n - len(st.final)}")
    out(f"retried decisions: {sum(1 for r in answered if r.get('retry'))}; served_model_unverifiable: "
        f"{sum(1 for r in answered if r.get('served_model_unverifiable'))}; open attempts: {len(st.open_attempts)}")
    for (rec, kind), c in sorted(kinds.items()):
        out(f"  {rec:17s} {kind:20s} {c}")
    for e in st.events:
        out(f"  run_event {e['event']:6s} {e.get('at_utc')} {e.get('reason', '')}")
    paused = {}
    for r in st.records:
        if r["record"] == "interruption" or (r["record"] == "technical_failure" and not r.get("counts_toward_retry")):
            paused[r["decision_id"]] = paused.get(r["decision_id"], 0) + 1
    repeated = sorted(k for k, v in paused.items() if v >= 3)
    out(f"decisions paused (uncounted) 3 or more times: {repeated or 'none'}")
    out(f"reported cost (sum of total_cost_usd): {cost:.2f} USD")
    if man_bytes:
        try:
            out(f"log integrity (git history, shadow): {log_integrity(ctx, K.sha256_bytes(man_bytes))}")
        except K.Refused as e:
            out(f"log integrity: {e}")
    complete = n is not None and len(st.final) == n and bool(st.events) and st.events[-1]["event"] == "stop"
    out(f"complete: {complete}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("points")
    b = sub.add_parser("build")
    b.add_argument("--out-dir", default=None, help="write prompts + manifest here instead of " + K.EXP_DIR)
    pr = sub.add_parser("probe")
    pr.add_argument("--n", type=int, default=12)
    sub.add_parser("selfcheck")
    i = sub.add_parser("init")
    i.add_argument("--no-selfcheck", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("--concurrency", type=int, default=MAX_CONCURRENCY)
    r.add_argument("--max-decisions", type=int, default=None, help="pause after this many new stored decisions")
    r.add_argument("--no-selfcheck", action="store_true", help="skip the non-market check call before the first decision")
    sub.add_parser("status")
    a = ap.parse_args(argv)
    ctx = Ctx(exp_dir=os.path.abspath(a.out_dir) if getattr(a, "out_dir", None) else None)
    if a.cmd == "points":
        cmd_points(ctx)
        return 0
    if a.cmd == "build":
        cmd_build(ctx)
        return 0
    if a.cmd == "probe":
        return cmd_probe(ctx, a.n)
    if a.cmd == "selfcheck":
        return cmd_selfcheck(ctx)
    if a.cmd == "init":
        return cmd_init(ctx, selfcheck=not a.no_selfcheck)
    if a.cmd == "run":
        return cmd_run(ctx, a.concurrency, a.max_decisions, selfcheck=not a.no_selfcheck)
    return cmd_status(ctx)


if __name__ == "__main__":
    sys.exit(main())
