import requests

TOKEN = "8964245113:AAE-5cYyCYAGogkdA9VgYbyag0UuteAKIXs"
CHAT_ID = "7890036882"

def send_telegram_log(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try: requests.post(url, data={"chat_id": CHAT_ID, "text": f"📋 {message}", "parse_mode": "HTML"})
    except: pass

def alert_trade_entry(symbol, bias, entry, sl, tp, lots, rr):
    risk_money = abs(entry - sl) * lots * (100 if "XAU" in symbol else 100000)
    emoji = "🟢 BUY" if bias == 'bullish' else "🔴 SELL"
    msg = (
        f"🏛 <b>ENTRY: {symbol}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"Direction: {emoji} | Lots: {lots}\n"
        f"💵 <b>Risk:</b> ${round(risk_money, 2)}\n"
        f"⚖️ <b>RR:</b> 1:{round(rr, 2)}\n"
        f"🎯 <b>Target:</b> ${round(risk_money * rr, 2)}"
    )
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})

def alert_trade_closed(symbol, profit, rr_achieved, label):
    """Card for TP or SL hits."""
    emoji = "✅ TP HIT" if profit > 0 else "❌ SL HIT"
    if 0 <= profit < 0.5: emoji = "🛡️ BE HIT" # Small profit = Break-even
    
    msg = (
        f"🏁 <b>TRADE CLOSED: {symbol}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"Result: <b>{emoji}</b>\n"
        f"💰 <b>Profit:</b> ${round(profit, 2)}\n"
        f"⚖️ <b>RR Gain:</b> {round(rr_achieved, 2)}R\n"
        f"━━━━━━━━━━━━━━\n"
        f"Strategy: {label}"
    )
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})