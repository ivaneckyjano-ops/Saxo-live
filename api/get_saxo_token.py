import os
import pathlib
import json
import webbrowser
import subprocess
import socketserver
import requests
from dotenv import load_dotenv, set_key
from datetime import datetime, timezone, timedelta

import urllib.parse
import http.server

# ------------------------------------------------------------
# nacitnie nastaveni z .env
# ------------------------------------------------------------
BASE_DIR = pathlib.Path(__file__).parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

CLIENT_ID     = os.getenv("SAXO_CLIENT_ID")
CLIENT_SECRET = os.getenv("SAXO_CLIENT_SECRET")
REDIRECT_URI  = os.getenv("SAXO_REDIRECT_URI")      # napr. http://127.0.0.1:8080/callback
ENVIRONMENT   = os.getenv("SAXO_ENV", "simulation") # "simulation" alebo "live"

if not all([CLIENT_ID, CLIENT_SECRET, REDIRECT_URI]):
    raise RuntimeError(
        "V .env musia byt nastavene SAXO_CLIENT_ID, SAXO_CLIENT_SECRET a SAXO_REDIRECT_URI"
    )

# Endpoints (sandbox)
AUTH_ENDPOINT  = "https://sim.logonvalidation.net/authorize"
TOKEN_ENDPOINT = "https://sim.logonvalidation.net/token"

# ------------------------------------------------------------
# 1 Vytvorenie autorizacneho URL
# ------------------------------------------------------------
def build_auth_url():
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": "openid profile email trading",   # ak potrebujete dalsie rozsahy, pridajte ich sem
        "state": "saxo_demo_state_123",           # volitelny, pomaha predchadzat CSRF
    }
    return f"{AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"

# ------------------------------------------------------------
# 2 Lokalny HTTP server, ktory prijme redirect s kodom
# ------------------------------------------------------------
class CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Jednoduchy handler, ktory cita parameter `code` z URL a ulozi ho do `self.server.code`."""
    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        qs = urllib.parse.parse_qs(query)
        if "code" in qs:
            self.server.code = qs["code"][0]    # ulozime koddo objektu servera
            # odpoved pre pouzivatela v prehliadaci
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write("<h2>Autorizacia uspesna  zavrite toto okno.</h2>".encode('utf-8'))
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write("<h2>Chyba parameter `code`.</h2>".encode('utf-8'))

    # Potlaĝí výpis do konzoly
    def log_message(self, format, *args):
        return

def start_local_server():
    """Spustíme HTTP server na porte, ktorý je v REDIRECT_URI (predpokladáme 127.0.0.1:8080)."""
    parsed = urllib.parse.urlparse(REDIRECT_URI)
    host, port = parsed.hostname, parsed.port
    with socketserver.TCPServer((host, port), CallbackHandler) as httpd:
        httpd.code = None
        # Server bezi asynchronne - po prijatí kódu sa zastaví
        while httpd.code is None:
            httpd.handle_request()
        return httpd.code

# ------------------------------------------------------------
# 3vymena kodu za token
# ------------------------------------------------------------
def exchange_code_for_token(auth_code: str) -> dict:
    payload = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    resp = requests.post(TOKEN_ENDPOINT, data=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()   # obsahuje access_token, expires_in, refresh_token, token_type …

# ------------------------------------------------------------
# 4 ulozenie  tokenov do .env
# ------------------------------------------------------------
def persist_tokens(token_data: dict):
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")

    if not access_token:
        raise RuntimeError("V odpovedi chýba položka `access_token`")

    # Používame python-dotenv funkciu set_key, ktorá aktualizuje alebo pridá riadok
    set_key(str(ENV_PATH), "SAXO_ACCESS_TOKEN", access_token, quote_mode="none")
    print("? Access-token ulozeny do .env (SAXO_ACCESS_TOKEN)")

    if refresh_token:
        set_key(str(ENV_PATH), "SAXO_REFRESH_TOKEN", refresh_token, quote_mode="none")
        print("? Refresh-token ulozene do .env (SAXO_REFRESH_TOKEN)")

# ------------------------------------------------------------
# 5 Hlavna logika
# ------------------------------------------------------------
def main():
    print("\n=== SAXO Sandbox  získanie nového OAuth tokenu ===\n")

    auth_url = build_auth_url()
    print("Otváram prehliadač - prihláste sa do Saxo Sandbox a po schválení budete presmerovaní.")
    print("Ak prehliadač neotvorí automaticky, skopírujte a otvorte túto URL manuálne:\n")
    print(auth_url + "\n")

    # Pokusime sa otvori? prehliada? na hoste (ak je nastaveny $BROWSER, pouzijeme ho).
    try:
        browser_cmd = os.environ.get("BROWSER")
        if browser_cmd:
            # ak je BROWSER nastaveny, zavolame ho s URL (napr. "$BROWSER" <url> pod?a devcontainer)
            subprocess.Popen([browser_cmd, auth_url])
        else:
            webbrowser.open(auth_url, new=2)
    except Exception:
        pass

    # Spustime lokalny server, ktory pocka na redirect s kodom
    print(f"?ak�m na presmerovanie na {REDIRECT_URI} �")
    auth_code = start_local_server()
    print(f"? Z�skan� autoriza?n� k�d: {auth_code[:8]}�")

    # Vymena kodu  za token
    token_data = exchange_code_for_token(auth_code)
    print("? Token z�skan� zo servera")
    print(json.dumps(token_data, indent=2))

    # ulozime tokeny do .env
    persist_tokens(token_data)

    # kratka kontrola expiracie (len pre informaciu)
    exp_ts = token_data.get("expires_in")
    if exp_ts:
        exp_time = datetime.now(timezone.utc) + timedelta(seconds=int(exp_ts))
        print(f"Token expiruje: {exp_time.isoformat()} (priblizne za {exp_ts//60} minut)")

    print("\n=== Hotovo! ===")
    print("Teraz môžete spustiť svoj test:")
    print("  python test_saxo_with_env_token.py")

if __name__ == "__main__":
    main()