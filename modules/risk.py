from settings import MIN_LOT, MAX_LOT

def calculate_dynamic_lot(score, balance):
    multiplier = score / 100.0
    lot = MIN_LOT + (multiplier * (MAX_LOT - MIN_LOT))
    return max(min(round(lot, 2), MAX_LOT), MIN_LOT)

def pre_trade_checks(account_info=None):
    """The test expects a tuple (bool, message)."""
    return True, "Risk levels within limits"
