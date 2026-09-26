"""The recorder's ONLY outbound network path (BMREC-26, BMREC-28) and the reconciliation arithmetic.

- `BinancePublic.get(path, params)` is the single chokepoint: HTTPS GET to `fapi.binance.com` only, on four
  public paths, with a per-path parameter allowlist. Anything else raises OutboundRefused before a socket opens.
- Unsigned: no API-key header, no request signing, no secret loader (BMREC-27). TLS verification stays on (default
  context), redirects are refused, timeouts are explicit.
- Request budget: own weight per rolling minute <= REST_BUDGET_FRACTION x the REQUEST_WEIGHT limit read from
  exchangeInfo (not hard-coded), and no request while the IP-wide X-MBX-USED-WEIGHT-1M exceeds
  REST_IP_HEADROOM_FRACTION of that limit. 429 -> back off; 418 -> stop all outbound calls for the run.
- Responses are schema-validated; an invalid or refused fetch yields UNKNOWN, never a match (CLAUDE.md §20).
"""
import json
import math
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation

ALLOWED_HOST = "fapi.binance.com"
ALLOWED_PATHS = {
    "/fapi/v1/depth": frozenset({"symbol", "limit"}),
    "/fapi/v1/aggTrades": frozenset({"symbol", "startTime", "endTime", "limit", "fromId"}),
    "/fapi/v1/exchangeInfo": frozenset(),
    "/fapi/v1/time": frozenset(),
}

# contract §8
REST_BUDGET_FRACTION = 0.1
REST_IP_HEADROOM_FRACTION = 0.8
REST_TIMEOUT_S = 5
REST_429_BACKOFF_INITIAL_S = 30
REST_429_BACKOFF_CAP_S = 600
WEIGHT_DEPTH_LIMIT_20 = 2
WEIGHT_AGGTRADES = 20
WEIGHT_EXCHANGEINFO = 1
WEIGHT_TIME = 1
DEPTH_RECON_INTERVAL_S = 60
DEPTH_RECON_REST_LIMIT = 20
DEPTH_RECON_LEVELS = 10
DEPTH_RECON_SAMPLE_MS = 50
DEPTH_RECON_ALIGN_WINDOW_MS = 250
DEPTH_RECON_MIN_MATCH_FRACTION = 0.8
DEPTH_RECON_FAIL_STREAK_INVALID = 3
AGG_RECON_INTERVAL_S = 300
AGG_RECON_WINDOW_S = 60
AGG_RECON_LAG_S = 30
AGG_RECON_VOLUME_REL_TOL = 0.01
CLOCK_OFFSET_INTERVAL_S = 60
TICK_GATE_DEADLINE_S = 3600

WEIGHTS = {"/fapi/v1/depth": WEIGHT_DEPTH_LIMIT_20, "/fapi/v1/aggTrades": WEIGHT_AGGTRADES,
           "/fapi/v1/exchangeInfo": WEIGHT_EXCHANGEINFO, "/fapi/v1/time": WEIGHT_TIME}

MATCH, MISMATCH, UNKNOWN = "MATCH", "MISMATCH", "UNKNOWN"


class OutboundRefused(RuntimeError):
    """Raised BEFORE any socket is opened."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise OutboundRefused(f"redirect refused (HTTP {code})")


def build_url(path, params=None):
    """Validate and build the one allowed URL shape. Raises OutboundRefused."""
    if path not in ALLOWED_PATHS:
        raise OutboundRefused(f"path not allowlisted: {path!r}")
    params = dict(params or {})
    extra = set(params) - ALLOWED_PATHS[path]
    if extra:
        raise OutboundRefused(f"parameters not allowlisted for {path}: {sorted(extra)}")
    for k, v in params.items():
        if not isinstance(v, (int, str)) or (isinstance(v, str) and not v.isalnum()):
            raise OutboundRefused(f"parameter {k} has a disallowed value")
    q = urllib.parse.urlencode(sorted(params.items()))
    return f"https://{ALLOWED_HOST}{path}" + (f"?{q}" if q else "")


def check_url(url, method="GET"):
    """The chokepoint's own guard, applied to the final URL string as well."""
    if method != "GET":
        raise OutboundRefused(f"method not allowed: {method}")
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or u.hostname != ALLOWED_HOST or u.port not in (None, 443) or u.username or u.password:
        raise OutboundRefused(f"host/scheme not allowlisted: {u.scheme}://{u.hostname}")
    if u.path not in ALLOWED_PATHS:
        raise OutboundRefused(f"path not allowlisted: {u.path!r}")
    keys = {k for k, _v in urllib.parse.parse_qsl(u.query, keep_blank_values=True)}
    if keys - ALLOWED_PATHS[u.path]:
        raise OutboundRefused(f"parameters not allowlisted: {sorted(keys - ALLOWED_PATHS[u.path])}")


class BinancePublic:
    def __init__(self, event=None, opener=None, clock=time.time):
        self.event = event or (lambda **kw: None)
        self.clock = clock
        self._opener = opener or urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl.create_default_context()), _NoRedirect())
        self.limit_per_min = None        # REQUEST_WEIGHT/minute from exchangeInfo
        self.own = []                    # [(t, weight)] within the last 60 s
        self.ip_used = None              # last X-MBX-USED-WEIGHT-1M
        self.backoff_until = 0.0
        self.backoff_s = REST_429_BACKOFF_INITIAL_S
        self.halted = False              # 418

    def budget_ok(self, path):
        now = self.clock()
        self.own = [(t, w) for t, w in self.own if now - t < 60]
        if self.halted:
            return False, "HALTED_418"
        if now < self.backoff_until:
            return False, "BACKOFF_429"
        if self.limit_per_min is None:
            return (path == "/fapi/v1/exchangeInfo"), "LIMIT_UNKNOWN"
        w = WEIGHTS[path]
        if sum(x for _t, x in self.own) + w > REST_BUDGET_FRACTION * self.limit_per_min:
            return False, "OWN_BUDGET"
        if self.ip_used is not None and self.ip_used > REST_IP_HEADROOM_FRACTION * self.limit_per_min:
            return False, "IP_HEADROOM"
        return True, "OK"

    def get(self, path, params=None):
        """Returns {"status": "OK"|"REFUSED"|"HTTP_ERROR"|"INVALID"|"NETWORK_ERROR", "http": int|None,
        "data": obj|None, "t_send": float, "t_recv": float, "reason": str}."""
        url = build_url(path, params)
        check_url(url)
        ok, why = self.budget_ok(path)
        if not ok:
            self.event(kind="rest_refused", endpoint=path, reason=why)
            return {"status": "REFUSED", "http": None, "data": None, "t_send": None, "t_recv": None, "reason": why}
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "tds-h1-recorder",
                                                                  "Accept": "application/json"})
        t0 = self.clock()
        self.own.append((t0, WEIGHTS[path]))
        http, body, headers = None, None, {}
        try:
            with self._opener.open(req, timeout=REST_TIMEOUT_S) as resp:
                http = resp.status
                headers = {k.lower(): v for k, v in resp.headers.items()}
                body = resp.read(8 * 1024 * 1024)
        except urllib.error.HTTPError as e:
            http = e.code
            headers = {k.lower(): v for k, v in (e.headers or {}).items()}
        except OutboundRefused:
            raise
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            t1 = self.clock()
            self.event(kind="rest_fetch", endpoint=path, t_send=t0, t_recv=t1, http=None,
                       error=type(e).__name__)
            return {"status": "NETWORK_ERROR", "http": None, "data": None, "t_send": t0, "t_recv": t1,
                    "reason": type(e).__name__}
        t1 = self.clock()
        used = headers.get("x-mbx-used-weight-1m")
        if used is not None and str(used).isdigit():
            self.ip_used = int(used)
        self.event(kind="rest_fetch", endpoint=path, t_send=t0, t_recv=t1, http=http, ip_used_weight=self.ip_used)
        if http == 418:
            self.halted = True
            self.event(kind="alert", what="HTTP_418_IP_BANNED", endpoint=path)
            return {"status": "HTTP_ERROR", "http": 418, "data": None, "t_send": t0, "t_recv": t1, "reason": "418"}
        if http == 429:
            ra = headers.get("retry-after")
            wait = max(self.backoff_s, int(ra) if ra and str(ra).isdigit() else 0)
            self.backoff_until = t1 + wait
            self.backoff_s = min(self.backoff_s * 2, REST_429_BACKOFF_CAP_S)
            self.event(kind="rest_429", endpoint=path, backoff_s=wait)
            return {"status": "HTTP_ERROR", "http": 429, "data": None, "t_send": t0, "t_recv": t1, "reason": "429"}
        if http != 200 or body is None:
            return {"status": "HTTP_ERROR", "http": http, "data": None, "t_send": t0, "t_recv": t1,
                    "reason": str(http)}
        self.backoff_s = REST_429_BACKOFF_INITIAL_S
        try:
            data = json.loads(body.decode("utf-8"), parse_constant=_reject_constant)
            VALIDATORS[path](data)
        except (ValueError, KeyError, TypeError, InvalidOperation) as e:
            return {"status": "INVALID", "http": http, "data": None, "t_send": t0, "t_recv": t1,
                    "reason": f"invalid body: {type(e).__name__}"}
        if path == "/fapi/v1/exchangeInfo":
            self.limit_per_min = request_weight_limit(data)
        return {"status": "OK", "http": http, "data": data, "t_send": t0, "t_recv": t1, "reason": "OK"}


def _reject_constant(name):
    raise ValueError(f"non-finite JSON constant {name}")


# ---------------------------------------------------------------- response validation


def _dec(s):
    d = Decimal(str(s))
    if not d.is_finite():
        raise ValueError("non-finite number")
    return d


def _v_time(d):
    if not isinstance(d, dict) or not isinstance(d.get("serverTime"), int) or d["serverTime"] <= 0:
        raise ValueError("serverTime")


def _v_depth(d):
    if not isinstance(d, dict):
        raise ValueError("depth")
    for k in ("lastUpdateId", "E", "T"):
        if not isinstance(d.get(k), int) or d[k] <= 0:
            raise ValueError(k)
    for side in ("bids", "asks"):
        rows = d.get(side)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"empty {side}")
        for row in rows:
            if not isinstance(row, list) or len(row) != 2 or _dec(row[0]) <= 0 or _dec(row[1]) <= 0:
                raise ValueError(f"bad {side} row")


def _v_agg(d):
    if not isinstance(d, list):
        raise ValueError("aggTrades")
    for t in d:
        if not isinstance(t, dict) or not isinstance(t.get("T"), int) or not isinstance(t.get("m"), bool):
            raise ValueError("aggTrade row")
        if _dec(t["p"]) <= 0 or _dec(t["q"]) <= 0:
            raise ValueError("aggTrade values")


def _v_info(d):
    if not isinstance(d, dict) or not isinstance(d.get("rateLimits"), list) or not isinstance(d.get("symbols"), list):
        raise ValueError("exchangeInfo")
    if request_weight_limit(d) is None:
        raise ValueError("no REQUEST_WEIGHT limit")


VALIDATORS = {"/fapi/v1/time": _v_time, "/fapi/v1/depth": _v_depth, "/fapi/v1/aggTrades": _v_agg,
              "/fapi/v1/exchangeInfo": _v_info}


def request_weight_limit(info):
    """REQUEST_WEIGHT per minute from exchangeInfo.rateLimits (BMREC-28: read, not hard-coded)."""
    for rl in info.get("rateLimits", []):
        if (isinstance(rl, dict) and rl.get("rateLimitType") == "REQUEST_WEIGHT" and rl.get("interval") == "MINUTE"
                and isinstance(rl.get("limit"), int) and rl["limit"] > 0):
            per = rl.get("intervalNum", 1) or 1
            return rl["limit"] / per
    return None


# ---------------------------------------------------------------- first-hour gate (plan H1, N3)


def symbol_from_alias(alias):
    """'BTCUSDT@BNF' -> 'BTCUSDT'. None if the alias does not look like a Binance futures symbol."""
    base = (alias or "").split("@", 1)[0].strip().upper()
    if 2 <= len(base) <= 20 and base.isalnum():
        return base
    return None


def exchange_filters(info, symbol):
    for s in info.get("symbols", []):
        if s.get("symbol") == symbol:
            out = {"symbol": symbol}
            for f in s.get("filters", []):
                if f.get("filterType") == "PRICE_FILTER":
                    out["tickSize"] = str(f.get("tickSize"))
                if f.get("filterType") == "LOT_SIZE":
                    out["stepSize"] = str(f.get("stepSize"))
            return out if "tickSize" in out and "stepSize" in out else None
    return None


def tick_gate(pips, size_multiplier, filters):
    """(status, detail): status MATCH / MISMATCH / UNKNOWN. pips must equal tickSize and sizeMultiplier must equal
    1/stepSize, both to 1e-9 relative (Decimal arithmetic)."""
    if not filters:
        return UNKNOWN, "exchange filters unavailable"
    try:
        tick, step = _dec(filters["tickSize"]), _dec(filters["stepSize"])
        p, m = _dec(repr(float(pips))), _dec(repr(float(size_multiplier)))
    except (InvalidOperation, ValueError, KeyError):
        return UNKNOWN, "unparseable filters"
    if tick <= 0 or step <= 0:
        return UNKNOWN, "non-positive filter"
    ok_tick = abs(p - tick) <= tick * Decimal("1e-9")
    ok_step = abs(m * step - 1) <= Decimal("1e-9")
    detail = f"pips={p} tickSize={tick} sizeMultiplier={m} stepSize={step}"
    return (MATCH if ok_tick and ok_step else MISMATCH), detail


# ---------------------------------------------------------------- reconciliation arithmetic (contract §8.1)


def clock_offset(server_time_ms, t_send_s, t_recv_s):
    mid_ms = (t_send_s + t_recv_s) * 500.0
    return {"offset_ms": server_time_ms - mid_ms, "rtt_ms": (t_recv_s - t_send_s) * 1000.0}


def rest_side_levels(rows, pips, size_multiplier, n):
    """REST [[price, qty], ...] -> [(level, size_units)] for the top n. None if a price is not on the pips grid."""
    out = []
    for price, qty in rows[:n]:
        lv = float(_dec(price)) / pips
        lvl = round(lv)
        if abs(lv - lvl) > 1e-6:
            return None
        out.append((lvl, int(round(float(_dec(qty)) * size_multiplier))))
    return out


def compare_depth(rest, sample, pips, size_multiplier, n=DEPTH_RECON_LEVELS):
    """rest: validated depth body; sample: {"bids": [(level,size)...] best-first, "asks": [...]}.
    Returns (result, detail)."""
    detail = {}
    results = []
    for side in ("bids", "asks"):
        ref = rest_side_levels(rest[side], pips, size_multiplier, n)
        if ref is None:
            return UNKNOWN, {"reason": "REST price not on pips grid"}
        mine = dict(sample[side][:max(n * 3, n)])
        match = sum(1 for lvl, sz in ref if mine.get(lvl) == sz)
        frac = match / len(ref) if ref else 0.0
        detail[side] = {"compared": len(ref), "matched": match, "fraction": round(frac, 4)}
        results.append(frac >= DEPTH_RECON_MIN_MATCH_FRACTION)
    return (MATCH if all(results) else MISMATCH), detail


def pick_sample(samples, target_local_ms, window_ms=DEPTH_RECON_ALIGN_WINDOW_MS):
    """samples: [(local_ms, sample)]. Closest within the window, else None (-> UNKNOWN)."""
    best = None
    for t, s in samples:
        d = abs(t - target_local_ms)
        if d <= window_ms and (best is None or d < best[0]):
            best = (d, t, s)
    return best


def compare_aggtrades(rest_rows, recorded, size_multiplier, rel_tol=AGG_RECON_VOLUME_REL_TOL):
    """rest_rows: validated aggTrades; recorded: [(is_bid_aggressor, size_units)] in the same window.
    Returns (result, detail). A response at the 1000-row limit is truncated -> UNKNOWN."""
    if len(rest_rows) >= 1000:
        return UNKNOWN, {"reason": "aggTrades response truncated at limit"}
    rest_buy = sum(float(_dec(r["q"])) for r in rest_rows if r["m"] is False) * size_multiplier
    rest_sell = sum(float(_dec(r["q"])) for r in rest_rows if r["m"] is True) * size_multiplier
    rec_buy = float(sum(s for b, s in recorded if b))
    rec_sell = float(sum(s for b, s in recorded if not b))
    detail = {"rest_buy": rest_buy, "rest_sell": rest_sell, "rec_buy": rec_buy, "rec_sell": rec_sell}
    if rest_buy + rest_sell == 0 and rec_buy + rec_sell == 0:
        return UNKNOWN, dict(detail, reason="no trades in window")
    ok = True
    for r, m in ((rest_buy, rec_buy), (rest_sell, rec_sell)):
        if r == 0:
            ok = ok and m == 0
        else:
            ok = ok and abs(m - r) / r <= rel_tol
    if not all(math.isfinite(x) for x in detail.values() if isinstance(x, float)):
        return UNKNOWN, dict(detail, reason="non-finite")
    return (MATCH if ok else MISMATCH), detail
