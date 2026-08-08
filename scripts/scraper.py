
"""
Scraper prezzi componenti PC - versione multi-fonte.

Ogni funzione 'scrape_<fonte>' prende una URL e restituisce il prezzo piu'
basso trovato (float) oppure None se non riesce a estrarlo.

NOTA: i siti cambiano struttura HTML periodicamente e alcuni bloccano
attivamente lo scraping (in particolare dagli IP dei server GitHub Actions).
Se una fonte smette di funzionare, il resto continua a girare normalmente:
si prende il prezzo migliore tra tutte le fonti che hanno risposto.
"""

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
COMPONENTS_FILE = ROOT / "components.json"
HISTORY_FILE = ROOT / "data" / "prices_history.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.google.com/",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

REQUEST_TIMEOUT = 20
DELAY_BETWEEN_REQUESTS = 4

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

PREZZO_MIN_RAGIONEVOLE = 50
PREZZO_MAX_RAGIONEVOLE = 3000


def _parse_price_it(text):
    if not text:
        return None
    match = re.search(r"(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)", text)
    if not match:
        return None
    raw = match.group(1).replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _prezzi_ragionevoli(prices):
    return [p for p in prices if PREZZO_MIN_RAGIONEVOLE <= p <= PREZZO_MAX_RAGIONEVOLE]


def scrape_trovaprezzi(url):
    """
    NOTA: Trovaprezzi blocca sistematicamente gli IP dei server GitHub
    Actions con 403 Forbidden. Questa funzione resta qui per completezza
    ma va considerata inaffidabile finche' non si usa un proxy a pagamento.
    """
    try:
        SESSION.get("https://www.trovaprezzi.it/", timeout=REQUEST_TIMEOUT)
        time.sleep(1)
    except requests.RequestException:
        pass

    resp = SESSION.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    prices = []
    for el in soup.select(".listing_item .prezzo, .prod_price, .price"):
        p = _parse_price_it(el.get_text())
        if p:
            prices.append(p)

    if not prices:
        for m in re.finditer(r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*€", resp.text):
            p = _parse_price_it(m.group(1))
            if p:
                prices.append(p)

    prices = _prezzi_ragionevoli(prices)
    return min(prices) if prices else None


def scrape_amazon(url):
    """
    Cerca SOLO dentro i veri blocchi risultato di ricerca
    (div[data-component-type="s-search-result"]), non in tutta la pagina,
    per evitare di catturare prezzi di banner pubblicitari o widget
    scorrelati dal prodotto cercato.
    """
    resp = SESSION.get(url, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")

    prices = []
    result_cards = soup.select('div[data-component-type="s-search-result"]')
    for card in result_cards:
        el = card.select_one(".a-price .a-offscreen")
        if el:
            p = _parse_price_it(el.get_text())
            if p:
                prices.append(p)

    prices = _prezzi_ragionevoli(prices)
    return min(prices) if prices else None


def scrape_ebay(url):
    """
    eBay cambia spesso le classi CSS dei risultati. Proviamo piu' selettori
    noti, poi un fallback regex generico su pattern di prezzo in euro
    dentro i blocchi risultato (evitando l'header/footer di pagina).
    """
    resp = SESSION.get(url, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")

    prices = []
    for selector in [".s-item__price", ".s-card__price", "span.s-card__price"]:
        for el in soup.select(selector):
            p = _parse_price_it(el.get_text())
            if p:
                prices.append(p)
        if prices:
            break

    if not prices:
        for item in soup.select("li.s-item, li.s-card, div.s-card"):
            text = item.get_text(" ", strip=True)
            m = re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*€", text)
            if m:
                p = _parse_price_it(m.group(1))
                if p:
                    prices.append(p)

    prices = _prezzi_ragionevoli(prices)
    return min(prices) if prices else None


SCRAPERS = {
    "trovaprezzi": scrape_trovaprezzi,
    "amazon": scrape_amazon,
    "ebay": scrape_ebay,
}


def load_components():
    with open(COMPONENTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)["components"]


def load_history():
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_history(history):
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def run(debug=False):
    components = load_components()
    history = load_history()
    now = datetime.now(timezone.utc).isoformat()

    alerts = []

    for comp in components:
        comp_id = comp["id"]
        history.setdefault(comp_id, {"nome": comp["nome"], "prezzi": []})

        best_price = None
        best_source = None

        for source_name, url in comp["fonti"].items():
            scraper_fn = SCRAPERS.get(source_name)
            if not scraper_fn:
                print(f"[WARN] nessuno scraper per la fonte '{source_name}'")
                continue
            try:
                price = scraper_fn(url)
            except Exception as e:
                print(f"[ERRORE] {comp_id} / {source_name}: {e}")
                price = None

            print(f"{comp['nome']} @ {source_name}: {price}")

            if price is not None and (best_price is None or price < best_price):
                best_price = price
                best_source = source_name

            time.sleep(DELAY_BETWEEN_REQUESTS)

        if best_price is not None:
            history[comp_id]["prezzi"].append(
                {"data": now, "prezzo": best_price, "fonte": best_source}
            )
            print(f"OK  {comp['nome']}: {best_price} EUR ({best_source})")

            if best_price <= comp.get("soglia_prezzo", 0):
                alerts.append(
                    f"🔔 {comp['nome']} e' sceso a {best_price:.2f} EUR "
                    f"(soglia: {comp['soglia_prezzo']:.2f} EUR) su {best_source}"
                )
        else:
            print(f"KO  {comp['nome']}: nessun prezzo trovato su nessuna fonte")

    save_history(history)

    alerts_file = ROOT / "data" / "alerts.json"
    with open(alerts_file, "w", encoding="utf-8") as f:
        json.dump(alerts, f, ensure_ascii=False, indent=2)

    return alerts


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    run(debug=args.debug)
