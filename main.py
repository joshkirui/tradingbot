import time
import MetaTrader5 as mt5
from modules import connector, strategy, execution, alerts
from settings import SYMBOLS

def start_bot():
    print("="*30 + "\n FROST BOT ACTIVE \n" + "="*30)
    if not connector.connect(): return
    alerts.send("?? Frost Bot Online")

    try:
        while True:
            execution.manage_open_positions()
            for symbol in SYMBOLS:
                print(f"[*] Scanning {symbol}...", end="\r")
                direction, score, atr = strategy.score_setup(symbol)
                
                if direction is not None and score >= 60:
                    tick = mt5.symbol_info_tick(symbol)
                    price = tick.ask if direction == 1 else tick.bid
                    result = execution.place_order(symbol, direction, price, atr, score)
                    if result["success"]:
                        alerts.send(f"? Trade: {symbol} | Score: {score}")
            time.sleep(30)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        connector.disconnect()

if __name__ == "__main__":
    start_bot()
