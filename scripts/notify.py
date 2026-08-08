"""
Invia su Telegram gli alert generati da scraper.py (data/alerts.json).

Richiede le variabili d'ambiente:
- TELEGRAM_TOKEN
- TELEGRAM_CHAT_ID
"""

import json
import os
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
ALERTS_FILE = ROOT / "data" / "alerts.json"


def send_telegram_message(text):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("[WARN] TELEGRAM_TOKEN o TELEGRAM_CHAT_ID mancanti, salto invio")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(
        url,
        data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"[ERRORE] invio Telegram fallito: {resp.status_code} {resp.text}")
    else:
        print("Messaggio Telegram inviato.")


def main():
    if not ALERTS_FILE.exists():
        print("Nessun file alert trovato, niente da inviare.")
        return

    with open(ALERTS_FILE, "r", encoding="utf-8") as f:
        alerts = json.load(f)

    if not alerts:
        print("Nessun alert da inviare in questo ciclo.")
        return

    message = "📉 <b>Aggiornamento prezzi PC</b>\n\n" + "\n".join(alerts)
    send_telegram_message(message)


if __name__ == "__main__":
    main()
