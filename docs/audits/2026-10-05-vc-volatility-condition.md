# VC: does the XAUUSD trend edge (H7 / G9) concentrate on volatile days or early entries? NOT SHOWN (2026-10-05)

Sealed pre-registration `docs/plans/2026-10-04-vc-volatility-condition-preregistration.md` [VC-P1] (seal `d997faa`), the
one read `docs/audits/2026-10-05-edge-vc-xau-holdout.json` (commit `676e365`), ledger `vc_volatility_condition`.

**Plain answer.** The idea came from a table seen after the fact: on 2018+ data, H7 / G9 gold trades with wide stops
earned more (personal-account audit §2.2). A wide stop means a volatile day, an early entry (more bars left in the day),
or both. On the clean window (XAUUSD entries before 2008-12-10, never split this way before) neither half is shown:
- **Volatile days: no.** High-volatility days earned slightly LESS than calm ones (-0.023 R_bar, p 0.62). The partly
  exposed 2008-12 -> 2017 window says the same (-0.014, p 0.70). "Trade only volatile days" is not supported.
- **Early entries: same direction, not shown on the clean window.** Long-hold (early) entries earned more than late ones
  (+0.072 R_bar, p 0.14; G9 alone +0.144, p 0.044, component level). On the partly exposed 2008-12 -> 2017 window the
  gap is large: early entries +0.23 R net, late entries -0.08 R net (t 8.9). That window is report-only: it was partly
  exposed through the personal-account replays (they compared stop-width-dependent sizing on it), so it is a strong
  pointer, not a confirmation.

## 1. The decisive test (window B, XAUUSD H7 + G9, 762 trades with a volatility ratio)

| test | halves | mean R_bar (net) | difference | p (one-sided) | pass |
|---|---|---|---|---|---|
| T1a volatility (option C: by day AND by run) | HIGH 545 / LOW 217 | 0.071 / 0.082 | -0.023 | 0.618 by day, 0.666 by run | no |
| T1b hold length (early vs late entry) | long 378 / short 384 | 0.121 / 0.028 | +0.072 | 0.140 | no |

Holm m = 2 at 0.05: nothing rejected. Reading: **NOT SHOWN** (inconclusive for a G9-concentrated effect: the read had
~0.4-0.5 power for the 2018+ shape, VC-P1 §7, §9). The research-mode and causal-density sensitivities give the same
verdict (not data-sensitive). Silver T2 not run (no silver trade with a volatility ratio before 2008-12).

Per component (descriptive): H7 volatility -0.041 (p 0.64), hold -0.013 (p 0.56); G9 volatility -0.003 (p 0.51), hold
+0.144 (p 0.044).

## 2. Report-only window A (2008-12-10 -> 2017-12-31, partly exposed)

| test | halves | mean R_bar (net) | difference | t | p |
|---|---|---|---|---|---|
| T1a volatility | HIGH 1,474 / LOW 1,804 | 0.128 / 0.125 | -0.014 | -0.52 | 0.70 |
| T1b hold length | long 2,183 / short 1,095 | 0.230 / -0.079 | +0.300 | 8.86 | < 0.001 |

## 3. What it means

- **The forward test (TF) is not scheduled:** the sealed rule runs it only if T1a or T1b passed. VC on gold is closed
  as NOT SHOWN. The crypto part (VC-X) still waits for the CX reads.
- **Personal account (the 100 USD minimum-lot cap, personal-account audit §5.4):** VC was the test of "how much of the
  cap's gain is real". It found no volatility effect. The early-entry effect points the same way as the cap's gain (wide
  stops are mostly early entries), strongly on the partly exposed years and weakly on the clean ones. So the cap's gain
  is neither confirmed nor refuted; the recommendation stays a CANDIDATE, and the half-edge rows stay the planning rows.
- **FTMO book (fvg-book v4):** late-day entries look unprofitable on 2008-2017 (-0.08 R net on a third of the trades).
  A rule "no new H7 / G9 entry after a fixed clock time" is a natural candidate, but it was found on partly exposed data:
  it can only be tested on new data (forward), under its own pre-registration, with the cut fixed before any forward bar.
  Not drafted here.
- **No change to the demo.**
