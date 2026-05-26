import requests
from settings import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

def send(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload)
        return True
    except:
        return False
