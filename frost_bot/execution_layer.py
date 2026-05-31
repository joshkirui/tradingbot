import os, time, math, requests
import MetaTrader5 as mt5
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

MT5_LOGIN    = int(os.getenv("MT5_LOGIN", "2001385306"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "Joshkirui@123")
MT5_SERVER   = os.getenv("MT5_SERVER",   "JustMarkets-Demo")
MAGIC_NUMBER = int(os.getenv("MAGIC_NUMBER", "20240525"))
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN",   "8964245113:AAFhkOde3G_s4acBhqiO1-BFrRMEbS8OSR0")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "7890036882")

SYMBOLS       = ["EURUSD", "GBPUSD", "USDJPY", "BTCUSD", "XAGUSD"]
BREAK_EVEN_RR = 1.5
MIN_LOT       = 0.01
MAX_LOT       = 0.10
RISK_PERCENT  = 1.0
MAX_TRADES    = 3
SLIPPAGE      = 10
MIN_RR        = 1.5
SCAN_INTERVAL = 60


def mt5_connect():
    if not mt5.initialize():
        print("[MT5] initialize() failed:", mt5.last_error())
        return False
    if not mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        print("[MT5] login failed:", mt5.last_error())
        mt5.shutdown()
        return False
    i = mt5.account_info()
    print(f"[MT5] Connected | {i.login} | Balance: {i.balance} {i.currency}")
    return True


def mt5_disconnect():
    mt5.shutdown()


def count_open_trades():
    p = mt5.positions_get()
    return sum(1 for x in p if x.magic == MAGIC_NUMBER) if p else 0


def already_in_symbol(symbol):
    e = mt5.positions_get(symbol=symbol)
    return bool(e and any(x.magic == MAGIC_NUMBER for x in e))


def calculate_lot_size(symbol, sl_price, entry_price):
    a = mt5.account_info()
    s = mt5.symbol_info(symbol)
    if not a or not s:
        return None
    dist = abs(entry_price - sl_price)
    if dist == 0:
        return None
    risk = a.balance * (RISK_PERCENT / 100)
    pv   = s.trade_tick_value / s.trade_tick_size
    lots = math.floor((risk / (dist * pv)) / s.volume_step) * s.volume_step
    return round(max(MIN_LOT, min(lots, MAX_LOT)), 2)


def check_break_even():
    positions = mt5.positions_get()
    if not positions:
        return
    for pos in positions:
        if pos.magic != MAGIC_NUMBER or not pos.sl or not pos.tp:
            continue
        entry = pos.price_open
        risk  = abs(entry - pos.sl)
        if not risk:
            continue
        tick = mt5.symbol_info_tick(pos.symbol)
        if not tick:
            continue
        if pos.type == mt5.ORDER_TYPE_BUY:
            be_hit = (tick.bid - entry) >= risk * BREAK_EVEN_RR
            done   = pos.sl >= entry
        else:
            be_hit = (entry - tick.ask) >= risk * BREAK_EVEN_RR
            done   = pos.sl <= entry
        if be_hit and not done:
            s      = mt5.symbol_info(pos.symbol)
            new_sl = round(entry, s.digits)
            r      = mt5.order_send({
                "action":   mt5.TRADE_ACTION_SLTP,
                "position": pos.ticket,
                "sl":       new_sl,
                "tp":       pos.tp,
            })
            if r.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"[BE] {pos.symbol} SL moved to {new_sl}")
                _tg_post(f"Break-even hit | {pos.symbol} | SL to {new_sl}")


def place_order(symbol, bias, sl, tp, lots):
    s = mt5.symbol_info(symbol)
    if not s:
        return False
    if not s.visible:
        mt5.symbol_select(symbol, True)
        time.sleep(0.1)
    tick = mt5.symbol_info_tick(symbol)
    ot   = mt5.ORDER_TYPE_BUY if bias == "bullish" else mt5.ORDER_TYPE_SELL
    px   = tick.ask if bias == "bullish" else tick.bid
    r    = mt5.order_send({
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       symbol,
        "volume":       lots,
        "type":         ot,
        "price":        px,
        "sl":           round(sl, s.digits),
        "tp":           round(tp, s.digits),
        "deviation":    SLIPPAGE,
        "magic":        MAGIC_NUMBER,
        "comment":      "FrostBot_SMC",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    })
    if r.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"[ORDER] {bias.upper()} {symbol} {lots} lots | SL {sl:.5f} TP {tp:.5f} #{r.order}")
        return True
    print(f"[ORDER] Failed {symbol}: {r.retcode} {r.comment}")
    return False


def _tg_post(text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception as e:
        print(f"[TG] {e}")


def send_telegram(setup, executed, lots=None):
    flag   = "BUY" if setup["bias"] == "bullish" else "SELL"
    status = "TRADE PLACED" if executed else "ALERT ONLY"
    score  = setup["score"]
    _tg_post(
        f"[{flag}] FrostBot - {setup['symbol']}\n"
        f"Grade: {score['grade']} | Score: {score['total']}/10\n"
        f"SL: {setup['sl']:.5f} | TP: {setup['tp']:.5f} | RR: {setup['rr']:.2f}\n"
        f"Status: {status}"
    )


def execute_valid_setups():
    from modules.score_engine import score_setup
    print(f"Scanning {len(SYMBOLS)} symbols...")
    for symbol in SYMBOLS:
        try:
            setup = score_setup(symbol)
        except Exception as e:
            print(f"[SCAN] {symbol}: {e}")
            continue
        if not setup.get("valid"):
            print(f" [-] {symbol}")
            continue
        rr = setup.get("rr", 0)
        print(f" [OK] {symbol} | {setup['score']['grade']} | RR {rr:.2f}")
        if rr < MIN_RR:
            send_telegram(setup, False)
            continue
        if count_open_trades() >= MAX_TRADES:
            send_telegram(setup, False)
            continue
        if already_in_symbol(symbol):
            continue
        tick = mt5.symbol_info_tick(symbol)
        ep   = tick.ask if setup["bias"] == "bullish" else tick.bid
        lots = calculate_lot_size(symbol, setup["sl"], ep)
        if not lots:
            send_telegram(setup, False)
            continue
        ok = place_order(symbol, setup["bias"], setup["sl"], setup["tp"], lots)
        send_telegram(setup, ok, lots if ok else None)


if __name__ == "__main__":
    print("=== FrostBot SMC ===")
    if not mt5_connect():
        raise SystemExit("MT5 connection failed. Is the terminal open?")
    try:
        while True:
            execute_valid_setups()
            check_break_even()
            print(f"[BOT] Sleeping {SCAN_INTERVAL}s...")
            time.sleep(SCAN_INTERVAL)
    except KeyboardInterrupt:
        print("[BOT] Stopped.")
    finally:
        mt5_disconnect()
