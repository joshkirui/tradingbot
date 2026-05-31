def run_test(name: str, fn) -> bool:
    try:
        result = fn()
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {name}")
        return bool(result)
    except Exception as e:
        print(f"  [FAIL] {name} — {e}")
        return False

def test_imports():
    import modules.connector, modules.data_engine
    import modules.strategy, modules.risk
    import modules.execution, modules.news, modules.alerts
    return True

def test_mt5():
    from modules.connector import connect, disconnect
    ok = connect()
    disconnect()
    return ok

def test_data():
    from modules.connector import connect
    from modules.data_engine import get_candles, get_atr
    connect()
    df = get_candles("EURUSD", "M15", 50)
    atr = get_atr(df)
    return len(df) > 0 and atr > 0

def test_strategy():
    from modules.strategy import score_setup
    result = score_setup("EURUSD")
    return "score" in result

def test_risk():
    from modules.risk import pre_trade_checks
    ok, msg = pre_trade_checks("EURUSD")
    return isinstance(ok, bool)

def test_news():
    from modules.news import is_news_blackout
    result = is_news_blackout()
    return isinstance(result, bool)

def test_alerts():
    from modules.alerts import send
    send("🔧 System test ping")
    return True

if __name__ == "__main__":
    print("\n" + "="*40)
    print("  FROST BOT — SYSTEM TEST")
    print("="*40)
    tests = [
        ("Module imports",   test_imports),
        ("MT5 connectivity", test_mt5),
        ("Data engine",      test_data),
        ("Strategy engine",  test_strategy),
        ("Risk engine",      test_risk),
        ("News manager",     test_news),
        ("Alert system",     test_alerts),
    ]
    results = [run_test(name, fn) for name, fn in tests]
    passed  = sum(results)
    print("="*40)
    print(f"  {passed}/{len(tests)} tests passed")
    if all(results):
        print("  ✅ ALL SYSTEMS GO — starting scanner...")
        # from main import start_scanner
        # start_scanner()
    else:
        print("  ❌ Fix failing modules before going live.")
    print("="*40 + "\n")