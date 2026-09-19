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
#property version   "1.00"
#property script_show_inputs

input int  InpBars       = 200000;  // Max bars per timeframe. CopyRates returns what the terminal HAS; ask for more than you expect.
input bool InpW1         = true;
input bool InpD1         = true;
input bool InpH4         = true;
input bool InpH1         = true;
input bool InpM15        = true;
input bool InpM5         = false;   // M5 over years is large and most CFD brokers do not keep it. Turn on only if you need it.

//+------------------------------------------------------------------+
void OnStart()
{
   PrintFormat("ExportHistory: symbol=%s  common folder=%s",
               _Symbol, TerminalInfoString(TERMINAL_COMMONDATA_PATH));
   PrintFormat("ExportHistory: server=%s  current server-GMT offset=%d sec",
               AccountInfoString(ACCOUNT_SERVER), (int)(TimeCurrent() - TimeGMT()));

   if(InpW1)  ExportOne(PERIOD_W1,  "1W");
   if(InpD1)  ExportOne(PERIOD_D1,  "1D");
   if(InpH4)  ExportOne(PERIOD_H4,  "4H");
   if(InpH1)  ExportOne(PERIOD_H1,  "1H");
   if(InpM15) ExportOne(PERIOD_M15, "15m");
   if(InpM5)  ExportOne(PERIOD_M5,  "5m");

   Print("ExportHistory: done. Copy history.*.json out of the Common\\Files folder, "
         "then run scripts/import-mt5-history.py in the repo.");
}

//+------------------------------------------------------------------+
void ExportOne(ENUM_TIMEFRAMES tf, string tfLabel)
{
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   int copied = CopyRates(_Symbol, tf, 0, InpBars, rates);
   if(copied <= 0)
   {
      PrintFormat("ExportHistory: CopyRates failed for %s %s, error=%d. "
                  "Open that chart, press Home until the bar count stops growing, then re-run.",
                  _Symbol, tfLabel, GetLastError());
      return;
   }

   string filename = "history." + _Symbol + "." + tfLabel + ".json";
   int h = FileOpen(filename, FILE_WRITE | FILE_TXT | FILE_COMMON | FILE_ANSI);
   if(h == INVALID_HANDLE)
   {
      PrintFormat("ExportHistory: FileOpen failed for %s, error=%d", filename, GetLastError());
      return;
   }

   // Written incrementally rather than built as one string: concatenating tens of thousands of
   // rows in MQL5 is quadratic and will appear to hang the terminal.
   FileWriteString(h, "{\n");
   FileWriteString(h, "  \"symbol\": \"" + _Symbol + "\",\n");
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
                 + "\"open\": "   + DoubleToString(rates[i].open,  _Digits) + ", "
                 + "\"high\": "   + DoubleToString(rates[i].high,  _Digits) + ", "
                 + "\"low\": "    + DoubleToString(rates[i].low,   _Digits) + ", "
                 + "\"close\": "  + DoubleToString(rates[i].close, _Digits) + ", "
                 + "\"volume\": " + IntegerToString((long)rates[i].tick_volume) + "}";
      if(i > 0) row += ",";
      FileWriteString(h, row + "\n");
   }

   FileWriteString(h, "  ]\n}\n");
   FileClose(h);

   PrintFormat("ExportHistory: %s %s -> %d bars, %s .. %s (server time)",
               _Symbol, tfLabel, copied, IsoServer(rates[copied - 1].time), IsoServer(rates[0].time));
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
