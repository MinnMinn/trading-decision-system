# Session model (project-defined)

**Status: project-defined, not sourced.** Created 2026-09-10 by user decision (`knowledge/integrated/method.md` §7 decision 4, option C: "define it yourself and document it").

This file exists because the ICT sources leave the question open. `knowledge/ict/core-a.md` §6 records three gaps that make the sourced killzone material unusable as-is for this project's instruments:

1. **Two competing killzone sets.** Forex NY AM is 07:00–10:00; indices NY AM is 08:30–11:00. Forex has a London Close window, indices have an NY PM window.
2. **No rule for anything that is not forex or an index.** Crypto and commodity CFDs are simply not addressed.
3. **Times are labelled "EST" year-round** and whether they shift with US daylight saving is never stated.

Everything below is this project's own answer. **Any timing credit derived from this file must be reported as a project assumption, never cited as a rule from the ICT sources.** The numeric caps live in `docs/architecture/analysis-params.json` under `timing`.

---

## 1. Reference clock

**Windows are defined in the exchange's local time and converted to UTC per date, so they follow daylight saving.**

Rationale: session behaviour follows the local clock of the market that is opening. The US macro releases that move gold and oil are scheduled at 08:30 America/New_York, which is 12:30Z in winter and 11:30Z in summer. Taking the sources' "EST year-round" label literally would leave the window an hour off the real open for roughly eight months of the year. The sources never defend the year-round EST label; `knowledge/ict/core-a.md` §6 item 3 flags it as unresolved.

**Consequence:** the fixed UTC windows previously used in `scripts/local-eval-brief.py` ("London 06–09Z, NY AM 11–14Z") are correct in summer only. Any code computing a session must convert from the local zone for the date in question, not hardcode a UTC hour.

---

## 2. Windows

**The windows themselves live in `docs/architecture/sessions.json`** (added 2026-09-18, CLAUDE.md §21). That
file is the single source: `scripts/sessions.py` is the one reader, `scripts/sync-sessions.py --write`
regenerates the `session` enum in `schemas/trade-file.schema.json` and the `SESSIONS` / `KZ_WEIGHT` literals in
`scripts/chart.js`, and `scripts/tests/test_sessions.py` fails the build on drift. Until then the same numbers
were written out in six places with nothing keeping them in step — including this table.

This document keeps the **reasoning**, which the JSON does not duplicate. The table below is a reader's
convenience, not an authority: if it disagrees with `sessions.json`, the JSON is right and this is stale.

| Label | Local window | Zone | What it is |
|---|---|---|---|
| `london` | 08:00–11:00 | Europe/London | London open through the LBMA morning gold fix (10:30 London) |
| `ny_am` | 08:30–11:00 | America/New_York | US macro release time (CPI, NFP, EIA) through the first 90 minutes of the equity session |
| `ny_pm` | 13:30–16:00 | America/New_York | Afternoon session into the equity close |
| `asia` | 20:00–00:00 | America/New_York | The decks' own Asia killzone (`1. Killzones p3`). Used for the Asian session high/low liquidity levels (`knowledge/ict/core-a.md` §2.9) and for journalling; carries no timing credit for any instrument. **Chosen by measurement 2026-09-12** — see below |
| `off` | everything else | — | No timing credit |

**Why `asia` is 20:00–00:00 New York (decided 2026-09-12 from data, replacing 00:00–06:00 Asia/Tokyo).** `scripts/asia-session-eval.py` scored five candidate clocks on 365 days of 15m BTC/ETH/SOL plus 70 days of XAUUSD by how much the session's high/low behave like liquidity: how often the rest of the day sweeps them, how often a sweep reverses back through the range (48% for this window vs 30% for the Tokyo 00–06 window, which is really the New York afternoon), and how narrow the session range is against the whole day (36% vs 55%). Results in `docs/backtests/2026-09-12-asia-session.md`. It is also the only Asia definition any ingested source gives. The `london`/`ny_*` windows were not part of that measurement.

**The `ny_am` and `ny_pm` windows follow the *indices* set, not the forex set.** Choice, not a source: this project trades metals and oil, whose dominant scheduled catalyst is the 08:30 New York macro release, and the indices set is the only one whose NY AM window contains it. `knowledge/ict/core-a.md` §6 item 1 records that both sets exist and the decks do not reconcile them.

---

## 3. Weight by instrument

Weight **classes** live in `sessions.json` → `weights`, keyed by `instruments.json` `display.<sym>.asset_class`.
The class → points mapping stays in `analysis-params.json` → `timing.weight_by_class` (`full` = 7,
`reduced` = 3, `none` = 0), because that is the scoring parameter and the tuning surface for `/improve`; the
class is the model. An asset class the registry does not name gets `_default` — `none` everywhere — rather
than inheriting another class's weights.

As with §2, the table below is a reader's convenience and `sessions.json` is the authority.

| Instrument | `london` | `ny_am` | `ny_pm` | `asia` / `off` |
|---|---|---|---|---|
| XAUUSD, XAGUSD | full | full | full | none |
| USOIL, UKOIL | reduced | full | full | none |
| BTCUSDT, ETHUSDT, SOLUSDT | reduced | reduced | none | none |

**Why metals get a full London weight and oil does not.** Gold and silver have a physical London fixing at 10:30 London; crude's pricing centre and its scheduled inventory catalyst (the EIA petroleum status report, Wednesdays 10:30 New York) are both American.

**Why crypto never gets a full weight.** Crypto has no exchange open and trades continuously, so no window carries the structural meaning a killzone is supposed to carry. The reduced weights reflect that institutional crypto flow does cluster around the equity session, but that observation is not in any ingested source. If measurement later shows no edge in these windows, set crypto to `none` everywhere rather than defending the model.

---

## 4. Gates

- **Timeframe gate.** No timing credit below `analysis-params.json` → `timing.min_timeframe_minutes` (15m). A one-minute chart inside a three-hour window carries no timing information. This matches what the local-read brief already told the model.
- **Weekend gate.** Crypto trades weekends; metals and oil do not. **No timing credit is awarded on Saturday or Sunday UTC for any instrument**, including crypto, because the sessions the windows name are not running.
- **Event overlap is not timing credit.** A scheduled release inside `ny_am` is an Event Risk input (`docs/architecture/event-calendar.md`, `SYSTEM-DESIGN.md` §6.3), not a reason to raise the timing score. Event Risk can force NO TRADE regardless of session.

---

## 5. What must be stated in output

Any analysis that awards timing points states, in one line: the window, the instrument's weight class, the local-to-UTC conversion used for that date, and the fact that the weighting is a project assumption. Example shape:

> Timing: `ny_am` (08:30–11:00 America/New_York = 12:30–15:00Z on this date), XAUUSD weight `full`. Project assumption per `docs/architecture/session-model.md`; the ICT sources give no rule for commodity CFDs.

---

## 6. Review triggers

Revisit this file when any of these happen:

- The journal accumulates enough closed trades to compare outcomes by session (`journal.py` already groups by `session`). If a window shows no edge, drop its weight rather than keeping it for symmetry.
- A new ICT source is ingested that addresses crypto or commodity sessions directly.
- The instrument universe changes.

---

## 7. Overlaps and custom sessions (2026-09-18)

CLAUDE.md §21 names both as first-class. Neither existed before `sessions.json`:

- **Overlaps.** `sessions.active(t)` returns *every* window an instant is inside, in the registry's declared
  `precedence` order; `sessions.primary(t)` collapses that to the one label a trade file records. The old
  `journal.session_of` was an if/elif chain, so an overlap would have been resolved by branch order — a rule
  nobody wrote down. Today's four windows do not overlap (London 08:00–11:00 local is 13:30–16:00 London while
  NY AM runs), so this changes no label today. It exists so that moving a window later cannot introduce a
  silent resolution.
- **Custom sessions.** Adding one is a data edit plus `sync-sessions.py --write`. The loader validates that the
  zone is a real IANA zone, that the hours are in range, that the window is not zero-width, that no two windows
  share a precedence, and that every asset class states a class for every window.

**Model version.** `sessions.json` carries `version`. A session label is stamped on every journalled trade, so
moving a window silently re-labels history; the version is what lets a configuration snapshot (§11) say which
model produced a label, and CLAUDE.md §59 treats a session-rule change as potentially Trading System version
significant.
