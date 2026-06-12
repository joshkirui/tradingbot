print("1. Script started...")
try:
    import MetaTrader5 as mt5
    print("2. MetaTrader5 library imported successfully!")
except Exception as e:
    print(f"2. FAILED to import MetaTrader5: {e}")

try:
    import pandas as pd
    print("3. Pandas library imported successfully!")
except Exception as e:
    print(f"3. FAILED to import Pandas: {e}")

print("4. Checking MT5 Initialization...")
if not mt5.initialize():
    print(f"FAILED: MT5 could not initialize. Error: {mt5.last_error()}")
else:
    print("SUCCESS: MT5 is connected!")
    mt5.shutdown()