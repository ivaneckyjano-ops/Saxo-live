from __future__ import annotations
import os
import json
import time
import signal
import pathlib
from typing import Optional, Dict
from ib_insync import Stock

#!/usr/bin/env python3
# collector.py – sťahuje dáta každých 5 min. a automaticky obnovuje token
# Upravené: robustnejší refresh, bezpečné ukladanie tokenu, čisté ukončenie.

import urllib.request
import urllib.parse
import urllib.error

from ib_insync import IB  # pip install ib_insync

# -------------------- KONFIGURÁCIA --------------------
CLIENT_ID       = "4252e068bf8b41b4a41545b73d1ccc6d"
CLIENT_SECRET   = "9c4a5493160a4a72b91febb98e7cd63c"
TOKEN_ENDPOINT  = "https://sim.logonvalidation.net/token"
TOKEN_FILE      = pathlib.Path(os.path.expanduser("~/.ibkr_token.json"))
IB_HOST         = "127.0.0.1"
IB_PORT         = 7497
IB_CLIENT_ID    = 1                     # libib‑clientId
# -----------------------------------------------------

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    _shutdown = True
    print(f"Signal {signum} received — ukončujem po aktuálnej iterácii.")


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ---------- 1. načítanie a uloženie tokenu ----------
def load_token() -> Optional[Dict]:
    try:
        with TOKEN_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        raise RuntimeError(f"Chyba pri čítaní token súboru: {e}")


def save_token(data: Dict) -> None:
    tmp = TOKEN_FILE.with_suffix(".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        # atomický presun a nastavenie prístupových práv
        tmp.replace(TOKEN_FILE)
        TOKEN_FILE.chmod(0o600)
        print(f"Token saved to {TOKEN_FILE}")
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass


# ---------- 2. refresh ----------
def refresh_token(refresh_tok: str, retries: int = 2, backoff: float = 1.0) -> Dict:
    payload = {
        "grant_type":    "refresh_token",
        "refresh_token": refresh_tok,
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    body = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(TOKEN_ENDPOINT, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    last_exc = None
    for attempt in range(1 + retries):
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode()
                data = json.loads(raw)
            # pridáme absolútny čas expirácie (unix timestamp)
            data["exp"] = int(time.time()) + int(data.get("expires_in", 0))
            return data
        except urllib.error.HTTPError as e:
            # Ak server vrátil 4xx/5xx, nechceme nekonečne retryovať pri 4xx
            last_exc = e
            if 400 <= e.code < 500:
                raise RuntimeError(f"HTTP error {e.code}: {e.read().decode()}")
        except Exception as e:
            last_exc = e

        if attempt < retries:
            sleep_for = backoff * (2 ** attempt)
            print(f"Refresh failed (attempt {attempt+1}), retryujem o {sleep_for:.1f}s...")
            time.sleep(sleep_for)

    raise RuntimeError(f"Failed to refresh token: {last_exc}")


# ---------- 3. získať platný access_token ----------
def get_valid_token() -> Dict:
    tok = load_token()
    if not tok:
        raise RuntimeError(
            "Token súbor chýba – najskôr spusti OAuth flow (QQQ_demo_apl.py)."
        )

    now = int(time.time())
    # ak token má v sebe pole "exp" – použijeme ho, inak ho spočítame
    if "exp" not in tok:
        tok["exp"] = now + int(tok.get("expires_in", 0))

    if now < tok["exp"] - 30:               # ešte platný (30 s rezerva)
        return tok

    # access token expiroval → refresh
    print("Access token expired – obnovujem pomocou refresh_token.")
    refreshed = refresh_token(tok["refresh_token"])
    # ak server vráti nový refresh_token, tak ho uložíme
    if "refresh_token" not in refreshed:
        refreshed["refresh_token"] = tok["refresh_token"]
    save_token(refreshed)
    return refreshed


# ---------- 4. funkcia na sťahovanie dát ----------
def download_qqq_data(ib: IB) -> None:
    # QQQ (NASDAQ‑100) – futures?  Tu používame spot‑symbol QQQ
    contract = Stock("QQQ", "SMART", "USD")
    qualified = ib.qualifyContracts(contract)
    if not qualified:
        print("Kontrakt nebolo možné kvalifikovať.")
        return
    contract = qualified[0]

    # 5‑minútové historické OHLC (1‑minúta bar)
    bars = ib.reqHistoricalData(
        contract,
        endDateTime='',
        durationStr='5 M',
        barSizeSetting='1 min',
        whatToShow='TRADES',
        useRTH=False,
        formatDate=1,
    )
    if bars:
        last = bars[-1]
        print(
            f"{last.date}  O:{last.open:.2f}  H:{last.high:.2f}  "
            f"L:{last.low:.2f}  C:{last.close:.2f}"
        )
    else:
        print("Žiadne historické dáta.")


# ---------- 5. hlavná slučka ----------
def main() -> None:
    global _shutdown
    while not _shutdown:
        ib = None
        try:
            token = get_valid_token()                 # refresh, ak treba
            # ib_insync momentálne nepoužíva access_token pri pripojení k IB‑Gateway.
            # Token slúži iba pre Client‑Portal API, ale ho musíme mať.
            ib = IB()
            ib.connect(host=IB_HOST, port=IB_PORT, clientId=IB_CLIENT_ID, timeout=10)
            download_qqq_data(ib)
        except Exception as e:
            print("ERROR:", e)
        finally:
            if ib is not None and ib.isConnected():
                try:
                    ib.disconnect()
                except Exception:
                    pass

        # čakáme 5 minút (300 s), ale umožníme rýchle ukončenie
        for _ in range(300):
            if _shutdown:
                break
            time.sleep(1)


if __name__ == "__main__":
    main()