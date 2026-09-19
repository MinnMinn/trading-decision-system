//+------------------------------------------------------------------+
//| OrderBridge.mq5 -- file-based order bridge for the TYME trading    |
//| system (pilot profile top5, CFD leg). Companion of ExportOHLCV.mq5.|
//|                                                                    |
//| Protocol (all files under the terminal's Common\Files folder,      |
//| which the project symlinks as data/live/mt5-bridge):               |
//|   bridge/cmd-<id>.json   written by scripts/mt5-order-bridge.py    |
//|   bridge/res-<id>.json   written here, then the cmd file is deleted|
//|   bridge/state.json      account + positions + orders, every timer |
//|   bridge/symbols.json    contract data for the allowed symbols     |
//| Commands (flat JSON, string values):                               |
//|   ping | limit(symbol, side buy|sell, volume, price, sl, tp, comment)|
//|   market(symbol, side, volume, sl, tp, comment)  -- Wyckoff entries    |
//|   cancel(ticket) | modify(ticket, sl, tp) | close(ticket)           |
//|   order_status(ticket) | position_status(ticket) | symbol(symbol)   |
//| Safety (HARD, enforced here, mirrors the Binance connector):       |
//|   demo accounts only (InpDemoOnly), symbol allowlist, max lots,     |
//|   every order carries InpMagic, GTC pending orders with SL/TP set   |
//|   at placement so a fill is never unprotected.                      |
//| Install: MetaEditor -> compile -> attach to any chart (one instance)|
//| Status: compiled 2026-09-11 (MetaEditor via Wine, 0 errors); the   |
//| first live ping failed on an unescaped Windows path -> Esc() added. |
//+------------------------------------------------------------------+
#property copyright "TYME Trading"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

input int    InpPollMs        = 1000;                          // poll interval for command files
input long   InpMagic         = 20260911;                      // magic number on every order
input string InpAllowedSymbols = "XAUUSD,XAGUSD,EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF,NZDUSD"; // allowlist -- must mirror the MT5-fed execution lists in docs/architecture/instruments.json (cfd + forex). COMPILED INPUT: editing this source changes nothing until the EA is recompiled and re-attached in MetaTrader.
input double InpMaxLots       = 1.0;                           // hard cap per order
input bool   InpDemoOnly      = true;                          // refuse anything but a demo account
input string InpBridgeDir     = "bridge";                      // command/response folder inside Common\Files. ONE PER ACCOUNT when several MT5 terminals share one Common folder: give each terminal its own name (e.g. "bridge-acc-001") and point that account's runner at the same name via MT5_BRIDGE_SUBDIR. Leaving every terminal on the default makes them read and DELETE each other's replies (scripts/mt5-order-bridge.py consumes res-<id>.json), so one account's fill could be reported to another. COMPILED INPUT: editing this source changes nothing until the EA is recompiled and re-attached.

CTrade trade;
string g_dir = "bridge";

//---------------------------------------------------------------- helpers
bool Allowed(const string sym)
  {
   string s = "," + InpAllowedSymbols + ",";
   return(StringFind(s, "," + sym + ",") >= 0);
  }

string Esc(string v)                       // JSON string escaping: backslashes (Windows paths) and quotes
  {
   StringReplace(v, "\\", "\\\\");
   StringReplace(v, "\"", "\\\"");
   return(v);
  }
string J(const string k, const string v) { return("\"" + k + "\":\"" + Esc(v) + "\""); }
string JN(const string k, const double v, const int d = 8) { return("\"" + k + "\":" + DoubleToString(v, d)); }
string JI(const string k, const long v) { return("\"" + k + "\":" + IntegerToString(v)); }

// minimal flat-JSON reader: value of "key" as string (quoted or bare)
string Get(const string json, const string key)
  {
   int p = StringFind(json, "\"" + key + "\"");
   if(p < 0) return("");
   p = StringFind(json, ":", p);
   if(p < 0) return("");
   p++;
   while(p < StringLen(json) && (StringGetCharacter(json, p) == ' ')) p++;
   if(p < StringLen(json) && StringGetCharacter(json, p) == '"')
     {
      int e = StringFind(json, "\"", p + 1);
      return(StringSubstr(json, p + 1, e - p - 1));
     }
   int e = p;
   while(e < StringLen(json))
     {
      ushort c = StringGetCharacter(json, e);
      if(c == ',' || c == '}' || c == ' ') break;
      e++;
     }
   return(StringSubstr(json, p, e - p));
  }

bool WriteFile(const string name, const string body)
  {
   int h = FileOpen(name, FILE_WRITE | FILE_TXT | FILE_COMMON | FILE_ANSI);
   if(h == INVALID_HANDLE) return(false);
   FileWriteString(h, body);
   FileClose(h);
   return(true);
  }

string ReadFile(const string name)
  {
   int h = FileOpen(name, FILE_READ | FILE_TXT | FILE_COMMON | FILE_ANSI);
   if(h == INVALID_HANDLE) return("");
   string s = "";
   while(!FileIsEnding(h)) s += FileReadString(h);
   FileClose(h);
   return(s);
  }

string TradeMode()
  {
   long m = AccountInfoInteger(ACCOUNT_TRADE_MODE);
   if(m == ACCOUNT_TRADE_MODE_DEMO) return("demo");
   if(m == ACCOUNT_TRADE_MODE_CONTEST) return("contest");
   return("real");
  }

//---------------------------------------------------------------- state snapshots
void WriteSymbols()
  {
   string parts[]; int n = StringSplit(InpAllowedSymbols, ',', parts);
   string out = "{";
   for(int i = 0; i < n; i++)
     {
      string s = parts[i];
      if(!SymbolSelect(s, true)) continue;
      if(i > 0) out += ",";
      out += "\"" + s + "\":{" + JN("tick_size", SymbolInfoDouble(s, SYMBOL_TRADE_TICK_SIZE)) + "," + JN("tick_value", SymbolInfoDouble(s, SYMBOL_TRADE_TICK_VALUE)) + ","
             + JN("contract_size", SymbolInfoDouble(s, SYMBOL_TRADE_CONTRACT_SIZE)) + "," + JN("volume_min", SymbolInfoDouble(s, SYMBOL_VOLUME_MIN)) + ","
             + JN("volume_max", MathMin(SymbolInfoDouble(s, SYMBOL_VOLUME_MAX), InpMaxLots)) + "," + JN("volume_step", SymbolInfoDouble(s, SYMBOL_VOLUME_STEP)) + ","
             + JI("digits", SymbolInfoInteger(s, SYMBOL_DIGITS)) + "," + JN("bid", SymbolInfoDouble(s, SYMBOL_BID)) + "," + JN("ask", SymbolInfoDouble(s, SYMBOL_ASK)) + "}";
     }
   out += "}";
   WriteFile(g_dir + "/symbols.json", out);
  }

void WriteState()
  {
   string out = "{\"updated\":\"" + TimeToString(TimeGMT(), TIME_DATE | TIME_SECONDS) + "\",\"account\":{" + J("trade_mode", TradeMode()) + "," + JN("balance", AccountInfoDouble(ACCOUNT_BALANCE), 2) + ","
                + JN("equity", AccountInfoDouble(ACCOUNT_EQUITY), 2) + "," + JN("margin_free", AccountInfoDouble(ACCOUNT_MARGIN_FREE), 2) + "," + J("currency", AccountInfoString(ACCOUNT_CURRENCY)) + "," + JI("login", AccountInfoInteger(ACCOUNT_LOGIN)) + "},\"positions\":[";
   int np = PositionsTotal(); bool first = true;
   for(int i = 0; i < np; i++)
     {
      ulong tk = PositionGetTicket(i);
      if(tk == 0 || !PositionSelectByTicket(tk)) continue;
      if(!first) out += ","; first = false;
      out += "{" + JI("ticket", (long)tk) + "," + J("symbol", PositionGetString(POSITION_SYMBOL)) + "," + J("type", PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? "buy" : "sell") + ","
             + JN("volume", PositionGetDouble(POSITION_VOLUME), 2) + "," + JN("price_open", PositionGetDouble(POSITION_PRICE_OPEN), 5) + "," + JN("sl", PositionGetDouble(POSITION_SL), 5) + ","
             + JN("tp", PositionGetDouble(POSITION_TP), 5) + "," + JN("profit", PositionGetDouble(POSITION_PROFIT), 2) + "," + JI("magic", PositionGetInteger(POSITION_MAGIC)) + ","
             + JI("order_ticket", PositionGetInteger(POSITION_IDENTIFIER)) + "," + J("comment", PositionGetString(POSITION_COMMENT)) + "}";
     }
   out += "],\"orders\":[";
   int no = OrdersTotal(); first = true;
   for(int i = 0; i < no; i++)
     {
      ulong tk = OrderGetTicket(i);
      if(tk == 0 || !OrderSelect(tk)) continue;
      if(!first) out += ","; first = false;
      out += "{" + JI("ticket", (long)tk) + "," + J("symbol", OrderGetString(ORDER_SYMBOL)) + "," + JI("type", OrderGetInteger(ORDER_TYPE)) + "," + JN("volume", OrderGetDouble(ORDER_VOLUME_CURRENT), 2) + ","
             + JN("price_open", OrderGetDouble(ORDER_PRICE_OPEN), 5) + "," + JN("sl", OrderGetDouble(ORDER_SL), 5) + "," + JN("tp", OrderGetDouble(ORDER_TP), 5) + "," + JI("magic", OrderGetInteger(ORDER_MAGIC)) + ","
             + J("comment", OrderGetString(ORDER_COMMENT)) + "}";
     }
   out += "]}";
   WriteFile(g_dir + "/state.json", out);
  }

//---------------------------------------------------------------- command handlers
string Fail(const string id, const string why, const long retcode = 0)
  {
   return("{" + J("id", id) + ",\"ok\":false," + JI("retcode", retcode) + "," + J("comment", why) + "}");
  }

string OrderStatus(const string id, const ulong ticket)
  {
   // live pending order?
   if(OrderSelect(ticket))
      return("{" + J("id", id) + ",\"ok\":true," + J("state", "pending") + "," + JI("ticket", (long)ticket) + "," + JN("price", OrderGetDouble(ORDER_PRICE_OPEN), 5) + "}");
   // history: filled / canceled / expired
   if(HistoryOrderSelect(ticket))
     {
      long st = HistoryOrderGetInteger(ticket, ORDER_STATE);
      string state = (st == ORDER_STATE_FILLED) ? "filled" : (st == ORDER_STATE_CANCELED ? "canceled" : (st == ORDER_STATE_EXPIRED ? "expired" : (st == ORDER_STATE_REJECTED ? "rejected" : "other")));
      long posid = HistoryOrderGetInteger(ticket, ORDER_POSITION_ID);
      double price = HistoryOrderGetDouble(ticket, ORDER_PRICE_OPEN);
      double vol = HistoryOrderGetDouble(ticket, ORDER_VOLUME_INITIAL);
      if(st == ORDER_STATE_FILLED && HistorySelectByPosition(posid))
        {
         int nd = HistoryDealsTotal();
         for(int i = 0; i < nd; i++)
           {
            ulong d = HistoryDealGetTicket(i);
            if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_IN) { price = HistoryDealGetDouble(d, DEAL_PRICE); vol = HistoryDealGetDouble(d, DEAL_VOLUME); break; }
           }
        }
      return("{" + J("id", id) + ",\"ok\":true," + J("state", state) + "," + JI("ticket", (long)ticket) + "," + JI("position_ticket", posid) + "," + JN("price", price, 5) + "," + JN("volume", vol, 2) + "}");
     }
   return("{" + J("id", id) + ",\"ok\":true," + J("state", "missing") + "}");
  }

string PositionStatus(const string id, const ulong ticket)
  {
   if(PositionSelectByTicket(ticket))
      return("{" + J("id", id) + ",\"ok\":true," + J("state", "open") + "," + JN("price_open", PositionGetDouble(POSITION_PRICE_OPEN), 5) + "," + JN("sl", PositionGetDouble(POSITION_SL), 5) + "," + JN("tp", PositionGetDouble(POSITION_TP), 5) + "," + JN("profit", PositionGetDouble(POSITION_PROFIT), 2) + "}");
   if(HistorySelectByPosition(ticket))
     {
      int nd = HistoryDealsTotal(); double profit = 0, px = 0; string reason = "other";
      for(int i = 0; i < nd; i++)
        {
         ulong d = HistoryDealGetTicket(i);
         if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_OUT || HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_OUT_BY)
           {
            profit += HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_COMMISSION) + HistoryDealGetDouble(d, DEAL_SWAP);
            px = HistoryDealGetDouble(d, DEAL_PRICE);
            long r = HistoryDealGetInteger(d, DEAL_REASON);
            reason = (r == DEAL_REASON_SL) ? "sl" : (r == DEAL_REASON_TP ? "tp" : (r == DEAL_REASON_EXPERT ? "expert" : "other"));
           }
        }
      if(px > 0) return("{" + J("id", id) + ",\"ok\":true," + J("state", "closed") + "," + JN("price_close", px, 5) + "," + JN("profit", profit, 2) + "," + J("reason", reason) + "}");
     }
   return("{" + J("id", id) + ",\"ok\":true," + J("state", "missing") + "}");
  }

string Handle(const string cmd)
  {
   string id = Get(cmd, "id"), action = Get(cmd, "action");
   if(id == "") return(Fail("", "no id"));
   if(InpDemoOnly && TradeMode() != "demo") return(Fail(id, "account is not DEMO -- OrderBridge refuses (InpDemoOnly)"));
   if(action == "ping") return("{" + J("id", id) + ",\"ok\":true," + J("trade_mode", TradeMode()) + "," + J("common", TerminalInfoString(TERMINAL_COMMONDATA_PATH)) + "}");
   if(action == "symbol") { WriteSymbols(); return("{" + J("id", id) + ",\"ok\":true," + J("file", g_dir + "/symbols.json") + "}"); }
   if(action == "state") { WriteState(); return("{" + J("id", id) + ",\"ok\":true," + J("file", g_dir + "/state.json") + "}"); }
   if(action == "order_status") return(OrderStatus(id, (ulong)StringToInteger(Get(cmd, "ticket"))));
   if(action == "position_status") return(PositionStatus(id, (ulong)StringToInteger(Get(cmd, "ticket"))));
   if(action == "limit")
     {
      string sym = Get(cmd, "symbol"), side = Get(cmd, "side");
      if(!Allowed(sym)) return(Fail(id, "symbol not in allowlist"));
      double vol = StringToDouble(Get(cmd, "volume")), price = StringToDouble(Get(cmd, "price")), sl = StringToDouble(Get(cmd, "sl")), tp = StringToDouble(Get(cmd, "tp"));
      if(vol <= 0 || vol > InpMaxLots) return(Fail(id, "volume outside 0..InpMaxLots"));
      if(sl <= 0 || tp <= 0) return(Fail(id, "sl and tp are mandatory"));
      trade.SetExpertMagicNumber(InpMagic);
      bool ok = (side == "buy") ? trade.BuyLimit(vol, price, sym, sl, tp, ORDER_TIME_GTC, 0, Get(cmd, "comment")) : trade.SellLimit(vol, price, sym, sl, tp, ORDER_TIME_GTC, 0, Get(cmd, "comment"));
      long rc = (long)trade.ResultRetcode();
      if(!ok || (rc != TRADE_RETCODE_DONE && rc != TRADE_RETCODE_PLACED)) return(Fail(id, trade.ResultRetcodeDescription(), rc));
      return("{" + J("id", id) + ",\"ok\":true," + JI("retcode", rc) + "," + JI("ticket", (long)trade.ResultOrder()) + "}");
     }
   if(action == "market")
     {
      string sym = Get(cmd, "symbol"), side = Get(cmd, "side");
      if(!Allowed(sym)) return(Fail(id, "symbol not in allowlist"));
      double vol = StringToDouble(Get(cmd, "volume")), sl = StringToDouble(Get(cmd, "sl")), tp = StringToDouble(Get(cmd, "tp"));
      if(vol <= 0 || vol > InpMaxLots) return(Fail(id, "volume outside 0..InpMaxLots"));
      if(sl <= 0 || tp <= 0) return(Fail(id, "sl and tp are mandatory"));
      trade.SetExpertMagicNumber(InpMagic);
      trade.SetDeviationInPoints(30);
      bool ok = (side == "buy") ? trade.Buy(vol, sym, 0.0, sl, tp, Get(cmd, "comment")) : trade.Sell(vol, sym, 0.0, sl, tp, Get(cmd, "comment"));
      long rc = (long)trade.ResultRetcode();
      if(!ok || (rc != TRADE_RETCODE_DONE && rc != TRADE_RETCODE_PLACED && rc != TRADE_RETCODE_DONE_PARTIAL)) return(Fail(id, trade.ResultRetcodeDescription(), rc));
      return("{" + J("id", id) + ",\"ok\":true," + JI("retcode", rc) + "," + JI("ticket", (long)trade.ResultOrder()) + "," + JI("deal", (long)trade.ResultDeal()) + "," + JN("price", trade.ResultPrice(), 5) + "," + JN("volume", trade.ResultVolume(), 2) + "}");
     }
   if(action == "cancel")
     {
      ulong tk = (ulong)StringToInteger(Get(cmd, "ticket"));
      if(!OrderSelect(tk)) return("{" + J("id", id) + ",\"ok\":true," + J("note", "no such pending order (already filled/canceled)") + "}");
      bool ok = trade.OrderDelete(tk);
      return(ok ? "{" + J("id", id) + ",\"ok\":true}" : Fail(id, trade.ResultRetcodeDescription(), (long)trade.ResultRetcode()));
     }
   if(action == "modify")
     {
      ulong tk = (ulong)StringToInteger(Get(cmd, "ticket"));
      if(!PositionSelectByTicket(tk)) return(Fail(id, "no such position"));
      bool ok = trade.PositionModify(tk, StringToDouble(Get(cmd, "sl")), StringToDouble(Get(cmd, "tp")));
      return(ok ? "{" + J("id", id) + ",\"ok\":true}" : Fail(id, trade.ResultRetcodeDescription(), (long)trade.ResultRetcode()));
     }
   if(action == "close")
     {
      ulong tk = (ulong)StringToInteger(Get(cmd, "ticket"));
      if(!PositionSelectByTicket(tk)) return(Fail(id, "no such position"));
      bool ok = trade.PositionClose(tk);
      if(!ok) return(Fail(id, trade.ResultRetcodeDescription(), (long)trade.ResultRetcode()));
      return("{" + J("id", id) + ",\"ok\":true," + JN("price", trade.ResultPrice(), 5) + "," + JN("profit", 0, 2) + "," + J("note", "profit: read position_status after the deal settles") + "}");
     }
   return(Fail(id, "unknown action " + action));
  }

//---------------------------------------------------------------- lifecycle
int OnInit()
  {
   g_dir = (StringLen(InpBridgeDir) > 0) ? InpBridgeDir : "bridge";
   FolderCreate(g_dir, FILE_COMMON);
   PrintFormat("OrderBridge: magic %d, bridge dir %s, allowlist %s, max lots %.2f, demo-only %s, account mode %s, common folder %s",
               InpMagic, g_dir, InpAllowedSymbols, InpMaxLots, InpDemoOnly ? "yes" : "no", TradeMode(), TerminalInfoString(TERMINAL_COMMONDATA_PATH));
   WriteSymbols(); WriteState();
   EventSetMillisecondTimer(InpPollMs);
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason) { EventKillTimer(); }

void OnTimer()
  {
   string name; long h = FileFindFirst(g_dir + "/cmd-*.json", name, FILE_COMMON);
   if(h != INVALID_HANDLE)
     {
      do
        {
         string path = g_dir + "/" + name;
         string body = ReadFile(path);
         if(body == "") continue;
         string res = Handle(body);
         string id = Get(body, "id");
         WriteFile(g_dir + "/res-" + id + ".json", res);
         FileDelete(path, FILE_COMMON);
        }
      while(FileFindNext(h, name));
      FileFindClose(h);
     }
   static int n = 0;
   if(++n % 5 == 0) WriteState();          // every ~5 s
  }
//+------------------------------------------------------------------+
