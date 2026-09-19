"""CLAUDE.md §22 -- footprint is DERIVED analytics, and the derivation is here rather than in a diagram.

    import footprint as F
    bars = F.build(trades, "15m", rule=F.TICK_RULE, provenance=prov)   # the whole chain
    F.from_vendor(bar, provenance=prov)                                # a pre-aggregated bar, labelled as one

§22 states a chain and a field list:

    Raw Trades -> Trade Classification -> Aggregation -> Footprint

    Preserve: source trades, provider, source venue, market type, timestamp, aggregation rule,
              price level, bid/ask classification, timeframe.

Neither existed. There was no footprint record type at all, so none of the nine fields was preserved
anywhere, and the only footprint in the repo was `mock/coinglass/footprint-history.BTCUSDT.json` -- read as
TEXT by an agent, never parsed. (It could not have been: it carried `"delta": +176`, which is not JSON. Nothing
had ever loaded it.)

**What is implemented, and what deliberately is not.** `providers.json` declares `trades_raw` and records that
**no provider supplies it** -- which is why footprint arrives pre-aggregated. So the chain has no live input
today, and `methods.live_sourced("footprint", …)` is False for every market. Building a trades FEED now, to
supply a dimension that is switched off, is the speculative implementation §0 and §57 forbid. What is built
here is the part that is §22's actual subject and needs no feed: **classification and aggregation as pure
functions**, plus the record type that makes the nine fields required rather than hoped for. When `trades_raw`
gains a provider, the wiring is `build(fetch(...), ...)` and the domain logic is already tested.

**The honesty half.** §22: *"Never pretend provider-native footprint exists if it does not."* A vendor bar and
a derived bar are different claims about where a number came from, so they are built by different constructors
and carry a different `derivation`. `from_vendor` REFUSES to name source trades, because a pre-aggregated bar
does not have any it can point to -- and a field saying `source_trades: 0` would read as "we checked".

**Classification.** §22 says "Trade Classification" without saying how, because there is no single answer: a
trade's side is a fact only the venue knows, and everything else is an inference. Two rules are provided and
named in the record, which is the point -- an aggregation whose rule is not recorded cannot be reproduced
(§10, §46):

  * `VENUE_RULE` -- use the venue's own maker/taker flag. Correct where it exists; Binance aggTrades carries
    `m` (buyer is maker), so a taker-buy is `m == False`.
  * `TICK_RULE` -- infer from the price change against the previous trade (uptick = buy, downtick = sell,
    unchanged = repeat the last classification). The classical fallback where no flag is published. It is an
    INFERENCE and the record says so, so a downstream read never treats it as the venue's word.
"""
import datetime
import types

# §22's own field list, snake_cased. A record missing any of them is refused rather than defaulted: a default
# for "which venue was this" is a guess about provenance, and §7 exists to stop exactly that.
REQUIRED_FIELDS = ("source_trades", "provider", "source_venue", "market_type", "timestamp",
                   "aggregation_rule", "price_levels", "classification_rule", "timeframe")

# How a bar came to exist. Not cosmetic: it is the difference between a number this system computed from
# trades it can name and a number a vendor handed over pre-chewed.
DERIVED = "derived_from_trades"
VENDOR = "vendor_aggregated"
DERIVATIONS = (DERIVED, VENDOR)

VENUE_RULE = "venue_maker_flag"
TICK_RULE = "tick_rule_inferred"
CLASSIFICATION_RULES = (VENUE_RULE, TICK_RULE)

BUY, SELL, UNKNOWN = "buy", "sell", "unknown"


def classify(trades, rule=VENUE_RULE):
    """Raw trades -> (trade, side) pairs. Step 2 of §22's chain, kept separate from step 3 on purpose.

    Returns a new list; the input trades are not mutated. A trade whose side cannot be determined is
    `unknown` and stays unknown -- §9's "Unknown is a valid state", and calling an undeterminable trade a buy
    would put a fabricated imbalance into every bar that contains it.
    """
    if rule not in CLASSIFICATION_RULES:
        raise ValueError(f"unknown classification rule {rule!r}; §22 requires the rule to be recorded, so it "
                         f"must be one this module can name: {list(CLASSIFICATION_RULES)}")
    out, last_price, last_side = [], None, UNKNOWN
    for t in trades:
        if rule == VENUE_RULE:
            maker = t.get("buyer_is_maker")
            side = UNKNOWN if maker is None else (SELL if maker else BUY)
        else:
            price = float(t["price"])
            if last_price is None or price == last_price:
                side = last_side          # the classical tick rule: an unchanged price repeats the last side
            else:
                side = BUY if price > last_price else SELL
            last_price, last_side = price, side
        out.append((t, side))
    return out


def aggregate(classified, timeframe, tick_size, *, bar_seconds):
    """Classified trades -> price levels per bar. Step 3.

    `tick_size` is the price granularity the levels are bucketed to, and it is an ARGUMENT rather than a
    constant because it is an instrument fact: bucketing BTC and XAU to the same grid would make one bar a
    single level and the other ten thousand.
    """
    bars = {}
    for t, side in classified:
        when = _parse(t["time"])
        key = when - datetime.timedelta(seconds=when.timestamp() % bar_seconds)
        level = round(float(t["price"]) / tick_size) * tick_size
        b = bars.setdefault(key.strftime("%Y-%m-%dT%H:%M:%SZ"), {})
        lv = b.setdefault(level, {"price": level, "buy_vol": 0.0, "sell_vol": 0.0, "unknown_vol": 0.0})
        lv[f"{side}_vol"] += float(t.get("size", t.get("quantity", 0)) or 0)
    return {k: [v[p] for p in sorted(v)] for k, v in sorted(bars.items())}


def build(trades, timeframe, *, tick_size, bar_seconds, provenance, rule=VENUE_RULE):
    """The whole §22 chain, end to end, returning one sealed record per bar.

    `provenance` must name provider / source_venue / market_type -- the three §7 facts a derived value has to
    keep a line back to. They are not defaulted (see REQUIRED_FIELDS).
    """
    classified = classify(trades, rule)
    levels = aggregate(classified, timeframe, tick_size, bar_seconds=bar_seconds)
    counts = {}
    for t, _ in classified:
        when = _parse(t["time"])
        key = (when - datetime.timedelta(seconds=when.timestamp() % bar_seconds)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        counts[key] = counts.get(key, 0) + 1
    return [_seal({
        "timestamp": ts,
        "timeframe": timeframe,
        "price_levels": lv,
        "source_trades": counts.get(ts, 0),
        "classification_rule": rule,
        "aggregation_rule": f"tick_size={tick_size:g}, bar_seconds={bar_seconds}",
        "derivation": DERIVED,
        "delta": round(sum(x["buy_vol"] - x["sell_vol"] for x in lv), 8),
        "unknown_vol": round(sum(x["unknown_vol"] for x in lv), 8),
        **_prov(provenance),
    }) for ts, lv in levels.items()]


def from_vendor(bar, *, provenance, timeframe=None):
    """A pre-aggregated vendor bar, recorded as one. §22: never pretend a native footprint is a derived one.

    `source_trades` is None -- not 0. A vendor bar has no trades this system can point at, and a zero would
    read as "we looked and there were none". The value that means "not knowable from here" is None (§9).
    """
    levels = [{"price": float(l["price"]),
               "buy_vol": float(l.get("ask_vol", 0)),     # taker BUY lifts the ask
               "sell_vol": float(l.get("bid_vol", 0)),    # taker SELL hits the bid
               "unknown_vol": 0.0} for l in (bar.get("price_levels") or [])]
    return _seal({
        "timestamp": bar["time"],
        "timeframe": timeframe or bar.get("timeframe"),
        "price_levels": levels,
        "source_trades": None,
        "classification_rule": None,
        "aggregation_rule": "vendor-defined; not disclosed by the feed",
        "derivation": VENDOR,
        "delta": bar.get("delta"),
        "cumulative_delta": bar.get("cumulative_delta"),
        **_prov(provenance),
    })


def is_native(record):
    """Whether this bar came from trades this system classified itself. The question §22's last line asks."""
    return record["derivation"] == DERIVED


def _prov(provenance):
    missing = [f for f in ("provider", "source_venue", "market_type") if f not in provenance]
    if missing:
        raise ValueError(f"footprint provenance is missing {missing}. CLAUDE.md §22 requires a footprint to "
                         f"keep a line back to the provider, venue and market type it came from; §7 requires "
                         f"a derived value to be traceable to its source state. Neither has a safe default.")
    return {k: provenance[k] for k in ("provider", "source_venue", "market_type")}


def _seal(mapping):
    """Immutable, and refusing to exist without §22's nine fields."""
    missing = [f for f in REQUIRED_FIELDS if f not in mapping]
    if missing:
        raise ValueError(f"footprint record is missing required field(s): {missing} (CLAUDE.md §22)")
    if mapping["derivation"] not in DERIVATIONS:
        raise ValueError(f"derivation must be one of {list(DERIVATIONS)}; a bar that will not say where it "
                         f"came from is the pretence §22's last line forbids")
    return types.MappingProxyType(dict(mapping))


def _parse(ts):
    if isinstance(ts, datetime.datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=datetime.timezone.utc)
    return datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
