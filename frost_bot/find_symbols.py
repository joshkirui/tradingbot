import MetaTrader5 as mt5

if not mt5.initialize():
    print("Failed to initialize")
    quit()

# Log in
mt5.login(2001385306, password="Joshkirui@123", server="JustMarkets-Demo")

# 1. Get ALL available symbols from your broker
symbols = mt5.symbols_get()
print(f"Total symbols found: {len(symbols)}")

# 2. Look for anything containing "EURUSD"
print("\nLooking for EURUSD variations:")
for s in symbols:
    if "EURUSD" in s.name:
        print(f"--> Found Symbol Name: '{s.name}'")

# 3. Check for common majors to see their exact naming
print("\nFirst 10 symbols in your Market Watch:")
selected_symbols = mt5.symbols_get(group="*,!*") # gets all
for i, s in enumerate(selected_symbols[:10]):
    print(f"{i}. {s.name}")

mt5.shutdown()