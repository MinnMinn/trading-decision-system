---
title: An account trades one market through one broker and runs one Trading System version at a time; switching appends an assignment, and the many-to-many mandate table is removed
date: 2026-10-03
status: ACCEPTED
context: Until 2026-10-03 the platform was single-account in practice. The forward demo read one side file (docs/architecture/fvg-demo.json), wrote one state file and one log, and drove one bridge folder. strategy-runner.py could bind an account (--account), but the id was an account-profile id, which mixed up a rule set with the account using it. The 2026-09-19 plan added a many-to-many mandate table (account x setup x market) for renting methods to clients; it was never filled and never wired into a tick. The owner asked for several accounts, each on one market, able to switch between methods and setups, and approved the design document "Hạ tầng đa tài khoản" on 2026-10-03.
problem: How to run several accounts with separate capital and fund rules, switch what an account trades without losing which version took which trade, and keep every safety invariant (risk ceiling, allowlist, demo-only, PIT, required dependencies) checkable from configuration.
decision: |
  1. docs/architecture/accounts.json is the account registry, read and validated by scripts/registry.py. An account declares one market (instruments.json), one broker (an execution provider in providers.json), one account profile (account-profiles.json, the fund's rules), its environment, real_money (must be false), and, on MT5, its bridge channel.
  2. Assignments bind an account to a Trading System version. They form an append-only history: at most one is live per account (effective_from <= t < ended_at), and a switch ends the live row and appends a new one, effective at the next 5-minute slot. scripts/accounts.py switch writes a switch only after the whole new registry validates.
  3. A Trading System may be a BOOK, a versioned list of mechanical setup components (trading-systems.json `books`). Its setups are declared in docs/architecture/setups.json, with per-instrument evidence status. An APPROVED or RETIRED version carries a content digest, and editing it in place makes the registry refuse to load (§47).
  4. A switch's open_position_policy decides what happens to positions the previous assignment opened. DRAIN (the default) keeps them to their own exits; CLOSE closes them at the next tick; BLOCK refuses the switch while any is open. Every order, position and log line carries account, assignment and Trading System version.
  5. scripts/fvg_demo.py runs per account from the registry; the side file is removed. forward_cycle.py ticks every account in the order dispatch_order.py derives for the cycle. strategy-runner.py --account takes a registry account: only that account's venue, its profile, and the setups of the Trading System it is assigned.
  6. mandates.json and scripts/mandates.py are removed.
alternatives:
  - Keep the many-to-many mandate table (one account runs several methods on several markets at once).
  - Put method_id / setup_id columns directly on the account row.
  - A database (SQLite/Postgres) for configuration and runtime state now.
  - A separate risk-model table referenced by Trading System versions.
chosen_approach: Account registry plus append-only assignments to immutable Trading System versions, as JSON in git validated at import; runtime state as per-account files under data/live/accounts/<id>/.
reason: The owner rejected several methods on several markets in one account (2026-10-03) because the account's capital and its daily-loss rule cannot then be budgeted per method. One live version per account keeps sizing, fund rules and attribution unambiguous. Columns on the account cannot express a book (demo v2 is four components) and would lose which version took which trade after a switch. JSON in git makes every configuration change a reviewed diff (§41, §47) and a reproducible snapshot (§11); with fewer than 20 accounts and one writer per account, a database adds no capability (§57). Risk lives inside the version so that a risk change cannot bypass a version bump.
consequences: |
  Switching an account is a registry change that must be committed: the file in git is the record of what each account ran. Demo accounts switch through the CLI; a real-money account would switch only through a reviewed PR, and none is enabled.

  The demo's state and log move once from data/live/forward/ into data/live/accounts/ftmo-demo-01/ on the first tick (migrate_legacy). The initial balance the throttle keys off is carried over.

  A second MT5 account needs its own terminal and bridge channel, and every MT5 account then needs login_ref so that a terminal on the wrong login refuses.

  strategy-runner.py house mode (no --account) is unchanged and still resolves profiles with account_profile.for_venue(). That one-account-per-venue path is retired when the crypto pilot gets a registry account.

  Revisit the database choice above 20 accounts, or when cross-account queries or concurrent writers appear.
rejected_alternatives:
  - The many-to-many mandate table -- rejected by the owner 2026-10-03; several methods sharing one account's capital and daily-loss rule cannot be budgeted per method, and the table was never wired into a tick.
  - method_id / setup_id columns on the account -- rejected; a book is several components, and a mutable column loses which version opened a trade once it changes.
  - A database now -- rejected for this phase (§57); JSON in git gives review, history and snapshots, and the schema maps one-to-one to tables when the scale or query needs appear.
  - A separate risk-model table -- rejected; a risk change must be a Trading System version change, and a shared table would let one edit change several versions' behaviour without a version bump.
---

Design document (owner-approved 2026-10-03): "Hạ tầng đa tài khoản — Thiết kế để duyệt" (Claude Docs). Reader and
validator: scripts/registry.py; CLI: scripts/accounts.py; tests: scripts/tests/test_registry.py,
scripts/tests/test_fvg_demo.py (Registry, Switch, TerminalIdentity, Migration).
