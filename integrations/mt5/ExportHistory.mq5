//+------------------------------------------------------------------+
//| ExportHistory.mq5 — ONE-SHOT deep-history export for backtests    |
//|                                                                   |
//| Companion to ExportOHLCV.mq5, and deliberately NOT the same file. |
//| ExportOHLCV is an EA: it runs on a timer, exports ~600 recent     |
//| bars, and feeds data/live/mt5-bridge/ — the LIVE path, where      |
//| freshness is checked. This is a SCRIPT: you run it by hand, once, |
//| it exports as much history as the terminal holds, and it writes   |
//| different filenames so it can never overwrite the live feed.      |
//|                                                                   |
//| CLAUDE.md §23.1: CFD backtests currently read Yahoo front-month   |
//| FUTURES (GC=F, SI=F, CL=F, BZ=F), not the CFD the system actually |
//| trades. Different session hours, real contract volume instead of  |
//| tick volume, a futures basis and roll gaps. This script exists to |
//| replace that with the broker's own CFD history.                   |
//|                                                                   |
//| TIMESTAMPS ARE RAW SERVER TIME AND ARE NOT CONVERTED HERE.        |
//| ExportOHLCV converts with `TimeCurrent() - TimeGMT()` — the       |
//| CURRENT offset — which is right for a 600-bar window and WRONG    |
//| for years of history: most brokers run UTC+2 in winter and UTC+3  |
//| in summer, so today's offset applied to a bar from six months ago |
//| shifts it by an hour. MQL5 cannot tell you the offset that was in |
//| force for a historical bar. So this writes the server's own       |
//| numbers plus everything needed to convert them properly on the    |
//| Python side, where real tzdata is available (the same machinery   |
//| docs/architecture/sessions.json already uses for DST).            |
//+------------------------------------------------------------------+
#property copyright "Institutional Trading System MT5 Bridge"
#property version   "1.01"
#property script_show_inputs

// v1.01 (2026-10-01, UNTESTED -- written without MetaEditor/MT5; compile it and read the Experts log before
// trusting it): BATCH MODE. InpSymbols names the symbols to export in one run; EMPTY keeps the v1.00 behaviour
// exactly (the chart's own symbol). Needed for the FTMO symbol-universe import
// (docs/architecture/mt5-ftmo-symbol-universe-export.md): one script run per chart does not scale to ~100 symbols.
// The file format and file names are unchanged.

input string InpSymbols  = "";      // v1.01: comma list, e.g. "EURUSD,US500.cash,BTCUSD". EMPTY = this chart's symbol only (v1.00)
input int  InpSyncWaitMs = 5000;    // v1.01: per symbol+timeframe, max wait for the terminal to synchronise the series before copying
input int  InpBars       = 5000000; // Max bars per timeframe. CopyRates returns what the terminal HAS (bounded by Tools > Options > Charts > Max bars in chart -- set it to Unlimited for deep M1/M5).
input bool InpW1         = true;
input bool InpD1         = true;
input bool InpH4         = true;
input bool InpH1         = true;
input bool InpM15        = true;
input bool InpM30        = true;
input bool InpM5         = true;    // owner 2026-09-28: fund setups are searched on 1m/5m/15m/30m
input bool InpM1         = true;    // large: ~2.5M bars / ~300 MB per symbol for 2019->now; the importer gzips it per year

//+------------------------------------------------------------------+
void OnStart()
{
   PrintFormat("ExportHistory: chart symbol=%s  common folder=%s",
               _Symbol, TerminalInfoString(TERMINAL_COMMONDATA_PATH));
   PrintFormat("ExportHistory: server=%s  current server-GMT offset=%d sec",
               AccountInfoString(ACCOUNT_SERVER), (int)(TimeCurrent() - TimeGMT()));

   string syms[];
   int n = 0;
   if(StringLen(InpSymbols) > 0) n = StringSplit(InpSymbols, ',', syms);
   if(n <= 0) { ArrayResize(syms, 1); syms[0] = _Symbol; n = 1; }       // v1.00 behaviour

   for(int i = 0; i < n; i++)
   {
      string s = syms[i];
      StringTrimLeft(s); StringTrimRight(s);
      if(s == "") continue;
      if(s != _Symbol && !SymbolSelect(s, true))
      {
         PrintFormat("ExportHistory: %s not available on this server -- skipped", s);
         continue;
      }
      PrintFormat("ExportHistory: [%d/%d] %s", i + 1, n, s);
      if(InpW1)  ExportOne(s, PERIOD_W1,  "1W");
      if(InpD1)  ExportOne(s, PERIOD_D1,  "1D");
      if(InpH4)  ExportOne(s, PERIOD_H4,  "4H");
      if(InpH1)  ExportOne(s, PERIOD_H1,  "1H");
      if(InpM15) ExportOne(s, PERIOD_M15, "15m");
      if(InpM30) ExportOne(s, PERIOD_M30, "30m");
      if(InpM5)  ExportOne(s, PERIOD_M5,  "5m");
      if(InpM1)  ExportOne(s, PERIOD_M1,  "1m");
   }

   Print("ExportHistory: done. Copy history.*.json out of the Common\\Files folder, "
         "then run scripts/import-mt5-history.py in the repo.");
}

// v1.01: ask for one bar first (that is what starts the terminal's download of this symbol+timeframe) and wait
// for SERIES_SYNCHRONIZED, so a symbol that was never opened on a chart is not exported from an empty cache.
// It does not guarantee full depth: the receipt line printed by ExportOne is still the proof.
void Prime(string sym, ENUM_TIMEFRAMES tf)
{
   MqlRates one[];
   CopyRates(sym, tf, 0, 1, one);
   int waited = 0;
   while(!(bool)SeriesInfoInteger(sym, tf, SERIES_SYNCHRONIZED) && waited < InpSyncWaitMs)
   {
      Sleep(100);
      waited += 100;
   }
}

//+------------------------------------------------------------------+
void ExportOne(string sym, ENUM_TIMEFRAMES tf, string tfLabel)
{
   Prime(sym, tf);
   int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   int copied = CopyRates(sym, tf, 0, InpBars, rates);
   if(copied <= 0)
   {
      PrintFormat("ExportHistory: CopyRates failed for %s %s, error=%d. "
                  "Open that chart, press Home until the bar count stops growing, then re-run.",
                  sym, tfLabel, GetLastError());
      return;
   }

   string filename = "history." + sym + "." + tfLabel + ".json";
   int h = FileOpen(filename, FILE_WRITE | FILE_TXT | FILE_COMMON | FILE_ANSI);
   if(h == INVALID_HANDLE)
   {
      PrintFormat("ExportHistory: FileOpen failed for %s, error=%d", filename, GetLastError());
      return;
   }

   // Written incrementally rather than built as one string: concatenating tens of thousands of
   // rows in MQL5 is quadratic and will appear to hang the terminal.
   FileWriteString(h, "{\n");
   FileWriteString(h, "  \"symbol\": \"" + sym + "\",\n");
   FileWriteString(h, "  \"timeframe\": \"" + tfLabel + "\",\n");
   FileWriteString(h, "  \"_source\": \"mt5_bridge_history\",\n");
   FileWriteString(h, "  \"_time_basis\": \"BROKER SERVER TIME, NOT UTC -- convert with the zone named in "
                      "providers.json mt5_bridge.server_timezone; see ExportHistory.mq5 header\",\n");
   FileWriteString(h, "  \"_server\": \"" + AccountInfoString(ACCOUNT_SERVER) + "\",\n");
   FileWriteString(h, "  \"_server_utc_offset_sec_now\": "
                      + IntegerToString((long)(TimeCurrent() - TimeGMT())) + ",\n");
   FileWriteString(h, "  \"_exported_at_utc\": \"" + IsoGmt(TimeGMT()) + "\",\n");
   FileWriteString(h, "  \"_bars\": " + IntegerToString(copied) + ",\n");
   FileWriteString(h, "  \"_volume_caveat\": \"tick_volume, not real traded volume\",\n");
   FileWriteString(h, "  \"candles\": [\n");

   for(int i = copied - 1; i >= 0; i--)          // oldest first, matching every other feed in the repo
   {
      string row = "    {\"time\": \"" + IsoServer(rates[i].time) + "\", "
                 + "\"open\": "   + DoubleToString(rates[i].open,  digits) + ", "
                 + "\"high\": "   + DoubleToString(rates[i].high,  digits) + ", "
                 + "\"low\": "    + DoubleToString(rates[i].low,   digits) + ", "
                 + "\"close\": "  + DoubleToString(rates[i].close, digits) + ", "
                 + "\"volume\": " + IntegerToString((long)rates[i].tick_volume) + "}";
      if(i > 0) row += ",";
      FileWriteString(h, row + "\n");
   }

   FileWriteString(h, "  ]\n}\n");
   FileClose(h);

   PrintFormat("ExportHistory: %s %s -> %d bars, %s .. %s (server time)",
               sym, tfLabel, copied, IsoServer(rates[copied - 1].time), IsoServer(rates[0].time));
}

//+------------------------------------------------------------------+
// Server time, formatted, with NO offset applied and NO trailing Z -- the missing Z is the point:
// a Z would be a claim about UTC this script is not in a position to make for a historical bar.
string IsoServer(datetime t)
{
   MqlDateTime dt;
   TimeToStruct(t, dt);
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02d", dt.year, dt.mon, dt.day, dt.hour, dt.min, dt.sec);
}

// The export timestamp IS genuine UTC -- TimeGMT() is GMT by definition -- so this one keeps its Z.
string IsoGmt(datetime t)
{
   MqlDateTime dt;
   TimeToStruct(t, dt);
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02dZ", dt.year, dt.mon, dt.day, dt.hour, dt.min, dt.sec);
}
