# Vendored browser libraries

| File | What | Version | Source | License |
|---|---|---|---|---|
| `lightweight-charts.standalone.production.js` | TradingView Lightweight Charts™ (canvas financial charts; the chart layer of every page `scripts/build-artifact.py` renders) | 5.2.1 | `https://cdn.jsdelivr.net/npm/lightweight-charts@5.2.1/dist/lightweight-charts.standalone.production.js` (fetched 2026-09-12) | Apache-2.0 — `LICENSE-lightweight-charts.txt`. The license requires attribution (Apache-2.0 §4(d) + the library's `NOTICE`, copied to `NOTICE-lightweight-charts.txt`): the on-canvas logo is turned off (`layout.attributionLogo:false`) and the NOTICE line with the TradingView link is printed in the footer of every page that embeds the build (chart pages and the journal). Keep that footer line if you ever remove or restyle the footer. |

Pinned on purpose: the page inlines this file at build time so a published artifact never depends on a CDN. To upgrade,
replace the file, bump this table, and run `python3 -m unittest scripts/tests/test_build_artifact.py`.
