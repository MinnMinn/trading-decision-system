"""Which customer account gets a shared signal first, and why that one.

    import dispatch_order as DO
    DO.rank("2026-09-19T14:00:00Z|BTCUSDT|long|cfd-scalping-ict-15m", "acc-007", accounts)
        -> {"rank": 3, "of": 12, "delay_s": 0.6, "basis": "sha256(signal|account)"}

The problem this exists for
--------------------------
Customers rent a methodology and hand over their own account (user, 2026-09-19), so one setup serves many
accounts. When that setup fires, every one of those accounts wants the same instrument on the same side at the
same moment. They cannot all be first, and on a thin book the later fills are measurably worse.

Today the order is whichever runner process happens to tick first. That is not neutral -- process start time,
machine load and symbol-loop position all bias it, and they bias it the SAME WAY every time, so the same
customer is systematically last. It is also unauditable: asked "why did I fill 40 ticks after them", the only
honest answer would be "scheduling".

The rule
--------
Order by `sha256(signal_id || account_id)`. Three properties, all of which matter here:

* **Uniform.** The digest is independent per (signal, account) pair, so over many signals every account is
  first about 1/N of the time. No account is structurally advantaged.
* **Deterministic.** The same signal and the same account set always produce the same order, so a customer's
  position in the queue can be recomputed months later from the trade record alone. That is what makes it an
  answer to a dispute rather than an apology.
* **Stateless.** No shared counter, no lock, no central dispatcher. Each runner computes only its OWN rank and
  waits `rank x stagger` before placing. N independent processes therefore produce one agreed order without
  talking to each other, which matters because the architecture is one process per account
  (docs/plans/2026-09-19-multi-account.md §4: the MT5 bridge is a physical singleton).

The cost, stated plainly
------------------------
The stagger is real latency on the order path, and on a scalping setup it is not free: 12 accounts at the
declared 200 ms means the last account places 2.2 s after the first. That is the price of an order somebody
can check. The alternative is not "no delay" -- the accounts still queue at the venue - it is the same delay
distributed by luck and unaccountable afterwards.

It is BOUNDED, which matters more than its size. A fixed stagger does not survive growth (100 accounts x
200 ms is 19.8 s for the last one, which is a different product, not a fairer one), so the gap actually used
is `min(stagger_ms, max_total_delay_ms / (n - 1))`: the last account places within the declared total budget
for ANY N. What degrades with scale is the spacing between accounts, not the deadline -- the right thing to
give up, because the spacing exists to make the order legible and the deadline exists to make the entry good.

Both numbers are declared in docs/architecture/execution-safety.json `dispatch` so the trade-off is visible
and tunable rather than compiled in, and `rank()` returns `delay_s` for the caller to honour; this module
never sleeps, because a module that sleeps cannot be tested for what it decides.
"""
import hashlib
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "docs", "architecture", "execution-safety.json")


class DispatchError(Exception):
    """Raised rather than returning a default. An order nobody declared is an order nobody can defend."""


def _cfg():
    try:
        d = json.load(open(CONFIG, encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise DispatchError(f"{CONFIG} could not be read: {e}") from e
    block = d.get("dispatch")
    if not isinstance(block, dict):
        raise DispatchError(f"{CONFIG}: no `dispatch` block; the shared-signal ordering rule and its stagger "
                            f"are declared there and read only by scripts/dispatch_order.py")
    return block


def _num(key, why):
    v = _cfg().get(key)
    if not isinstance(v, (int, float)) or v < 0:
        raise DispatchError(f"{CONFIG}: dispatch.{key} is {v!r}; it must be a non-negative number of "
                            f"milliseconds. {why}")
    return float(v)


def stagger_ms():
    return _num("stagger_ms", "0 means every account places at once -- legal, and a deliberate choice, "
                              "not a default to fall back on.")


def max_total_delay_ms():
    return _num("max_total_delay_ms", "It is the WORST delay any account may be made to wait, whatever N is.")


def effective_stagger_ms(n):
    """The per-rank gap actually used for a queue of `n` accounts.

    A fixed stagger does not survive growth: at 200 ms the last of 100 accounts would wait 19.8 s, which is
    not "fair ordering" any more, it is a different product. So the gap is the smaller of the declared stagger
    and whatever fits the declared total budget:

        gap = min(stagger_ms, max_total_delay_ms / (n - 1))

    Below the point where the budget binds, the stagger is exactly as declared. Above it, the LAST account
    still places within max_total_delay_ms of the first, for any N. What degrades with scale is the spacing
    between accounts, not the deadline -- which is the right thing to give up, because the spacing exists to
    make the order legible and the deadline exists to make the entry good.
    """
    if n <= 1:
        return 0.0
    return min(stagger_ms(), max_total_delay_ms() / (n - 1))


def _key(signal_id, account_id):
    return hashlib.sha256(f"{signal_id}\x00{account_id}".encode()).hexdigest()


def order(signal_id, accounts):
    """The account ids for this signal, in the order they may place. Deterministic, uniform, reproducible."""
    if not signal_id:
        raise DispatchError("a signal id is required: the order is derived from it, and an empty id would "
                            "give every signal the same permutation")
    seen = sorted(set(accounts))
    if len(seen) != len(list(accounts)):
        raise DispatchError(f"duplicate account ids in {list(accounts)!r}; each account queues once")
    return sorted(seen, key=lambda a: _key(signal_id, a))


def rank(signal_id, account_id, accounts):
    """This account's place in the queue for this signal, and how long it should wait before placing."""
    seq = order(signal_id, accounts)
    if account_id not in seq:
        raise DispatchError(f"{account_id!r} is not among the accounts eligible for this signal "
                            f"({seq!r}); rank is only meaningful inside the set it is drawn from")
    i = seq.index(account_id)
    gap = effective_stagger_ms(len(seq))
    return {"rank": i, "of": len(seq), "delay_s": i * gap / 1000.0, "gap_ms": gap,
            "worst_delay_s": (len(seq) - 1) * gap / 1000.0,
            "basis": "sha256(signal|account)", "queue": seq}


def signal_id(setup_id, symbol, side, signal_time):
    """The identity a queue position is derived from. Same four fields the runner already dedupes a signal on
    (strategy-runner.py `seen`), so the queue is keyed on exactly one signal and not on a tick."""
    for name, v in (("setup_id", setup_id), ("symbol", symbol), ("side", side), ("signal_time", signal_time)):
        if not v:
            raise DispatchError(f"signal_id: {name} is required")
    return f"{setup_id}|{symbol}|{side}|{signal_time}"
