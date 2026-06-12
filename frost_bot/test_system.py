import os
import json
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

# --- IMPORT ACTUAL BOT FUNCTIONS ---
try:
    from modules.data_engine import get_candles, get_session, normalize_symbol
    from modules.logic import score_setup
    from modules.telegram_utils import send_telegram_alert
except ImportError as e:
    print(f"❌ Critical Setup Error: {e}")

# ==============================================================================
# --- TEST UTILITIES ---
# ==============================================================================

def run_test(name: str, fn) -> bool:
    try:
        result = fn()
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {name}")
        return bool(result)
    except Exception as e:
        # Handling the Python 3.14 Ambiguity error even in tests
        err_msg = str(e).split('\n')[0]
        print(f"  [FAIL] {name} — {err_msg}")
        return False

# ==============================================================================
# --- TEST SUITE ---
# ==============================================================================

def test_imports():
    """Verify all required modules are present."""
    import modules.data_engine
    import modules.logic
    import modules.telegram_utils
    return True

def test_accounts_config():
    """Verify that the accounts.json file exists and is valid."""
    if not os.path.exists("accounts.json"):
        print("  [!] accounts.json missing. Run /add_account first.")
        return False
    with open("accounts.json", "r") as f:
        accs = json.load(f)
    return len(accs) > 0

def test_mt5_path():
    """Verify the MetaTrader 5 executable path."""
    path = "C:/Program Files/MetaTrader 5/terminal64.exe"
    if not os.path.exists(path):
        print(f"  [!] MT5 not found at {path}")
        return False
    return True

def test_data_fetch():
    """Verify candles and session extraction (Ambiguity Check)."""
    if not mt5.initialize(): return False
    
    symbol = "EURUSD"
    # Some brokers use .m suffix
    try: symbol = normalize_symbol(symbol)
    except: pass
    
    df = get_candles(symbol, "M1", 10)
    if df is None or len(df) == 0:
        return False
    
    # Test our new 'force to string' logic for Python 3.14
    sess_raw = get_session(df)
    if hasattr(sess_raw, 'iloc'):
        session_name = str(sess_raw.iloc[-1])
    else:
        session_name = str(sess_raw)
    
    return isinstance(session_name, str) and len(session_name) > 0

def test_strategy_logic():
    """Verify SMC Logic module receives data correctly."""
    symbol = "EURUSD"
    df_h1 = get_candles(symbol, "H1", 20)
    df_m15 = get_candles(symbol, "M15", 20)
    df_m1 = get_candles(symbol, "M1", 20)
    
    # Force scalar string for session
    session = "London" 
    
    res = score_setup(df_h1, df_m15, df_m1, session)
    return isinstance(res, dict) and "valid" in res

def test_journal_system():
    """Verify the AI Journal file is writable."""
    file = "trading_journal.csv"
    try:
        with open(file, "a") as f:
            f.write("") # Just check if we can touch the file
        return True
    except:
        return False

def test_alerts():
    """Test the Telegram outgoing connection."""
    # We return True but check terminal if the message actually arrives
    try:
        send_telegram_alert("🔧 <b>System Test:</b> Diagnostics passed.")
        return True
    except:
        return False

# ==============================================================================
# --- EXECUTION ---
# ==============================================================================

if __name__ == "__main__":
    print("\n" + "="*45)
    print("  FROST BOT — MULTI-ACCOUNT SYSTEM TEST")
    print("="*45)
    
    tests = [
        ("Module imports",      test_imports),
        ("Account Database",    test_accounts_config),
        ("MT5 Executable Path", test_mt5_path),
        ("Data Engine (M1)",    test_data_fetch),
        ("SMC Logic Engine",    test_strategy_logic),
        ("AI Journaling File",  test_journal_system),
        ("Telegram Alerts",     test_alerts),
    ]
    
    results = []
    for name, fn in tests:
        results.append(run_test(name, fn))
    
    passed = sum(results)
    print("="*45)
    print(f"  {passed}/{len(tests)} tests passed")
    
    if all(results):
        print("  ✅ ALL SYSTEMS GO")
        print("  Bot is ready for /run in Telegram.")
    else:
        print("  ❌ SYSTEM FAILURE")
        print("  Fix the failing modules before starting the manager.")
    print("="*45 + "\n")
    
    mt5.shutdown()