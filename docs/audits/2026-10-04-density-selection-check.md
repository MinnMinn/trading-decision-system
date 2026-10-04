# Same-day completeness selection in the research mode -- measured on the gold book (2026-10-04)

**DESCRIPTIVE.** Raw data: docs/audits/2026-10-04-density-selection-check.json. Script:
`scripts/research/density_selection_check.py`.

**The selection.** `edge_census.Series` in research mode (`sigma_every_day=False`, used by F3 / F4 / `book_sim` and so by
A1 / A3) gives a day a sigma, and F3 a MOM20, only if the whole day turns out dense. An event on a day that later proves
sparse is dropped. That is a same-day completeness selection: it uses information from after the signal (CLAUDE.md §8). It
was disclosed in the Series docstring but never measured. The adversarial review of the CX pre-registration flagged it. The
demo executor and the paper twin run point in time (`sigma_every_day=True`).

**Measured.** Same bars, the book components replayed both ways (full stored history):

| component, stop | trades research -> point in time | extra trades' mean R | mean R research -> point in time | worst R |
|---|---|---|---|---|
| H7 XAUUSD, 2.0 | 2,430 -> 2,485 (+55) | +0.068 | 0.0467 -> 0.0472 | -1.10 both |
| H7 XAUUSD, 1.4 | 2,430 -> 2,485 | +0.130 | 0.0761 -> 0.0773 | -1.23 both |
| G9 XAUUSD, 2.0 | 3,549 -> 3,627 (+78) | +0.022 | 0.0916 -> 0.0901 | -1.18 both |
| G9 XAUUSD, 1.4 | 3,549 -> 3,627 | +0.034 | 0.1319 -> 0.1298 | -1.39 both |
| G9 XAGUSD, 2.0 / 1.4 | 3,019 -> 3,040 (+21) | +0.056 / +0.044 | 0.0622 -> 0.0622 / 0.0895 -> 0.0891 | -1.32 / -1.89 |

The selection only REMOVES trades (none appears in the research mode alone), and every common trade's R is identical. The
removed trades were profitable on average. The book's mean R moves by at most 0.002 R, and its worst trade does not move.
**The gold evidence behind fvg-book v4 stands.** For crypto, where feed gaps cluster on crash days, CX uses the point-in-time
rule (docs/plans/2026-10-04-edge-cx-ftmo-crypto-preregistration.md §1).
