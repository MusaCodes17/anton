"""THROWAWAY spike (COROS direct sync §1) — not production code.

Run with backend/venv/bin/python:
  auth     DCR + PKCE sign-in via a loopback callback; saves tokens to a gitignored state file
  probe    refresh once (records rotation + lifetimes), tools/list, querySportRecords, getActivityDetail, fixtures
  refresh  refresh again later (run days apart to prove unattended refresh)
Tokens are never printed.
"""
import base64, hashlib, http.server, json, os, secrets, sys, threading, time, urllib.parse, webbrowser
from datetime import datetime, timedelta
import httpx

BASE = "https://mcpus.coros.com"
MCP = f"{BASE}/mcp"
AS = httpx.get(f"{BASE}/.well-known/oauth-authorization-server", timeout=15).json()
SCOPE = "openid mcp.tools offline_access"
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, ".coros_spike_state.json")
FIX = os.path.join(HERE, "fixtures")
PORT = 8765
REDIRECT = f"http://127.0.0.1:{PORT}/callback"


def load(): return json.load(open(STATE))
def save(s):
    json.dump(s, open(STATE, "w"), indent=2); os.chmod(STATE, 0o600)


def auth():
    reg = httpx.post(AS["registration_endpoint"], timeout=15, json={
        "client_name": "Anton (spike)", "redirect_uris": [REDIRECT],
        "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
        "token_endpoint_auth_method": "none", "scope": SCOPE}).json()
    cid = reg["client_id"]
    print("DCR ok; auth method:", reg.get("token_endpoint_auth_method"), "secret issued:", "client_secret" in reg)
    # does DCR accept the production https callback too? (needed for §2)
    p = httpx.post(AS["registration_endpoint"], timeout=15, json={
        "client_name": "Anton (spike https probe)", "redirect_uris": ["https://anton.musasouled.com/api/coros/callback"],
        "grant_types": ["authorization_code", "refresh_token"], "token_endpoint_auth_method": "none", "scope": SCOPE})
    print("DCR https prod redirect:", p.status_code)
    ver = secrets.token_urlsafe(64); st = secrets.token_urlsafe(16)
    chal = base64.urlsafe_b64encode(hashlib.sha256(ver.encode()).digest()).rstrip(b"=").decode()
    q = urllib.parse.urlencode({"response_type": "code", "client_id": cid, "redirect_uri": REDIRECT, "scope": SCOPE,
        "state": st, "code_challenge": chal, "code_challenge_method": "S256", "resource": MCP})
    got = {}
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            got.update(urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query))
            self.send_response(200); self.end_headers(); self.wfile.write(b"Done - you can close this tab.")
        def log_message(self, *a): pass
    srv = http.server.HTTPServer(("127.0.0.1", PORT), H)
    url = f"{AS['authorization_endpoint']}?{q}"
    print("Opening browser; sign in to COROS and approve.\n", url); webbrowser.open(url)
    while "code" not in got and "error" not in got: srv.handle_request()
    if got.get("state", [None])[0] != st or "error" in got: sys.exit(f"auth failed: {got}")
    r = httpx.post(AS["token_endpoint"], timeout=15, data={"grant_type": "authorization_code", "code": got["code"][0],
        "redirect_uri": REDIRECT, "client_id": cid, "code_verifier": ver, "resource": MCP})
    t = r.json(); print("token status", r.status_code, "keys", sorted(t))
    save({"client_id": cid, "tok": t, "obtained": time.time()})
    summarize(t)


def summarize(t):
    print({"expires_in_s": t.get("expires_in"), "has_refresh": "refresh_token" in t, "scope": t.get("scope"),
           "token_type": t.get("token_type"), "refresh_expires_in": t.get("refresh_token_expires_in")})


def refresh():
    s = load(); old = s["tok"]["refresh_token"]
    r = httpx.post(AS["token_endpoint"], timeout=15, data={"grant_type": "refresh_token", "refresh_token": old,
        "client_id": s["client_id"], "resource": MCP})
    print("refresh status", r.status_code)
    if r.status_code != 200: sys.exit(f"refresh failed: {r.text[:300]}")
    t = r.json(); summarize(t)
    print("refresh token ROTATED:", t.get("refresh_token") not in (None, old), "| omitted (reuse old):", "refresh_token" not in t)
    t.setdefault("refresh_token", old)
    s["tok"] = t; s["last_refresh"] = time.time(); save(s)
    return t


def rpc(tok, method, params=None, sid=None, id_=1):
    h = {"Authorization": f"Bearer {tok['access_token']}", "Accept": "application/json, text/event-stream",
         "Content-Type": "application/json", "MCP-Protocol-Version": "2025-06-18"}
    if sid: h["Mcp-Session-Id"] = sid
    r = httpx.post(MCP, headers=h, timeout=60, json={"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}})
    body = r.text
    if "text/event-stream" in r.headers.get("content-type", ""):
        body = next((l[5:].strip() for l in body.splitlines() if l.startswith("data:")), "{}")
    rl = {k: v for k, v in r.headers.items() if "limit" in k.lower() or "retry" in k.lower()}
    return r.status_code, (json.loads(body) if body.strip().startswith("{") else body), r.headers.get("mcp-session-id"), rl


def scrub(o):
    drop = ("name", "email", "nick", "openid", "userid", "location", "city", "lat", "lng", "address")
    if isinstance(o, dict): return {k: scrub(v) for k, v in o.items() if not any(d in k.lower() for d in drop)}
    if isinstance(o, list): return [scrub(v) for v in o]
    return o


def probe():
    os.makedirs(FIX, exist_ok=True)
    s = load(); tok = s['tok']
    if time.time() - s['obtained'] > tok.get('expires_in', 0) - 300: tok = refresh()  # only refresh when near expiry
    sc, init, sid, rl = rpc(tok, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "anton-spike", "version": "0"}})
    print("initialize", sc, "session-id issued:", bool(sid), "rate headers:", rl); print(json.dumps(init)[:400])
    sc, tl, _, _ = rpc(tok, "tools/list", sid=sid, id_=2)
    tools = {t["name"]: t for t in tl["result"]["tools"]}; print("tools:", len(tools))
    json.dump(tl, open(f"{FIX}/tools_list.json", "w"), indent=1)
    props = tools["querySportRecords"]["inputSchema"]["properties"]; print("querySportRecords props:", sorted(props))
    end = datetime.now(); start = end - timedelta(days=14)
    args = {"startDate": start.strftime("%Y%m%d"), "endDate": end.strftime("%Y%m%d"), "sportTypeCodes": [100, 101, 102, 103],
            "minDistanceKm": None, "maxDistanceKm": None, "minDurationMinutes": None, "maxDurationMinutes": None,
            "maxAveragePace": None, "locationKeyword": None, "limit": 50}
    if "timezone" in props: args["timezone"] = "America/Toronto"
    else: print("NOTE: no timezone arg in schema")
    sc, lst, _, rl = rpc(tok, "tools/call", {"name": "querySportRecords", "arguments": args}, sid, 3)
    print("querySportRecords", sc, rl); json.dump(scrub(lst), open(f"{FIX}/query_sport_records.json", "w"), indent=1)
    print(json.dumps(lst)[:1500])
    txt = "".join(c.get("text", "") for c in lst.get("result", {}).get("content", []))
    import re
    m = re.search(r"LabelId: (\d+) \| SportType: (\d+)", txt)
    if not m: print("no LabelId in text"); return
    rec = {"labelId": m.group(1), "sportType": int(m.group(2))}
    sc, det, _, _ = rpc(tok, "tools/call", {"name": "getActivityDetail", "arguments": {"labelId": str(rec["labelId"]), "sportType": rec["sportType"]}}, sid, 4)
    print("getActivityDetail", sc); json.dump(scrub(det), open(f"{FIX}/get_activity_detail.json", "w"), indent=1)
    print(json.dumps(det)[:2000])


if __name__ == "__main__":
    {"auth": auth, "probe": probe, "refresh": refresh}[sys.argv[1]]()
