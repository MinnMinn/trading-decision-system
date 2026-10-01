//+------------------------------------------------------------------+
//| ExportSymbolList.mq5 -- ONE-SHOT inventory of EVERY symbol on the |
//| account, so history depth is known BEFORE any history is exported.|
//|                                                                   |
//| STATUS: UNTESTED. Written without access to MetaEditor/MT5 and    |
//| never compiled. Compile it in MetaEditor (F7) and fix whatever the|
//| compiler reports before trusting a single line. Every function it  |
//| uses is a documented MQL5 call (SymbolsTotal, SymbolName,          |
//| SymbolInfo*, SymbolInfoSessionTrade, SeriesInfoInteger, FileOpen); |
//| the structure copies ExportSymbolSpec.mq5 / ExportHistory.mq5.     |
//|                                                                   |
//| Why: the owner decision of 2026-10-01 is to add the full FTMO CFD  |
//| universe and the FTMO crypto CFDs to the fund search. Before ~100  |
//| symbols x 8 timeframes are exported (M1 alone is ~300 MB per       |
//| symbol), the pipeline needs to know WHAT exists, in which class    |
//| (SYMBOL_PATH), with which contract terms, and how deep each of     |
//| M1/M5/M15 goes. scripts/import-ftmo-symbols.py reads this file and |
//| turns it into a validation report plus proposed registry additions.|
//|                                                                   |
//| Writes Common\Files\symbollist.<server>.json (one file, all        |
//| symbols). Read-only: it places no orders and changes no settings.  |
//| Market Watch: a symbol that is not selected is selected only for   |
//| the duration of its own probe (InpProbeHistory) and deselected      |
//| again; if MT5 refuses to deselect it (open chart / position), it    |
//| stays selected and the Experts log says so.                         |
//|                                                                   |
//| TIMES ARE RAW SERVER TIME, NO Z -- the same rule as ExportHistory   |
//| (see its header). SERIES_FIRSTDATE depends on what the terminal has |
//| loaded; SERIES_SERVER_FIRSTDATE is the first date on the broker's   |
//| server for the symbol regardless of timeframe and is the number to  |
//| trust for "how deep can this go". Both are written.                 |
//+------------------------------------------------------------------+
#property copyright "Institutional Trading System MT5 Bridge"
#property version   "1.00"
#property script_show_inputs

input bool InpOnlyMarketWatch = false;  // false = SymbolsTotal(false): EVERY symbol on the server, not just Market Watch
input bool InpProbeHistory    = true;   // select each symbol briefly to read first-bar dates (needed for the depth numbers)
input int  InpSyncWaitMs      = 3000;   // max wait per symbol for the series to synchronise before reading first dates
input bool InpSessions        = true;   // write SymbolInfoSessionTrade windows (cheap; server time)

//+------------------------------------------------------------------+
void OnStart()
{
   int total = SymbolsTotal(InpOnlyMarketWatch);
   string server = AccountInfoString(ACCOUNT_SERVER);
   string safe = server;
   StringReplace(safe, " ", "_");
   string fn = "symbollist." + safe + ".json";
   int offset = (int)(TimeCurrent() - TimeGMT());
   PrintFormat("ExportSymbolList: %d symbol(s), server=%s, server-GMT offset now=%d s, common folder=%s",
               total, server, offset, TerminalInfoString(TERMINAL_COMMONDATA_PATH));

   int f = FileOpen(fn, FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(f == INVALID_HANDLE) { PrintFormat("ExportSymbolList: cannot write %s (%d)", fn, GetLastError()); return; }

   // Written incrementally, one symbol per line (a thousand symbols concatenated in one string is quadratic).
   FileWriteString(f, "{\n");
   FileWriteString(f, "  \"_source\": \"mt5_symbol_list\",\n");
   FileWriteString(f, "  \"_server\": \"" + Esc(server) + "\",\n");
   FileWriteString(f, "  \"_account_currency\": \"" + Esc(AccountInfoString(ACCOUNT_CURRENCY)) + "\",\n");
   FileWriteString(f, "  \"_exported_at_utc\": \"" + TimeToString(TimeGMT(), TIME_DATE | TIME_SECONDS) + "\",\n");
   FileWriteString(f, "  \"_server_utc_offset_sec_now\": " + IntegerToString(offset) + ",\n");
   FileWriteString(f, "  \"_time_basis\": \"BROKER SERVER TIME, NOT UTC (first_bar_*, sessions_trade)\",\n");
   FileWriteString(f, "  \"_count\": " + IntegerToString(total) + ",\n");
   FileWriteString(f, "  \"symbols\": [\n");

   int written = 0;
   for(int i = 0; i < total; i++)
   {
      string s = SymbolName(i, InpOnlyMarketWatch);
      if(s == "") continue;
      string row = OneSymbol(s);
      FileWriteString(f, (written > 0 ? ",\n" : "") + row);
      written++;
      if((i % 50) == 0) PrintFormat("ExportSymbolList: %d / %d", i, total);
   }
   FileWriteString(f, "\n  ]\n}\n");
   FileClose(f);
   PrintFormat("ExportSymbolList: done, %d symbol(s) -> %s. Copy it out of the Common\\Files folder, then run "
               "scripts/import-ftmo-symbols.py --symbol-list <file> (docs/architecture/mt5-ftmo-symbol-universe-export.md).",
               written, fn);
}

//+------------------------------------------------------------------+
string Num(double v, int d = 10) { return DoubleToString(v, d); }

// ASCII-only, JSON-escaped. SYMBOL_PATH carries backslashes ("Indices\\US500.cash") that MUST be doubled, and a
// description can hold quotes or non-ASCII; the file is written FILE_ANSI, so anything above 126 becomes '?'.
string Esc(string s)
{
   string out = "";
   int n = StringLen(s);
   for(int i = 0; i < n; i++)
   {
      ushort c = StringGetCharacter(s, i);
      if(c == '\\')      out += "\\\\";
      else if(c == '"')  out += "\\\"";
      else if(c < 32 || c > 126) out += "?";
      else               out += ShortToString(c);
   }
   return out;
}

string IsoServer(long t)
{
   if(t <= 0) return "";
   MqlDateTime dt;
   TimeToStruct((datetime)t, dt);
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02d", dt.year, dt.mon, dt.day, dt.hour, dt.min, dt.sec);
}

// First bar time of one timeframe for one symbol (server time), "" when the terminal has none loaded.
string FirstBar(string s, ENUM_TIMEFRAMES tf)
{
   long first = 0;
   if(!SeriesInfoInteger(s, tf, SERIES_FIRSTDATE, first)) return "";
   return IsoServer(first);
}

string Sessions(string s)
{
   string out = "[";
   bool anyDay = false;
   for(int d = 0; d < 7; d++)                 // ENUM_DAY_OF_WEEK: SUNDAY=0 .. SATURDAY=6
   {
      string day = "";
      for(uint k = 0; k < 10; k++)
      {
         datetime from, to;
         if(!SymbolInfoSessionTrade(s, (ENUM_DAY_OF_WEEK)d, k, from, to)) break;
         day += (day == "" ? "" : ", ") + "[\"" + TimeToString(from, TIME_MINUTES) + "\", \"" + TimeToString(to, TIME_MINUTES) + "\"]";
      }
      out += (anyDay ? ", " : "") + "{\"dow\": " + IntegerToString(d) + ", \"windows\": [" + day + "]}";
      anyDay = true;
   }
   return out + "]";
}

string OneSymbol(string s)
{
   bool wasSelected = (bool)SymbolInfoInteger(s, SYMBOL_SELECT);
   bool touched = false;
   string m1 = "", m5 = "", m15 = "", serverFirst = "", terminalFirst = "";
   if(InpProbeHistory)
   {
      if(!wasSelected) touched = SymbolSelect(s, true);
      if(wasSelected || touched)
      {
         // Ask for one bar: that is what makes the terminal start synchronising this symbol's series.
         MqlRates tmp[];
         CopyRates(s, PERIOD_M1, 0, 1, tmp);
         int waited = 0;
         while(!(bool)SeriesInfoInteger(s, PERIOD_M1, SERIES_SYNCHRONIZED) && waited < InpSyncWaitMs)
         {
            Sleep(100);
            waited += 100;
         }
         m1  = FirstBar(s, PERIOD_M1);
         m5  = FirstBar(s, PERIOD_M5);
         m15 = FirstBar(s, PERIOD_M15);
         long v = 0;
         if(SeriesInfoInteger(s, PERIOD_M1, SERIES_SERVER_FIRSTDATE, v))   serverFirst = IsoServer(v);
         v = 0;
         if(SeriesInfoInteger(s, PERIOD_M1, SERIES_TERMINAL_FIRSTDATE, v)) terminalFirst = IsoServer(v);
      }
      if(touched && !SymbolSelect(s, false))
         PrintFormat("ExportSymbolList: %s could not be deselected again (open chart or position) -- left in Market Watch", s);
   }

   int tm = (int)SymbolInfoInteger(s, SYMBOL_TRADE_MODE);
   string row = "    {";
   row += "\"name\": \"" + Esc(s) + "\", ";
   row += "\"path\": \"" + Esc(SymbolInfoString(s, SYMBOL_PATH)) + "\", ";
   row += "\"description\": \"" + Esc(SymbolInfoString(s, SYMBOL_DESCRIPTION)) + "\", ";
   row += "\"currency_base\": \"" + Esc(SymbolInfoString(s, SYMBOL_CURRENCY_BASE)) + "\", ";
   row += "\"currency_profit\": \"" + Esc(SymbolInfoString(s, SYMBOL_CURRENCY_PROFIT)) + "\", ";
   row += "\"currency_margin\": \"" + Esc(SymbolInfoString(s, SYMBOL_CURRENCY_MARGIN)) + "\", ";
   row += "\"digits\": " + IntegerToString((int)SymbolInfoInteger(s, SYMBOL_DIGITS)) + ", ";
   row += "\"point\": " + Num(SymbolInfoDouble(s, SYMBOL_POINT)) + ", ";
   row += "\"contract_size\": " + Num(SymbolInfoDouble(s, SYMBOL_TRADE_CONTRACT_SIZE), 4) + ", ";
   row += "\"volume_min\": " + Num(SymbolInfoDouble(s, SYMBOL_VOLUME_MIN), 4) + ", ";
   row += "\"volume_step\": " + Num(SymbolInfoDouble(s, SYMBOL_VOLUME_STEP), 4) + ", ";
   row += "\"volume_max\": " + Num(SymbolInfoDouble(s, SYMBOL_VOLUME_MAX), 4) + ", ";
   row += "\"trade_mode\": " + IntegerToString(tm) + ", ";
   row += "\"trade_mode_name\": \"" + EnumToString((ENUM_SYMBOL_TRADE_MODE)tm) + "\", ";
   row += "\"calc_mode\": " + IntegerToString((int)SymbolInfoInteger(s, SYMBOL_TRADE_CALC_MODE)) + ", ";
   row += "\"swap_mode\": " + IntegerToString((int)SymbolInfoInteger(s, SYMBOL_SWAP_MODE)) + ", ";
   row += "\"swap_long\": " + Num(SymbolInfoDouble(s, SYMBOL_SWAP_LONG), 6) + ", ";
   row += "\"swap_short\": " + Num(SymbolInfoDouble(s, SYMBOL_SWAP_SHORT), 6) + ", ";
   row += "\"spread_now_points\": " + IntegerToString((int)SymbolInfoInteger(s, SYMBOL_SPREAD)) + ", ";
   row += "\"spread_float\": " + (SymbolInfoInteger(s, SYMBOL_SPREAD_FLOAT) ? "true" : "false") + ", ";
   row += "\"selected_before\": " + (wasSelected ? "true" : "false") + ", ";
   row += "\"first_bar_server\": {\"1m\": \"" + m1 + "\", \"5m\": \"" + m5 + "\", \"15m\": \"" + m15 + "\"}, ";
   row += "\"server_first_date\": \"" + serverFirst + "\", ";
   row += "\"terminal_first_date\": \"" + terminalFirst + "\", ";
   row += "\"sessions_trade\": " + (InpSessions ? Sessions(s) : "[]");
   row += "}";
   return row;
}
