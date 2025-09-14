import os
import subprocess
import pathlib
import webbrowser
import requests
from dotenv import load_dotenv
from saxo_openapi.saxo_openapi import API

#!/usr/bin/env python3
# droplet-sync/api/auth_code_flow.py

import urllib.parse

# ------------------------------------------------------------
# Načítanie .env
# ------------------------------------------------------------
env_path = pathlib.Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# ------------------------------------------------------------
# Konfigurácia (z .env a z JSON‑súboru)
# ------------------------------------------------------------
CLIENT_ID = os.getenv("SAXO_CLIENT_ID")
CLIENT_SECRET = os.getenv("SAXO_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SAXO_REDIRECT_URI")
ENVIRONMENT = os.getenv("SAXO_ENV", "simulation").lower()

if not (CLIENT_ID and CLIENT_SECRET and REDIRECT_URI):
    raise RuntimeError(
        "V .env musia byť nastavené SAXO_CLIENT_ID, SAXO_CLIENT_SECRET a SAXO_REDIRECT_URI"
    )

# Konštanty podľa vášho JSON‑súboru
AUTH_ENDPOINT = "https://sim.logonvalidation.net/authorize"
TOKEN_ENDPOINT = "https://sim.logonvalidation.net/token"
BASE_API_URL = "https://gateway.saxobank.com/sim/openapi/"

# ------------------------------------------------------------
# 1️⃣ Vytvorenie autorizačného URL a otvorenie prehliadača
# ------------------------------------------------------------
def build_auth_url():
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": "openid profile email trading",
        "state": "test_state_123",
    }
    return f"{AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"

def try_open_url(url: str):
    # Prefer host browser forwarded via $BROWSER in devcontainer setup:
    browser_cmd = os.environ.get("BROWSER")
    if browser_cmd:
        try:
            subprocess.run([browser_cmd, url], check=False)
            return
        except Exception:
            pass
    # Fallback to Python's webbrowser
    try:
        webbrowser.open(url)
    except Exception:
        pass

print("\n=== AUTORIZAČNÝ KROK ===")
auth_url = build_auth_url()
print("Otvorte nasledujúci odkaz v prehliadači a prihláste sa:")
print(auth_url)

# Pokúsime sa otvoriť automaticky (použije $BROWSER ak je nastavené v devcontainer)
try_open_url(auth_url)

# ------------------------------------------------------------
# 2️⃣ Získajte autorizačný kód z redirect‑URL
# ------------------------------------------------------------
print("\n> Po prihlásení budete presmerovaní na URL:")
print(f"    {REDIRECT_URI}?code=XXXX&state=...")
print("Skopírujte hodnotu parametra **code** a vložte ju sem.")
code = input("Enter authorization code: ").strip()
if not code:
    raise RuntimeError("Nebolo zadané žiadne kód (code).")

# ------------------------------------------------------------
# 3️⃣ Vymenujeme kód za access‑token
# ------------------------------------------------------------
def fetch_token(auth_code: str) -> dict:
    payload = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    resp = requests.post(TOKEN_ENDPOINT, data=payload, timeout=12)
    resp.raise_for_status()
    return resp.json()

token_data = fetch_token(code)

access_token = token_data.get("access_token")
refresh_token = token_data.get("refresh_token")

if not access_token:
    raise RuntimeError(f"Nenašiel sa access_token v odpovedi: {token_data}")

print("\n=== TOKEN ZÍSKANÝ ===")
print(f"Access‑token (valid approx. {token_data.get('expires_in')} s)")
if refresh_token:
    print(f"Refresh‑token : {refresh_token[:8]}…")
else:
    print("Refresh‑token : (not provided)")

# ------------------------------------------------------------
# 4️⃣ Vytvorenie API‑klienta a rýchly test
# ------------------------------------------------------------
api_environment = "simulation" if ENVIRONMENT == "simulation" else {"api": "https://gateway.saxobank.com"}
api = API(access_token=access_token, environment=api_environment)

print("\n✅ API‑klient inicializovaný")
print("API verzia:", getattr(api, "VERSION", "unknown"))

try:
    accounts = api.accounts()
    print("Počet účtov:", len(accounts))
except Exception as exc:
    print("Chyba pri volaní endpointu /accounts:", exc)

# ------------------------------------------------------------
# 5️⃣ (Voliteľne) Refresh token – ako príklad
# ------------------------------------------------------------
def refresh_access(refresh_tok: str) -> str:
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_tok,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    r = requests.post(TOKEN_ENDPOINT, data=payload, timeout=12)
    r.raise_for_status()
    return r.json()["access_token"]

# príklad použitia:
# if refresh_token:
#     new_token = refresh_access(refresh_token)
#     print("Nový token:", new_token[:8], "...")