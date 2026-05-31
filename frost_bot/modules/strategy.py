import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Literal

# Import from your other bot modules
from modules.data_engine import get_candles, get_atr, normalize_symbol, get_session
from modules.logic import (
    detect_bias, 
    detect_choch_bos, 
    detect_order_block, 
    detect_fvg, 
    detect_displacement,
    detect_inducement_zone,
    detect_liquidity_sweep,
    premium_discount_ok,
    detect_indicator_signals
)

# ---------------------------------------------------------------------------
# 1. TYPES & DATA CLASSES
# ---------------------------------------------------------------------------
Bias      = Literal["bullish", "bearish", "neutral"]
EntryType = Literal["aggressive", "confirmed", "continuation", "none"]
Grade     = Literal["A+", "A", "B", "avoid"]

@dataclass
class ScoreCard:
    htf_alignment:    int = 0   
    liquidity_sweep:  int = 0   
    displacement:     int = 0   
    fvg_present:      int = 0   
    session_timing:   int = 0   
    bos_confirmation: int = 0   
    clean_structure:  int = 0   

    @property
    def total(self) -> int:
        return (self.htf_alignment + self.liquidity_sweep + self.displacement + 
                self.fvg_present + self.session_timing + self.bos_confirmation + self.clean_structure)

    def to_dict(self) -> dict:
        return {"total": self.total, "grade": self.grade}

    @property
    def grade(self) -> Grade:
        t = self.total
        if t >= 8: return "A+"
        if t >= 6: return "A"
        if t >= 5: return "B" 
        return "avoid"

@dataclass
class SetupResult:
    symbol:       str
    bias:         Bias
    score:        ScoreCard
    entry_type:   EntryType
    entry_zone:   tuple[float, float]
    sl:           float
    tp:           float
    rr:           float
    poi_type:     str
    notes:        list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.score.total >= 5 and self.entry_type != "none"

    def to_dict(self) -> dict:
        return {
            "symbol":     self.symbol,
            "bias":       self.bias,
            "score":      {"total": self.score.total, "grade": self.score.grade},
            "entry_type": self.entry_type,
            "entry_zone": self.entry_zone,
            "sl":         self.sl,
            "tp":         self.tp,
            "rr":         round(self.rr, 2),
            "poi_type":   self.poi_type,
            "valid":      self.is_valid,
            "notes":      self.notes,
        }

# ---------------------------------------------------------------------------
# 2. SCORING HELPERS
# ---------------------------------------------------------------------------
def session_score(session_name: str) -> int:
    killzones = ["london_open", "ny_open"]
    return 1 if session_name in killzones else 0

def detect_breaker_block(df: pd.DataFrame, bias: Bias) -> dict | None:
    if df is None or len(df) < 15: return None
    try:
        for i in range(len(df) - 12, 5, -1):
            c = df.iloc[i]
            if bias == "bullish" and c["close"] < c["open"] and df["close"].iloc[-1] > c["high"]:
                return {"high": c["high"], "low": c["low"], "type": "Breaker Block"}
            if bias == "bearish" and c["close"] > c["open"] and df["close"].iloc[-1] < c["low"]:
                return {"high": c["high"], "low": c["low"], "type": "Breaker Block"}
    except:
        return None
    return None

def detect_inversion_fvg(df: pd.DataFrame, bias: Bias) -> dict | None:
    if df is None or len(df) < 10: return None
    try:
        for i in range(len(df) - 10, 2, -1):
            p, n = df.iloc[i-1], df.iloc[i+1]
            if bias == "bullish" and p["low"] > n["high"] and df["close"].iloc[-1] > p["low"]:
                return {"high": p["low"], "low": n["high"], "type": "Inversion FVG"}
            if bias == "bearish" and p["high"] < n["low"] and df["close"].iloc[-1] < p["high"]:
                return {"high": n["low"], "low": p["high"], "type": "Inversion FVG"}
    except:
        return None
    return None

def build_entry_high_freq(pois: list, atr: float, bias: Bias, price: float):
    valid_pois = [p for p in pois if p is not None]
    if not valid_pois:
        return (price, price), price, price, 0.0, "None", "none"
    valid_pois.sort(key=lambda x: abs(x['high'] - price))
    best_poi = valid_pois[0]
    low, high = best_poi["low"], best_poi["high"]
    if bias == "bullish":
        sl = low - (atr * 0.7)
        tp = price + (atr * 4.0)
        rr = (tp - price) / (price - sl) if (price - sl) > 0 else 0
        return (low, high), sl, tp, rr, best_poi["type"], "aggressive"
    else:
        sl = high + (atr * 0.7)
        tp = price - (atr * 4.0)
        rr = (price - tp) / (sl - price) if (sl - price) > 0 else 0
        return (low, high), sl, tp, rr, best_poi["type"], "aggressive"

# Alias for compatibility
build_entry = build_entry_high_freq

# ---------------------------------------------------------------------------
# 3. MAIN SCORE SETUP (Logic starts here)
# ---------------------------------------------------------------------------
def score_setup(symbol: str) -> dict:
    symbol = normalize_symbol(symbol)
    notes = []
    sc = ScoreCard()

    df_h1 = get_candles(symbol, "H1", 100)
    df_m15 = get_candles(symbol, "M15", 100)
    df_m1 = get_candles(symbol, "M1", 200)

    if df_h1.empty or df_m1.empty:
        return {"valid": False, "notes": ["Missing Data"]}

    htf_bias = detect_bias(df_h1)
    notes.append(f"H1 Bias: {htf_bias}")
    if htf_bias == "neutral":
        return {"valid": False, "notes": ["Neutral Bias"]}

    if premium_discount_ok(df_h1, htf_bias):
        sc.clean_structure = 1
        notes.append("Correct Premium/Discount zone (+1)")

    m15_shift = detect_choch_bos(df_m15, htf_bias)
    if m15_shift["type"]:
        sc.htf_alignment = 2
        sc.bos_confirmation = 1
        notes.append(f"M15 {m15_shift['type']} (+3)")

    # Indicator Confluence
    indicator_sig = detect_indicator_signals(df_m1)
    if indicator_sig == "long" and htf_bias == "bullish":
        sc.displacement += 1
        notes.append("T&M Master: Bullish Confluence (+1)")
    elif indicator_sig == "short" and htf_bias == "bearish":
        sc.displacement += 1
        notes.append("T&M Master: Bearish Confluence (+1)")

    atr = get_atr(df_m1)
    price = df_m1["close"].iloc[-1]
    poi_stack = [
        detect_order_block(df_m1, htf_bias),
        detect_fvg(df_m1, htf_bias),
        detect_breaker_block(df_m1, htf_bias),
        detect_inversion_fvg(df_m1, htf_bias)
    ]

    if detect_liquidity_sweep(df_m1, htf_bias):
        sc.liquidity_sweep = 2
        notes.append("Liquidity Sweep confirmed (+2)")
    else:
        idm = detect_inducement_zone(df_m1, htf_bias)
        if idm:
            sc.liquidity_sweep = 1
            poi_stack.append(idm)
            notes.append("Inducement found (+1)")

    if any(p and 'FVG' in p['type'] for p in poi_stack):
        sc.fvg_present = 1
    if detect_displacement(df_m1, htf_bias):
        sc.displacement += 1
    
    session_name = get_session(df_m1)
    sc.session_timing = session_score(session_name)
    notes.append(f"Session: {session_name}")

    entry_zone, sl, tp, rr, poi_label, entry_type = build_entry_high_freq(
        poi_stack, atr, htf_bias, price
    )

    result = SetupResult(
        symbol=symbol, bias=htf_bias, score=sc, entry_type=entry_type,
        entry_zone=entry_zone, sl=sl, tp=tp, rr=rr, poi_type=poi_label, notes=notes
    )

    return result.to_dict()

# ---------------------------------------------------------------------------
# 4. SCANNER (The likely cause of your indentation error)
# ---------------------------------------------------------------------------
def scan_watchlist(symbols: list[str]) -> list[dict]:
    results = []
    print(f"--- Scanning {len(symbols)} symbols | Ultra-High Volume Mode ---")
    for symbol in symbols:
        try:
            r = score_setup(symbol)
            if r["valid"]:
                results.append(r)
                print(f" [✓] {symbol} | Score: {r['score']['total']} | POI: {r['poi_type']}")
        except Exception as e:
            # Added a pass to ensure the block is never empty
            print(f"Error scanning {symbol}: {e}")
            continue
    return results