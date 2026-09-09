---
description: Explicit check of price/thesis/data invalidation on one open trade, without the full exit-management recommendation /exit gives.
argument-hint: <trade id>
---

Lighter-weight sibling of `/exit`: read `trades/<id>.md`, re-check only the three invalidation types (price, thesis, data — master spec §21) and report INVALIDATED / NOT INVALIDATED for each with the specific evidence, without producing management recommendations (breakeven/partial/full-exit logic). Use `/exit` instead when you also want a management recommendation, not just the invalidation status. Useful as the lightweight check to run periodically (e.g. via the `loop` skill on a user-chosen interval) since there's no live position-monitoring hook in this system (`SYSTEM-DESIGN.md` §10).
