import pandas as pd
import MetaTrader5 as mt5
from datetime import timedelta
from modules.data_engine import get_candles, normalize_symbol
from modules.logic import score_setup

# --- $100 SIMULATION SETTINGS ---
START_BALANCE = 100.0  
RISK_PER_TRADE = 0.01  # $1.00 risk

def run_backtest():
    mt5.initialize()
    symbol = normalize_symbol("XAUUSD")
    df_m5 = get_candles(symbol, "M5", 10000) 
    df_m30 = get_candles(symbol, "M30", 1000); df_h4 = get_candles(symbol, "H4", 500)
    df_d1 = get_candles(symbol, "D1", 200); df_mn1 = get_candles(symbol, "MN1", 24)

    trades = []
    bal = START_BALANCE
    cooldown_until = None 

    print(f"--- $100 Small Account Backtest: {symbol} ---")

    for i in range(100, len(df_m5) - 150):
        now = df_m5.iloc[i]["time"]
        if cooldown_until and now < cooldown_until: continue

        res = score_setup(symbol, df_mn1[df_mn1["time"]<now].tail(2), df_d1[df_d1["time"]<now].tail(10),
                          df_h4[df_h4["time"]<now].tail(10), df_m30[df_m30["time"]<now].tail(10), df_m5.iloc[i-15:i+1])
        
        if res.get("valid"):
            cooldown_until = now + timedelta(minutes=240)
            entry, sl, tp, bias = res["entry"], res["sl"], res["tp"], res["bias"]
            initial_risk_px = abs(entry - sl)
            
            # Dollar risk based on 1% ($1.00)
            dollar_risk = bal * RISK_PER_TRADE
            
            be_price = entry + (initial_risk_px * 3.0) if bias == "bullish" else entry - (initial_risk_px * 3.0)
            partial_price = entry + (initial_risk_px * 5.0) if bias == "bullish" else entry - (initial_risk_px * 5.0)
            
            sl_at_be, partials_taken = False, False
            outcome, r_gain = "expired", 0.0
            future = df_m5.iloc[i+1 : i+144]
            
            for _, candle in future.iterrows():
                high, low = candle["high"], candle["low"]

                if not sl_at_be and ((bias=="bullish" and high>=be_price) or (bias=="bearish" and low<=be_price)):
                    sl_at_be, sl = True, entry

                if not partials_taken and ((bias=="bullish" and high>=partial_price) or (bias=="bearish" and low<=partial_price)):
                    partials_taken = True
                    if res["rr"] <= 5.0: outcome, r_gain = "win", res["rr"]; break

                if (bias=="bullish" and low<=sl) or (bias=="bearish" and high>=sl):
                    outcome = "be" if sl_at_be else "loss"
                    r_gain = 2.5 if (partials_taken and sl_at_be) else (0.0 if sl_at_be else -1.0)
                    break

                if (bias=="bullish" and high >= tp) or (bias=="bearish" and low <= tp):
                    outcome = "win"
                    r_gain = (2.5 + (res["rr"] * 0.5)) if partials_taken else res["rr"]
                    break
            
            if outcome != "expired":
                trade_money = dollar_risk * r_gain
                bal += trade_money
                trades.append(r_gain)
                print(f"[{now}] {outcome.upper():<7} | {r_gain:>5.2f}R | Net: ${trade_money:>6.2f} | Balance: ${bal:,.2f}")

    mt5.shutdown()
    if trades:
        print(f"\nFinal Statistics for $100 Account:")
        print(f"Net Profit: ${bal - START_BALANCE:.2f} | Final Balance: ${bal:.2f}")

if __name__ == "__main__":
    run_backtest()