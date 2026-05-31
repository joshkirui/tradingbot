import pandas as pd
import numpy as np

# ==============================================================================
# --- 1. DETECTION ENGINE ---
# ==============================================================================

def detect_bias(df_h1: pd.DataFrame) -> str:
    """EMA9 vs EMA21 on H1 close to determine trend direction."""
    if len(df_h1) < 22:
        return "neutral"
    ema9  = df_h1["close"].tail(9).mean()
    ema21 = df_h1["close"].tail(21).mean()
    return "bullish" if ema9 > ema21 else "bearish" if ema9 < ema21 else "neutral"


def detect_choch_bos(df: pd.DataFrame, bias: str) -> dict:
    """
    Detects Break of Structure (BOS) or Change of Character (ChoCH).
    Looks back 50 candles for swing high/low break.
    """
    res = {"type": None, "level": None}
    if len(df) < 50:
        return res
    curr = df["close"].iloc[-1]

    if bias == "bullish":
        # BOS: current close breaks above highest high in last 50 candles
        lvl = df["high"].iloc[-50:-1].max()
        if curr > lvl:
            return {"type": "BOS", "level": lvl}
        # ChoCH: recent swing high breaks above previous swing high
        recent_high = df["high"].iloc[-15:-1].max()
        prev_high   = df["high"].iloc[-50:-15].max()
        if recent_high > prev_high and curr > recent_high:
            return {"type": "ChoCH", "level": recent_high}

    elif bias == "bearish":
        # BOS: current close breaks below lowest low in last 50 candles
        lvl = df["low"].iloc[-50:-1].min()
        if curr < lvl:
            return {"type": "BOS", "level": lvl}
        # ChoCH: recent swing low breaks below previous swing low
        recent_low = df["low"].iloc[-15:-1].min()
        prev_low   = df["low"].iloc[-50:-15].min()
        if recent_low < prev_low and curr < recent_low:
            return {"type": "ChoCH", "level": recent_low}

    return res


def detect_liquidity_sweep(df: pd.DataFrame, bias: str) -> bool:
    """
    Detects a liquidity grab: price wicks below/above a prior range
    extreme then closes back inside — classic stop hunt.
    """
    if len(df) < 30:
        return False
    prev_h = df['high'].iloc[-30:-2].max()
    prev_l = df['low'].iloc[-30:-2].min()
    curr   = df.iloc[-1]

    if bias == "bullish":
        return curr['low'] < prev_l and curr['close'] > prev_l
    if bias == "bearish":
        return curr['high'] > prev_h and curr['close'] < prev_h
    return False


def detect_order_block(df: pd.DataFrame, bias: str) -> dict | None:
    """
    Finds the most recent order block:
    - Bullish OB: last bearish candle before a strong bullish move
    - Bearish OB: last bullish candle before a strong bearish move
    """
    if len(df) < 5:
        return None
    for i in range(len(df) - 2, 2, -1):
        c = df.iloc[i]
        n = df.iloc[i + 1]
        if bias == "bullish" and c["close"] < c["open"] and n["close"] > c["high"]:
            return {"high": c["high"], "low": c["low"], "type": "OB"}
        if bias == "bearish" and c["close"] > c["open"] and n["close"] < c["low"]:
            return {"high": c["high"], "low": c["low"], "type": "OB"}
    return None


def detect_displacement(df: pd.DataFrame) -> bool:
    """
    Detects an impulsive displacement candle — any of the last 3 candles
    must be 1.3x larger than the 20-candle average body size.
    """
    if len(df) < 20:
        return False
    bodies     = (df["close"] - df["open"]).abs()
    avg        = bodies.tail(20).mean()
    recent_max = bodies.tail(3).max()
    return recent_max > (avg * 1.3)


def premium_discount_ok(df_h1: pd.DataFrame, bias: str, price: float) -> bool:
    """
    Checks whether price is in a valid entry zone:
    - Bullish entries should be in discount (below equilibrium) or up to 75% of range
    - Bearish entries should be in premium (above equilibrium) or down to 25% of range
    """
    if len(df_h1) < 40:
        return True
    h          = df_h1['high'].tail(40).max()
    l          = df_h1['low'].tail(40).min()
    eq         = (h + l) / 2
    range_size = h - l

    if bias == "bullish":
        if price < eq:                          return True   # Pure discount
        if price < (l + range_size * 0.75):    return True   # Upper mid-range allowed
        return False                                          # Too deep in premium
    else:
        if price > eq:                          return True   # Pure premium
        if price > (l + range_size * 0.25):    return True   # Lower mid-range allowed
        return False                                          # Too deep in discount


# ==============================================================================
# --- 2. MASTER SCORE ENGINE ---
# ==============================================================================

def score_setup(df_h1: pd.DataFrame, df_m1: pd.DataFrame, session_name: str, symbol: str = "") -> dict:

    # Crypto trades 24/7 — bypass session filter
    is_crypto = any(x in symbol.upper() for x in ["BTC", "ETH", "XRP"])

    VALID_SESSIONS = ["sydney_open", "asian", "london_open", "london", "ny_open", "new_york"]
    if not is_crypto and session_name not in VALID_SESSIONS:
        return {"valid": False, "reason": f"Session: {session_name}"}

    bias = detect_bias(df_h1)
    if bias == "neutral":
        return {"valid": False, "reason": "Neutral bias on H1"}

    price = df_m1['close'].iloc[-1]
    if not premium_discount_ok(df_h1, bias, price):
        return {"valid": False, "reason": f"Price not in zone (bias={bias}, price={price:.4f})"}

    score = 0

    struct = detect_choch_bos(df_m1, bias)
    if not struct["type"]:
        return {"valid": False, "reason": "No BOS/ChoCH detected"}
    score += 3

    swept = detect_liquidity_sweep(df_m1, bias)
    if swept: score += 3

    poi = detect_order_block(df_m1, bias)
    if poi: score += 2

    displaced = detect_displacement(df_m1)
    if displaced: score += 2

    if score >= 9:   grade = "S"
    elif score >= 7: grade = "A"
    elif score >= 5: grade = "B"
    else:            grade = "C"

    is_valid = score >= 5

    return {
        "valid":  is_valid,
        "score":  score,
        "grade":  grade,
        "bias":   bias,
        "poi":    poi,
        "struct": struct,
        "reason": None if is_valid else (
            f"Score {score}/5 | Sweep:{swept} | POI:{poi is not None} | Disp:{displaced}"
        ),
    }