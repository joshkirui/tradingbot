import os, sys
import pandas as pd
import numpy as np
from datetime import datetime
import MetaTrader5 as mt5

# Import your custom logic
from modules.data_engine import get_candles, normalize_symbol, MT5Connection, get_session
from modules.logic import score_setup

# --- CONFIG ---
WATCHLIST = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"] 
BACKTEST_CANDLES = 15000  
LOOKFORWARD = 180        
MIN_SCORE_THRESHOLD = 6  # Added a variable for easy adjustment

def simulate_trade_outcome(entry, sl, tp, bias, start_index, df_m1):
    """
    Checks future candles to see if price hits TP or SL first.
    """
    future_candles = df_m1.iloc[start_index + 1 : start_index + LOOKFORWARD]
    
    for _, candle in future_candles.iterrows():
        if bias == "bullish":
            if candle["low"] <= sl: return "loss"
            if candle["high"] >= tp: return "win"
        else: # bearish
            if candle["high"] >= sl: return "loss"
            if candle["low"] <= tp: return "win"
            
    return "expired"

def run_backtest():
    try:
        MT5Connection.ensure()
    except Exception as e:
        print(f"Connection Error: {e}")
        return []

    all_trades = []
    
    for base_symbol in WATCHLIST:
        symbol = normalize_symbol(base_symbol)
        print(f"\n[ANALYZING] {symbol}...")
        
        df_h1 = get_candles(symbol, "H1", 600)
        df_m1 = get_candles(symbol, "M1", BACKTEST_CANDLES)
        
        if df_h1.empty or df_m1.empty:
            print(f"  - No data for {symbol}")
            continue

        print(f"  - Loaded {len(df_m1)} M1 bars. Scanning for Score {MIN_SCORE_THRESHOLD}+ setups...")

        for i in range(100, len(df_m1) - LOOKFORWARD, 15):
            now_time = df_m1.iloc[i]["time"]
            
            m1_slice = df_m1.iloc[i-100 : i]
            h1_slice = df_h1[df_h1["time"] <= now_time].tail(50)
            
            session = get_session(m1_slice)
            res = score_setup(h1_slice, m1_slice, session)
            
            # --- MODIFIED FILTER HERE ---
            # Checks if logic is valid AND score is 6, 7, 8, or 9
            if res["valid"] and res.get("score", 0) >= MIN_SCORE_THRESHOLD:
                bias = res["bias"]
                price = df_m1.iloc[i]["close"]
                
                poi = res["poi"]
                if bias == "bullish":
                    sl = poi["low"] 
                    risk = abs(price - sl)
                    tp = price + (risk * 2.0) 
                else:
                    sl = poi["high"]
                    risk = abs(sl - price)
                    tp = price - (risk * 2.0)

                outcome = simulate_trade_outcome(price, sl, tp, bias, i, df_m1)
                
                if outcome != "expired":
                    pnl = 20.0 if outcome == "win" else -10.0
                    
                    all_trades.append({
                        "time": now_time,
                        "symbol": symbol,
                        "grade": res.get("grade", "B"),
                        "score": res["score"],
                        "bias": bias,
                        "outcome": outcome,
                        "pnl": pnl
                    })
                    print(f"  [SIGNAL FOUND] {now_time} | Score: {res['score']} ({res.get('grade')}) | {outcome.upper()}")

    mt5.shutdown()
    return all_trades

if __name__ == "__main__":
    print("=== FrostBot SMC PRO Backtester (High Quality Only) ===")
    trades = run_backtest()
    
    if trades:
        df = pd.DataFrame(trades)
        print("\n" + "="*50)
        print(f"BACKTEST RESULTS (SCORE {MIN_SCORE_THRESHOLD}+)")
        print("="*50)
        print(f"Total Trades: {len(df)}")
        win_rate = (len(df[df['outcome']=='win'])/len(df))*100
        print(f"Win Rate:     {win_rate:.1f}%")
        print(f"Total Profit: ${df['pnl'].sum():.2f}")
        print("-" * 50)
        
        if "grade" in df.columns:
            grade_perf = df.groupby("grade").agg({'pnl': 'sum', 'outcome': 'count'})
            grade_perf.columns = ['Total PnL', 'Trade Count']
            print("Performance by Grade:")
            print(grade_perf)
        print("="*50)
    else:
        print(f"\nNo setups found with Score {MIN_SCORE_THRESHOLD}+.")