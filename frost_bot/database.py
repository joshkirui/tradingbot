"""
FROST BOT 2.0 — Backtester
Pulls historical data directly from MT5 and replays the strategy engine
candle by candle across the full D1 → H4 → H1 → M15 stack.

Usage:
    python backtest.py
    python backtest.py --symbol EURUSD.m --days 180
"""

import argparse
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field

import pandas as pd
import MetaTrader5 as mt5

from modules.connector import connect, disconnect
from modules.data_engine import WATCHLIST, TIMEFRAME_MAP, normalize_symbol
from modules.strategy import (
    detect_bias,
    detect_choch_bos,
    detect_order_block,
    detect_fvg,
    detect_liquidity_sweep,
    detect_displacement,
    premium_discount_ok,
    get_session,
    session_score,
    build_entry,
    ScoreCard,
)
from modules.data_engine import get_atr


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_DAYS       = 180
DEFAULT_SYMBOLS    = WATCHLIST
MIN_SCORE          = 7
RISK_PER_TRADE_PCT = 0.01    # 1% risk per trade for backtest
SPREAD_PIPS        = 0.0002  # simulated spread (2 pips)


# ---------------------------------------------------------------------------
# Data fetch from MT5
# ---------------------------------------------------------------------------

def fetch_history(symbol: str, timeframe: str, days: int) -> pd.DataFrame:
    tf    = TIMEFRAME_MAP[timeframe]
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rates = mt5.copy_rates_from(symbol, tf, since, 99999)
    if rates is None or len(rates) == 0:
        return pd.DataFrame()
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.astype({
        "open": float, "high": float,
        "low": float, "close": float,
    })
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Trade simulation
# ---------------------------------------------------------------------------

@dataclass
class Trade:
    symbol:     str
    direction:  str          # "bullish" or "bearish"
    entry:      float
    sl:         float
    tp:         float
    score:      int
    grade:      str
    poi:        str
    entry_type: str
    open_time:  pd.Timestamp
    close_time: pd.Timestamp = None
    close_price: float       = 0.0
    pnl_r:      float        = 0.0   # P&L in R multiples
    outcome:    str          = ""    # "WIN", "LOSS", "BE", "OPEN"


def simulate_trade(trade: Trade, future: pd.DataFrame) -> Trade:
    """
    Walk forward through future candles and check if SL or TP is hit first.
    Returns the trade with outcome filled in.
    """
    for _, candle in future.iterrows():
        if trade.direction == "bullish":
            if candle["low"] <= trade.sl:
                trade.outcome    = "LOSS"
                trade.close_price = trade.sl
                trade.close_time  = candle["time"]
                trade.pnl_r       = -1.0
                return trade
            if candle["high"] >= trade.tp:
                trade.outcome    = "WIN"
                trade.close_price = trade.tp
                trade.close_time  = candle["time"]
                risk   = abs(trade.entry - trade.sl)
                reward = abs(trade.tp    - trade.entry)
                trade.pnl_r = round(reward / risk, 2) if risk > 0 else 0
                return trade
        else:
            if candle["high"] >= trade.sl:
                trade.outcome    = "LOSS"
                trade.close_price = trade.sl
                trade.close_time  = candle["time"]
                trade.pnl_r       = -1.0
                return trade
            if candle["low"] <= trade.tp:
                trade.outcome    = "WIN"
                trade.close_price = trade.tp
                trade.close_time  = candle["time"]
                risk   = abs(trade.entry - trade.sl)
                reward = abs(trade.tp    - trade.entry)
                trade.pnl_r = round(reward / risk, 2) if risk > 0 else 0
                return trade

    trade.outcome = "OPEN"
    return trade


# ---------------------------------------------------------------------------
# Strategy replay (candle by candle)
# ---------------------------------------------------------------------------

def replay_symbol(symbol: str, days: int) -> list[Trade]:
    symbol = normalize_symbol(symbol)
    print(f"\n  Fetching history for {symbol}...")

    df_d1  = fetch_history(symbol, "D1",  days + 50)
    df_h4  = fetch_history(symbol, "H4",  days + 50)
    df_h1  = fetch_history(symbol, "H1",  days + 50)
    df_m1  = fetch_history(symbol, "M1",  days + 5)

    if any(df.empty for df in [df_d1, df_h4, df_h1, df_m1]):
        print(f"  [!] Insufficient data for {symbol}")
        return []

    # Cutoff: only evaluate candles within the requested date range
    cutoff   = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
    m1_range = df_m1[df_m1["time"] >= cutoff].reset_index(drop=True)

    trades: list[Trade] = []
    seen_entries: set   = set()

    for i in range(50, len(m1_range)):
        candle_time = m1_range.iloc[i]["time"]

        # Slice all TFs up to this candle (no look-ahead)
        d1_slice = df_d1[df_d1["time"] <= candle_time].tail(100)
        h4_slice = df_h4[df_h4["time"] <= candle_time].tail(100)
        h1_slice = df_h1[df_h1["time"] <= candle_time].tail(100)
        m1_slice = df_m1[df_m1["time"] <= candle_time].tail(300)

        if len(m1_slice) < 30:
            continue

        # --- Strategy logic (mirrors score_setup) ---
        sc = ScoreCard()

        htf_bias = detect_bias(d1_slice)
        if htf_bias == "neutral":
            continue

        h4_struct = detect_choch_bos(h4_slice, htf_bias)
        if h4_struct["type"] in ("BOS", "CHOCH"):
            sc.htf_alignment = 2
        elif detect_bias(h4_slice) == htf_bias:
            sc.htf_alignment = 1

        h1_struct = detect_choch_bos(h1_slice, htf_bias)
        if h1_struct["type"] in ("BOS", "CHOCH"):
            sc.bos_confirmation = 1

        if detect_liquidity_sweep(m1_slice, htf_bias):
            sc.liquidity_sweep = 2
        elif detect_liquidity_sweep(h1_slice, htf_bias):
            sc.liquidity_sweep = 1

        if detect_displacement(m1_slice, htf_bias):
            sc.displacement = 2
        elif detect_displacement(h1_slice, htf_bias):
            sc.displacement = 1

        ob  = detect_order_block(m1_slice, htf_bias)
        fvg = detect_fvg(m1_slice, htf_bias)

        if fvg:
            sc.fvg_present = 1

        if premium_discount_ok(d1_slice, htf_bias):
            sc.clean_structure = 1

        session = get_session(m1_slice)
        sc.session_timing = session_score(session, htf_bias)

        if sc.total < MIN_SCORE:
            continue

        atr = get_atr(m1_slice)
        entry_zone, sl, tp, rr, poi_label, entry_type = build_entry(
            ob, fvg, atr, htf_bias, m1_slice
        )

        if entry_type == "none" or sl == 0 or tp == 0:
            continue

        # Entry price = mid of entry zone + simulated spread
        entry_mid = (entry_zone[0] + entry_zone[1]) / 2
        spread     = SPREAD_PIPS if htf_bias == "bullish" else -SPREAD_PIPS
        entry_price = round(entry_mid + spread, 5)

        # De-duplicate: skip if same zone already triggered recently
        zone_key = (symbol, round(entry_mid, 4), htf_bias)
        if zone_key in seen_entries:
            continue
        seen_entries.add(zone_key)

        # Build trade
        trade = Trade(
            symbol     = symbol,
            direction  = htf_bias,
            entry      = entry_price,
            sl         = sl,
            tp         = tp,
            score      = sc.total,
            grade      = sc.grade,
            poi        = poi_label,
            entry_type = entry_type,
            open_time  = candle_time,
        )

        # Simulate forward on M1
        future = m1_range.iloc[i + 1:i + 1000]
        trade  = simulate_trade(trade, future)
        trades.append(trade)

        # Skip ahead past this trade to avoid re-entering same move
        if trade.outcome in ("WIN", "LOSS"):
            seen_entries.discard(zone_key)

    return trades


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(all_trades: list[Trade], days: int):
    if not all_trades:
        print("\n  No trades found in backtest period.")
        return

    df = pd.DataFrame([{
        "symbol":     t.symbol,
        "direction":  t.direction,
        "score":      t.score,
        "grade":      t.grade,
        "poi":        t.poi,
        "entry_type": t.entry_type,
        "open_time":  t.open_time,
        "close_time": t.close_time,
        "outcome":    t.outcome,
        "pnl_r":      t.pnl_r,
    } for t in all_trades])

    closed  = df[df["outcome"].isin(["WIN", "LOSS"])]
    wins    = closed[closed["outcome"] == "WIN"]
    losses  = closed[closed["outcome"] == "LOSS"]

    total      = len(closed)
    win_count  = len(wins)
    loss_count = len(losses)
    win_rate   = win_count / total * 100 if total > 0 else 0
    total_r    = closed["pnl_r"].sum()
    avg_win_r  = wins["pnl_r"].mean()   if not wins.empty   else 0
    avg_loss_r = losses["pnl_r"].mean() if not losses.empty else 0
    profit_factor = (
        wins["pnl_r"].sum() / abs(losses["pnl_r"].sum())
        if not losses.empty and losses["pnl_r"].sum() != 0 else 0
    )

    print("\n" + "=" * 50)
    print(f"  FROST BOT — BACKTEST REPORT ({days} days)")
    print("=" * 50)
    print(f"  Symbols tested : {df['symbol'].nunique()}")
    print(f"  Total trades   : {total}")
    print(f"  Wins           : {win_count}")
    print(f"  Losses         : {loss_count}")
    print(f"  Win rate       : {win_rate:.1f}%")
    print(f"  Total R        : {total_r:+.2f}R")
    print(f"  Avg win        : {avg_win_r:.2f}R")
    print(f"  Avg loss       : {avg_loss_r:.2f}R")
    print(f"  Profit factor  : {profit_factor:.2f}")
    print("=" * 50)

    # Per-symbol breakdown
    print("\n  Per-symbol breakdown:")
    print(f"  {'Symbol':<15} {'Trades':>6} {'Win%':>6} {'Total R':>8} {'PF':>6}")
    print("  " + "-" * 45)
    for sym in df["symbol"].unique():
        s       = closed[closed["symbol"] == sym]
        if s.empty: continue
        sw      = s[s["outcome"] == "WIN"]
        sl_     = s[s["outcome"] == "LOSS"]
        wr      = len(sw) / len(s) * 100 if len(s) > 0 else 0
        tr      = s["pnl_r"].sum()
        pf      = (sw["pnl_r"].sum() / abs(sl_["pnl_r"].sum())
                   if not sl_.empty and sl_["pnl_r"].sum() != 0 else 0)
        print(f"  {sym:<15} {len(s):>6} {wr:>5.1f}% {tr:>+8.2f}R {pf:>6.2f}")

    # Per-grade breakdown
    print("\n  Per-grade breakdown:")
    for grade in ["A+", "A", "B"]:
        g = closed[closed["grade"] == grade]
        if g.empty: continue
        gw = g[g["outcome"] == "WIN"]
        wr = len(gw) / len(g) * 100
        tr = g["pnl_r"].sum()
        print(f"  {grade}: {len(g)} trades | {wr:.1f}% WR | {tr:+.2f}R")

    print("=" * 50)

    # Save to CSV
    out = "data/backtest_results.csv"
    import os; os.makedirs("data", exist_ok=True)
    df.to_csv(out, index=False)
    print(f"\n  Full results saved to {out}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_backtest(symbols: list[str], days: int):
    print("\n" + "=" * 50)
    print(f"  FROST BOT BACKTESTER — {days} days")
    print("=" * 50)

    if not connect():
        print("  [!] MT5 connection failed")
        return

    all_trades = []
    for symbol in symbols:
        trades = replay_symbol(symbol, days)
        all_trades.extend(trades)
        wins   = sum(1 for t in trades if t.outcome == "WIN")
        losses = sum(1 for t in trades if t.outcome == "LOSS")
        print(f"  {symbol}: {len(trades)} trades | {wins}W {losses}L")

    disconnect()
    print_report(all_trades, days)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Frost Bot Backtester")
    parser.add_argument("--symbol", type=str,  default=None,         help="Single symbol to test")
    parser.add_argument("--days",   type=int,  default=DEFAULT_DAYS, help="Days of history to test")
    args = parser.parse_args()

    symbols = [args.symbol] if args.symbol else DEFAULT_SYMBOLS
    run_backtest(symbols, args.days)