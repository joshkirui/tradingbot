import sqlite3
from settings import DB_NAME

def check_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    print("\n" + "="*50)
    print(" SYSTEM LOGS (Last 10)")
    print("="*50)
    try:
        cursor.execute("SELECT * FROM logs ORDER BY timestamp DESC LIMIT 10")
        logs = cursor.fetchall()
        for log in logs:
            print(f"[{log[3]}] {log[1]}: {log[2]}")
    except Exception as e:
        print("No logs found yet.")

    print("\n" + "="*50)
    print(" TRADE HISTORY (Last 10)")
    print("="*50)
    try:
        cursor.execute("SELECT * FROM trades ORDER BY timestamp DESC LIMIT 10")
        trades = cursor.fetchall()
        if not trades:
            print("No trades recorded yet.")
        for t in trades:
            print(f"ID: {t[1]} | {t[2]} | {t[3]} | Vol: {t[4]} | Profit: ${t[7]}")
    except Exception as e:
        print("No trades found yet.")

    conn.close()
    print("="*50 + "\n")

if __name__ == "__main__":
    check_database()
