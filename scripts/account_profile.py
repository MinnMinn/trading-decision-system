"""THE Account Profile (CLAUDE.md §33), read from one registry instead of four constants in the order engine.

    import account_profile as AP
    AP.for_venue("futures")                       -> the profile for the crypto pilot account
    AP.max_positions(prof)                        -> 9        (derived from the execution book, not typed)
    AP.for_account('acc-001')                     -> that account's profile, by id (multi-account)
    AP.owner_of(prof)                             -> 'cust-42' (risk-pool boundary; defaults to the id)
    AP.effective_risk_pct(prof)                   -> 0.01     (never above the platform ceiling)
    AP.entry_gate(prof, facts)                    -> ['đủ 9 vị thế (futures)']   reasons a NEW ENTRY is refused
    AP.halt_check(prof, facts)                    -> ('HALT', 'equity 8400.00 <= 85 % of start 10000.00')

§33 asks for an Account Profile as a first-class domain concept with fifteen named, configurable attributes.
What existed before 2026-09-18 was one of them in configuration (max risk/trade, `risk-config.json`) and three
more as literal constants inside `strategy-runner.py`:

    EQUITY_HALT_FRAC = 0.85     # = a 15 % max total drawdown rule
    MAX_TRADES_PER_DAY = 3      # = a per-symbol daily entry cap
    LEVERAGE = 3                # = a max leverage rule
    CONSEC_LOSS_HALT = 5        # = a custom failure condition

Those are not runner settings. They are the ACCOUNT's rules, and keeping them in the order engine's source
made two things impossible: a second account could not have different ones (§5: "do not assume that all CFD
accounts have identical rules"), and no research run could record which rule set it was run under (§11).

**A profile may only tighten.** `max_risk_per_trade` cannot exceed the platform ceiling and
`news_restrictions` cannot shorten a calendar buffer -- both are refused, loudly, rather than applied. An
account is a constraint on what a Trading System may do; it is not a licence to do more.

**A declared null is not a missing key.** Every profile must spell out all sixteen rule keys. `null` means
"this account has no such rule"; an absent key is refused at import. Those are different facts and a reader
that cannot tell them apart will eventually enforce a limit nobody wrote, or skip one somebody did (the same
three-valued discipline §20 applies to data quality).

**Objectives are not gates.** `profit_target` and `min_trading_days` are progress, not permission: reaching a
profit target must never block an entry. They are reported by `objectives()` and are absent from both gates.
"""
import json
import os

import instruments as _I
import providers as _P
import sessions as _S
import event_risk as _ER
import trading_env as _TE

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "docs", "architecture", "account-profiles.json")

# What a rule can do about a breach. UNKNOWN is here for the same reason it is in §20's list: a rule that
# could not be evaluated must be expressible, and it is never permission.
OK, BLOCK_ENTRY, HALT, UNKNOWN, HUMAN = "OK", "BLOCK_ENTRY", "HALT", "UNKNOWN", "HUMAN_CONFIRMATION"
ACTIONS = (BLOCK_ENTRY, HALT, UNKNOWN, HUMAN)
BLOCKING = (BLOCK_ENTRY, HALT, UNKNOWN, HUMAN)

# The fifteen §33 attributes, plus this platform's own per-symbol churn cap. All sixteen are REQUIRED keys.
RULE_KEYS = ("initial_balance", "max_daily_loss", "max_total_drawdown", "trailing_drawdown", "profit_target",
             "min_trading_days", "max_leverage", "max_risk_per_trade", "max_positions", "consistency_rules",
             "news_restrictions", "overnight_restrictions", "weekend_restrictions", "session_restrictions",
             "custom_failure_conditions", "max_trades_per_day_per_symbol")

# Rule kinds `check` knows how to evaluate. An unrecognised kind is refused at import rather than ignored:
# a consistency rule nobody evaluates is worse than no rule, because the profile claims it is enforced.
FAILURE_KINDS = ("consecutive_losses", "consecutive_errors")
CONSISTENCY_KINDS = ("max_share_of_profit_from_best_day", "max_share_of_profit_from_one_symbol")

DRAWDOWN_BASES = ("initial_balance", "equity_start", "day_start_equity", "peak_equity")


def _read(path=None):
    with open(path or PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _public(d):
    return {k: v for k, v in d.items() if not k.startswith("_")}


# --------------------------------------------------------------------------------------------------
# Validation at import. Every fault below would otherwise surface as a silently unenforced account rule.

def _validate(data, path=PATH):
    if not isinstance(data.get("version"), int):
        raise ValueError(f"{path}: `version` must be an integer -- it is what a configuration snapshot "
                         f"records to say which rule set a research run used (CLAUDE.md §11).")
    types = tuple(data.get("context_types") or ())
    if not types or not all(isinstance(t, str) for t in types):
        raise ValueError(f"{path}: `context_types` must be a non-empty list of names (CLAUDE.md §5).")

    profiles = _public(data.get("profiles") or {})
    if not profiles:
        raise ValueError(f"{path}: no profiles declared. An empty registry would make `for_venue()` refuse "
                         f"every venue, which is safe but is not a configuration anybody chose.")

    unroutable = tuple(data.get("unroutable_environments") or ())
    if not all(isinstance(e, str) for e in unroutable):
        raise ValueError(f"{path}: `unroutable_environments` must be a list of environment-name strings.")
    # Declaring a routable environment unroutable would switch the uniqueness rule off for a path that still
    # places orders -- the one direction of this setting that is unsafe, so it is refused rather than obeyed.
    both = sorted(set(unroutable) & set(_TE.ENV_NAMES))
    if both:
        raise ValueError(f"{path}: {both} are listed in `unroutable_environments` but are environments an "
                         f"order path can be switched to (trading_env.ENV_NAMES). An environment orders route "
                         f"to is routable by definition; exempting it from the uniqueness check below would "
                         f"let two accounts claim the same live venue.")

    seen = {}          # (venue, environment) -> [profile ids]; see the note where it is filled
    for pid, prof in profiles.items():
        for field in ("what", "context_type", "venue", "environment", "rules"):
            if field not in prof:
                raise ValueError(f"{path}: profile {pid!r} is missing {field!r}.")
        if "owner" in prof and not (isinstance(prof["owner"], str) and prof["owner"].strip()):
            raise ValueError(f"{path}: profile {pid!r} has owner={prof['owner']!r}; an owner is a non-empty "
                             f"customer id or the key is absent (see account_profile.owner_of).")
        if prof["context_type"] not in types:
            raise ValueError(f"{path}: profile {pid!r} declares context_type {prof['context_type']!r}, which "
                             f"is not one of {list(types)} (CLAUDE.md §5).")
        # An environment that is neither routable nor declared unroutable is almost always a typo, and the
        # damage is silent: the profile can never be reached by `for_venue()`, and because it shares no
        # (venue, environment) key with anything, the uniqueness check below never looks at it either. A
        # rule set nobody can reach is exactly the "silently unenforced account rule" this validator exists
        # to prevent, so an unknown environment is named and refused at import.
        if prof["environment"] not in _TE.ENV_NAMES and prof["environment"] not in unroutable:
            raise ValueError(
                f"{path}: profile {pid!r} declares environment {prof['environment']!r}, which is neither one "
                f"an order path can be switched to ({list(_TE.ENV_NAMES)}) nor one declared in "
                f"`unroutable_environments` ({list(unroutable)}). Fix the spelling, or declare the "
                f"environment -- an unreachable profile enforces nothing while looking like it does.")
        key = (prof["venue"], prof["environment"])
        # Two profiles MAY now share a (venue, environment): that is what running several accounts on one
        # broker means (docs/plans/2026-09-19-multi-account.md Pha 0). What must never happen is an order
        # path RESOLVING one of them by guessing, and that invariant moved from here into the resolvers:
        # `for_account(id)` names the account explicitly, and `for_venue()` still refuses whenever the
        # (venue, environment) pair does not identify exactly one profile (see below). Before 2026-09-19 this
        # loop raised at import instead, which made multi-account a REFUSED configuration rather than an
        # unimplemented one -- correct for a one-account design, and the first thing that had to change.
        # The collision is still recorded so `for_venue`'s refusal can name the profiles that caused it.
        seen.setdefault(key, []).append(pid)
        _validate_rules(pid, prof["rules"], path)
    return profiles


def _validate_rules(pid, rules, path):
    missing = [k for k in RULE_KEYS if k not in rules]
    if missing:
        raise ValueError(
            f"{path}: profile {pid!r} does not declare {missing}. Every rule key must be present; write "
            f"`null` to say this account has no such rule. An absent key and a declared absence are "
            f"different facts and this reader will not guess which one it is looking at (CLAUDE.md §33).")

    for k in ("max_daily_loss", "max_total_drawdown", "trailing_drawdown"):
        lim = rules.get(k)
        if lim is None:
            continue
        _need(pid, k, lim, ("pct", "basis", "action"), path)
        if not isinstance(lim["pct"], (int, float)) or not 0 < lim["pct"] <= 1:
            raise ValueError(f"{path}: profile {pid!r} {k}.pct is {lim['pct']!r}. Express it as a FRACTION in "
                             f"(0, 1] -- a `5` typed for '5 %' would be a 500 % limit, i.e. no limit at all.")
        if lim["basis"] not in DRAWDOWN_BASES:
            raise ValueError(f"{path}: profile {pid!r} {k}.basis is {lim['basis']!r}, not one of "
                             f"{list(DRAWDOWN_BASES)}.")
        if lim["action"] not in ACTIONS:
            raise ValueError(f"{path}: profile {pid!r} {k}.action is {lim['action']!r}, not one of "
                             f"{list(ACTIONS)}.")
        if lim["basis"] == "initial_balance" and rules.get("initial_balance") is None:
            raise ValueError(f"{path}: profile {pid!r} {k} is measured against `initial_balance`, which this "
                             f"profile declares as null. The rule would have nothing to measure against.")

    tgt = rules.get("profit_target")
    if tgt is not None:
        _need(pid, "profit_target", tgt, ("pct", "basis"), path)
        if tgt["basis"] not in DRAWDOWN_BASES:
            raise ValueError(f"{path}: profile {pid!r} profit_target.basis is {tgt['basis']!r}.")

    mp = rules.get("max_positions")
    if mp is not None:
        if mp.get("mode") == "fixed":
            if not isinstance(mp.get("count"), int) or mp["count"] < 1:
                raise ValueError(f"{path}: profile {pid!r} max_positions fixed count is {mp.get('count')!r}.")
        elif mp.get("mode") != "full_book":
            raise ValueError(f"{path}: profile {pid!r} max_positions.mode is {mp.get('mode')!r}; expected "
                             f"'full_book' or 'fixed'.")

    risk = rules.get("max_risk_per_trade")
    if risk is not None:
        if not isinstance(risk, (int, float)) or isinstance(risk, bool) or not 0 < risk <= 1:
            raise ValueError(f"{path}: profile {pid!r} max_risk_per_trade is {risk!r}; express it as a "
                             f"fraction in (0, 1].")
        if risk > _TE.MAX_RISK_PCT:
            raise ValueError(
                f"{path}: profile {pid!r} max_risk_per_trade {risk} is ABOVE the platform ceiling "
                f"{_TE.MAX_RISK_PCT} (docs/architecture/risk-config.json max_risk_pct). An account profile "
                f"may only tighten a platform limit. Raising the ceiling is a decision made in one place, "
                f"and this is not that place.")

    lev = rules.get("max_leverage")
    if lev is not None and (not isinstance(lev, (int, float)) or isinstance(lev, bool) or lev <= 0):
        raise ValueError(f"{path}: profile {pid!r} max_leverage is {lev!r}.")

    n = rules.get("max_trades_per_day_per_symbol")
    if n is not None and (not isinstance(n, int) or isinstance(n, bool) or n < 1):
        raise ValueError(f"{path}: profile {pid!r} max_trades_per_day_per_symbol is {n!r}.")

    d = rules.get("min_trading_days")
    if d is not None and (not isinstance(d, int) or isinstance(d, bool) or d < 1):
        raise ValueError(f"{path}: profile {pid!r} min_trading_days is {d!r}.")

    for k, kinds in (("consistency_rules", CONSISTENCY_KINDS), ("custom_failure_conditions", FAILURE_KINDS)):
        items = rules.get(k)
        if items is None:
            continue
        if not isinstance(items, list):
            raise ValueError(f"{path}: profile {pid!r} {k} must be a list (use [] for none).")
        for item in items:
            _need(pid, k, item, ("id", "kind", "threshold", "action", "what"), path)
            if item["kind"] not in kinds:
                raise ValueError(
                    f"{path}: profile {pid!r} {k} entry {item['id']!r} has kind {item['kind']!r}, which no "
                    f"evaluator knows ({list(kinds)}). A rule this module cannot evaluate would be listed as "
                    f"enforced and enforce nothing.")
            if item["action"] not in ACTIONS:
                raise ValueError(f"{path}: profile {pid!r} {k} entry {item['id']!r} action "
                                 f"{item['action']!r} is not one of {list(ACTIONS)}.")

    for k in ("overnight_restrictions", "weekend_restrictions"):
        r = rules.get(k)
        if r is None:
            continue
        _need(pid, k, r, ("hold_allowed", "action"), path)
        if r["action"] not in ACTIONS:
            raise ValueError(f"{path}: profile {pid!r} {k}.action is {r['action']!r}.")

    sr = rules.get("session_restrictions")
    if sr is not None:
        _need(pid, "session_restrictions", sr, ("allowed_sessions", "action"), path)
        unknown = [s for s in sr["allowed_sessions"] if s not in _S.LABELS]
        if unknown:
            raise ValueError(
                f"{path}: profile {pid!r} session_restrictions names {unknown}, which are not sessions in "
                f"docs/architecture/sessions.json ({list(_S.LABELS)}). A renamed window must not be able to "
                f"leave a rule behind that matches nothing and therefore blocks everything.")
        if sr["action"] not in ACTIONS:
            raise ValueError(f"{path}: profile {pid!r} session_restrictions.action is {sr['action']!r}.")

    nr = rules.get("news_restrictions")
    if nr is not None:
        bad = [i for i in (nr.get("impacts") or ()) if i not in _ER.IMPACTS]
        if bad:
            raise ValueError(f"{path}: profile {pid!r} news_restrictions names impacts {bad}, not in "
                             f"{list(_ER.IMPACTS)} (CLAUDE.md §25).")
        for f in ("pre_minutes", "post_minutes"):
            v = nr.get(f)
            if v is not None and (not isinstance(v, int) or isinstance(v, bool) or v < 0):
                raise ValueError(f"{path}: profile {pid!r} news_restrictions.{f} is {v!r}.")


def _need(pid, where, obj, fields, path):
    miss = [f for f in fields if f not in obj]
    if miss:
        raise ValueError(f"{path}: profile {pid!r} {where} is missing {miss}.")


_DATA = _read()
VERSION = _DATA["version"]
CONTEXT_TYPES = tuple(_DATA["context_types"])
UNROUTABLE_ENVIRONMENTS = tuple(_DATA.get("unroutable_environments") or ())
PROFILES = _validate(_DATA)


# --------------------------------------------------------------------------------------------------
# Lookup

def get(profile_id):
    if profile_id not in PROFILES:
        raise KeyError(f"no account profile {profile_id!r} in {PATH} (have {sorted(PROFILES)})")
    return dict(PROFILES[profile_id], id=profile_id)


def for_venue(venue, environment="demo"):
    """The account profile for this execution venue in this environment, or a refusal.

    Refusing is the point when the answer is absent: it means switching `execution.environment` to "real"
    cannot place an order until somebody has written that account's rules down (§51). Refuses outright for an
    `unroutable_environments` value (e.g. "research") -- a research template must never become the account an
    order is sized against, not even when it is the only profile on that venue.
    """
    if environment in UNROUTABLE_ENVIRONMENTS:
        raise ValueError(
            f"environment {environment!r} is declared unroutable (docs/architecture/account-profiles.json "
            f"unroutable_environments): no order path may resolve an account through it. Load a research "
            f"profile by id with account_profile.get(...) instead.")
    hits = [pid for pid, p in PROFILES.items() if p["venue"] == venue and p["environment"] == environment]
    if len(hits) != 1:
        more = (f" Several accounts on one venue is now a legal configuration "
                f"(docs/plans/2026-09-19-multi-account.md); when it is the case, the caller must name the "
                f"account -- account_profile.for_account(<id>), and strategy-runner.py --account <id>."
                if len(hits) > 1 else "")
        raise ValueError(
            f"{len(hits)} account profiles for venue {venue!r} in environment {environment!r} "
            f"({hits or 'none'}); exactly one is needed. Declare it in {PATH} -- an order path must not "
            f"guess which account's rules apply (CLAUDE.md §33).{more}")
    return get(hits[0])


def for_account(account_id, venue=None, environment=None):
    """The account profile named by `account_id` -- the multi-account resolver (CLAUDE.md §33).

    `for_venue()` above answers "which account is on this venue", which only has an answer while there is one
    account per venue. This answers "this account", which has an answer for any number of them, and is what
    every per-account order path uses (docs/plans/2026-09-19-multi-account.md Pha 0/Pha 1).

    The optional `venue` / `environment` are ASSERTIONS, not filters: pass what the caller believes it is
    trading, and a mismatch refuses instead of silently routing this account's rules to another venue's
    orders. A runner launched with `--account acc-001` against the wrong bridge is exactly the mistake worth
    paying one comparison to catch.

    An `unroutable_environments` profile (e.g. "research") is refused here for the same reason `for_venue`
    refuses one: a research template must never become the account an order is sized against. Load it with
    `get(...)` when the caller genuinely wants a template to evaluate against (§57).
    """
    prof = get(account_id)
    if prof["environment"] in UNROUTABLE_ENVIRONMENTS:
        raise ValueError(
            f"account {account_id!r} declares environment {prof['environment']!r}, which is unroutable "
            f"({list(UNROUTABLE_ENVIRONMENTS)}): no order path may resolve an account through it. It is a "
            f"research template -- load it with account_profile.get(...) to EVALUATE against it.")
    for field, want in (("venue", venue), ("environment", environment)):
        if want is not None and prof[field] != want:
            raise ValueError(
                f"account {account_id!r} is {field} {prof[field]!r}, but the caller asserted {want!r}. "
                f"Refusing rather than applying this account's rules to another {field}'s orders.")
    return prof


def owner_of(prof):
    """Whose account this is -- the boundary of a risk pool (docs/plans/2026-09-19-multi-account.md §0.2).

    Customers rent a methodology and hand over their own account (user, 2026-09-19), so "how concentrated is
    this bet" is a question about ONE OWNER's accounts, not about everything running here. Ten accounts of one
    owner long the same symbol is that owner's concentrated bet; two different customers holding the same
    symbol is two people's separate decisions, and scripts/exposure.py refuses on the first and only reports
    the second.

    Defaults to the profile's own id. That makes an undeclared account its own pool, which is the safe answer
    for a concentration question (it cannot dilute anybody else's cap) and the honest one (we do not know
    whose it is, so we do not pool it with anyone).
    """
    return prof.get("owner") or prof["id"]


def rule(prof, key):
    return prof["rules"][key]


# --------------------------------------------------------------------------------------------------
# Ceilings

def effective_risk_pct(prof):
    """Risk per trade for this account: the platform ceiling, tightened by the profile if it says so."""
    own = rule(prof, "max_risk_per_trade")
    return _TE.MAX_RISK_PCT if own is None else min(own, _TE.MAX_RISK_PCT)


def max_leverage(prof, default=None):
    lev = rule(prof, "max_leverage")
    return default if lev is None else lev


def max_positions(prof):
    """How many positions this account may hold at once; None when it declares no cap.

    `full_book` is DERIVED: one slot per symbol the account may trade, counted across every market whose
    unattended execution venue is this profile's venue. Deriving it is what keeps the cap correct when a
    symbol is added, and what fixes the previous per-venue constant -- `len(CFD)` ignored the seven FX majors
    that route to the same MT5 account.
    """
    mp = rule(prof, "max_positions")
    if mp is None:
        return None
    if mp["mode"] == "fixed":
        return mp["count"]
    return len(tradeable_symbols(prof))


def tradeable_symbols(prof):
    """Every orderable symbol routed to this profile's venue, from the instrument + provider registries."""
    out = []
    for market in _I.MARKETS:
        try:
            venue = _P.unattended_venue_for(market)
        except ValueError:
            continue           # a market with no unattended execution provider is not this account's book
        if venue == prof["venue"]:
            out.extend(_I.execution(market))
    return tuple(out)


def max_trades_per_day(prof):
    return rule(prof, "max_trades_per_day_per_symbol")


# --------------------------------------------------------------------------------------------------
# Enforcement. Two gates, deliberately separate.
#
#   entry_gate  -- rules about taking a NEW ENTRY. Evaluated on every signal, live and dry.
#   halt_check  -- rules about the ACCOUNT's survival. Evaluated only where real balances are known.
#
# Splitting them is not tidiness. An entry rule that cannot be evaluated must block that entry; an account
# rule that cannot be evaluated must NOT write a kill switch, because "I could not read the balance" is not
# "the account is down 15 %". Both refuse to call an unevaluated rule OK.

def _finding(name, state, why):
    return {"rule": name, "state": state, "why": why}


def entry_gate(prof, facts):
    """Findings for a NEW ENTRY. Returns a list; anything with a blocking state refuses the entry.

    facts (all optional -- a rule whose facts are absent reports UNKNOWN, never OK):
      open_positions  int   positions + resting orders already held on this account
      trades_today    int   entries already taken today in THIS symbol
      at              str|datetime  the decision instant (session / weekend rules)
      holding_overnight / holding_over_weekend  bool
      news_state      str   CLEAR / BLOCKED / UNAVAILABLE, when the account adds its own news rule
    """
    out = []
    cap = max_positions(prof)
    if cap is not None:
        n = facts.get("open_positions")
        if n is None:
            out.append(_finding("max_positions", UNKNOWN, "số vị thế đang mở không đọc được"))
        elif n >= cap:
            out.append(_finding("max_positions", BLOCK_ENTRY, f"đủ {cap} vị thế ({prof['venue']})"))

    per_day = max_trades_per_day(prof)
    if per_day is not None:
        n = facts.get("trades_today")
        if n is None:
            out.append(_finding("max_trades_per_day_per_symbol", UNKNOWN, "số lệnh trong ngày không đọc được"))
        elif n >= per_day:
            out.append(_finding("max_trades_per_day_per_symbol", BLOCK_ENTRY, "đủ lệnh trong ngày"))

    sr = rule(prof, "session_restrictions")
    if sr is not None:
        at = facts.get("at")
        if at is None:
            out.append(_finding("session_restrictions", UNKNOWN, "không biết thời điểm quyết định"))
        else:
            label = _S.primary(at)
            if label not in sr["allowed_sessions"]:
                out.append(_finding("session_restrictions", sr["action"],
                                    f"tài khoản chỉ vào lệnh trong {sr['allowed_sessions']}, hiện tại {label}"))

    for key, fact, what in (("overnight_restrictions", "holding_overnight", "qua đêm"),
                            ("weekend_restrictions", "holding_over_weekend", "qua cuối tuần")):
        r = rule(prof, key)
        if r is None or r.get("hold_allowed"):
            continue
        v = facts.get(fact)
        if v is None:
            out.append(_finding(key, UNKNOWN, f"không biết lệnh này có giữ {what} hay không"))
        elif v:
            out.append(_finding(key, r["action"], f"tài khoản không cho giữ lệnh {what}"))

    nr = rule(prof, "news_restrictions")
    if nr is not None:
        st = facts.get("news_state")
        if st is None:
            out.append(_finding("news_restrictions", UNKNOWN, "trạng thái tin tức không đọc được"))
        elif st != _ER.CLEAR:
            out.append(_finding("news_restrictions", BLOCK_ENTRY, f"tin tức: {st}"))
    return out


def halt_check(prof, facts):
    """(action, reason) when an account rule has been breached, else (None, None).

    facts:
      equity, equity_start, initial_balance, day_start_equity, peak_equity, realised_today  (numbers)
      consec_losses, consec_errors   (ints)
      profit_by_day / profit_by_symbol  ({key: number}, for consistency rules)
    """
    for finding in account_state(prof, facts):
        if finding["state"] in (HALT, HUMAN, BLOCK_ENTRY):
            return finding["state"], finding["why"]
    return None, None


def account_state(prof, facts):
    """Every account-survival rule, evaluated. Findings in declaration order; OK rules are omitted."""
    out = []
    for key, sign in (("max_total_drawdown", "drawdown"), ("max_daily_loss", "daily loss"),
                      ("trailing_drawdown", "trailing drawdown")):
        lim = rule(prof, key)
        if lim is None:
            continue
        equity = facts.get("equity")
        basis = _basis_value(prof, lim["basis"], facts)
        if equity is None or basis is None:
            out.append(_finding(key, UNKNOWN,
                                f"{sign}: không đọc được {'equity' if equity is None else lim['basis']}"))
            continue
        floor = basis * (1 - lim["pct"])
        if equity <= floor:
            out.append(_finding(key, lim["action"],
                                f"{sign}: equity {equity:.2f} <= {1 - lim['pct']:.0%} of "
                                f"{lim['basis']} {basis:.2f}"))

    for item in rule(prof, "custom_failure_conditions") or ():
        fact = {"consecutive_losses": "consec_losses", "consecutive_errors": "consec_errors"}[item["kind"]]
        v = facts.get(fact)
        if v is None:
            out.append(_finding(item["id"], UNKNOWN, f"{item['kind']}: không đọc được"))
        elif v >= item["threshold"]:
            out.append(_finding(item["id"], item["action"],
                                f"{item['threshold']} {item['kind'].replace('_', ' ')}"))

    for item in rule(prof, "consistency_rules") or ():
        src = {"max_share_of_profit_from_best_day": "profit_by_day",
               "max_share_of_profit_from_one_symbol": "profit_by_symbol"}[item["kind"]]
        book = facts.get(src)
        if not book:
            out.append(_finding(item["id"], UNKNOWN, f"{item['kind']}: không có {src}"))
            continue
        gains = {k: v for k, v in book.items() if v > 0}
        total = sum(gains.values())
        if total <= 0:
            continue                     # no profit yet: a consistency rule has nothing to be inconsistent about
        worst = max(gains.items(), key=lambda kv: kv[1])
        share = worst[1] / total
        if share > item["threshold"]:
            out.append(_finding(item["id"], item["action"],
                                f"{worst[0]} chiếm {share:.0%} lợi nhuận (trần {item['threshold']:.0%})"))
    return out


def _basis_value(prof, basis, facts):
    if basis == "initial_balance":
        ib = rule(prof, "initial_balance")
        return None if ib is None else ib["amount"]
    return facts.get(basis)


def objectives(prof, facts):
    """Progress toward the account's targets. NEVER a gate -- reaching a profit target must not stop trading."""
    out = []
    tgt = rule(prof, "profit_target")
    if tgt is not None:
        equity, basis = facts.get("equity"), _basis_value(prof, tgt["basis"], facts)
        if equity is None or basis is None:
            out.append({"objective": "profit_target", "state": UNKNOWN, "progress": None})
        else:
            need = basis * (1 + tgt["pct"])
            out.append({"objective": "profit_target", "state": "REACHED" if equity >= need else "OPEN",
                        "progress": (equity - basis) / (basis * tgt["pct"]) if tgt["pct"] else None,
                        "target_equity": need})
    days = rule(prof, "min_trading_days")
    if days is not None:
        have = facts.get("trading_days")
        out.append({"objective": "min_trading_days",
                    "state": UNKNOWN if have is None else ("REACHED" if have >= days else "OPEN"),
                    "progress": None if have is None else have / days, "required": days})
    return out


# --------------------------------------------------------------------------------------------------
# News: an account may tighten the calendar policy, never loosen it.

def tighten_calendar(prof, cal):
    """The §24-§32 calendar policy with this account's own news restrictions applied.

    Returns `cal` unchanged when the profile declares none, which is the case for every account today. An
    account rule that would SHORTEN a buffer or UNRESTRICT an impact level is refused rather than applied:
    the platform policy is a floor, and an account that could lower it would be an account that opts out of
    event risk by writing a config key.
    """
    nr = rule(prof, "news_restrictions")
    if nr is None:
        return cal
    pol = dict(cal.get("policy") or {})
    for f in ("pre_minutes", "post_minutes"):
        want = nr.get(f)
        if want is None:
            continue
        base = pol.get(f, 10)
        if want < base:
            raise ValueError(
                f"account profile {prof['id']!r} asks for {f}={want} where the calendar policy says {base}. "
                f"An account profile may only TIGHTEN event risk (CLAUDE.md §33 rules constrain a Trading "
                f"System; they do not exempt it from §24).")
        pol[f] = want
    if nr.get("impacts"):
        by = {k: dict(v) for k, v in (pol.get("by_impact") or {}).items()}
        for impact in _ER.IMPACTS:
            entry = by.setdefault(impact, {})
            if impact in nr["impacts"]:
                entry["restricted"] = True
            elif entry.get("restricted"):
                raise ValueError(
                    f"account profile {prof['id']!r} lists impacts {nr['impacts']}, which would UNRESTRICT "
                    f"{impact} -- the calendar policy restricts it. Name every impact the platform already "
                    f"restricts, plus the ones this account adds.")
        pol["by_impact"] = by
    return dict(cal, policy=pol)


# --------------------------------------------------------------------------------------------------

def snapshot(prof):
    """The profile as a configuration-snapshot field (§11): the rules in force, plus what was derived."""
    return {
        "profile_id": prof["id"], "registry_version": VERSION, "context_type": prof["context_type"],
        "venue": prof["venue"], "environment": prof["environment"],
        "rules": dict(_public(prof["rules"])),
        "derived": {"max_positions": max_positions(prof),
                    "tradeable_symbols": list(tradeable_symbols(prof)),
                    "effective_risk_pct": effective_risk_pct(prof),
                    "risk_source": "docs/architecture/risk-config.json max_risk_pct via trading_env"
                                   f"{'' if rule(prof, 'max_risk_per_trade') is None else ', tightened by this profile'}"},
    }


def describe(prof):
    r = _public(prof["rules"])
    named = [k for k in RULE_KEYS if r.get(k) not in (None, [], {})]
    return (f"{prof['id']} · {prof['context_type']} · {prof['venue']}/{prof['environment']} · "
            f"risk {effective_risk_pct(prof):.2%}/trade · "
            f"{max_positions(prof)} positions · rules in force: {', '.join(named) or 'none'}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Account Profiles (CLAUDE.md §33).")
    ap.add_argument("--venue", help="show the profile for this execution venue")
    ap.add_argument("--environment", default="demo")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    profs = [for_venue(a.venue, a.environment)] if a.venue else [get(p) for p in sorted(PROFILES)]
    if a.json:
        print(json.dumps([snapshot(p) for p in profs], indent=2, ensure_ascii=False))
    else:
        for p in profs:
            print(describe(p))
