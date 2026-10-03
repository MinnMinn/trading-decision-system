# Multi-day holding of the surviving trend rules -- pre-registration (2026-10-03, committed BEFORE any run)

Parent: docs/audits/2026-10-03-ftmo-rules-audit.md §3 -- FTMO allows overnight holding in the Challenge / Verification;
"flat before the rollover" was a design choice, and holding the rules that WORK (H7 / G9 trend on metals) was never measured.
Code: `scripts/research/edge_hold.py`; tests: `scripts/tests/test_edge_hold.py`.

Unit: the INCREMENT from the entry day's last close to the close of the k-th following dense server day (k = 1, 2, 3), in the
trade's direction, minus the real FTMO-Demo swap for the nights held (triple night included), for H7 XAUUSD, G9 XAUUSD, G9 XAGUSD
(the F3 / F4 events, unchanged). FAMILY = 9 tests; direction fixed (+1 = keep the trade's side); one-sided.
Placebo: the same increment from every dense day's close in the same period, signed by the side. Three reads, each once:
discovery (BH q = 0.10 over 9 + net > 0), confirmation (p < 0.05, net > 0), exposed 2024-03-01 -> (p < 0.10, net > 0).
Disclosed: today's swap points stand in for history's; the increments overlap the following days' own signals.
A survivor becomes a book variant ("hold k days") measured with pass_policy against v2, floating limits included.
