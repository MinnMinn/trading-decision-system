//+------------------------------------------------------------------+
//| ExportSymbolSpec.mq5 — ONE-SHOT export of the broker's real costs  |
//|                                                                   |
//| Methodology improvement plan A0 (docs/plans/2026-09-28-           |
//| methodology-improvement-plan.md): the backtest prices every CFD   |
//| trade at a flat 0.05 %/side that risk-config.json itself labels   |
//| "an assumption". Owner decision 2026-09-28: always prefer what is |
//| real -> take the costs from the broker's own terminal.            |
//|                                                                   |
//| Writes Common\Files\symbolspec.<SYMBOL>.json for every symbol in  |
//| InpSymbols:                                                       |
//|   * the contract specification as the broker reports it           |
//|     (digits, point, contract size, tick size/value, swap long /   |
//|     short and mode, triple-swap day, volume limits);              |
//|   * the spread the terminal RECORDED on every M15 bar it holds    |
//|     (MqlRates.spread, in points) -- summarised per UTC hour as    |
//|     median / p90 plus the bar count, so a session effect is       |
//|     visible, and the raw per-bar series is NOT written (size);    |
//|   * commission actually charged on this account's closed deals of |
//|     that symbol (sum and per-lot), if there are any -- MQL5 has   |
//|     no symbol property for commission, so a symbol never traded   |
//|     here reports "no_deals" and the value must come from the      |
//|     broker's contract page instead. It is NEVER guessed.          |
//| Times: bar times are server time; the hour buckets use the        |
//| CURRENT server-GMT offset, stated in the file (a DST shift moves  |
//| a bucket by one hour -- disclosed, not corrected here).           |
//| Read-only: it places no orders and changes no settings.           |
//+------------------------------------------------------------------+
#property copyright "Institutional Trading System MT5 Bridge"
#property version   "1.00"
#property script_show_inputs

input string InpSymbols   = "XAUUSD,XAGUSD,US500,US30,USTEC,DE40,FRA40,AUS200";
input int    InpBars      = 100000;   // M15 bars of recorded spread to summarise per symbol
input int    InpDealDays  = 3650;     // how far back to read this account's deals for commission

struct Bucket { int v[]; };

void OnStart()
{
   // v1.01 (2026-10-01): when Common\\Files\\export-list.txt exists its `symbols=` line overrides InpSymbols (same file as
   // ExportHistory v1.02), so no long string has to be typed into the Inputs tab.
   string symsCsv = InpSymbols;
   int hl = FileOpen("export-list.txt", FILE_READ | FILE_TXT | FILE_COMMON | FILE_ANSI);
   if(hl != INVALID_HANDLE)
   {
      while(!FileIsEnding(hl))
      {
         string ln = FileReadString(hl);
         StringTrimLeft(ln); StringTrimRight(ln);
         if(StringFind(ln, "symbols=") == 0) symsCsv = StringSubstr(ln, 8);
      }
      FileClose(hl);
   }
   string syms[];
   int n = StringSplit(symsCsv, ',', syms);
   int offset = (int)(TimeCurrent() - TimeGMT());
   PrintFormat("ExportSymbolSpec: %d symbol(s), server=%s, server-GMT offset now=%d s, common folder=%s",
               n, AccountInfoString(ACCOUNT_SERVER), offset, TerminalInfoString(TERMINAL_COMMONDATA_PATH));
   HistorySelect(TimeCurrent() - (datetime)InpDealDays * 86400, TimeCurrent());
   for(int i = 0; i < n; i++)
   {
      string s = syms[i];
      StringTrimLeft(s); StringTrimRight(s);
      if(s == "") continue;
      if(!SymbolSelect(s, true)) { PrintFormat("ExportSymbolSpec: %s not available on this server -- skipped", s); continue; }
      ExportOne(s, offset);
   }
   Print("ExportSymbolSpec: done. Copy symbolspec.*.json out of the Common\\Files folder into data/history/costs/ in the repo.");
}

string Num(double v, int d = 10) { return DoubleToString(v, d); }

void ExportOne(string s, int offset)
{
   MqlRates r[];
   ArraySetAsSeries(r, false);
   SymbolSelect(s, true);
   { MqlRates one[]; CopyRates(s, PERIOD_M15, 0, 1, one); int w = 0;
     while(!(bool)SeriesInfoInteger(s, PERIOD_M15, SERIES_SYNCHRONIZED) && w < 8000) { Sleep(100); w += 100; } }
   int copied = CopyRates(s, PERIOD_M15, 0, InpBars, r);
   // per-UTC-hour buckets of recorded spread (points)
   int all[]; ArrayResize(all, MathMax(copied, 0));
   Bucket hb[24];
   for(int k = 0; k < copied; k++)
   {
      all[k] = r[k].spread;
      MqlDateTime t; TimeToStruct(r[k].time - offset, t);
      int m = ArraySize(hb[t.hour].v); ArrayResize(hb[t.hour].v, m + 1, 4096); hb[t.hour].v[m] = r[k].spread;
   }
   // commission from this account's deals
   double comm = 0, lots = 0; int deals = 0;
   for(int d = HistoryDealsTotal() - 1; d >= 0; d--)
   {
      ulong tk = HistoryDealGetTicket(d);
      if(HistoryDealGetString(tk, DEAL_SYMBOL) != s) continue;
      comm += HistoryDealGetDouble(tk, DEAL_COMMISSION);
      lots += HistoryDealGetDouble(tk, DEAL_VOLUME);
      deals++;
   }

   string fn = "symbolspec." + s + ".json";
   int f = FileOpen(fn, FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(f == INVALID_HANDLE) { PrintFormat("ExportSymbolSpec: cannot write %s (%d)", fn, GetLastError()); return; }
   FileWriteString(f, "{\n");
   FileWriteString(f, "  \"symbol\": \"" + s + "\",\n");
   FileWriteString(f, "  \"_source\": \"mt5_symbol_spec\",\n");
   FileWriteString(f, "  \"_server\": \"" + AccountInfoString(ACCOUNT_SERVER) + "\",\n");
   FileWriteString(f, "  \"_account_currency\": \"" + AccountInfoString(ACCOUNT_CURRENCY) + "\",\n");
   FileWriteString(f, "  \"_exported_at_utc\": \"" + TimeToString(TimeGMT(), TIME_DATE | TIME_SECONDS) + "\",\n");
   FileWriteString(f, "  \"_server_utc_offset_sec_now\": " + IntegerToString(offset) + ",\n");
   FileWriteString(f, "  \"digits\": " + IntegerToString((int)SymbolInfoInteger(s, SYMBOL_DIGITS)) + ",\n");
   FileWriteString(f, "  \"point\": " + Num(SymbolInfoDouble(s, SYMBOL_POINT)) + ",\n");
   FileWriteString(f, "  \"contract_size\": " + Num(SymbolInfoDouble(s, SYMBOL_TRADE_CONTRACT_SIZE), 4) + ",\n");
   FileWriteString(f, "  \"tick_size\": " + Num(SymbolInfoDouble(s, SYMBOL_TRADE_TICK_SIZE)) + ",\n");
   FileWriteString(f, "  \"tick_value\": " + Num(SymbolInfoDouble(s, SYMBOL_TRADE_TICK_VALUE)) + ",\n");
   FileWriteString(f, "  \"currency_profit\": \"" + SymbolInfoString(s, SYMBOL_CURRENCY_PROFIT) + "\",\n");
   FileWriteString(f, "  \"spread_now_points\": " + IntegerToString((int)SymbolInfoInteger(s, SYMBOL_SPREAD)) + ",\n");
   FileWriteString(f, "  \"spread_float\": " + (SymbolInfoInteger(s, SYMBOL_SPREAD_FLOAT) ? "true" : "false") + ",\n");
   FileWriteString(f, "  \"swap_mode\": " + IntegerToString((int)SymbolInfoInteger(s, SYMBOL_SWAP_MODE)) + ",\n");
   FileWriteString(f, "  \"swap_long\": " + Num(SymbolInfoDouble(s, SYMBOL_SWAP_LONG), 6) + ",\n");
   FileWriteString(f, "  \"swap_short\": " + Num(SymbolInfoDouble(s, SYMBOL_SWAP_SHORT), 6) + ",\n");
   FileWriteString(f, "  \"swap_rollover3days\": " + IntegerToString((int)SymbolInfoInteger(s, SYMBOL_SWAP_ROLLOVER3DAYS)) + ",\n");
   FileWriteString(f, "  \"volume_min\": " + Num(SymbolInfoDouble(s, SYMBOL_VOLUME_MIN), 4) + ",\n");
   FileWriteString(f, "  \"volume_step\": " + Num(SymbolInfoDouble(s, SYMBOL_VOLUME_STEP), 4) + ",\n");
   FileWriteString(f, "  \"volume_max\": " + Num(SymbolInfoDouble(s, SYMBOL_VOLUME_MAX), 4) + ",\n");
   FileWriteString(f, "  \"commission\": {\"deals\": " + IntegerToString(deals) + ", \"lots\": " + Num(lots, 4) +
                      ", \"sum_account_ccy\": " + Num(comm, 4) + ", \"status\": \"" + (deals > 0 ? "from_deals" : "no_deals") + "\"},\n");
   FileWriteString(f, "  \"recorded_spread_m15\": {\"bars\": " + IntegerToString(copied) +
                      ", \"first_bar_server\": \"" + (copied > 0 ? TimeToString(r[0].time, TIME_DATE | TIME_MINUTES) : "") +
                      "\", \"last_bar_server\": \"" + (copied > 0 ? TimeToString(r[copied - 1].time, TIME_DATE | TIME_MINUTES) : "") +
                      "\", \"median_points\": " + IntegerToString(Pct(all, 0.5)) + ", \"p90_points\": " + IntegerToString(Pct(all, 0.9)) + ",\n");
   FileWriteString(f, "    \"by_utc_hour\": [");
   for(int h = 0; h < 24; h++)
   {
      FileWriteString(f, (h ? ", " : "") + "{\"h\": " + IntegerToString(h) + ", \"n\": " + IntegerToString(ArraySize(hb[h].v)) +
                         ", \"median\": " + IntegerToString(Pct(hb[h].v, 0.5)) + ", \"p90\": " + IntegerToString(Pct(hb[h].v, 0.9)) + "}");
   }
   FileWriteString(f, "]}\n}\n");
   FileClose(f);
   PrintFormat("ExportSymbolSpec: %s -> %s (%d M15 bars, %d deal(s))", s, fn, copied, deals);
}

int Pct(int &v[], double q)
{
   int n = ArraySize(v);
   if(n == 0) return -1;
   int c[]; ArrayCopy(c, v); ArraySort(c);
   int i = (int)MathFloor(q * (n - 1));
   return c[i];
}
