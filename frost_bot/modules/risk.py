import MetaTrader5 as mt5
from datetime import datetime

def calculate_lots(symbol, entry, sl, risk_pct=0.01):
    acc = mt5.account_info()
    sym = mt5.symbol_info(symbol)
    if not acc or not sym: return 0.0
    
    risk_usd = acc.balance * risk_pct
    dist = abs(entry - sl) / sym.point
    if dist == 0: return 0.0
    
    lots = risk_usd / (dist * sym.trade_tick_value)
    lots = round(lots / sym.volume_step) * sym.volume_step
    
    if lots < sym.volume_min:
        # Emergency safety: Check if 0.01 is too much risk (>5%)
        if (sym.volume_min * dist * sym.trade_tick_value) > (acc.balance * 0.05):
            return 0.0
        return sym.volume_min
    return min(lots, sym.volume_max)

def pre_trade_checks(magic, score):
    start = datetime.now().replace(hour=0, minute=0, second=0)
    history = mt5.history_deals_get(start, datetime.now(), group=f"*{magic}*")
    losses = sum(1 for d in history if d.entry == mt5.DEAL_ENTRY_OUT and d.profit < 0) if history else 0
    if losses >= 5 and score < 10:
        return False, "5 Loss Cooldown"
    return True, "OK"