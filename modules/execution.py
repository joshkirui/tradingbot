import MetaTrader5 as mt5
from settings import RISK_REWARD_RATIO, BREAK_EVEN_RR, EA_MAGIC, ATR_SL_MULTIPLIER
from modules.risk import calculate_dynamic_lot

def get_symbol_info(symbol):
    """Fetch symbol properties: digits, point size, and volume steps."""
    si = mt5.symbol_info(symbol)
    if not si:
        print(f"[!] Error: Could not get info for {symbol}")
        return None
    return si

def place_order(symbol: str, direction: int, price: float, atr: float, confidence_score: float) -> dict:
    """
    direction: 1 = BUY, -1 = SELL
    Uses ATR to set Stop Loss and Strategy Confidence to set Lot Size.
    """
    si = get_symbol_info(symbol)
    if not si: return {"success": False, "error": "No symbol info"}

    # --- POINT CONVERTER LOGIC ---
    # We ensure SL is at least 'min_stop' distance away from price
    min_stop = si.type_stops_level * si.point
    sl_dist = max(atr * ATR_SL_MULTIPLIER, min_stop * 2)

    # Round SL/TP to correct decimal places for the specific symbol
    if direction == 1: # BUY
        order_type = mt5.ORDER_TYPE_BUY
        sl = round(price - sl_dist, si.digits)
        tp = round(price + (sl_dist * RISK_REWARD_RATIO), si.digits)
    else: # SELL
        order_type = mt5.ORDER_TYPE_SELL
        sl = round(price + sl_dist, si.digits)
        tp = round(price - (sl_dist * RISK_REWARD_RATIO), si.digits)

    # Calculate Lot based on Confidence Score
    acc = mt5.account_info()
    lot = calculate_dynamic_lot(confidence_score, acc.balance)

    # Send Market Order
    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       symbol,
        "volume":       lot,
        "type":         order_type,
        "price":        price,
        "sl":           sl,
        "tp":           tp,
        "magic":        EA_MAGIC,
        "comment":      f"FrostBot_{confidence_score}%",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC, # Use IOC for better execution
    }

    result = mt5.order_send(request)

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return {"success": False, "error": f"Error {result.retcode}: {result.comment}"}

    return {"success": True, "ticket": result.order, "lot": lot}

def manage_open_positions():
    """Handles Break-even and Partial Profit (50% at 2R)."""
    positions = mt5.positions_get(magic=EA_MAGIC)
    if not positions:
        return

    for pos in positions:
        si = get_symbol_info(pos.symbol)
        tick = mt5.symbol_info_tick(pos.symbol)
        
        cur_price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask
        open_price = pos.price_open
        risk_dist = abs(open_price - pos.sl) if pos.sl else 0
        
        if risk_dist <= 0: continue

        # Calculate Current Risk-to-Reward (RR)
        profit_dist = (cur_price - open_price) if pos.type == mt5.POSITION_TYPE_BUY else (open_price - cur_price)
        rr_current = profit_dist / risk_dist

        # 1. MOVE TO BREAK-EVEN
        if rr_current >= BREAK_EVEN_RR and pos.sl != open_price:
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": pos.ticket,
                "sl": open_price,
                "tp": pos.tp
            }
            mt5.order_send(request)
            print(f"[✓] BE set for {pos.symbol}")

        # 2. PARTIAL CLOSE (50% @ 2R)
        if rr_current >= 2.0 and pos.volume > (si.volume_min * 2):
            half_lot = round((pos.volume / 2) / si.volume_step) * si.volume_step
            close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
            
            close_request = {
                "action":    mt5.TRADE_ACTION_DEAL,
                "position":  pos.ticket,
                "symbol":    pos.symbol,
                "volume":    round(half_lot, 2),
                "type":      close_type,
                "price":     tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask,
                "magic":     EA_MAGIC,
                "comment":   "Partial 50% @ 2R"
            }
            mt5.order_send(close_request)
            print(f"[✓] Partial Profit taken on {pos.symbol}")