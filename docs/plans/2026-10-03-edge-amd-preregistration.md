# Edge family AMD (session Power of Three) -- pre-registration (2026-10-03, committed BEFORE any run on real data)

Owner question 2026-10-03: "Kết hợp lựa chọn đánh theo phiên Á (Accumulation), phiên Âu (Manipulation), phiên Mỹ (Distribution)
thì thế nào?" Code: `scripts/research/edge_amd.py`; tests: `scripts/tests/test_edge_amd.py` (synthetic bars only).

## 1. Sources (no rule beyond them)

- knowledge/ict/models.md §2.5.6 (TTrades daily profiles): London Reversal -> New York continuation; London consolidation /
  opposing run -> New York reversal; London expansion -> avoid New York.
- knowledge/ict/core-b.md §2.11 (PO3 / AMD): accumulation around the open, manipulation beyond the open AGAINST the eventual
  direction, distribution in the true direction.
- Windows: docs/architecture/sessions.json -- Asia 20:00-24:00 New York (evening before), London 08:00-11:00 London, New York
  from 08:30 New York. DST-aware (zoneinfo per bar). Every trade exits at the last bar before 16:00 New York (intraday).

## 2. Rules (direction FIXED by the source; one-sided p)

| id | condition (all known at the signal bar's close) | entry |
|---|---|---|
| AMD1 London Reversal | London takes exactly one Asia extreme and, at the last bar before 08:30 NY, price is back across the London open | 08:30 NY bar open, reversal direction |
| AMD2 New York Reversal | London inside the Asia range; first 08:30-11:00 NY bar trading beyond the Asia+London high (low) and closing back inside | next bar open, reversal direction |
| AMD3 PO3 daily open | at the last bar before 08:30 NY, the excursion beyond the server-day open AGAINST the close's side is the larger one | 08:30 NY bar open, toward the close's side |

Simplification disclosed: the sources' CISD confirmation and 2R / projection targets are NOT modelled (mechanical proxies:
back across the London open; close back inside; time exit at 16:00 NY). A null here rejects these proxies, not every
discretionary reading of the profiles.

## 3. Universe, family, reads

All eight allowlisted CFDs; FAMILY = 24 tests. Three reads, each once, identical to F5 §2 (BH q = 0.10 over the 24 discovery
one-sided p-values + net > 0; confirmation p < 0.05, net > 0, p90 net > 0; exposed 2024-03-01 -> end p < 0.10, net > 0).
Placebo: same period, same 5m time of day, to the same 16:00 NY exit. Zero survivors is a valid result. Survivors are then
measured against docs/architecture/book-baseline.json with `book_sim.py compare` (independence from the gold-trend book).
