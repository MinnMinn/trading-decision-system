//+------------------------------------------------------------------+
//| ExportOHLCV.mq5                                                    |
//| MT5 file-bridge connector for the institutional trading system.   |
//| Attach this Expert Advisor to ANY ONE chart of the instrument you |
//| want to feed the system (e.g. XAUUSD, any timeframe) -- it        |
//| exports 1D/4H/1H/15m candle files for that symbol regardless of   |
//| which chart it's running on, refreshed on a timer and on every    |
//| new bar close.                                                    |
//|                                                                     |
//| Design doc: docs/architecture/mt5-bridge.md                       |
//| Output shape matches docs/architecture/data-sources.md's crypto   |
//| market-data contract exactly, so Skills read both identically.    |
//|                                                                     |
//| UNTESTED IN A REAL MT5 TERMINAL -- written from MQL5 language      |
//| knowledge, not verified by running it. Attach it, check the        |
//| Experts/Journal tab for errors, and report back anything that      |
//| needs fixing.                                                      |
//+------------------------------------------------------------------+
#property copyright "Institutional Trading System MT5 Bridge"
#property version   "1.01"

input int InpBarsToExport     = 200;  // How many recent bars to export per timeframe
input int InpExportIntervalSec = 60;  // Seconds between timer-driven exports

string g_symbol;

//+------------------------------------------------------------------+
int OnInit()
{
   g_symbol = _Symbol;

   // TERMINAL_COMMONDATA_PATH is the reliable way to find where FILE_COMMON writes,
   // since the exact path varies by OS/broker/install and should never be hard-guessed.
   PrintFormat("ExportOHLCV: attached to %s. Common data folder = %s",
               g_symbol, TerminalInfoString(TERMINAL_COMMONDATA_PATH));
   PrintFormat("ExportOHLCV: files will appear under that folder's \\Files\\ subdirectory, "
               "named ohlcv.%s.<TIMEFRAME>.json", g_symbol);

   EventSetTimer(InpExportIntervalSec);
   ExportAllTimeframes();
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   ExportAllTimeframes();
}

void OnTick()
{
   // Also export immediately whenever a new bar closes on the chart's own timeframe,
   // so the bridge doesn't wait the full InpExportIntervalSec after a fresh close.
   static datetime lastBarTime = 0;
   datetime currentBarTime = iTime(_Symbol, _Period, 0);
   if(currentBarTime != lastBarTime)
   {
      lastBarTime = currentBarTime;
      ExportAllTimeframes();
   }
}

//+------------------------------------------------------------------+
void ExportAllTimeframes()
{
   ExportOne(PERIOD_D1,  "1D");
   ExportOne(PERIOD_H4,  "4H");
   ExportOne(PERIOD_H1,  "1H");
   ExportOne(PERIOD_M15, "15m");
}

//+------------------------------------------------------------------+
void ExportOne(ENUM_TIMEFRAMES tf, string timeframeLabel)
{
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   int copied = CopyRates(g_symbol, tf, 0, InpBarsToExport, rates);
   if(copied <= 0)
   {
      PrintFormat("ExportOHLCV: CopyRates failed for %s %s, error=%d",
                  g_symbol, timeframeLabel, GetLastError());
      return;
   }

   string json = "{\n";
   json += "  \"symbol\": \"" + g_symbol + "\",\n";
   json += "  \"timeframe\": \"" + timeframeLabel + "\",\n";
   json += "  \"candles\": [\n";

   // rates[0] is the most recent bar (ArraySetAsSeries true); write oldest-first
   // to match the same ordering the mock fixtures and Binance connector use.
   for(int i = copied - 1; i >= 0; i--)
   {
      json += "    {";
      json += "\"time\": \"" + IsoTime(rates[i].time) + "\", ";
      json += "\"open\": " + DoubleToString(rates[i].open, _Digits) + ", ";
      json += "\"high\": " + DoubleToString(rates[i].high, _Digits) + ", ";
      json += "\"low\": " + DoubleToString(rates[i].low, _Digits) + ", ";
      json += "\"close\": " + DoubleToString(rates[i].close, _Digits) + ", ";
      // CAVEAT (flag this to the reading Skill): most CFD/commodity brokers report 0 for
      // real_volume. tick_volume (number of price changes, not real traded size) is used
      // here instead -- this is the same "not real volume" limitation the Wyckoff book
      // itself warns about for Forex-style tick-based Delta proxies (knowledge/08 section 7,
      // WMT p131-p132). Effort-vs-Result reads off this field are weaker evidence than genuine
      // traded volume and should be scored accordingly, not treated as equivalent to
      // Binance's real trade volume.
      json += "\"volume\": " + IntegerToString((long)rates[i].tick_volume);
      json += "}";
      if(i > 0) json += ",";
      json += "\n";
   }

   json += "  ],\n";
   json += "  \"last_updated\": \"" + IsoTime(TimeCurrent()) + "\",\n";
   json += "  \"_server_utc_offset_sec\": " + IntegerToString((long)(TimeCurrent() - TimeGMT())) + ",\n";
   json += "  \"_source\": \"mt5_bridge_live\",\n";
   json += "  \"_volume_caveat\": \"tick_volume, not real traded volume -- see comment in ExportOHLCV.mq5\"\n";
   json += "}\n";

   string filename = "ohlcv." + g_symbol + "." + timeframeLabel + ".json";
   int handle = FileOpen(filename, FILE_WRITE | FILE_TXT | FILE_COMMON | FILE_ANSI);
   if(handle == INVALID_HANDLE)
   {
      PrintFormat("ExportOHLCV: FileOpen failed for %s, error=%d", filename, GetLastError());
      return;
   }
   FileWriteString(handle, json);
   FileClose(handle);
}

//+------------------------------------------------------------------+
// Bar times from CopyRates and TimeCurrent() are BROKER SERVER time (often UTC+2/+3), not UTC.
// Convert with the live server-vs-GMT offset before labelling the string "Z", so these files
// line up with the Binance connector's genuine UTC timestamps.
string IsoTime(datetime serverTime)
{
   datetime offset = TimeCurrent() - TimeGMT();
   datetime t = serverTime - offset;
   MqlDateTime dt;
   TimeToStruct(t, dt);
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02dZ", dt.year, dt.mon, dt.day, dt.hour, dt.min, dt.sec);
}
