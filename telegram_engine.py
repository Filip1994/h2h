import os
import requests

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
GITHUB_REPO = "Filip1994/h2h"

def send_telegram_message(text, bet_id=None):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram token ili Chat ID nisu podešeni u Secrets.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    if bet_id:
        skip_url = f"https://github.com/{GITHUB_REPO}/issues/new?title=SKIP_{bet_id}"
        payload["reply_markup"] = {
            "inline_keyboard": [
                [{"text": "❌ Preskoči ovaj tip", "url": skip_url}]
            ]
        }

    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"Greška pri slanju na Telegram: {e}")
        return False

def send_bulletin_header(bank, profit, roi, win_rate, total_matches, total_spent, max_risk):
    roi_icon = "📈" if profit >= 0 else "📉"
    profit_sign = "+" if profit > 0 else ""
    
    header = (
        f"🚀 <b>MASTER ANALITIČKI BILTEN</b>\n"
        f"───────────────────────────\n"
        f"🏦 <b>Banka:</b> {bank:,.0f} RSD\n"
        f"{roi_icon} <b>Profit:</b> {profit_sign}{profit:,.0f} RSD\n"
        f"📊 <b>ROI:</b> {roi:.2f}%\n"
        f"🎯 <b>Prolaznost:</b> {win_rate:.1f}% ({total_matches} mečeva)\n"
        f"───────────────────────────\n"
        f"💰 <b>Uloženo danas:</b> {total_spent:,.0f} RSD (Max: {max_risk:,.0f} RSD)"
    )
    send_telegram_message(header)
