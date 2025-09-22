import os
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

#!/usr/bin/env python3
# saxo_client.py – jednoduchý wrapper pre Saxo API (SIM‑prostredie)
# Používa rovnaké OAuth 2.0 nastavenia ako QQQ_demo_apl.py

import urllib.parse
import urllib.request
import urllib.error

# -------------------- KONFIGURÁCIA --------------------
CLIENT_ID       = "4252e068bf8b41b4a41545b73d1ccc6d"
CLIENT_SECRET   = "9c4a5493160a4a72b91febb98e7cd63c"
TOKEN_ENDPOINT  = "https://sim.logonvalidation.net/token"
TOKEN_FILE      = Path(os.path.expanduser("~/.ibkr_token.json"))
# -----------------------------------------------------

# ---------- 1. načítanie a uloženie tokenu ----------
def _load_token() -> Optional[Dict]:
    try:
        with TOKEN_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        raise RuntimeError(f"Chyba pri čítaní token súboru: {e}")

def _save_token(data: Dict) -> None:
    tmp = TOKEN_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(TOKEN_FILE)
    TOKEN_FILE.chmod(0o600)
    # print(f"Token uložený do {TOKEN_FILE}")

# ---------- 2. refresh ----------
def _refresh_token(refresh_tok: str, retries: int = 2, backoff: float = 1.0) -> Dict:
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
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            data["exp"] = int(time.time()) + int(data.get("expires_in", 0))
            return data
        except urllib.error.HTTPError as e:
            last_exc = e
            if 400 <= e.code < 500:
                raise RuntimeError(f"HTTP error {e.code}: {e.read().decode()}")
        except Exception as e:
            last_exc = e

        if attempt < retries:
            sleep = backoff * (2 ** attempt)
            time.sleep(sleep)

    raise RuntimeError(f"Nepodarilo sa obnoviť token: {last_exc}")

# ---------- 3. získať platný access_token ----------
def get_valid_token() -> Dict:
    tok = _load_token()
    if not tok:
        raise RuntimeError(
            "Token súbor chýba – najskôr spustite OAuth flow (QQQ_demo_apl.py)."
        )
    now = int(time.time())
    # ak token nemá pole "exp", doplňte ho (použijeme expires_in)
    if "exp" not in tok:
        tok["exp"] = now + int(tok.get("expires_in", 0))

    if now < tok["exp"] - 30:          # ešte platný (30 s rezerva)
        return tok

    # token expiroval → refresh
    refreshed = _refresh_token(tok["refresh_token"])
    # udržíme starý refresh_token, ak server nevrátil nový
    if "refresh_token" not in refreshed:
        refreshed["refresh_token"] = tok["refresh_token"]
    _save_token(refreshed)
    return refreshed

# ---------- 4. HTTP wrapper ----------
def _prepare_headers(token: str, extra: Optional[Dict] = None) -> Dict:
    hdr = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if extra:
        hdr.update(extra)
    return hdr

def _request(method: str, url: str, *, params: Optional[Dict] = None,
             json_data: Optional[Any] = None, retry: bool = True) -> Dict:
    """
    Vykoná HTTP požiadavku a vráti dekódovaný JSON.
    V prípade 401 (neplatný token) automaticky token obnoví a požiadavku zopakuje.
    """
    token_obj = get_valid_token()
    token = token_obj["access_token"]

    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    data = None
    if json_data is not None:
        data = json.dumps(json_data).encode()

    req = urllib.request.Request(url, data=data, method=method.upper())
    req.headers = _prepare_headers(token)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 401 and retry:
            # token pravdepodobne expiroval – obnovíme a zopakujeme
            _save_token(_refresh_token(token_obj["refresh_token"]))
            return _request(method, url, params=params,
                            json_data=json_data, retry=False)
        # iné chyby necháme predať vyššie
        raise RuntimeError(f"HTTP {e.code} – {e.read().decode()}")

def get(url: str, *, params: Optional[Dict] = None) -> Dict:
    """GET request s automatickým refreshom tokenu."""
    return _request("GET", url, params=params)

def post(url: str, *, json_data: Optional[Any] = None) -> Dict:
    """POST request s automatickým refreshom tokenu."""
    return _request("POST", url, json_data=json_data)

# -------------------------------------------------
# Priame testovanie (volá sa iba keď spustíme modul)
if __name__ == "__main__":
    # jednoduchý test – vypíše aktuálny token a
    # pokúsi sa získať info o účte (endpoint z dokumentácie SIM‑prostredia)
    try:
        token = get_valid_token()
        print("Access token loaded / refreshed.")
        # ukážka volania – získanie zoznamu účtov (ak dokumentácia obsahuje taký endpoint)
        # URL = "https://gateway.saxobank.com/sim/openapi/port/v1/accounts"
        # resp = get(URL)
        # print(json.dumps(resp, indent=2))
    except Exception as exc:
        print("Chyba:", exc)
