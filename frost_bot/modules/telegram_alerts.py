import requests
from datetime import datetime

# ==============================================================================
# --- TELEGRAM CONFIG ---
# ==============================================================================
BOT_TOKEN = "8964245113:AAE-5cYyCYAGogkdA9VgYbyag0UuteAKIXs"
CHAT_ID   = "7890036882"
# ==============================================================================


def _send(message: str):
    """Base sender — all other functions call this."""
    url     = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":    CHAT_ID,
        "text":       message,
        "parse_mode": "HTML",
    }
    try:
        r = requests.post(url, data=payload, timeout=10)
        if r.status_code != 200:
            print(f"  [Telegram] Failed: {r.text}")
    except Exception as e:
        print(f"  [Telegram] Connection error: {e}")


# ==============================================================================
# --- ALERT: TRADE EXECUTED ---
# ==============================================================================
def alert_trade_entry(symbol, bias, entry, sl, tp, lots, score, grade, rr):
    emoji     = "🟢" if bias == "bullish" else "🔴"
    direction = "BUY  📈" if bias == "bullish" else "SELL 📉"
    sl_pips   = abs(entry - sl)
    tp_pips   = abs(entry - tp)

    msg = (
        f"{emoji} <b>TRADE OPENED — {symbol}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Direction:</b> {direction}\n"
        f"🏅 <b>Grade:</b> {grade}  |  <b>Score:</b> {score}/10\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>Entry:</b>      <code>{entry}</code>\n"
        f"🛑 <b>Stop Loss:</b>  <code>{sl}</code>  ({sl_pips:.5f})\n"
        f"🎯 <b>Take Profit:</b> <code>{tp}</code>  ({tp_pips:.5f})\n"
        f"⚖️ <b>RR:</b>         1 : {rr:.1f}\n"
        f"📦 <b>Lot Size:</b>   {lots}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )
    _send(msg)


# ==============================================================================
# --- ALERT: TRADE CLOSED ---
# ==============================================================================
def alert_trade_closed(symbol, bias, outcome, entry, close_price, sl, tp, lots, rr_achieved):
    if outcome == "win":
        emoji  = "✅"
        result = "WIN"
        pnl_emoji = "💰"
    else:
        emoji  = "❌"
        result = "LOSS"
        pnl_emoji = "💸"

    direction = "BUY" if bias == "bullish" else "SELL"
    pips      = abs(close_price - entry)

    msg = (
        f"{emoji} <b>TRADE CLOSED — {symbol}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Direction:</b> {direction}\n"
        f"🏁 <b>Result:</b>    {pnl_emoji} <b>{result}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔓 <b>Entry:</b>      <code>{entry}</code>\n"
        f"🔒 <b>Exit:</b>       <code>{close_price}</code>\n"
        f"📏 <b>Pips:</b>       {pips:.5f}\n"
        f"⚖️ <b>RR Achieved:</b> 1 : {rr_achieved:.1f}\n"
        f"📦 <b>Lot Size:</b>   {lots}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )
    _send(msg)


# ==============================================================================
# --- ALERT: SETUP SKIPPED ---
# ==============================================================================
def alert_setup_skipped(symbol, bias, score, reason):
    msg = (
        f"⏭️ <b>SETUP SKIPPED — {symbol}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Bias:</b>   {bias}\n"
        f"📊 <b>Score:</b>  {score}/10\n"
        f"❓ <b>Reason:</b> {reason}\n"
        f"🕐 {datetime.utcnow().strftime('%H:%M:%S')} UTC"
    )
    _send(msg)


# ==============================================================================
# --- ALERT: BOT ERROR / CRASH ---
# ==============================================================================
def alert_error(error_msg: str, location: str = ""):
    msg = (
        f"🚨 <b>BOT ERROR</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 <b>Where:</b> {location if location else 'Main loop'}\n"
        f"💬 <b>Error:</b>\n<code>{error_msg[:500]}</code>\n"
        f"🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )
    _send(msg)


# ==============================================================================
# --- ALERT: BOT STARTED ---
# ==============================================================================
def alert_bot_started(watchlist, min_score, rr):
    symbols = ", ".join(watchlist)
    msg = (
        f"🤖 <b>FrostBot STARTED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 <b>Symbols:</b>   {symbols}\n"
        f"📊 <b>Min Score:</b> {min_score}/10\n"
        f"⚖️ <b>RR Target:</b> 1 : {rr}\n"
        f"🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )
    _send(msg)


# ==============================================================================
# --- ALERT: BOT STOPPED ---
# ==============================================================================
def alert_bot_stopped():
    msg = (
        f"🛑 <b>FrostBot STOPPED</b>\n"
        f"🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )
    _send(msg)