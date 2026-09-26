---
title: Self-improving research is built in a fixed order, and may only extend -- never alter -- each methodology's source-book framework
date: 2026-09-26
status: ACCEPTED
context: The owner wants the platform, once correct, to run backtests continuously over custom methods and rank as many profitable approaches as possible -- a self-learning, self-upgrading research loop (CLAUDE.md §41-§48). The 2026-09-24 audit (docs/audits/2026-09-24-system-audit.md) and rounds 1-4 (ADR 0001-0005) showed the engine was not yet correct, and a stability run takes ~2 hours per file on single-threaded Python. The methodologies (Wyckoff, ICT/TTrades, Footprint, Heatmap) are sourced from books and PDFs the owner supplied, ingested under knowledge/ (knowledge/INDEX.md).
problem: A search loop that proposes and ranks many candidates will, by construction, find variants that look profitable by chance (data snooping, multiple testing, §43-§45). Built before the validation gates exist, it produces a ranking of overfits. Separately, a loop free to change rules could quietly rewrite a methodology into something the source books do not say, which CLAUDE.md §13 forbids ("Do not invent methodology rules that are not supported by the methodology specification").
decision: |
  1. Build in this order, each stage gated on the previous one being verified: (a) a correct engine (audit rounds 1-4); (b) a fast engine -- same results, measured before/after, byte-identical stability rows as the acceptance test; (c) the experiment ledger and validation gates (§42-§46: experiment budget, multiple-testing accounting, untouched vs EXPOSED OOS, walk-forward, sensitivity/robustness); (d) only then the self-proposing and ranking loop.
  2. Methodology fidelity: every methodology's framework as written in its source (knowledge/ and the PDFs it cites) is fixed. The loop and any human-directed change may ADD within it -- e.g. new parameter values for project-defined thresholds, filters, sessions, exit variants, combinations, or objects the source defines but the engine does not yet implement -- but may NOT change, remove, reorder or reinterpret the source's framework (its event vocabulary, phase structure, setup definitions, entry/invalidation logic, typing tables). Every added rule carries a citation to the source passage it extends, or is explicitly labelled project-defined.
  3. The loop only proposes. Adopting any candidate into a live Trading System remains a human decision through the §42 lifecycle and §47 versioning (§41: "AI must NEVER silently rewrite the production Trading System").
alternatives:
  - Build the self-proposing loop now on the current engine and add validation gates later.
  - Let the loop tune any rule, including the methodology frameworks themselves, and judge candidates by backtest results alone.
  - Skip the speed stage and rely on buying hardware.
chosen_approach: The fixed order (a)->(b)->(c)->(d) above, plus the extend-never-alter methodology rule, recorded here and enforced in every dispatch prompt and review of research-loop work.
reason: Validation gates are what make a ranking mean anything (§45 "actively attempt to disprove candidates"); without them the loop's output is indistinguishable from noise. Allowing framework changes would let backtest performance redefine Wyckoff/ICT into unsourced systems, violating §13 and destroying explainability (§1 priority 7). Speed comes before the loop because the loop's value scales with how many honest experiments fit in a day, and profiling shows the engine uses one core at ~99% while the machine idles the rest -- a software gain of one to two orders of magnitude is available before hardware matters.
consequences: |
  Research-loop work (stage d) is blocked until stages (b) and (c) are merged and verified. Every candidate the loop emits must name the knowledge/ passage it extends or be marked project-defined; a candidate that changes a source framework is rejected on sight, whatever its backtest says. Reviews of methodology code check fidelity to knowledge/ first and performance second. Hardware upgrades (RAM kit, more CPU cores) are the owner's later step and do not change this order.
rejected_alternatives:
  - Building the self-proposing loop before the validation gates -- refused; it ranks overfits (§43-§45).
  - Allowing the loop to modify a methodology's source framework when a backtest improves -- refused by CLAUDE.md §13 and the owner's instruction of 2026-09-26.
  - Replacing the speed stage with hardware purchases alone -- refused; the engine runs single-threaded, so more cores do not help until the software is parallel.
---

## Owner's instruction (2026-09-26)

"Nên xây theo thứ tự: engine đúng → engine nhanh → sổ thí nghiệm và các cổng kiểm định → vòng lặp tự đề xuất
và xếp hạng" -- agreed, with the added rule that the system must always follow the knowledge from the original
books and PDFs provided; it may add to them, but must not alter the framework of any methodology.

## What "extend, never alter" means in practice

| Allowed (extend) | Forbidden (alter) |
|---|---|
| New values for a project-defined threshold (e.g. a volume ratio the book leaves unquantified) | Changing a threshold or table the book states (e.g. the Spring/Upthrust typing tables, WMT Bảng 2.1/2.2) |
| Implementing an object the source defines but the engine lacks (e.g. a Mentorship 2024 object) | Redefining an existing object (what counts as an FVG, an MSS, a Spring, a SOS) |
| Additional filters, sessions, exit variants, combinations across methodologies | Removing or reordering a methodology's phases/steps, or skipping its invalidation logic |
| A new setup built from source-defined parts, cited | A setup whose logic contradicts its source, whatever its backtest |

Sources: knowledge/INDEX.md and the files it lists.
