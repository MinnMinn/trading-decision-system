# knowledge/ — index

The ingested source material this system reasons from. **Nothing here is read at runtime**: every reference to
these files anywhere in the repo is prose, a docstring, a JSON `cite` string or a prompt body. They are the
provenance layer — the answer to "where does this rule come from?" — and `docs/architecture/SYSTEM-DESIGN.md`
§6 is the answer to "what does the system do with it?".

Organised per methodology since 2026-09-17. Before that it was ten files in one flat directory with numeric
prefixes and **no index at all** — which is how five citations of a filename that never existed
(`08-ttrades-core-B.md`, meaning `05`) survived unnoticed. `scripts/tests/test_doc_citations.py`
(`KnowledgeCitationsResolve`) now fails the build if a citation points at a file that is not here, if a live
file uses a retired spelling, or if a file in this tree is missing from this index.

## Wyckoff — `knowledge/wyckoff/`

| File | Source | What it carries |
|---|---|---|
| [`wyckoff/advance.md`](wyckoff/advance.md) | *Wyckoff Advance* — Nguyễn Vũ Tuấn Hải (`WA pNNN`), full book, pp. 4–56 + 59–293 of 294 | The complete Phase A–E event vocabulary (PS/SC/AR/ST/SOS/LPS and the distribution mirror), the CHoBEV/CHoCH gate, the mislabelling (*đối nhãn*) tests, Effort-vs-Result, the CO plan, Tape Reading, Volume Profile, SOT |
| [`wyckoff/modern-tools.md`](wyckoff/modern-tools.md) | *Wyckoff and Modern Tools* — same author (`WMT pNNN`) | Spring and Upthrust **typing** (types 1/2/3 by volume), trading-range construction, and — despite living under `wyckoff/` — the **primary source for Footprint and Delta**, including the subjectivity and tick-volume caveats in §7. The `footprint/` files below cross-reference it rather than restating it. |

## ICT / TTrades — `knowledge/ict/`

| File | Source | What it carries |
|---|---|---|
| [`ict/core-a.md`](ict/core-a.md) | TTrades decks 1–13 (`docs/TTrades PDFs/`) | Killzones, position sizing, liquidity and important liquidity levels, premium/discount, OTE, FVG |
| [`ict/core-b.md`](ict/core-b.md) | TTrades decks 14–22 | CISD, Order/Breaker/Mitigation blocks, MSS, SMT, PO3/AMD, standard deviations, IRL/ERL |
| [`ict/models.md`](ict/models.md) | TTrades model decks | The TTrades Model (OSOK + Fractal), the Sons Model (+HTF), TTRS Reversal |
| [`ict/mentorship-2024.md`](ict/mentorship-2024.md) | *Mentorship 2024* (`docs/Mentorship 2024.pdf`), 21 lectures, cited `M L<n>` | Objects the three files above do **not** contain: NDOG/NWOG, ORG and its quadrants, the extended CE object set, BPR, Rejection Block, Event Horizon, Turtle Soup in the MM Buy/Sell Model, STDEV measured moves, Ideal FVG Delivery. **Read its scope header first** — the deck is CME index futures on the NY session, and the whole Opening-Gap family requires a session discontinuity that 24/7 crypto does not have. |

## Footprint / order flow — `knowledge/footprint/`

| File | Source | What it carries |
|---|---|---|
| [`footprint/wyckoff-logic.md`](footprint/wyckoff-logic.md) | Footprint course PDFs, cited `[P1 pN]` / `[P2 pN]` / `[P3 pN]` | Wyckoff logic and auction theory as the course teaches it, distribution + absorption of supply, the volume shorthand used on all charts |
| [`footprint/tape-reading.md`](footprint/tape-reading.md) | StockMap *Dải Băng Giá* | Tape reading as Effort vs Result, without Delta |
| [`footprint/chart-delta.md`](footprint/chart-delta.md) | Stockmap.vn series, docs 6–8 | Footprint chart reading, POC, imbalance and stacked imbalance, Delta and cumulative Delta, Footprint + Wyckoff together |

## Integrated — `knowledge/integrated/`

| File | What it carries |
|---|---|
| [`integrated/wyckoff-ict-mapping.md`](integrated/wyckoff-ict-mapping.md) | The concept-by-concept Wyckoff ↔ ICT correspondence table **and the double-counting risk register** — the file that makes SYSTEM-DESIGN §6.1's Independent-Confluence Check enforceable, so two dimensions cannot score one phenomenon twice. `docs/audits/2026-09-11-knowledge-09-mapping-audit.md` records 21 stale and 9 wrong claims in it that are still open. |
| [`integrated/method.md`](integrated/method.md) | The operating procedure built on the mapping — source precedence, and which read owns which decision |

## Raw extractions (hidden)

`.wyckoff-parts/` and `.wyckoff-advance-parts/` hold the page-by-page extractions the two Wyckoff syntheses
were built from. Dot-prefixed so they stay out of greps and out of this index's sibling listings; kept because
a synthesis without its extraction cannot be re-verified. Cite the synthesis, not the parts.

## Previous layout → current path

Retired 2026-09-17 (user decision: one folder per methodology, full paths everywhere, no short codes). This
table is the **only** live file permitted to carry the retired spellings, because it is what makes them
decodable: `docs/audits/`, `docs/plans/`, `docs/backtests/` and `docs/prompts/` are dated records whose
citations were true when written and are deliberately not re-pointed, and older commit messages use them too.

| Old filename | Old short code | Current path |
|---|---|---|
| `01-footprint-wyckoff-logic-structure-absorption.md` | `k01` | `knowledge/footprint/wyckoff-logic.md` |
| `02-footprint-tape-reading.md` | `k02` | `knowledge/footprint/tape-reading.md` |
| `03-footprint-chart-delta-wyckoff.md` | `k03` | `knowledge/footprint/chart-delta.md` |
| `04-ttrades-core-A.md` | `k04` | `knowledge/ict/core-a.md` |
| `05-ttrades-core-B.md` | `k05` | `knowledge/ict/core-b.md` |
| `06-ttrades-models.md` | `k06` | `knowledge/ict/models.md` |
| `07-wyckoff-advance.md` | `k07` | `knowledge/wyckoff/advance.md` |
| `08-wyckoff-and-modern-tools.md` | `k08` | `knowledge/wyckoff/modern-tools.md` |
| `09-wyckoff-ict-mapping.md` | `k09` | `knowledge/integrated/wyckoff-ict-mapping.md` |
| `10-integrated-method.md` | `k10` | `knowledge/integrated/method.md` |

Two traps in the old numbering, recorded because they explain citations that look wrong:

- `08-wyckoff-and-modern-tools.md` was `07-` until 2026-09-10, when the files were renumbered so that `07`
  meant *Wyckoff Advance*. A citation of `07` in a document written before that date may mean *Modern Tools*.
- `06-ttrades-models.md` cited `08-ttrades-core-B.md` in five places. No file ever had that name; the intended
  target was `05-ttrades-core-B.md`, now `knowledge/ict/core-b.md`. Fixed during the move.

## Citation format

`knowledge/<methodology>/<file>.md §<section>`, plus the source's own page citation where the file carries one
(`WA p71`, `WMT p036`, `[P1 p24]`, `M L18`, or a TTrades deck reference as printed, e.g. `17. Orderblocks p3`).
Never a bare number, never a short code — `scripts/tests/test_doc_citations.py` enforces both.
