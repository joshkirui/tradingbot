import time
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

from modules.data_engine import get_candles, normalize_symbol, MT5Connection, get_session
from modules.logic import score_setup

# ==============================================================================
# --- CONFIGURATION ---
# ==============================================================================
MAGIC_NUMBER  = 202405
WATCHLIST     = [
    "BTCUSD", "XAUUSD",
    "EURUSD",  "GBPUSD", "AUDUSD",
    "USDJPY",  "USDCAD", "USDCHF",
]

MIN_SCORE_THRESHOLD = 5      # Minimum score to take a trade (5 = BOS + 1 confluence)
MAX_LOT_SIZE        = 5.0    # Hard cap on lot size
RISK_REWARD         = 2.0    # Take profit at 2x the risk distance
POLLING_INTERVAL    = 60     # Seconds between full scans
USE_SILVER_CONFIRM  = False  # Set True to require XAGUSD to agree with XAUUSD bias

# Per-symbol minimum SL distance in points
MIN_SL_POINTS = {
    "XAUUSD":  500,    # Gold:  min 50 cents
    "BTCUSD":  5000,   # BTC:   min $50
    "DEFAULT": 50,     # Forex: min 5 pips
}
# ==============================================================================


def get_min_sl_points(symbol: str) -> int:
    for key, val in MIN_SL_POINTS.items():
        if key in symbol:
            return val
    return MIN_SL_POINTS["DEFAULT"]


def calculate_dynamic_lot(symbol: str, score: int, entry_price: float, sl_price: float) -> float:
    risk_map = {
        5:  0.003,
        6:  0.005,
        7:  0.0075,
        8:  0.01,
        9:  0.015,
        10: 0.02,
    }
    risk_percent = risk_map.get(score, 0.003)

    account = mt5.account_info()
    if account is None:
        return 0.01

    balance     = account.balance
    risk_amount = balance * risk_percent

    sl_distance = abs(entry_price - sl_price)
    if sl_distance == 0:
        return 0.01

    sym_info = mt5.symbol_info(symbol)
    if sym_info is None:
        return 0.01

    tick_value = sym_info.trade_tick_value
    tick_size  = sym_info.trade_tick_size
    if tick_value <= 0 or tick_size <= 0:
        return 0.01

    lots = risk_amount / ((sl_distance / tick_size) * tick_value)
    lots = round(lots / sym_info.volume_step) * sym_info.volume_step
    lots = min(lots, MAX_LOT_SIZE, sym_info.volume_max)
    lots = max(lots, sym_info.volume_min)
    return round(lots, 2)


def get_filling_mode(symbol: str) -> int:
    info = mt5.symbol_info(symbol)
    if info is None:
        return 2
    fm = info.filling_mode
    if fm & 1: return 0   # FOK
    if fm & 2: return 1   # IOC
    return 2               # RETURN


def has_open_position(symbol: str) -> bool:
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return False
    return any(p.magic == MAGIC_NUMBER for p in positions)


def execute_trade(symbol, bias, price, sl, tp, score, grade, lot_size):
    order_type = mt5.ORDER_TYPE_BUY if bias == "bullish" else mt5.ORDER_TYPE_SELL
    filling    = get_filling_mode(symbol)
    sym_info   = mt5.symbol_info(symbol)
    if sym_info is None:
        return
    digits = sym_info.digits

    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       symbol,
        "volume":       lot_size,
        "type":         order_type,
        "price":        price,
        "sl":           round(sl, digits),
        "tp":           round(tp, digits),
        "deviation":    20,
        "magic":        MAGIC_NUMBER,
        "comment":      f"Frost {grade}({score})",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }

    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        msg     = result.comment if result else "Connection Error"
        retcode = result.retcode if result else "N/A"
        print(f"  [!] {symbol} FAILED | Code: {retcode} | {msg}")
    else:
        direction = "BUY" if bias == "bullish" else "SELL"
        print(f"  [✓] {direction} {symbol} | Grade:{grade} Score:{score} | "
              f"Lots:{lot_size} | Entry:{price} SL:{round(sl,digits)} TP:{round(tp,digits)}")


def get_symbol_bias(base_symbol: str):
    """Returns bias for a symbol — used for Silver confirmation on Gold."""
    symbol  = normalize_symbol(base_symbol)
    df_h1   = get_candles(symbol, "H1", 100)
    df_m1   = get_candles(symbol, "M1", 500)
    if df_h1 is None or df_h1.empty or df_m1 is None or df_m1.empty:
        return None
    session = get_session(df_m1)
    # ✅ Pass symbol so crypto bypass works here too
    res = score_setup(df_h1, df_m1, session, symbol=symbol)
    return res["bias"] if res.get("valid") else None


def log_result(symbol: str, res: dict):
    if not res.get("valid"):
        reason = res.get("reason", "Unknown")
        print(f"  [-] {symbol:<12} | INVALID | {reason}")
    else:
        score = res.get("score", "?")
        bias  = res.get("bias", "?")
        grade = res.get("grade", "?")
        print(f"  [+] {symbol:<12} | Score:{score} Grade:{grade} Bias:{bias} — QUALIFIES")


def run_live_bot():
    print("=" * 65)
    print("  FrostBot LIVE")
    print(f"  Symbols : {len(WATCHLIST)} | Min Score: {MIN_SCORE_THRESHOLD} | RR: {RISK_REWARD}")
    print(f"  Silver Confirm: {USE_SILVER_CONFIRM}")
    print("=" * 65)

    while True:
        try:
            MT5Connection.ensure()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"\n[{now}] Scanning {len(WATCHLIST)} symbols...")

            for base_symbol in WATCHLIST:
                symbol = normalize_symbol(base_symbol)

                if has_open_position(symbol):
                    print(f"  [~] {symbol:<12} | Position open, skipping")
                    continue

                df_h1 = get_candles(symbol, "H1", 100)
                df_m1 = get_candles(symbol, "M1", 500)

                if df_m1 is None or df_m1.empty:
                    print(f"  [!] {symbol:<12} | No M1 data")
                    continue

                session = get_session(df_m1)

                # ✅ FIXED: symbol now passed so crypto bypasses session filter
                res = score_setup(df_h1, df_m1, session, symbol=symbol)

                log_result(symbol, res)

                if not res.get("valid") or res.get("score", 0) < MIN_SCORE_THRESHOLD:
                    continue

                bias = res["bias"]

                # Optional Silver confirmation for Gold
                if "XAUUSD" in symbol and USE_SILVER_CONFIRM:
                    silver_bias = get_symbol_bias("XAGUSD")
                    if silver_bias != bias:
                        print(f"  [x] Gold blocked — Silver({silver_bias}) ≠ Gold({bias})")
                        continue

                tick = mt5.symbol_info_tick(symbol)
                if tick is None:
                    print(f"  [!] {symbol} | No tick data")
                    continue

                entry_price = tick.ask if bias == "bullish" else tick.bid

                poi = res.get("poi")
                if poi is None:
                    print(f"  [x] {symbol} | No POI for SL — skipping")
                    continue

                sl_price = poi["low"] if bias == "bullish" else poi["high"]
                dist     = abs(entry_price - sl_price)
                sym_info = mt5.symbol_info(symbol)

                min_points = get_min_sl_points(symbol)
                if dist < sym_info.point * min_points:
                    print(f"  [x] {symbol} | SL too tight: {dist:.5f}")
                    continue

                tp_price = entry_price + (dist * RISK_REWARD) if bias == "bullish" \
                           else entry_price - (dist * RISK_REWARD)

                lots = calculate_dynamic_lot(symbol, res["score"], entry_price, sl_price)

                execute_trade(
                    symbol, bias, entry_price, sl_price, tp_price,
                    res["score"], res.get("grade", "B"), lots
                )

            print(f"  Sleeping {POLLING_INTERVAL}s...")
            time.sleep(POLLING_INTERVAL)

        except KeyboardInterrupt:
            print("\n[STOPPED] Bot shut down by user.")
            break

        except Exception as e:
            import traceback
            print(f"[ERROR] {str(e)}")
            traceback.print_exc()
            time.sleep(15)


if __name__ == "__main__":
    run_live_bot()