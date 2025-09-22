#!/usr/bin/env python3
# collector.py – sťahuje cenu QQQ každých 15 minút a automaticky obnovuje OAuth token
# Používa Saxo SIM API (REST) namiesto IB‑Gateway.

import os
import sys
import json
import time
import signal
import pathlib
from typing import Dict

# Naše vlastné wrapper‑funkcie (saxo_client.py)
from saxo_client import get, get_valid_token

# -------------------- KONFIGURÁCIA --------------------
SYMBOL          = "QQQ"                     # ticker, ktorý chceme sledovať
EXCHANGE_ID     = "XNAS"                    # v SIM‑prostredí často nie je potrebné, ale ponecháme ako “fallback”
CURRENCY        = "USD"
PRICE_ENDPOINT  = "https://gateway.saxobank.com/sim/openapi/port/v1/infoprices"
SLEEP_INTERVAL  = 900                       # 15 min = 900 s
# -----------------------------------------------------

# -------------------- SIGNAL HANDLING --------------------
_shutdown = False

def _handle_signal(signum, frame):
    """Zachytí SIGINT / SIGTERM a nastaví flag, aby sme sa pekne ukončili."""
    global _shutdown
    _shutdown = True
    print(f"\nSignal {signum} received – ukončujem po aktuálnej iterácii.")

signal.signal(signal.SIGINT,  _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)
# -------------------------------------------------------

# -------------------- UIC RESOLUTION --------------------
def resolve_uic(symbol: str,
               exchange_id: str = EXCHANGE_ID,
               currency: str = CURRENCY) -> int:
    """
    Zistí UIC (Unique Instrument Code) pre daný symbol v SIM‑prostredí.
    Na niektoré tickery (napr. QQQ) je potrebné:
      • povoliť IncludeNonTradable = true
      • pridať CountryId = US
      • v prípade neúspešného výsledku skúsiť požiadavku aj bez ExchangeId
    """
    url = "https://gateway.saxobank.com/sim/openapi/ref/v1/instruments"

    # Základné parametre – používame IncludeNonTradable=true a CountryId=US,
    # pretože v sandboxe niekedy vracajú “non‑tradable” varianty.
    params = {
        "AssetTypes":        "Stock",
        "Filter":            symbol,
        "Currency":          currency,
        "IncludeNonTradable":"true",
        "StartIndex":        0,
        "Count":             10,
        "CountryId":         "US",
    }

    # Pridáme ExchangeId, ak je definovaný – môže pomôcť, ale nie je povinný.
    if exchange_id:
        params["ExchangeId"] = exchange_id

    # Prvý pokus (s ExchangeId)
    resp = get(url, params=params)
    data = resp.get("Data", [])
    if data:
        return int(data[0]["Uic"])

    # Ak sme nedostali žiadny výsledok, skúšame **bez** ExchangeId
    if "ExchangeId" in params:
        params.pop("ExchangeId")
        resp = get(url, params=params)
        data = resp.get("Data", [])
        if data:
            return int(data[0]["Uic"])

    # Zlyhalo aj po odstránení ExchangeId – vypíšeme úplnú odpoveď API,
    # aby ste videli, čo Saxo vrátil.
    raise RuntimeError(
        f"Nenašiel som UIC pre {symbol} (exchange={exchange_id}). "
        f"API odpoveď: {json.dumps(resp, indent=2)}"
    )
# -------------------------------------------------------

# -------------------- PRICE FETCHING --------------------
def fetch_last_price(uic: int) -> None:
    """
    Načítanie poslednej ceny (Bid/Ask/Last) pre zadaný UIC.
    Výsledok sa vypíše na stdout.
    """
    params = {
        "Uic":       uic,
        "AssetType": "Stock",      # pre QQQ je typ Stock (ETF)
        # AccountKey nie je povinný pre infoprices, takže ho vynecháme
    }

    resp = get(PRICE_ENDPOINT, params=params)

    # Odpoveď typicky obsahuje polia Bid, Ask, Last, Mid a SnapshotTime
    bid   = resp.get("Bid",   {}).get("Price")
    ask   = resp.get("Ask",   {}).get("Price")
    last  = resp.get("Last",  {}).get("Price")
    mid   = resp.get("Mid",   {}).get("Price")
    ts    = resp.get("SnapshotTime")   # ISO‑8601 časová značka

    # Ak Last nie je prítomný, použijeme Mid (alebo Bid/Ask ako poslednú cenu)
    price_display = last if last is not None else mid

    print(f"[{ts}] Symbol: {SYMBOL} – Bid: {bid}, Ask: {ask}, Price: {price_display}")
# -------------------------------------------------------

# -------------------- MAIN LOOP --------------------
def main() -> None:
    """
    Hlavná slučka:
      1. Získame (a prípadne refreshneme) token – to robí saxo_client.
      2. Zistíme UIC pre požadovaný symbol (jednorazovo, pretože sa nemení).
      3. V cykle každých SLEEP_INTERVAL sekúnd načítame cenu a vypíšeme ju.
      4. Na SIGINT/SIGTERM sa ukončí po ukončení aktuálnej iterácie.
    """
    # 1️⃣ Získame platný token – ak je potrebné, automaticky sa refreshne.
    try:
        _ = get_valid_token()
    except Exception as e:
        print("ERROR – nepodarilo sa načítať alebo obnoviť token:", e)
        sys.exit(1)

    # 2️⃣ Zistíme UIC – ak sa nepodarí, ukončíme program s chybou.
    try:
        uic = resolve_uic(SYMBOL)
        print(f"Uic pre {SYMBOL} = {uic}")
    except Exception as e:
        print("ERROR pri získavaní UIC:", e)
        sys.exit(1)

    # 3️⃣ Hlavná slučka – každých 15 minút načítame cenu.
    while not _shutdown:
        try:
            fetch_last_price(uic)
        except Exception as err:
            print("ERROR pri získavaní ceny:", err)

        # Počkáme SLEEP_INTERVAL sekúnd, ale kontrolujeme signál každú sekundu,
        # aby sme sa pri Ctrl+C nečakali celých 15 minút.
        for _ in range(SLEEP_INTERVAL):
            if _shutdown:
                break
            time.sleep(1)

    print("\nCollector ukončený – ďakujem za sledovanie.")

# -------------------------------------------------------
if __name__ == "__main__":
    main()
