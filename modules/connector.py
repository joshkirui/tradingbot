import MetaTrader5 as mt5
import time
from settings import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER

def connect(max_retries=3):
    # Try finding it automatically first, then try the specific path
    paths = [None, "C:/Program Files/JustMarkets MetaTrader 5/terminal64.exe"]
    
    for path in paths:
        for attempt in range(1, max_retries + 1):
            init_success = mt5.initialize(path=path) if path else mt5.initialize()
            
            if not init_success:
                time.sleep(1)
                continue
                
            if not mt5.login(int(MT5_LOGIN), password=MT5_PASSWORD, server=MT5_SERVER):
                print(f"[!] Login Failed for {MT5_LOGIN}: {mt5.last_error()}")
                mt5.shutdown()
                return False
                
            info = mt5.account_info()
            if info:
                print(f"[?] Connected: {info.name} (Balance: ${info.balance})")
                return True
    return False

def disconnect():
    mt5.shutdown()
