"""What N accounts are doing AT THE SAME TIME -- the only place the whole estate is visible at once.

    import exposure as EX
    EX.report("acc-001", positions, equity, owner="cust-42")       # after every state change
    EX.quota("acc-001", "BTCUSDT", "long", want_risk_usd=85.0)     # -> grant | raises ExposureRefused

Why this module exists, and the wrong reason it nearly existed
--------------------------------------------------------------
The first draft of this module (2026-09-19) was built on the claim that "ten accounts each risking 1 % on the
same signal is a 10 % bet". **That claim is arithmetically false and the tests caught it.** Each account has
its own equity, so risking 1 % of each is 1 % of the total, for any N:

    10 accounts x $10k = $100k equity, 10 x $100 risk = $1,000 = 1.00 % of total
   100 accounts x $10k = $1M   equity, 100 x $100 risk = $10,000 = 1.00 % of total

A ceiling expressed as a fraction of summed equity is INVARIANT in N and therefore cannot be the gate that
makes multi-account safe. It is kept below, but only for what it really does: bound CONCENTRATION, the case
where accounts differ in size or in risk fraction and a few of them carry most of the estate's risk.

The hazard that actually scales with N is **simultaneous failure**. These are prop-challenge accounts: each
has its own daily-loss limit and its own total-drawdown limit (docs/architecture/account-profiles.json). If
every account holds the same symbol on the same side, one adverse move breaches every account's daily limit
on the same day and the whole estate fails at once -- ten challenge fees, not ten percent. No per-account
check can see that, because from inside any one account nothing is wrong.

So the primary gate here counts **how many accounts hold the same (symbol, side) at the same time**, and
refuses past a declared cap. That number is a direct measure of how correlated the estate actually is, rather
than an assumption about it: if the accounts really are running different methodologies, they will rarely
collide and the cap will rarely bind. If they collide constantly, the "different methodologies" premise was
not true and the operator should see that as a refusal rather than as a drawdown.

Who shares a risk pool: OWNER, not "everything here"
----------------------------------------------------
The estate is not one person's (user, 2026-09-19): customers rent a methodology, hand over their own account,
and we attach that account to the setups they chose. That makes ownership the boundary that matters.

* Ten accounts belonging to the SAME owner all long BTCUSDT is one owner's concentrated bet. Cap it.
* Customer A and customer B both long BTCUSDT is two people who each chose that methodology. Refusing
  customer B because customer A got there first is not risk management, it is arbitrary, and it silently
  makes the product worse for whoever's runner ticks second.

So the cap is scoped PER OWNER. The house-wide count is still computed and returned on every grant
(`house_holders`), because it is the number that says how exposed the whole book of business is to one
instrument -- but it is reported, not refused on. A number you must look at is the right shape for a fact
nobody should resolve automatically.

CLAUDE.md §34 lists "existing exposure" among the inputs a risk calculation must consider;
scripts/risk_model.py:151 `open_risk()` already computes it for ONE book, in ONE process.

Design decisions, and the reason for each
-----------------------------------------
* **A file, not a server.** One runner process per account (docs/plans/2026-09-19-multi-account.md §4: the MT5
  bridge is a physical singleton, so process-per-account is forced anyway). The processes need one shared
  scoreboard and nothing more; a daemon would be a new failure mode on the order path for no gain (§57).

* **Fail CLOSED on every uncertainty.** A stale slice, an unreadable file, a position whose risk cannot be
  computed, a missing equity -- each REFUSES the quota rather than treating the unknown as zero. This matches
  what the rest of the repo does with unknowns (htf_pass returning None is not permission; bias "unknown" is
  not permission) and it matches §20's rule that UNKNOWN must never silently become a benign value. The
  asymmetry is deliberate: refusing a good trade costs an opportunity, granting a bad one costs capital.

* **A dead account keeps counting.** If a runner crashes while holding a position, that position is still on
  the exchange and still losing money. Its slice therefore never expires to zero -- it expires to STALE, which
  still counts toward the total AND blocks that account from getting new quota. Only an explicit
  `release(account_id)` (the runner's own clean shutdown, or an operator) removes a slice.

* **Total equity is the sum of what the accounts themselves reported.** Not a configured number: a configured
  total would drift from reality silently, and the one thing this gate must not do is be wrong in the
  permissive direction.

Capacity: the third thing, and the one we cannot yet measure
-----------------------------------------------------------
The same signal across N accounts sends N orders into the same book within seconds of each other, so on a thin
instrument the estate moves the price against itself and every account after the first few fills worse. That is
a real constraint and it is NOT the same as either ceiling above: it is about the INSTRUMENT, not about anybody's
equity.

We do not have the data to set it. Nothing here reads order-book depth, and inventing a number would be worse
than saying so. So capacity is handled the way CLAUDE.md §6/§20 handle any unavailable input -- expose the
state, preserve the reason, and refuse where the missing input actually gates the decision:

* Total estate notional per symbol is always computed and always returned (`symbol_notional_after`).
* A symbol MAY declare `max_estate_notional_usd` in docs/architecture/instruments.json; if it does, that is a
  hard refusal like the other two.
* If it does not, the grant carries `capacity: "UNDECLARED"` -- and once more than
  `capacity_required_above_accounts` accounts hold that symbol, UNDECLARED becomes a REFUSAL. Below that
  threshold the estate is too small for capacity to be the binding constraint; above it, trading on an
  unmeasured capacity assumption is exactly the silent-unknown §20 forbids.

All four values have one authored source and one reader here: `max_correlated_accounts`,
`max_portfolio_risk_pct` and `capacity_required_above_accounts` in docs/architecture/risk-config.json, and
`max_estate_notional_usd` per symbol in docs/architecture/instruments.json -- the same one-value-one-reader
shape as `max_risk_pct` (scripts/trading_env.py:63).
"""
import datetime
import json
import os
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "docs", "architecture", "risk-config.json")
PATH = os.path.join(ROOT, "data", "live", "exposure.json")
LOCK = PATH + ".lock"

# A slice older than this is STALE: it still counts toward the total, and its account cannot draw new quota.
# 300 s is five times the pilot loop's own cadence (scripts/pilot-loop.sh), so a healthy runner refreshes it
# many times over before it expires; a runner that has missed five consecutive ticks is not healthy.
STALE_AFTER_S = 300


class ExposureRefused(Exception):
    """Raised instead of returning a number, for the same reason risk_model.RiskRefused exists: a caller that
    forgets to check a boolean places the order anyway, and a caller that forgets to catch an exception does
    not."""


def _config():
    try:
        return json.load(open(CONFIG, encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ExposureRefused(f"{CONFIG} could not be read: {e}") from e


def _read_ceiling():
    """The CONCENTRATION ceiling as a FRACTION, or refuse. Never returns a fallback.

    Mirrors scripts/trading_env.py `_read_max_risk_pct`: a missing or malformed ceiling must stop the order
    path, not substitute a guess. Note what this does and does not bound -- see the module docstring: it is
    invariant in the number of accounts, so it catches a lopsided estate, not a correlated one.
    """
    raw = _config().get("max_portfolio_risk_pct")
    try:
        v = float(raw)
    except (TypeError, ValueError):
        raise ExposureRefused(f"{CONFIG}: max_portfolio_risk_pct is {raw!r}, not a number. Express it as a "
                              f"FRACTION (0.05 = 5 % of total equity across every account).")
    if not 0 < v <= 1:
        raise ExposureRefused(f"{CONFIG}: max_portfolio_risk_pct {v} is outside (0, 1]. A `5` typed for '5 %' "
                              f"would authorise 500 % of total equity.")
    return v


def _read_correlated_cap():
    """How many accounts may hold the SAME (symbol, side) at once. The primary gate. Refuses, never guesses."""
    raw = _config().get("max_correlated_accounts")
    try:
        v = int(raw)
    except (TypeError, ValueError):
        raise ExposureRefused(f"{CONFIG}: max_correlated_accounts is {raw!r}, not a whole number. It is a "
                              f"COUNT of accounts, not a fraction.")
    if v < 1:
        raise ExposureRefused(f"{CONFIG}: max_correlated_accounts {v} is below 1; that would forbid trading "
                              f"entirely. Remove the estate instead of setting a cap of zero.")
    return v


class _Lock:
    """Cross-process mutual exclusion around the ledger. `os.open(..., O_EXCL)` rather than fcntl.flock so the
    behaviour is identical on every filesystem this repo runs on, including the network mount the MT5 bridge
    directory lives on."""

    def __init__(self, timeout=5.0):
        self.timeout = timeout
        self.fd = None

    def __enter__(self):
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self.fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(self.fd, f"{os.getpid()} {time.time():.3f}\n".encode())
                return self
            except FileExistsError:
                # A lock older than the timeout belonged to a process that died holding it. Break it: the
                # alternative is that one crash wedges every account's order path permanently.
                try:
                    if time.time() - os.stat(LOCK).st_mtime > self.timeout:
                        os.unlink(LOCK)
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() > deadline:
                    raise ExposureRefused(f"exposure ledger lock held longer than {self.timeout}s ({LOCK})")
                time.sleep(0.02)

    def __exit__(self, *exc):
        if self.fd is not None:
            os.close(self.fd)
            try:
                os.unlink(LOCK)
            except FileNotFoundError:
                pass
        return False


def _load():
    try:
        d = json.load(open(PATH, encoding="utf-8"))
    except FileNotFoundError:
        return {"accounts": {}}
    except (OSError, ValueError) as e:
        raise ExposureRefused(f"{PATH} is unreadable ({e}); refusing rather than assuming an empty book")
    if not isinstance(d.get("accounts"), dict):
        raise ExposureRefused(f"{PATH} has no `accounts` object; refusing rather than assuming an empty book")
    return d


def _save(d):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + f".tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, PATH)          # atomic: a concurrent reader never sees a half-written ledger


def _read_capacity_threshold():
    """Above how many accounts on one symbol an UNDECLARED capacity becomes a refusal."""
    raw = _config().get("capacity_required_above_accounts")
    try:
        v = int(raw)
    except (TypeError, ValueError):
        raise ExposureRefused(f"{CONFIG}: capacity_required_above_accounts is {raw!r}, not a whole number. "
                              f"It is a COUNT of accounts holding one symbol.")
    if v < 1:
        raise ExposureRefused(f"{CONFIG}: capacity_required_above_accounts {v} is below 1")
    return v


def _instruments():
    """The instrument registry, imported ONCE. It used to be re-imported inside _declared_capacity on every
    quota call, which re-read and re-validated the whole allowlist on the order path for one dictionary
    lookup -- and made the table impossible to exercise from a test, because each call built a fresh module."""
    global _I
    if _I is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("instruments",
                                                      os.path.join(ROOT, "scripts", "instruments.py"))
        _I = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_I)
    return _I


_I = None


def _declared_capacity(symbol):
    """`max_estate_notional_usd` for this symbol, or None when the instrument registry does not declare one.
    Read through scripts/instruments.py so the allowlist keeps its single reader."""
    meta = getattr(_instruments(), "CAPACITY", {}) or {}
    v = meta.get(symbol)
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise ExposureRefused(f"{symbol}: max_estate_notional_usd is {meta[symbol]!r}, not a number")
    if v <= 0:
        raise ExposureRefused(f"{symbol}: max_estate_notional_usd {v} is not positive; remove the key to "
                              f"declare it unknown rather than declaring a capacity of zero")
    return v


def _side_of(p):
    """"long" | "short" | None. Explicit `side` wins; otherwise the stop tells us which way the trade leans."""
    v = (p or {}).get("side")
    if v in ("long", "short"):
        return v
    try:
        entry = float(p["entry"]); stop = float(p["stop"])
    except (KeyError, TypeError, ValueError):
        return None
    if entry == stop:
        return None
    return "long" if stop < entry else "short"


def report(account_id, positions, equity, owner=None, now=None):
    """Record what `account_id` currently has at risk. Call after every state change, not only before orders.

    `positions` is the runner's own positions dict (symbol -> {qty, entry, stop}); it is measured by
    risk_model.open_risk, so a position this repo cannot price lands in `unknown` and makes the slice
    incomplete -- which `quota()` then refuses on.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("risk_model", os.path.join(ROOT, "scripts", "risk_model.py"))
    rm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rm)
    r = rm.open_risk(positions, equity)
    # WHICH correlated positions, not only how much risk: the primary gate counts accounts per (symbol, side),
    # so the ledger has to carry the pairs. `side` is taken from the position when it declares one and
    # inferred from stop-vs-entry otherwise (stop below entry = long), because that is how every position this
    # repo opens is shaped (scripts/strategy-runner.py sizes from |entry - stop| with the stop on the losing
    # side). A position whose side cannot be determined lands in `unknown` via open_risk and blocks anyway.
    held = sorted({f"{sym}|{_side_of(p)}" for sym, p in (positions or {}).items() if _side_of(p)})
    # Notional per symbol, for the capacity question. |qty| x entry, summed per symbol; a position we cannot
    # price lands in open_risk's `unknown` and already blocks the grant, so it cannot silently count as zero.
    notional = {}
    for sym, pos_ in (positions or {}).items():
        try:
            notional[sym] = notional.get(sym, 0.0) + abs(float(pos_["qty"])) * float(pos_["entry"])
        except (KeyError, TypeError, ValueError):
            continue
    # `owner` defaults to the account's own id, which makes an undeclared account its own risk pool. That is
    # the SAFE default for the concentration question (an unowned account cannot dilute someone else's cap)
    # and the honest one: we do not know whose it is, so we do not pool it with anyone.
    slice_ = {"risk_usd": r["risk_usd"], "equity": float(equity), "positions": r["positions"],
              "owner": owner or account_id,
              "held": held, "notional": notional, "unknown": r["unknown"], "complete": r["complete"],
              "updated": (now or datetime.datetime.now(datetime.timezone.utc)).isoformat().replace("+00:00", "Z"),
              "updated_epoch": time.time()}
    with _Lock():
        d = _load()
        d["accounts"][account_id] = slice_
        _save(d)
    return slice_


def release(account_id):
    """Remove an account's slice. ONLY for a clean shutdown with a flat book, or an operator who has verified
    the account holds nothing -- a crashed runner must keep counting (see the module docstring)."""
    with _Lock():
        d = _load()
        d["accounts"].pop(account_id, None)
        _save(d)


def totals(now_epoch=None):
    """The whole picture: summed risk, summed equity, and which slices are stale. Read-only, no lock needed --
    `_save` is atomic, so a reader sees one consistent version or another, never a torn one."""
    now_epoch = time.time() if now_epoch is None else now_epoch
    d = _load()
    risk = equity = 0.0
    stale, incomplete = [], []
    crowd = {}          # "SYMBOL|side" -> [account ids holding it right now]  (house-wide, reported)
    owners = {}         # account id -> owner id
    notional = {}       # SYMBOL -> estate notional, both sides (the capacity question is about the book)
    symbol_accounts = {}
    for aid, s in sorted(d["accounts"].items()):
        risk += float(s.get("risk_usd") or 0.0)
        equity += float(s.get("equity") or 0.0)
        owners[aid] = s.get("owner") or aid
        for key in (s.get("held") or []):
            crowd.setdefault(key, []).append(aid)
        for sym, amt in (s.get("notional") or {}).items():
            notional[sym] = notional.get(sym, 0.0) + float(amt or 0.0)
            symbol_accounts.setdefault(sym, set()).add(aid)
        if now_epoch - float(s.get("updated_epoch") or 0.0) > STALE_AFTER_S:
            stale.append(aid)
        if not s.get("complete", False):
            incomplete.append(aid)
    return {"risk_usd": risk, "equity": equity, "accounts": len(d["accounts"]),
            "fraction": (risk / equity) if equity > 0 else None,
            "crowd": crowd, "owners": owners, "notional": notional,
            "symbol_accounts": {k: sorted(v) for k, v in symbol_accounts.items()},
            "stale": stale, "incomplete": incomplete}


def quota(account_id, symbol, side, want_risk_usd, want_notional_usd=None, now_epoch=None):
    """May `account_id` open `symbol`/`side` for `want_risk_usd`? Returns the headroom dict, or raises.

    Two gates, in this order:
      1. CORRELATION -- how many accounts already hold this exact (symbol, side). This is the one that scales
         with the size of the estate, because it is the one that decides how many prop challenges can fail on
         the same adverse move (see the module docstring).
      2. CONCENTRATION -- summed risk as a fraction of summed equity. Invariant in N; catches a lopsided
         estate, not a correlated one.
      3. CAPACITY -- estate notional in this symbol against what the instrument is declared to absorb.
         Always reported; a hard refusal when the symbol declares a capacity, and ALSO a refusal when it
         does not and more than `capacity_required_above_accounts` accounts already hold it (see the module
         docstring: below that threshold the estate is too small for capacity to bind, above it an unmeasured
         capacity assumption is the silent unknown §20 forbids).

    `want_notional_usd` is this order's own notional. Omitted, capacity is evaluated on what is already on
    the book -- honest, but it cannot see the order about to be added, so callers on the order path should
    pass it.

    Every refusal names the account that caused it, because with 100 runners the operator's first question is
    always "which one".
    """
    ceiling = _read_ceiling()
    cap = _read_correlated_cap()
    want = float(want_risk_usd)
    if want < 0:
        raise ExposureRefused(f"{account_id}: want_risk_usd {want} is negative")
    t = totals(now_epoch)
    if t["equity"] <= 0:
        raise ExposureRefused(f"{account_id}: total reported equity across accounts is {t['equity']}; no "
                              f"account has reported a book yet, so the portfolio ceiling has no denominator")
    if account_id in t["stale"]:
        raise ExposureRefused(f"{account_id}: its own exposure slice is stale (older than {STALE_AFTER_S}s). "
                              f"A runner that has not reported cannot be trusted about what it holds.")
    if t["stale"]:
        raise ExposureRefused(f"{account_id}: refused because {t['stale']} have stale exposure slices. Their "
                              f"positions still count toward the total and may have changed unseen; "
                              f"exposure.release() them only after verifying each is flat.")
    if t["incomplete"]:
        raise ExposureRefused(f"{account_id}: refused because {t['incomplete']} hold positions whose risk "
                              f"could not be computed. An unmeasurable position is the one most likely to be "
                              f"the large one (risk_model.open_risk).")
    key = f"{symbol}|{side}"
    house = [a for a in t["crowd"].get(key, []) if a != account_id]
    owner = t["owners"].get(account_id, account_id)
    siblings = [a for a in house if t["owners"].get(a, a) == owner]     # same owner = one risk pool
    if account_id not in t["crowd"].get(key, []) and len(siblings) >= cap:
        raise ExposureRefused(
            f"{account_id}: owner {owner!r} already holds {symbol} {side} on {cap} accounts "
            f"({', '.join(siblings[:cap])}{'...' if len(siblings) > cap else ''}), the "
            f"max_correlated_accounts cap in docs/architecture/risk-config.json. One adverse move on "
            f"{symbol} would put every one of them into its own daily-loss limit on the same day. If these "
            f"accounts are meant to run DIFFERENT methodologies, this refusal is the evidence that they are "
            f"not. ({len(house)} accounts house-wide hold it, across all owners -- that number is reported, "
            f"not refused on: one customer does not lose a signal because another customer took it first.)")
    room = ceiling * t["equity"]
    after = t["risk_usd"] + want
    if after > room:
        raise ExposureRefused(
            f"{account_id}: {want:.2f} would take portfolio risk to {after:.2f} of {t['equity']:.2f} equity "
            f"= {after / t['equity']:.2%}, over the {ceiling:.2%} ceiling "
            f"(docs/architecture/risk-config.json max_portfolio_risk_pct). "
            f"{t['accounts']} accounts already hold {t['risk_usd']:.2f} = {t['fraction']:.2%}.")
    # ---- 3. capacity
    cap_declared = _declared_capacity(symbol)
    sym_now = float(t["notional"].get(symbol, 0.0))
    sym_after = sym_now + float(want_notional_usd or 0.0)
    holders_n = len(t["symbol_accounts"].get(symbol, []))
    if cap_declared is not None:
        capacity_state = "DECLARED"
        if sym_after > cap_declared:
            raise ExposureRefused(
                f"{account_id}: {symbol} estate notional would reach {sym_after:,.0f} against the declared "
                f"max_estate_notional_usd {cap_declared:,.0f} (docs/architecture/instruments.json). "
                f"{holders_n} accounts already hold it. The estate would be trading against itself.")
    else:
        capacity_state = "UNDECLARED"
        threshold = _read_capacity_threshold()
        if holders_n >= threshold:
            raise ExposureRefused(
                f"{account_id}: {holders_n} accounts already hold {symbol} and the instrument declares no "
                f"max_estate_notional_usd (docs/architecture/instruments.json). Above "
                f"capacity_required_above_accounts={threshold} that unknown gates the decision rather than "
                f"being reported: N accounts sending the same order into one book move the price against "
                f"themselves, and nothing here measures depth. Declare the symbol's capacity, or keep the "
                f"estate on it below {threshold} accounts.")

    return {"granted_usd": want, "portfolio_risk_usd_after": after, "portfolio_equity": t["equity"],
            "symbol_notional_after": sym_after, "symbol_capacity": cap_declared,
            "capacity": capacity_state, "symbol_accounts": holders_n,
            "fraction_after": after / t["equity"], "ceiling": ceiling, "headroom_usd": room - after,
            "accounts": t["accounts"], "owner": owner, "correlated_holders": len(siblings),
            "house_holders": len(house), "correlated_cap": cap}
