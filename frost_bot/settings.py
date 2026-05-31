import requests

# --- CONFIG ---
# You can leave these as they are for now; the function will simply skip 
# sending if it doesn't see a real token.
TOKEN   = "YOUR_BOT_TOKEN_HERE"
CHAT_ID = "YOUR_CHAT_ID_HERE"

def send_telegram_alert(message: str):
    """
    Sends a message to your Telegram bot.
    """
    # If you haven't set up a real token, just print to console and return
    if TOKEN == "YOUR_BOT_TOKEN_HERE":
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, data=payload, timeout=5)
        return response.json()
    except Exception as e:
        print(f"[Telegram Error] {e}")
        return Noneimport MetaTrader5 as mt5
from telethon import TelegramClient, events
import re

# 1. --- CONFIGURATION ---
API_ID = 34688270
API_HASH = '06cc0a177e24da77c581297ea548778f'

# How much money are you willing to lose if the Stop Loss is hit?
RISK_DOLLARS = 50 

# ✅ UPDATED: Added your two channels here
CHANNELS = ['me', 'TRADEWITHUK500', 'HussainAi123'] 

# 2. --- INITIALIZE ---
if not mt5.initialize():
    print("❌ MT5 Failed to start. Make sure the MT5 app is open and logged in.")
    quit()

client = TelegramClient('session', API_ID, API_HASH)

# 3. --- TRADING FUNCTIONS ---
def calculate_lot(symbol, entry, sl):
    """Calculates lot size based on $ risk."""
    sym_info = mt5.symbol_info(symbol)
    if not sym_info: 
        print(f"❌ Cannot find info for {symbol}")
        return None
    
    dist = abs(entry - sl)
    if dist == 0: return None
    
    # Lot calculation: Risk / (Distance * Contract Size)
    # multiplier: 100 for Gold, 100000 for Forex
    multiplier = 100 if "XAU" in symbol or "GOLD" in symbol else 100000
    lot = RISK_DOLLARS / (dist * multiplier) 
    
    # Adjust for broker limits
    lot = round(lot, 2)
    if lot < sym_info.volume_min: lot = sym_info.volume_min
    if lot > sym_info.volume_max: lot = sym_info.volume_max
    return lot

def execute_trade(signal):
    mt5.symbol_select(signal['symbol'], True)
    tick = mt5.symbol_info_tick(signal['symbol'])
    if not tick:
        print(f"❌ Could not get price for {signal['symbol']}")
        return

    lot = calculate_lot(signal['symbol'], signal['entry'], signal['sl'])
    if lot is None: return

    price = tick.ask if signal['side'] == mt5.ORDER_TYPE_BUY else tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": signal['symbol'],
        "volume": lot,
        "type": signal['side'],
        "price": price,
        "sl": signal['sl'],
        "tp": signal['tp'],
        "magic": 202405,
        "comment": "Telegram Bot",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    result = mt5.order_send(request)
    
    # Retry with FOK if IOC fails
    if result.retcode == mt5.TRADE_RETCODE_INVALID_FILL:
        request["type_filling"] = mt5.ORDER_FILLING_FOK
        result = mt5.order_send(request)

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"❌ Trade Failed: {result.comment} (Code: {result.retcode})")
    else:
        print(f"✅ Trade Placed Successfully: {signal['symbol']} {lot} Lots")

# 4. --- MESSAGE LISTENER ---
@client.on(events.NewMessage(chats=CHANNELS))
async def handler(event):
    text = event.raw_text.upper()
    print(f"\n📩 Message from {event.chat.username if event.chat else 'Private'}:")
    print(f"{text}")

    try:
        # Detect Symbol
        sym_match = re.search(r'([A-Z]{3,6})', text)
        if not sym_match: return
        symbol = sym_match.group(1)
        
        # Detect Buy/Sell
        side = mt5.ORDER_TYPE_BUY if any(x in text for x in ["BUY", "LONG", "CALL"]) else mt5.ORDER_TYPE_SELL
        
        # Detect Prices (finds all decimals/numbers)
        nums = re.findall(r'\d+\.\d+|\d+', text)
        
        if len(nums) >= 3:
            # Assumes order: Entry, SL, TP
            signal = {
                'symbol': symbol, 
                'side': side, 
                'entry': float(nums[0]), 
                'sl': float(nums[1]), 
                'tp': float(nums[2])
            }
            print(f"🚀 Signal Parsed: {signal['symbol']} | {'BUY' if side==0 else 'SELL'}")
            execute_trade(signal)
        else:
            print("ℹ️ Message ignored: Not enough numbers found for a trade.")
            
    except Exception as e:
        print(f"⚠️ Error parsing message: {e}")

# 🚀 START
print("⚡ Bot is running and connected to MT5...")
print(f"📡 Listening to: {CHANNELS}")
with client:
    client.run_until_disconnected()