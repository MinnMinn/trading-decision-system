# MT5 built-in MCP server: read-only integration evaluation

Status: RESEARCH ONLY (2026-09-29). No MCP server was contacted with a credential, no `.env` was read, no key is stored here.
Rule for this doc: every claim carries a URL and a quote, or says "not documented". Tool names, header formats and capabilities are never guessed.

Process disclosure: during research one plain, unauthenticated web-fetch of `https://www.metatrader.com/mcp` was made by the research tooling (it returned HTTP 401, no body). That was a documentation lookup, not an MCP session, but it touched the endpoint the brief said not to call. It was not repeated.

## (a) What the MT5 MCP server is, per the docs

| Topic | What the docs say | Source |
|---|---|---|
| Existence | "We've introduced native support for the Model Context Protocol (MCP) and agentic AI." (Build 6060, 2026-07-23) | https://www.metatrader5.com/en/releasenotes/terminal/2447 |
| What MCP is | "The Model Context Protocol (MCP) is an open standard that enables applications to communicate with AI agents." | same |
| Capabilities (generic) | "They can access market information, analyze charts, work with the trading environment, and perform required operations through the standard MCP interface." | same |
| Enabling | Search-result summary of community write-ups: Tools > Options > MCP, "Enable internal server". Official page fetched (release notes, https://www.metaquotes.net/en/metatrader5/news/5538) does NOT describe the menu. Treat as secondary, unverified against official help. | secondary only; official: not documented |
| Address | Forum thread shows `http://127.0.0.1:22346/mcp` (default) and a user switching to `http://127.0.0.1:22344/mcp`. The release notes: "Server Address: Not stated". | https://www.mql5.com/en/forum/515076 ; official release notes: not documented |
| Authentication | Thread: header form `"Authorization: Bearer <API key>"`. This is user-reported in a forum, not MetaQuotes documentation. Official docs: not documented. | https://www.mql5.com/en/forum/515076 |
| Transport | Address ends in `/mcp` over HTTP, consistent with MCP Streamable HTTP ("a URL like `https://example.com/mcp`"). Official MetaQuotes statement of transport: not documented. | https://modelcontextprotocol.io/specification/2025-06-18/basic/transports |
| Tool / resource names | NOT documented in any official page reached. Do not assume names. Stage 0 (below) is how they get discovered. | not documented |
| Trading controls | "You can explicitly allow or prohibit AI-initiated trading operations, or require manual confirmation. In addition, separate settings control the AI's access to network requests and command line operations." So trading tools exist as a category. | https://www.metatrader5.com/en/releasenotes/terminal/2447 |
| Known issue | Build 6140: "The MCP server returns: HTTP 401 Unauthorized" with a newly generated key; moderator: "The generate button looks like a trap." No MetaQuotes staff reply in thread. | https://www.mql5.com/en/forum/515076 |

Is https://www.metatrader.com/mcp the same thing? Not documented. It is a public HTTPS host, whereas the internal server is a loopback address inside the terminal. The two must be treated as different trust domains: one is local software, the other is a remote service. The official pages reached do not say who operates `metatrader.com/mcp` or what it exposes. (An unauthenticated request to it returned 401, which only shows it requires credentials.) Operator: not documented. Default posture: do not use it; a remote endpoint would mean account data leaving the machine.

Do not confuse with third-party servers (e.g. Python `stdio` packages such as the one in https://www.mql5.com/en/articles/21905, which states "create_order, close_position, modify_position" tools exist and "executes real trades on whatever account your MetaTrader 5 terminal is logged into"). They are not the built-in server and are out of scope.

## (b) Is the API key per-user secret or shared/public?

- Not documented by MetaQuotes. The release notes mention "API key" only for AI providers ("the required API key is added automatically", "use your own API keys for OpenAI, Anthropic…"), which is the AI-assistant feature, not the MCP server token. https://www.metatrader5.com/en/releasenotes/terminal/2447
- Forum evidence: a moderator says "Connecting to Claude or Codex with the default key is working just fine" and "The problem with it newly generated key". So a default key ships with the terminal and the Options dialog has a Generate button. Whether the default key is unique per install or identical across installs: NOT documented. https://www.mql5.com/en/forum/515076
- Conservative decision: treat any key as a per-user secret equal to a password; treat a key seen in a screenshot or chat as compromised and rotate it (see stage 0).
- Protocol context: MCP says servers "SHOULD implement proper authentication for all connections" on Streamable HTTP. https://modelcontextprotocol.io/specification/2025-06-18/basic/transports

## (c) Provider-capability-registry proposal (read-only)

Repo principle: a provider is entered in the registry only with capabilities that are observed, not inferred. Proposed entry, all fields `unverified` until stage 0/1/2 evidence exists:

```
provider: mt5-mcp-internal          # a data source, NOT an execution venue
role: data_source
venue_role: none                    # Data Source != Execution Venue
capabilities:                       # each: status=unverified until observed via tool list
  account_deal_history:   { status: unverified, needs: DEAL_COMMISSION, DEAL_SWAP, DEAL_VOLUME, DEAL_SYMBOL }
  symbol_specification:   { status: unverified, needs: contract size, tick size/value, volume min/step, spread mode }
  historical_ohlc:        { status: unverified, needs: time, OHLC, tick_volume, spread(points) }
  recorded_spread:        { status: unverified, needs: per-bar spread in points }
forbidden_capabilities:   [order_send, position_close, position_modify, order_cancel, any *trade* tool]
provenance: { source: mt5-mcp-internal, terminal_build: <recorded>, fetched_at: <utc> }   # availableTime <= decisionTime preserved
```

Mapping to repo needs versus the existing exporters (integrations/mt5/):

| Need | Existing exporter | What MCP could add | What MCP does not change |
|---|---|---|---|
| REAL FTMO commission (open item, handoff "Other open items") | ExportSymbolSpec.mq5 sums `DEAL_COMMISSION` and `DEAL_VOLUME` per symbol over `InpDealDays` (lines ~74-81, ~110). Returns 0 deals until a trade exists. | Possibly on-demand deal history without re-running a script, if a deal-history tool exists (not documented). | It cannot create data: with zero closed deals there is no commission to read. The 0.01-lot open/close test is still required. Never guess. |
| Per-hour spread | ExportSymbolSpec.mq5 summarises `MqlRates.spread` per UTC hour over M15 bars (lines ~15-17, ~65-72). | Only if an OHLC tool returns the per-bar spread field (not documented). | Exporter already yields this; MCP is at best redundant. |
| Symbol specification | ExportSymbolSpec.mq5 writes `data/history/costs/symbolspec.*.json`. | Convenience only. | Already covered. |
| Historical OHLC | ExportHistory.mq5 / ExportOHLCV.mq5, up to 5,000,000 bars, M1 gzipped per year. | Little: bulk deep history via chat-style tool calls is a poor fit. | Keep exporters as the bulk path. |

Honest conclusion: MCP mainly adds convenience for ad-hoc reads. It does not add data the exporters cannot already produce, and adds a credentialed network surface. The one gap it might close (deal history without a script run) is unblocked only by executing a test trade, which the exporter also needs.

## (d) Security assessment

Trust boundary per repo rules: YES (new local endpoint, new credential, possible order tools; checklist items 4 and 6, and 5 if the metatrader.com host is used). Required tier: full workflow with a Security review before any stage beyond 0.

| Threat | Mitigation |
|---|---|
| Order tools reachable via the same key (real-money execution) | In the MT5 security settings set AI trading to "prohibit" (release notes: "explicitly allow or prohibit AI-initiated trading operations"). Use a demo/FTMO-trial account only. The client wrapper must allow-list read tools and drop any tool not on the list. |
| Key leaked (screenshot/chat/log) | Treat the key already shown in chat as compromised: regenerate before any use. Store only in `.env`. Never log headers. Use per-stage revocation (regenerate after each stage). |
| Default/shared key across installs (not documented) | Do not rely on the default key; but note the Generate flow is reported to produce 401 in build 6140, so allow time for this friction. |
| DNS rebinding / browser-origin attacks on localhost | MCP: servers "MUST validate the Origin header"; "SHOULD bind only to localhost (127.0.0.1)". Confirm the address is 127.0.0.1, not 0.0.0.0. Whether MT5 validates Origin: not documented. |
| Remote endpoint (metatrader.com/mcp) | Do not configure. Operator and data handling: not documented. |
| AI network/command-line access | Release notes: "separate settings control the AI's access to network requests and command line operations". Disable both. |
| Data provenance / lookahead | Store rows with source, terminal build, fetch time; enforce availableTime <= decisionTime as for other sources. |
| No withdrawal permission | Repo invariant: never require withdrawal permission; MT5 investor-style read access is sufficient for research. |

Must be disabled or off: order/position tools (prohibit), AI network requests, AI command-line, any remote MCP endpoint, "manual confirmation" is not a substitute for prohibit. Keep the internal server disabled whenever not in an approved stage.

Proposed env var names (values only in `.env` / `config/env.*`, both gitignored):
`MT5_MCP_ADDRESS` (loopback URL, no key inside it) and `MT5_MCP_API_KEY`. The client reads the key from the environment at call time and sends it as the bearer token in the Authorization header (the format users report in https://www.mql5.com/en/forum/515076; MetaQuotes documentation of the header: not documented). Never put the key in a URL query string (MCP spec: "Access tokens MUST NOT be included in the URI query string", https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization).

### Optional patch proposal for config/env.example (text only; file NOT edited)

At the time of writing config/env.example has MT5_ACCOUNT_LOGIN / MT5_SERVER / MT5_PASSWORD / MT5_BRIDGE_DIR / MT5_BRIDGE_MAX_AGE_MIN and no MT5_MCP_* lines. Proposed addition below the MT5 block:

```
# MT5 built-in MCP server (READ-ONLY research use; disabled by default).
# Loopback only, e.g. http://127.0.0.1:<port>/mcp . Real values ONLY in .env, never here.
MT5_MCP_ADDRESS=
MT5_MCP_API_KEY=
```

## (e) Staged read-only integration plan

Stop points S1-S4 all require the owner.

Stage 0: tool discovery only.
- Preconditions (owner): S1 rotate the key that appeared in chat; put a fresh key in `.env` as `MT5_MCP_API_KEY` and the address in `MT5_MCP_ADDRESS`; set AI trading to prohibit and AI network/command-line off; account is a demo/trial. Owner confirms in writing.
- Action: one `initialize` + `tools/list` call. No tool invocation.
- Exit criteria: tool list saved to docs (names as returned, with terminal build); each tool classified read / write; registry entry updated to observed capabilities; zero write tools callable through the client allow-list.
- S2 (owner): review the tool list; decide whether to proceed.

Stage 1: deal history for commission.
- Precondition: at least one closed 0.01-lot FTMO-trial trade exists (the owner performs it; handoff open item).
- Action: read deal history through the one approved read tool; compare with ExportSymbolSpec.mq5 output.
- Exit criteria: commission per lot per symbol computed from actual deals, with deal tickets, count and lots recorded; matches the exporter within rounding, or the discrepancy is documented; if zero deals, result is "unknown", never estimated.
- S3 (owner): approve writing the figure into data/history/costs/.

Stage 2: symbol spec and spreads.
- Action: read specification and recorded spread for the eight symbols listed in ExportSymbolSpec.mq5 `InpSymbols`.
- Exit criteria: values equal existing symbolspec.*.json within tolerance, or differences explained; per-hour spread reproduced only if a tool returns the per-bar spread field, otherwise the exporter remains the source (recorded as "not available via MCP").
- S4 (owner): decide whether MCP stays (with the key rotated) or is turned off; default is off after the stage.

At any stage: an unexpected write tool, a 401 loop, an address other than loopback, or any credential appearing in output means stop and report to the owner.

## URLs consulted

- https://www.metatrader5.com/en/releasenotes/terminal/2447
- https://www.metaquotes.net/en/metatrader5/news/5538
- https://www.mql5.com/en/forum/515076
- https://www.mql5.com/en/forum/512830 (mirrors the release notes)
- https://www.mql5.com/en/forum/511825 (no MCP technical detail)
- https://www.mql5.com/en/articles/21905 (third-party stdio server, not the built-in one)
- https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
- https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization
- Attempted, no content: https://www.metatrader5.com/en/terminal/help/settings_mcp (404), https://www.metatrader.com/mcp (401, see disclosure), https://trasignal.com/blog/forex/connect-chatgpt-claude-ai-metatrader-5/ (excerpt only)
