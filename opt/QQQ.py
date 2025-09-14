#!/usr/bin/env python3
# QQQ_demo_apl – OAuth2 flow with automatic token refresh

import os, sys, json, time, threading, urllib.parse, urllib.request, http.server, secrets

# -------------------- CONFIG --------------------
APP_NAME      = "QQQ"
CLIENT_ID     = "4252e068bf8b41b4a41545b73d1ccc6d"
CLIENT_SECRET = "9c4a5493160a4a72b91febb98e7cd63c"

AUTH_ENDPOINT = "https://sim.logonvalidation.net/authorize"
TOKEN_ENDPOINT = "https://sim.logonvalidation.net/token"
REDIRECT_URI   = "http://127.0.0.1:5327/callback"
SCOPE          = "openid profile"

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 5327
TOKEN_FILE  = os.path.expanduser("~/.ibkr_token.json")
# ------------------------------------------------

state = secrets.token_urlsafe(16)


class OAuthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            return

        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        recv_state = params.get("state", [None])[0]

        if recv_state != state or not code:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid callback parameters")
            self.server.code = None
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Authorization code received. You can close this window.")
            self.server.code = code

        self.server.event.set()

    def log_message(self, *args):
        return


def open_browser(url):
    browser_cmd = os.environ.get("BROWSER", "xdg-open")
    os.system(f'{browser_cmd} "{url}"')


def exchange_code_for_token(code):
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(TOKEN_ENDPOINT, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=15) as resp:
        token = json.loads(resp.read().decode())
    # add absolute expiry timestamp for easy checks
    token["exp"] = int(time.time()) + token.get("expires_in", 0)
    return token


def save_token(data):
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Token saved to {TOKEN_FILE}")


def load_token():
    try:
        with open(TOKEN_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def refresh_token(refresh_tok):
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_tok,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    body = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(TOKEN_ENDPOINT, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=10) as resp:
        token = json.loads(resp.read().decode())
    token["exp"] = int(time.time()) + token.get("expires_in", 0)
    return token


def get_valid_token():
    tok = load_token()
    if not tok:
        raise RuntimeError(
            "Token file missing – run the OAuth flow first (python QQQ_demo_apl.py)."
        )
    now = int(time.time())
    if now < tok.get("exp", 0) - 30:
        return tok

    print("Access token expired – refreshing...")
    refreshed = refresh_token(tok["refresh_token"])
    # keep old refresh token if new one not returned
    if "refresh_token" not in refreshed:
        refreshed["refresh_token"] = tok["refresh_token"]
    save_token(refreshed)
    return refreshed


def main():
    # ----- OAuth flow (only needed if no token file) -----
    if not os.path.isfile(TOKEN_FILE):
        auth_params = {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPE,
            "state": state,
        }
        url = AUTH_ENDPOINT + "?" + urllib.parse.urlencode(auth_params)
        print("Opening authorization URL in host browser…")
        print(url)
        threading.Thread(target=open_browser, args=(url,), daemon=True).start()

        httpd = http.server.HTTPServer((LISTEN_HOST, LISTEN_PORT), OAuthHandler)
        httpd.code = None
        httpd.event = threading.Event()
        print(f"Listening for redirect on {LISTEN_HOST}:{LISTEN_PORT} (path /callback) …")
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        waited = httpd.event.wait(timeout=300)   # 5 min
        httpd.shutdown()

        if not waited or not httpd.code:
            print("Did not receive authorization code (timeout or error).")
            sys.exit(1)

        token_resp = exchange_code_for_token(httpd.code)
        save_token(token_resp)
        print(json.dumps(token_resp, indent=2))
    else:
        # token exists – just ensure it is still valid (refresh if needed)
        token_resp = get_valid_token()
        print("Current token loaded/ refreshed.")
        print(json.dumps(token_resp, indent=2))


if __name__ == "__main__":
    main()