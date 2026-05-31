import requests

# PASTE YOUR DETAILS HERE
TOKEN   = "YOUR_ACTUAL_BOT_TOKEN"
CHAT_ID = "YOUR_ACTUAL_CHAT_ID"

def send_telegram_alert(message: str):
    """Sends a professional HTML formatted alert to your phone."""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"[Telegram Error] {e}")