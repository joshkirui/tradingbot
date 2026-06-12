import time
import os
import json
import sys
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

# --- IMPORTS ---
try:
    from modules.data_engine import get_candles, normalize_symbol, get_session
    from modules.logic import score_setup
    from modules.telegram_alerts import (
        alert_trade_entry, alert_trade_closed, alert_error, alert_bot_started, alert_bot_stopped
    )
except ImportError as e:
    print(f"❌ Import Error: {e}. Check your /modules folder.")
    sys.exit()

# --- CONFIG ---
MAGIC_NUMBER = 202405
WATCHLIST = ["BTCUSD", "XAUUSD", "EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCAD", "USDCHF"]
MIN_SCORE_THRESHOLD = 5
RISK_REWARD = 2.0
POLLING_INTERVAL = 60
MAX_SL_PIPS = 300 
AI_JOURNAL_FILE = "openclaw_journal.json"

# ==============================================================================
# --- OPENCLAW AI JOURNALING AGENT ---
# ==============================================================================

def log_to_openclaw(entry_data):
    journal = []
    if os.path.exists(AI_JOURNAL_FILE):
        try:
            with open(AI_JOURNAL_FILE, "r") as f:
                journal = json.load(f)
        except: journal = []
    journal.append(entry_data)
    with open(AI_JOURNAL_FILE, "w") as f:
        json.dump(journal, f, indent=4)

def record_trade_event(nickname, symbol, bias, score, result_dict, entry, sl, tp, lots, status="ENTRY"):
    event = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "account": nickname,
        "symbol": symbol,
        "bias": bias,
        "score": score,
        "params": {"entry": entry, "sl": sl, "tp": tp, "lots": lots},
        "status": status
    }
    log_to_openclaw(event)

# ==============================================================================
# --- CORE HELPERS ---
# ==============================================================================

def force_to_string(data_obj):
    """Fixes the Ambiguous DataFrame error for Python 3.14+."""
    try:
        if hasattr(data_obj, 'iloc'):
            return str(data_obj.iloc[-1]).split('\n')[0].split('dtype')[0].strip()
        return str(data_obj).strip()
    except: return "Unknown"

def login_to_mt5(nickname):
    try:
        if not os.path.exists("accounts.json"): return False
        with open("accounts.json", "r") as f: accounts = json.load(f)
        if nickname not in accounts: return False
        creds = accounts[nickname]
        path = "C:/Program Files/MetaTrader 5/terminal64.exe"
        if not mt5.initialize(path=path): return False
        return mt5.login(login=int(creds['login']), password=creds['password'], server=creds['server'])
    except: return False

def get_filling_mode(symbol):
    info = mt5.symbol_info(symbol)
    if not info: return 2
    if info.filling_mode & 1: return 0 
    if info.filling_mode & 2: return 1 
    return 2 

def calculate_dynamic_lot(symbol, score, entry, sl):
    acc = mt5.account_info()
    sym = mt5.symbol_info(symbol)
    if not acc or not sym or abs(entry - sl) == 0: return 0.01
    risk_pct = {5:0.005, 6:0.007, 7:0.01, 8:0.012, 9:0.015, 10:0.02}.get(score, 0.005)
    lots = (acc.balance * risk_pct) / ((abs(entry - sl) / sym.point) * sym.trade_tick_value)
    lots = round(lots / sym.volume_step) * sym.volume_step
    return max(min(lots, 5.0), sym.volume_min)

def execute_trade(nickname, symbol, bias, price, sl, tp, score, lots, full_res):
    digits = mt5.symbol_info(symbol).digits
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lots),
        "type": mt5.ORDER_TYPE_BUY if bias == "bullish" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": round(sl, digits),
        "tp": round(tp, digits),
        "magic": MAGIC_NUMBER,
        "comment": f"Frost {score}",
        "type_filling": get_filling_mode(symbol),
    }
    res = mt5.order_send(request)
    if res.retcode == mt5.TRADE_RETCODE_DONE:
        alert_trade_entry(symbol, bias, price, sl, tp, lots, score, "N/A", RISK_REWARD)
        record_trade_event(nickname, symbol, bias, score, full_res, price, sl, tp, lots, "ENTRY")
    else:
        alert_error(f"Trade Failed: {res.comment}", location="execute_trade")

# ==============================================================================
# --- MAIN ENGINE ---
# ==============================================================================

def run_live_bot(nickname):
    print(f"=== FrostBot: {nickname} (AI-Enabled) ===", flush=True)
    if not login_to_mt5(nickname): return
    alert_bot_started(WATCHLIST, MIN_SCORE_THRESHOLD, RISK_REWARD)

    while True:
        try:
            if not mt5.terminal_info().connected: login_to_mt5(nickname)
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Scanning...", flush=True)
            
            for base_symbol in WATCHLIST:
                symbol = normalize_symbol(base_symbol)
                pos = mt5.positions_get(symbol=symbol)
                if pos and any(p.magic == MAGIC_NUMBER for p in pos): continue

                df_h1 = get_candles(symbol, "H1", 100)
                df_m1 = get_candles(symbol, "M1", 500)
                if df_m1 is None or len(df_m1) < 10: continue
                
                sess_name = force_to_string(get_session(df_m1))
                res = score_setup(df_h1, df_m1, sess_name, symbol=symbol)
                
                if res.get("valid"):
                    print(f"  [+] {symbol:<12} | Score:{res['score']} — QUALIFIES", flush=True)
                else:
                    print(f"  [-] {symbol:<12} | INVALID | {res.get('reason')}", flush=True)

                if res.get("valid") and res.get("score") >= MIN_SCORE_THRESHOLD:
                    tick = mt5.symbol_info_tick(symbol)
                    bias = res["bias"]
                    entry = tick.ask if bias == "bullish" else tick.bid
                    sl = res["poi"]["low"] if bias == "bullish" else res["poi"]["high"]
                    dist = abs(entry - sl)
                    
                    pip_val = 0.01 if "JPY" in symbol else 0.1 if "XAU" in symbol else 0.0001
                    if dist > (MAX_SL_PIPS * pip_val):
                        dist = MAX_SL_PIPS * pip_val
                        sl = entry - dist if bias == "bullish" else entry + dist
                    
                    tp = entry + (dist * RISK_REWARD) if bias == "bullish" else entry - (dist * RISK_REWARD)
                    lots = calculate_dynamic_lot(symbol, res["score"], entry, sl)
                    execute_trade(nickname, symbol, bias, entry, sl, tp, res["score"], lots, res)
            
            time.sleep(POLLING_INTERVAL)
        except Exception as e: 
            print(f"Loop Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit()
    run_live_bot(sys.argv[1])