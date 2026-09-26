//+------------------------------------------------------------------+
//| ExportOHLCV.mq5                                                    |
//| MT5 file-bridge connector for the institutional trading system.   |
//| Attach this Expert Advisor to ANY ONE chart of the instrument you |
//| want to feed the system (e.g. XAUUSD, any timeframe) -- it        |
//| exports 1W/1D/4H/1H/15m/5m candle files for that symbol regardless|
//| of which chart it's running on, refreshed on a timer and on every |
//| new bar close.                                                    |
//|                                                                     |
//| Design doc: docs/architecture/mt5-bridge.md                       |
//|                                                                     |
//| v1.03 (audit PAR-5, ADR 0006): this EA writes RAW BROKER SERVER    |
//| TIME -- no "Z", no offset arithmetic -- into                       |
//| ohlcv.<SYM>.<TF>.server.json, plus the server name and the symbol's|
//| last tick time. scripts/mt5_time.py converts it to UTC with the    |
//| IANA zone declared in docs/architecture/providers.json and writes  |
//| the ohlcv.<SYM>.<TF>.json every reader consumes. v1.02 applied     |
//| TODAY's server offset to every bar (an hour wrong across a DST     |
//| change) and stamped last_updated from the PC clock (a frozen quote |
//| stream still looked fresh). This EA no longer writes the .json.    |
//|                                                                     |
//| UNTESTED IN A REAL MT5 TERMINAL -- written from MQL5 language      |
//| knowledge, not verified by running it. Attach it, check the        |
//| Experts/Journal tab for errors, and report back anything that      |
//| needs fixing.                                                      |
//+------------------------------------------------------------------+
#property copyright "Institutional Trading System MT5 Bridge"
#property version   "1.03"

input int InpBarsToExport     = 600;  // How many recent bars to export per timeframe (>= 576 for the 6-day 15m / 48h M5 windows)
input int InpExportIntervalSec = 60;  // Seconds between timer-driven exports

string g_symbol;

//+------------------------------------------------------------------+
int OnInit()
{
   g_symbol = _Symbol;

   // TERMINAL_COMMONDATA_PATH is the reliable way to find where FILE_COMMON writes,
   // since the exact path varies by OS/broker/install and should never be hard-guessed.
   PrintFormat("ExportOHLCV v1.03: attached to %s on server %s. Common data folder = %s",
               g_symbol, AccountInfoString(ACCOUNT_SERVER), TerminalInfoString(TERMINAL_COMMONDATA_PATH));
   PrintFormat("ExportOHLCV: files will appear under that folder's \\Files\\ subdirectory, "
               "named ohlcv.%s.<TIMEFRAME>.server.json (raw server time; scripts/mt5_time.py converts them)", g_symbol);

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
   ExportOne(PERIOD_W1,  "1W");   // swing context (2 years)
   ExportOne(PERIOD_D1,  "1D");
   ExportOne(PERIOD_H4,  "4H");
   ExportOne(PERIOD_H1,  "1H");
   ExportOne(PERIOD_M15, "15m");
   ExportOne(PERIOD_M5,  "5m");   // CFD scalping window (user decision 2026-09-11: M5, not M1)
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

   // Freshness = the symbol's LAST TICK (server time), not this EA's timer. When the quote stream freezes
   // (terminal disconnected, weekend) this stops moving and the Python side reads the file as STALE.
   MqlTick tick;
   string lastQuote = "null";
   if(SymbolInfoTick(g_symbol, tick) && tick.time > 0)
      lastQuote = "\"" + IsoServer(tick.time) + "\"";

   string json = "{\n";
   json += "  \"symbol\": \"" + g_symbol + "\",\n";
   json += "  \"timeframe\": \"" + timeframeLabel + "\",\n";
   json += "  \"_source\": \"mt5_bridge_live\",\n";
   json += "  \"_time_basis\": \"server\",\n";
   json += "  \"_server\": \"" + AccountInfoString(ACCOUNT_SERVER) + "\",\n";
   json += "  \"_ea_version\": \"1.03\",\n";
   json += "  \"last_quote_server\": " + lastQuote + ",\n";
   json += "  \"_exported_at_utc\": \"" + IsoGmt(TimeGMT()) + "\",\n";
   json += "  \"_volume_caveat\": \"tick_volume, not real traded volume -- see comment in ExportOHLCV.mq5\",\n";
   json += "  \"candles\": [\n";

   // rates[0] is the most recent bar (ArraySetAsSeries true); write oldest-first
   // to match the same ordering the mock fixtures and Binance connector use.
   for(int i = copied - 1; i >= 0; i--)
   {
      json += "    {";
      json += "\"time_server\": \"" + IsoServer(rates[i].time) + "\", ";
      json += "\"open\": " + DoubleToString(rates[i].open, _Digits) + ", ";
      json += "\"high\": " + DoubleToString(rates[i].high, _Digits) + ", ";
      json += "\"low\": " + DoubleToString(rates[i].low, _Digits) + ", ";
      json += "\"close\": " + DoubleToString(rates[i].close, _Digits) + ", ";
      // CAVEAT (flag this to the reading Skill): most CFD/commodity brokers report 0 for
      // real_volume. tick_volume (number of price changes, not real traded size) is used
      // here instead -- this is the same "not real volume" limitation the Wyckoff book
      // itself warns about for Forex-style tick-based Delta proxies (knowledge/wyckoff/modern-tools.md section 7,
      // WMT p131-p132). Effort-vs-Result reads off this field are weaker evidence than genuine
      // traded volume and should be scored accordingly, not treated as equivalent to
      // Binance's real trade volume.
      json += "\"volume\": " + IntegerToString((long)rates[i].tick_volume);
      json += "}";
      if(i > 0) json += ",";
      json += "\n";
   }

   json += "  ]\n";
   json += "}\n";

   // Write a temp file, then move it over the real name, so the Python converter never reads half a file.
   string filename = "ohlcv." + g_symbol + "." + timeframeLabel + ".server.json";
   string tmpname  = filename + ".tmp";
   int handle = FileOpen(tmpname, FILE_WRITE | FILE_TXT | FILE_COMMON | FILE_ANSI);
   if(handle == INVALID_HANDLE)
   {
      PrintFormat("ExportOHLCV: FileOpen failed for %s, error=%d", tmpname, GetLastError());
      return;
   }
   FileWriteString(handle, json);
   FileClose(handle);
   if(!FileMove(tmpname, FILE_COMMON, filename, FILE_REWRITE | FILE_COMMON))
      PrintFormat("ExportOHLCV: FileMove %s -> %s failed, error=%d", tmpname, filename, GetLastError());
}

//+------------------------------------------------------------------+
// Bar times from CopyRates and tick times are BROKER SERVER time. They are written exactly as the server
// reports them, with NO "Z": the offset in force for a past bar depends on daylight saving, which MQL5 cannot
// report, so the conversion happens in scripts/mt5_time.py with the IANA zone the provider registry declares.
string IsoServer(datetime t)
{
   MqlDateTime dt;
   TimeToStruct(t, dt);
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02d", dt.year, dt.mon, dt.day, dt.hour, dt.min, dt.sec);
}

// TimeGMT() comes from the PC clock: recorded as a diagnostic heartbeat only, never as freshness.
string IsoGmt(datetime t)
{
   MqlDateTime dt;
   TimeToStruct(t, dt);
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02dZ", dt.year, dt.mon, dt.day, dt.hour, dt.min, dt.sec);
}
