import time
import pandas as pd
import MetaTrader5 as mt5

# ==============================================================================
# --- CONFIG ---
# ==============================================================================
MT5_LOGIN     = 2001385306
MT5_PASSWORD  = "Joshkirui@123"
MT5_SERVER    = "JustMarkets-Demo"
BROKER_SUFFIX = ".m"


# ==============================================================================
# --- SYMBOL NORMALIZER ---
# ==============================================================================
def normalize_symbol(symbol: str) -> str:
    s = symbol.upper()
    for suffix in [".STD", ".M"]:
        if s.endswith(suffix):
            s = s[:-len(suffix)]
            break
    return f"{s}{BROKER_SUFFIX}"


# ==============================================================================
# --- MT5 CONNECTION ---
# ==============================================================================
class MT5Connection:
    _initialized = False

    @classmethod
    def ensure(cls):
        if not cls._initialized or not mt5.terminal_info():
            if not mt5.initialize():
                print("[!] MT5 initialize() failed")
                return False
            if not mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
                print(f"[!] MT5 login failed: {mt5.last_error()}")
                return False
            cls._initialized = True
        return True


# ==============================================================================
# --- CANDLE FETCHER ---
# ==============================================================================
def get_candles(symbol: str, timeframe: str, n: int = 200) -> pd.DataFrame:
    if not MT5Connection.ensure():
        return pd.DataFrame()

    full_symbol = normalize_symbol(symbol)

    if not mt5.symbol_select(full_symbol, True):
        print(f"  [!] Symbol {full_symbol} not found in Market Watch.")
        return pd.DataFrame()

    tf_map = {
        "M1":  mt5.TIMEFRAME_M1,
        "M5":  mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "H1":  mt5.TIMEFRAME_H1,
        "H4":  mt5.TIMEFRAME_H4,
        "D1":  mt5.TIMEFRAME_D1,
    }
    mt5_tf = tf_map.get(timeframe, mt5.TIMEFRAME_M1)

    rates = None
    for attempt in range(3):
        rates = mt5.copy_rates_from_pos(full_symbol, mt5_tf, 0, n)
        if rates is not None and len(rates) > 0:
            break
        time.sleep(0.5)

    if rates is None or len(rates) == 0:
        err = mt5.last_error()
        print(f"  [-] MT5 Error for {full_symbol} {timeframe}: {err}")
        return pd.DataFrame()

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.rename(columns={"tick_volume": "volume"})
    return df[["time", "open", "high", "low", "close", "volume"]]


# ==============================================================================
# --- ATR ---
# ==============================================================================
def get_atr(df: pd.DataFrame, length: int = 14) -> float:
    if df is None or df.empty or len(df) < length:
        return 0.0001
    high      = df["high"]
    low       = df["low"]
    close     = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low,
         (high - prev_close).abs(),
         (low  - prev_close).abs()],
        axis=1
    ).max(axis=1)
    return float(tr.rolling(window=length).mean().iloc[-1])


# ==============================================================================
# --- SESSION DETECTOR (UTC-based, covers full 24h) ---
# ==============================================================================
def get_session(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "off_hours"
    hour = pd.to_datetime(df['time'].iloc[-1]).hour  # UTC

    if 22 <= hour or hour < 2:  return "sydney_open"   # 22:00 - 02:00 UTC
    if 2  <= hour < 7:          return "asian"          # 02:00 - 07:00 UTC
    if 7  <= hour < 9:          return "london_open"    # 07:00 - 09:00 UTC
    if 9  <= hour < 12:         return "london"         # 09:00 - 12:00 UTC
    if 12 <= hour < 14:         return "ny_open"        # 12:00 - 14:00 UTC
    if 14 <= hour < 17:         return "new_york"       # 14:00 - 17:00 UTC
    return "off_hours"                                  # 17:00 - 22:00 UTC (dead zone)