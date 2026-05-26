import MetaTrader5 as mt5
import pandas as pd

def get_candles(symbol, timeframe, n=200):
    try:
        # Ensure connection
        if not mt5.terminal_info():
            mt5.initialize()
        
        # Select symbol
        mt5.symbol_select(symbol, True)
        
        # The specific line causing the C++ exception - wrapped in a try
        rates = mt5.copy_rates_from_pos(str(symbol), int(timeframe), 0, int(n))
        
        if rates is None or len(rates) == 0:
            return pd.DataFrame()
            
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df
    except Exception as e:
        # If MT5 crashes, return an empty DF so the strategy doesnt crash
        return pd.DataFrame()

def get_atr(df, length=14):
    try:
        if df is None or df.empty or len(df) < length: return 0.1
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        return float(true_range.rolling(window=int(length)).mean().iloc[-1])
    except:
        return 0.1
