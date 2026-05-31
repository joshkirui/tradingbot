import MetaTrader5 as mt5
from modules.data_engine import normalize_symbol
from modules.risk import calculate_dynamic_lot
from settings import BREAK_EVEN_RR, EA_MAGIC


def get_symbol_info(symbol: str):
    """Fetch symbol properties: digits, point size, volume steps."""
    si = mt5.symbol_info(symbol)
    if not si:
        print(f"[!] Error: Could not get info for {symbol}")
        return None
    return si


def place_order(
    symbol:    str,
    direction: int,    # 1 = BUY, -1 = SELL
    price:     float,
    sl:        float,  # Pre-calculated by strategy engine
    tp:        float,  # Pre-calculated by strategy engine
    score:     int,    # 0–10 from ScoreCard
) -> dict:
    """
    Places a market order using SL/TP from the strategy engine.

    SL and TP are computed by score_setup() and passed in directly —
    no ATR recalculation here. Lot size is derived from the score (0–10).
    """
    symbol = normalize_symbol(symbol)
    si     = get_symbol_info(symbol)
    if not si:
        return {"success": False, "error": "No symbol info"}

    # --- Validate SL distance meets broker minimum ---
    min_stop = si.type_stops_level * si.point
    sl_dist  = abs(price - sl)

    if sl_dist < min_stop:
        # Widen SL to meet broker minimum if strategy SL is too tight
        if direction == 1:
            sl = round(price - min_stop * 2, si.digits)
        else:
            sl = round(price + min_stop * 2, si.digits)
        print(f"[!] SL widened to meet broker minimum for {symbol}")

    # --- Round SL/TP to symbol precision ---
    sl = round(sl, si.digits)
    tp = round(tp, si.digits)

    # --- Order type ---
    order_type = mt5.ORDER_TYPE_BUY if direction == 1 else mt5.ORDER_TYPE_SELL

    # --- Lot size from score (0–10 mapped to confidence %) ---
    acc        = mt5.account_info()
    confidence = score * 10   # e.g. score 8 → 80% confidence
    lot        = calculate_dynamic_lot(confidence, acc.balance)

    # --- Build request ---
    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       symbol,
        "volume":       lot,
        "type":         order_type,
        "price":        price,
        "sl":           sl,
        "tp":           tp,
        "magic":        EA_MAGIC,
        "comment":      f"FrostBot_score{score}",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"[!] Order failed for {symbol}: {result.retcode} — {result.comment}")
        return {"success": False, "error": f"{result.retcode}: {result.comment}"}

    print(f"[✓] Order placed: {symbol} {'BUY' if direction == 1 else 'SELL'} "
          f"| Lot: {lot} | SL: {sl} | TP: {tp} | Score: {score}/10")

    return {"success": True, "ticket": result.order, "lot": lot}


def manage_open_positions():
    """
    Handles break-even and partial profit (50% close at 2R).
    Runs every loop cycle before new scans.
    """
    positions = mt5.positions_get(magic=EA_MAGIC)
    if not positions:
        return

    for pos in positions:
        si   = get_symbol_info(pos.symbol)
        tick = mt5.symbol_info_tick(pos.symbol)
        if not si or not tick:
            continue

        cur_price  = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask
        open_price = pos.price_open
        risk_dist  = abs(open_price - pos.sl) if pos.sl else 0

        if risk_dist <= 0:
            continue

        profit_dist = (
            (cur_price - open_price) if pos.type == mt5.POSITION_TYPE_BUY
            else (open_price - cur_price)
        )
        rr_current = profit_dist / risk_dist

        # 1. MOVE TO BREAK-EVEN
        if rr_current >= BREAK_EVEN_RR and pos.sl != open_price:
            be_request = {
                "action":   mt5.TRADE_ACTION_SLTP,
                "position": pos.ticket,
                "sl":       open_price,
                "tp":       pos.tp,
            }
            r = mt5.order_send(be_request)
            if r.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"[✓] Break-even set: {pos.symbol} ticket #{pos.ticket}")
            else:
                print(f"[!] BE failed for {pos.symbol}: {r.retcode}")

        # 2. PARTIAL CLOSE — 50% at 2R
        if rr_current >= 2.0 and pos.volume > (si.volume_min * 2):
            half_lot   = round(
                round((pos.volume / 2) / si.volume_step) * si.volume_step, 2
            )
            close_type = (
                mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY
                else mt5.ORDER_TYPE_BUY
            )
            close_price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask

            close_request = {
                "action":       mt5.TRADE_ACTION_DEAL,
                "position":     pos.ticket,
                "symbol":       pos.symbol,
                "volume":       half_lot,
                "type":         close_type,
                "price":        close_price,
                "magic":        EA_MAGIC,
                "comment":      "FrostBot_partial_2R",
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            r = mt5.order_send(close_request)
            if r.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"[✓] Partial close 50% @ 2R: {pos.symbol} ticket #{pos.ticket}")
            else:
                print(f"[!] Partial close failed for {pos.symbol}: {r.retcode}")