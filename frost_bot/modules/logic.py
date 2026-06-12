import pandas as pd
import numpy as np

def identify_single_area(df):
    if len(df) < 10: return None
    for i in range(len(df)-2, 5, -1):
        curr, prev = df.iloc[i], df.iloc[i-1]
        if abs(curr['close'] - curr['open']) > abs(prev['close'] - prev['open']) * 2.0:
            return {"high": prev['high'], "low": prev['low']}
    return None

def score_setup(symbol, df_mn1, df_d1, df_h4, df_m30, df_m5):
    # 1. Monthly Bias
    mn_bias = "bullish" if df_mn1["close"].iloc[-1] > df_mn1["open"].iloc[-1] else "bearish"

    # 2. Refined M30 POI
    m30_area = identify_single_area(df_m30)
    if not m30_area: return {"valid": False, "reason": "No M30 POI"}

    # 3. M5 Model
    curr_m5 = df_m5.iloc[-1]
    lookback = df_m5.tail(15)
    
    # Consolidation Check
    if (lookback["high"].max() - lookback["low"].min()) < (abs(curr_m5["close"]-curr_m5["open"])*1.5):
        return {"valid": False, "reason": "Consolidation"}

    if mn_bias == "bullish":
        x_low = lookback["low"].iloc[:-1].min()
        if not (curr_m5["low"] < x_low and curr_m5["close"] > x_low): 
            return {"valid": False, "reason": "Waiting for Sweep"}
        sl = curr_m5["low"]
        tp = df_h4["high"].iloc[-20:].max()
    else:
        x_high = lookback["high"].iloc[:-1].max()
        if not (curr_m5["high"] > x_high and curr_m5["close"] < x_high): 
            return {"valid": False, "reason": "Waiting for Sweep"}
        sl = curr_m5["high"]
        tp = df_h4["low"].iloc[-20:].min()

    # 4. Momentum Deletion
    avg_body = (df_m5['close'] - df_m5['open']).abs().tail(15).mean()
    if abs(curr_m5['close'] - curr_m5['open']) > (avg_body * 3.5):
        return {"valid": False, "reason": "High Momentum"}

    # 5. Risk & 10RR Cap
    entry = curr_m5["close"]
    risk = abs(entry - sl)
    min_risk = 0.00035 if "JPY" not in symbol else 0.035
    if risk < min_risk: risk = min_risk
    
    rr = abs(tp - entry) / risk
    if rr < 2.5: return {"valid": False, "reason": "Low RR"}
    if rr > 10.0:
        rr = 10.0
        tp = entry + (risk * 10) if mn_bias == "bullish" else entry - (risk * 10)

    return {"valid": True, "bias": mn_bias, "entry": entry, "sl": sl, "tp": tp, "rr": rr, "score": 10}