import MetaTrader5 as mt5
import pandas as pd
import time

def normalize_symbol(symbol: str) -> str:
    sym_info = mt5.symbols_get(group=f"*{symbol}*")
    return sym_info[0].name if sym_info else symbol

def get_candles(symbol: str, timeframe_str: str, n: int = 100) -> pd.DataFrame:
    tf_map = {
        "MN1": mt5.TIMEFRAME_MN1, "D1": mt5.TIMEFRAME_D1, "H4": mt5.TIMEFRAME_H4,
        "M30": mt5.TIMEFRAME_M30, "M5": mt5.TIMEFRAME_M5
    }
    symbol = normalize_symbol(symbol)
    
    # Ensure symbol is visible in MarketWatch
    mt5.symbol_select(symbol, True)
    
    # Try to fetch data with a quick retry if MT5 is syncing
    rates = None
    for _ in range(3):
        rates = mt5.copy_rates_from_pos(symbol, tf_map.get(timeframe_str, mt5.TIMEFRAME_M5), 0, n)
        if rates is not None and len(rates) > 0:
            break
        time.sleep(0.2) # Small pause to let MT5 sync

    if rates is None or len(rates) == 0:
        return pd.DataFrame()
        
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df