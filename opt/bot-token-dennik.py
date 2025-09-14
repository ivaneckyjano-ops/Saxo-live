##!/usr/bin/env python3
import json
import time
import logging
import requests
import jwt
import pandas as pd
from pathlib import Path
from configparser import ConfigParser, NoSectionError, NoOptionError
from datetime import datetime

# -------------------- Konfigurácia loggingu --------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# -------------------- Načítanie nastavení --------------------
cfg = ConfigParser()
config_path = Path(__file__).parent / "config.ini"
if not config_path.is_file():
    raise RuntimeError(f"Konfiguračný súbor nenájdený: {config_path}")
cfg.read(config_path)

try:
    CLIENT_ID     = cfg.get('oauth', 'client_id')
    CLIENT_SECRET = cfg.get('oauth', 'client_secret')
    REFRESH_TOKEN = cfg.get('oauth', 'refresh_token')
    TOKEN_URL     = cfg.get('oauth', 'token_url')
    REDIRECT_URI  = cfg.get('oauth', 'redirect_uri')
    BASE_URL      = cfg.get('api',   'base_url')
    TOKEN_FILE    = Path(cfg.get('settings', 'token_file'))
except (NoSectionError, NoOptionError) as e:
    raise RuntimeError(f"Chýbajúce nastavenie v config.ini: {e}") from e

# -------------------- Pomocné funkcie --------------------
def save_token(data: dict) -> None:
    """Uloží celý odpovedný JSON do súboru."""
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(data, indent=2))

def load_token() -> dict:
    """Načíta token JSON alebo vráti prázdny dict."""
    if not TOKEN_FILE.is_file():
        return {}
    try:
        return json.loads(TOKEN_FILE.read_text())
    except (json.JSONDecodeError, OSError) as e:
        log.warning(f"Nepodarilo sa načítať token súbor: {e}")
        return {}

def token_is_valid(token_data: dict) -> bool:
    """Skúsi získať exp z JWT alebo z `expiry_ts`."""
    expiry_ts = token_data.get('expiry_ts')
    now = int(time.time())

    if expiry_ts:
        try:
            return int(expiry_ts) > now
        except Exception:
            pass

    access = token_data.get('access_token')
    if not access:
        return False

    try:
        payload = jwt.decode(access, options={"verify_signature": False})
        exp = payload.get('exp')
        return bool(exp and int(exp) > now)
    except Exception:
        return False

def invalidate_token() -> None:
    """Odstráni lokálny token – použije sa pri 401."""
    if TOKEN_FILE.is_file():
        TOKEN_FILE.unlink()
        log.info("Lokálny token súbor odstránený (invalidovaný).")

def obtain_new_access(refresh_token: str = None) -> dict:
    """
    Získa nový access‑token (a nový refresh‑) pomocou grant_type=refresh_token.
    Používa HTTP Basic Auth, pretože endpoint to vyžaduje.
    """
    payload = {
        'grant_type':    'refresh_token',
        'refresh_token': refresh_token or REFRESH_TOKEN,
        'redirect_uri':  REDIRECT_URI,
    }

    # Basic Auth – klientský ID a secret v hlavičke
    auth = requests.auth.HTTPBasicAuth(CLIENT_ID, CLIENT_SECRET)

    log.debug("Obnovujem token…")
    r = requests.post(TOKEN_URL, data=payload, auth=auth, timeout=15)
    r.raise_for_status()
    data = r.json()

    # Pridáme unix timestamp expirácie pre rýchlejší check
    if 'expires_in' in data:
        try:
            data['expiry_ts'] = int(time.time()) + int(data['expires_in'])
        except Exception:
            pass

    # Uložíme do súboru (vrátane nového refresh_token)
    save_token(data)
    log.info("Token úspešne obnovený (expires_in=%s sekúnd).", data.get('expires_in'))
    return data

def get_valid_token() -> str:
    """Vráti platný access‑token – prípadne ho obnoví."""
    token_data = load_token()

    # Ak token neexistuje alebo už nie je platný → obnovíme
    if not token_is_valid(token_data):
        log.info("Token neplatný alebo chýba – obnovujem.")
        token_data = obtain_new_access()
    else:
        # Ak je menej ako 5 minút do expirácie – predbežná obnova
        remaining = token_data.get('expiry_ts', 0) - int(time.time())
        if remaining < 300:
            log.info("Token čoskoro expiruje (za %s sekúnd) – obnovujem.", remaining)
            token_data = obtain_new_access(token_data.get('refresh_token'))

    access = token_data.get('access_token')
    if not access:
        raise RuntimeError("Po obnove nebol vrátený access_token.")
    return access

# -------------------- API volanie --------------------
def example_api_call() -> None:
    """Ukážkový request – volá endpoint /port/v1/accountoverview."""
    token = get_valid_token()
    headers = {'Authorization': f'Bearer {token}'}
    url = f"{BASE_URL}/port/v1/accountoverview"

    # Prvé pokusenie
    r = requests.get(url, headers=headers, timeout=15)

    # Ak server odpovie 401 → pravdepodobne token expiroval alebo bol odvolaný
    if r.status_code == 401:
        log.warning("401 – token pravdepodobne neplatný, skúšam obnoviť.")
        invalidate_token()                     # odstránime lokálny token
        token = get_valid_token()              # získame čerstvý
        headers['Authorization'] = f'Bearer {token}'
        r = requests.get(url, headers=headers, timeout=15)

    r.raise_for_status()
    data = r.json()
    # Vypíšeme len úvodný úsek (aby sme nepreplnili terminál)
    pretty = json.dumps(data, indent=2, ensure_ascii=False)
    log.info("Úspešný výstup (prvé 500 znakov):\n%s", pretty[:500] + ("..." if len(pretty) > 500 else ""))

# -------------------- Hlavná slučka --------------------
if __name__ == '__main__':
    try:
        while True:
            try:
                # Volanie API endpointu pre stiahnutie údajov pozícii
                token = get_valid_token()
                headers = {'Authorization': f'Bearer {token}'}
                url = f"{BASE_URL}/port/v1/positions"
                r = requests.get(url, headers=headers, timeout=15)
                r.raise_for_status()
                data = r.json()
                # Zapisovanie údajov do súboru
                with open('positions.json', 'w') as f:
                    json.dump(data, f, indent=2)
                log.info("Údaje pozícii stiahnuté a uložené do súboru.")

                # Stahovanie cien pre každý inštrument
                instruments = pd.read_csv('instruments.csv')
                for instrument in instruments['UIC']:
                    url = f"{BASE_URL}/port/v1/instruments/{instrument}/prices"
                    r = requests.get(url, headers=headers, timeout=15)
                    r.raise_for_status()
                    data = r.json()
                    # Uloženie údajov do súboru
                    with open(f'{instrument}.json', 'w') as f:
                        json.dump(data, f, indent=2)
                    log.info(f"Ceny pre inštrument {instrument} stiahnuté a uložené do súboru.")
            except Exception as exc:
                log.error("Chyba počas volania API: %s", exc, exc_info=True)
                # jednoduchý back‑off – pri chybe čakáme 30 sekúnd
                time.sleep(30)
            else:
                # medzi volaniami čakáme 5 minút
                time.sleep(300)
    except KeyboardInterrupt:
        log.info("Ukončené používateľom.")