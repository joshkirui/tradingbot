import time
import MetaTrader5 as mt5
from modules.data_engine import get_candles, normalize_symbol
from modules.logic import score_setup
from modules.risk import calculate_lots, pre_trade_checks
from modules.execution import execute_institutional_order, manage_trade_evolution, check_closed_trades
from modules.alerts import alert_trade_entry, send_telegram_log

WATCHLIST = ["XAUUSD", "GBPUSD", "EURUSD"]
MAGIC = 202405

def run_loop():
    print("--- Institutional M5 Bot LIVE (History Tracking Active) ---")
    mt5.initialize()
    
    while True:
        try:
            # 1. Check for closed trades (Alert TP/SL hits)
            check_closed_trades(MAGIC)
            
            # 2. Manage open trades (BE/Partials)
            manage_trade_evolution(MAGIC)
            
            # 3. Scan for new entries
            for sym in WATCHLIST:
                symbol = normalize_symbol(sym)
                if mt5.positions_get(symbol=symbol): continue

                dfs = {tf: get_candles(symbol, tf, 20) for tf in ["MN1", "D1", "H4", "M30", "M5"]}
                if any(df.empty for df in dfs.values()): continue

                res = score_setup(symbol, dfs["MN1"], dfs["D1"], dfs["H4"], dfs["M30"], dfs["M5"])
                
                if res.get("valid"):
                    can_trade, reason = pre_trade_checks(MAGIC, res["score"])
                    if can_trade:
                        lots = calculate_lots(symbol, res["entry"], res["sl"], 0.01)
                        if lots > 0:
                            order = execute_institutional_order(symbol, res, lots, MAGIC)
                            if order.retcode == mt5.TRADE_RETCODE_DONE:
                                alert_trade_entry(symbol, res["bias"], res["entry"], res["sl"], res["tp"], lots, res["rr"])
            
            time.sleep(30) # Scan every 30s

        except Exception as e:
            print(f"Loop Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run_loop()