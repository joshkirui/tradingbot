import MetaTrader5 as mt5
from datetime import datetime, timedelta
from modules.alerts import send_telegram_log, alert_trade_closed

PROCESSED_TICKETS = set()

def get_filling_mode(symbol):
    info = mt5.symbol_info(symbol)
    if not info: return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_FOK if (info.filling_mode & 1) else mt5.ORDER_FILLING_IOC

def execute_institutional_order(symbol, setup, lots, magic):
    digits = mt5.symbol_info(symbol).digits
    request = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": float(lots),
        "type": mt5.ORDER_TYPE_BUY if setup["bias"] == "bullish" else mt5.ORDER_TYPE_SELL,
        "price": setup["entry"], "sl": round(setup["sl"], digits), "tp": round(setup["tp"], digits),
        "magic": magic, "comment": "Initial_Entry", "type_filling": get_filling_mode(symbol),
    }
    return mt5.order_send(request)

def check_closed_trades(magic):
    """Scans history for new closed trades and calculates RR."""
    global PROCESSED_TICKETS
    # Look back at history from last 15 minutes
    start = datetime.now() - timedelta(minutes=15)
    end = datetime.now()
    
    # Get history deals
    history = mt5.history_deals_get(start, end, group=f"*{magic}*")
    if not history: return

    for deal in history:
        # We only care about deals that close a position (Entry OUT)
        if deal.entry == mt5.DEAL_ENTRY_OUT:
            if deal.position_id not in PROCESSED_TICKETS:
                # Calculate RR: We need original risk. 
                # Calculation: Profit / (Lots * SL_Distance * TickValue)
                # For simplicity, we use deal.profit vs a base risk estimate
                
                # Try to get position info to see original risk (logic simplified for speed)
                profit = deal.profit + deal.commission + deal.swap
                
                # Logic: If it's a win, it's either a 5R partial or a 10R TP.
                # If profit is negative, it's -1R.
                # We calculate R based on the profit ratio.
                rr = 0
                if profit < 0: rr = -1.0
                else:
                    # Approximation based on your 1% risk rule
                    acc = mt5.account_info()
                    risk_unit = acc.balance * 0.01 
                    rr = profit / risk_unit if risk_unit > 0 else 0
                
                alert_trade_closed(deal.symbol, profit, rr, deal.comment)
                PROCESSED_TICKETS.add(deal.position_id)

def manage_trade_evolution(magic):
    # (Keep your existing BE @ 3R and Partials @ 5R logic here)
    # ... code from previous turn ...
    positions = mt5.positions_get(magic=magic)
    if not positions: return
    for pos in positions:
        initial_risk = abs(pos.price_open - pos.sl) if abs(pos.price_open - pos.sl) > 0 else abs(pos.price_open - pos.tp)/10
        if initial_risk == 0: continue
        current_rr = abs(pos.price_current - pos.price_open) / initial_risk

        if current_rr >= 3.0 and abs(pos.sl - pos.price_open) > 0.0001:
            mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "position": pos.ticket, "sl": pos.price_open, "tp": pos.tp})
            send_telegram_log(f"🛡️ {pos.symbol} moved to BE.")

        if current_rr >= 5.0 and pos.comment == "Initial_Entry" and pos.volume >= 0.02:
            part_vol = round((pos.volume / 2) / mt5.symbol_info(pos.symbol).volume_step) * mt5.symbol_info(pos.symbol).volume_step
            mt5.order_send({
                "action": mt5.TRADE_ACTION_DEAL, "position": pos.ticket, "symbol": pos.symbol, "volume": part_vol,
                "type": mt5.ORDER_TYPE_SELL if pos.type==0 else mt5.ORDER_TYPE_BUY, "magic": magic, 
                "comment": "Partials_Taken", "type_filling": get_filling_mode(pos.symbol),
            })
            send_telegram_log(f"💰 {pos.symbol} Partials Banked.")