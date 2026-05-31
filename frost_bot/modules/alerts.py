import pandas as pd
import MetaTrader5 as mt5
import time
import requests
from datetime import datetime

# --- CONFIGURATION ---
MT5_LOGIN    = 2001385306
MT5_PASSWORD = "Joshkirui@123"
MT5_SERVER   = "JustMarkets-Demo"
BROKER_SUFFIX = ".m"

# TELEGRAM CONFIG
BOT_TOKEN = 8964245113:AAE-5cYyCYAGogkdA9VgYbyag0UuteAKIXs # Get a new one from @BotFather
CHAT_ID   = "7890036882"

# --- CORE UTILITIES ---

class TelegramManager:
    """Handles all communication with Telegram."""
    @staticmethod
    def send(message):
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
        try:
            requests.post(url, data=payload, timeout=10)
        except Exception as e:
            print(f"Telegram Error: {e}")

    @staticmethod
    def format_signal(symbol, side, price, sl, tp, atr):
        emoji = "🔵" if side == "BUY" else "🔴"
        return (
            f"{emoji} <b>LIVE SIGNAL: {symbol}</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"⚡ <b>Action:</b> {side}\n"
            f"💵 <b>Entry:</b> {price:.5f}\n"
            f"🛡️ <b>Stop Loss:</b> {sl:.5f}\n"
            f"🎯 <b>Take Profit:</b> {tp:.5f}\n"
            f"📊 <b>ATR (Risk):</b> {atr:.5f}\n"
            f"⏰ <b>Time:</b> {datetime.now().strftime('%H:%M:%S')}"
        )

    @staticmethod
    def format_backtest(report):
        return (
            f"🏁 <b>BACKTEST REPORT: {report['symbol']}</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💰 <b>Total Profit:</b> ${report['profit']:.2f}\n"
            f"📈 <b>Win Rate:</b> {report['win_rate']:.1%}\n"
            f"🔄 <b>Total Trades:</b> {report['trades']}\n"
            f"📉 <b>Max Drawdown:</b> {report['drawdown']:.2f}%\n"
            f"━━━━━━━━━━━━━━━"
        )

class MT5Client:
    """Manages connection and data retrieval."""
    @classmethod
    def initialize(cls):
        if not mt5.initialize():
            print("MT5 Init Failed")
            return False
        if not mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
            print("MT5 Login Failed")
            return False
        return True

    @staticmethod
    def get_data(symbol, timeframe, n=200):
        s = symbol.upper().removesuffix(".M").removesuffix(".STD")
        full_symbol = f"{s}{BROKER_SUFFIX}"
        
        mt5.symbol_select(full_symbol, True)
        rates = mt5.copy_rates_from_pos(full_symbol, mt5.TIMEFRAME_H1, 0, n)
        
        if rates is None or len(rates) == 0:
            return pd.DataFrame()
            
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df

# --- STRATEGY HELPERS ---

def calculate_atr(df, length=14):
    high, low, close = df['high'], df['low'], df['close']
    tr = pd.concat([high-low, (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(window=length).mean().iloc[-1]

# --- MAIN ENGINES ---

def run_backtest(symbol, days=30):
    """Simple simulation to demonstrate backtest format."""
    print(f"Starting Backtest for {symbol}...")
    # Mock results (Replace with your actual loop logic)
    stats = {
        "symbol": symbol,
        "profit": 1250.45,
        "win_rate": 0.62,
        "trades": 48,
        "drawdown": 4.5
    }
    msg = TelegramManager.format_backtest(stats)
    TelegramManager.send(msg)
    print("Backtest report sent to Telegram.")

def run_live_bot(symbol):
    """Main loop for live trading."""
    print(f"Live Bot Started for {symbol}...")
    if not MT5Client.initialize(): return
    
    # Example logic: Run once for demonstration
    df = MT5Client.get_data(symbol, "H1")
    if not df.empty:
        curr_price = df['close'].iloc[-1]
        atr = calculate_atr(df)
        
        # Hypothetical Signal Logic
        side = "BUY"
        sl = curr_price - (atr * 2)
        tp = curr_price + (atr * 3)
        
        msg = TelegramManager.format_signal(symbol, side, curr_price, sl, tp, atr)
        TelegramManager.send(msg)
        print("Live signal sent to Telegram.")

# --- EXECUTION ---

if __name__ == "__main__":
    # Choose your mode:
    # 1. To see a signal:
    run_live_bot("EURUSD")
    
    # 2. To see a backtest report:
    # run_backtest("EURUSD")