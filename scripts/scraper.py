"""
Scraper prezzi componenti PC - versione multi-fonte con verifica titolo,
soglia minima per componente, e supporto siti JS-rendered (Playwright).
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

PREZZO_MAX_RAGIONEVOLE = 3000

_PLAYWRIGHT = None
_BROWSER = None
_PAGE = None


def _get_playwright_page():
    global _PLAYWRIGHT, _BROWSER, _PAGE
    if _PAGE is None:
        from playwright.sync_api import sync_playwright

        _PLAYWRIGHT = sync_playwright().start()
        _BROWSER = _PLAYWRIGHT.chromium.launch(headless=True)
        context = _BROWSER.new_context(
            user_agent=HEADERS["User-Agent"], locale="it-IT"
        )
        _PAGE = context.new_page()
    return _PAGE


def _chiudi_playwright():
    global _PLAYWRIGHT, _BROWSER, _PAGE
    if _BROWSER:
        _BROWSER.close()
    if _PLAYWRIGHT:
        _PLAYWRIGHT.stop()
    _PLAYWRIGHT, _BROWSER, _PAGE = None, None, None


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


def _prezzi_ragionevoli(prices, prezzo_min=20):
    return [p for p in prices if prezzo_min <= p <= PREZZO_MAX_RAGIONEVOLE]


def _titolo_corrisponde(titolo, parole_chiave):
    if not titolo or not parole_chiave:
        return False
    titolo_lower = titolo.lower()
    return all(kw.lower() in titolo_lower for kw in parole_chiave)


def scrape_trovaprezzi(url, parole_chiave, prezzo_min):
    try:
        SESSION.get("https://www.trovaprezzi.it/", timeout=REQUEST_TIMEOUT)
        time.sleep(1)
    except requests.RequestException:
        pass

    resp = SESSION.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    prices = []
    for item in soup.select(".listing_item"):
        titolo = item.get_text(" ", strip=True)
        if not _titolo_corrisponde(titolo, parole_chiave):
            continue
        prezzo_el = item.select_one(".prezzo, .prod_price, .price")
        if prezzo_el:
            p = _parse_price_it(prezzo_el.get_text())
            if p:
                prices.append(p)

    prices = _prezzi_ragionevoli(prices, prezzo_min)
    return min(prices) if prices else None


def scrape_amazon(url, parole_chiave, prezzo_min):
    resp = SESSION.get(url, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")

    prices = []
    result_cards = soup.select('div[data-component-type="s-search-result"]')
    for card in result_cards:
        titolo_el = card.select_one("h2")
        titolo = titolo_el.get_text(" ", strip=True) if titolo_el else ""
        if not _titolo_corrisponde(titolo, parole_chiave):
            continue
        prezzo_el = card.select_one(".a-price .a-offscreen")
        if prezzo_el:
            p = _parse_price_it(prezzo_el.get_text())
            if p:
                prices.append(p)

    prices = _prezzi_ragionevoli(prices, prezzo_min)
    return min(prices) if prices else None


def scrape_ebay(url, parole_chiave, prezzo_min):
    resp = SESSION.get(url, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")

    prices = []
    for item in soup.select("li.s-item, li.s-card, div.s-card"):
        titolo_el = item.select_one(".s-item__title, .s-card__title")
        titolo = titolo_el.get_text(" ", strip=True) if titolo_el else item.get_text(" ", strip=True)
        if not _titolo_corrisponde(titolo, parole_chiave):
            continue

        prezzo_el = item.select_one(".s-item__price, .s-card__price")
        if prezzo_el:
            p = _parse_price_it(prezzo_el.get_text())
        else:
            m = re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*€", titolo)
            p = _parse_price_it(m.group(1)) if m else None

        if p:
            prices.append(p)

    prices = _prezzi_ragionevoli(prices, prezzo_min)
    return min(prices) if prices else None


def scrape_bpm_power(termine_ricerca, parole_chiave, prezzo_min):
    """
    BPM-power non ha una pagina di ricerca raggiungibile via URL diretto:
    la ricerca e' gestita via JavaScript. Simuliamo l'uso reale della
    barra di ricerca: apriamo la home, troviamo il campo, digitiamo il
    termine, premiamo invio, aspettiamo i risultati.
    """
    page = _get_playwright_page()
    try:
        page.goto("https://www.bpm-power.com/it/", wait_until="networkidle", timeout=30000)

        for testo_bottone in ["Accetta tutti", "Accetta", "Accept all", "Accetto"]:
            try:
                bottone = page.get_by_text(testo_bottone, exact=False).first
                if bottone.is_visible(timeout=2000):
                    bottone.click(timeout=2000)
                    page.wait_for_timeout(800)
                    break
            except Exception:
                continue

        campo_ricerca = None
        for selettore in [
            "input[type='search']",
            "input[placeholder*='erca']",
            "input[name*='search']",
            "#search",
            ".search-input input",
        ]:
            try:
                el = page.locator(selettore).first
                if el.is_visible(timeout=1500):
                    campo_ricerca = el
                    break
            except Exception:
                continue

        if campo_ricerca is None:
            try:
                lente = page.get_by_role("button", name=re.compile("cerca", re.I)).first
                lente.click(timeout=2000)
                page.wait_for_timeout(500)
                for selettore in ["input[type='search']", "input[placeholder*='erca']"]:
                    el = page.locator(selettore).first
                    if el.is_visible(timeout=1500):
                        campo_ricerca = el
                        break
            except Exception:
                pass

        if campo_ricerca is None:
            print("  [bpm_power debug] campo di ricerca non trovato, salto questa fonte")
            return None

        campo_ricerca.click(timeout=2000)
        campo_ricerca.fill(termine_ricerca)
        campo_ricerca.press("Enter")
        page.wait_for_load_state("networkidle", timeout=15000)
        page.wait_for_timeout(2000)
    except Exception as e:
        print(f"  [bpm_power debug] errore durante la ricerca: {e}")
        return None

    html = page.content()
    soup = BeautifulSoup(html, "html.parser")

    testo_pagina = soup.get_text(" ", strip=True)
    print(f"  [bpm_power debug] lunghezza testo pagina: {len(testo_pagina)} caratteri")
    print(f"  [bpm_power debug] anteprima: {testo_pagina[:200]}")

    prices = []
    candidati = soup.select(
        ".product-item, .product-card, article.product, .card-product, "
        "li.product, .product-list-item, [class*='product-item']"
    )
    print(f"  [bpm_power debug] candidati (selettori specifici): {len(candidati)}")

    for card in candidati:
        titolo = card.get_text(" ", strip=True)
        if not _titolo_corrisponde(titolo, parole_chiave):
            continue
        m = re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*€", titolo)
        if m:
            p = _parse_price_it(m.group(1))
            if p:
                prices.append(p)

    if not prices:
        testo_completo = soup.get_text("\n", strip=True)
        righe = testo_completo.split("\n")
        print(f"  [bpm_power debug] fallback: {len(righe)} righe di testo nella pagina")
        for i, riga in enumerate(righe):
            if _titolo_corrisponde(riga, parole_chiave):
                blocco = " ".join(righe[i:i + 4])
                m = re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*€", blocco)
                if m:
                    p = _parse_price_it(m.group(1))
                    if p:
                        prices.append(p)

    prices = _prezzi_ragionevoli(prices, prezzo_min)
    return min(prices) if prices else None


SCRAPERS = {
    "trovaprezzi": scrape_trovaprezzi,
    "amazon": scrape_amazon,
    "ebay": scrape_ebay,
    "bpm_power": scrape_bpm_power,
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

    try:
        for comp in components:
            comp_id = comp["id"]
            parole_chiave = comp.get("parole_chiave", [])
            prezzo_min = comp.get("prezzo_min_atteso", 20)
            history.setdefault(comp_id, {"nome": comp["nome"], "prezzi": []})

            best_price = None
            best_source = None

            for source_name, url in comp["fonti"].items():
                scraper_fn = SCRAPERS.get(source_name)
                if not scraper_fn:
                    print(f"[WARN] nessuno scraper per la fonte '{source_name}'")
                    continue
                try:
                    price = scraper_fn(url, parole_chiave, prezzo_min)
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
    finally:
        _chiudi_playwright()

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
