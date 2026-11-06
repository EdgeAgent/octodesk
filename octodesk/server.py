"""Local dashboard server (stdlib http.server, 127.0.0.1 only).

Endpoints:
  GET  /                  the Kraken Pit page (web/index.html)
  GET  /api/state         portfolio, last run, wallet, broker, modes, holdings
  POST /api/run           {"live": bool} — run the desk, apply paper fills,
                          issue broker proposals from a gate-passed run
  POST /api/wallet        {"address": "0x..."} — set the watch-only address
  POST /api/import        raw CSV body — Wealthsimple-style holdings import
  POST /api/broker/link   register (if needed) + return the SnapTrade
                          Connection Portal URL (the only place a
                          Wealthsimple password is ever typed)
  GET  /api/broker/accounts  real accounts + holdings via SnapTrade
  POST /api/mode          {"mode": "paper|connected|armed"}
  POST /api/place         {"proposal_id", "token"} — guarded placement
  POST /api/kill          big red button: paper mode + placement blocked
  POST /api/kill/clear    manually clear the kill switch (mode stays paper)
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import engine, paper, prices, wallet as wallet_mod, wealthsimple
from .broker import SnapTradeClient
from .config import load_config
from .trades import TradingGuard

_PAGE = Path(__file__).with_name("web") / "index.html"

_cfg = load_config()
_broker = SnapTradeClient()
_guard = TradingGuard(_broker, mode=_cfg.get("mode", "paper"),
                      max_order_usd=_cfg["broker"]["max_order_usd"],
                      max_day_usd=_cfg["broker"]["max_day_usd"])

_ctx = {
    "config": _cfg,
    "last_run": None,
    "wallet_balances": None,
    "wallet_error": None,
    "holdings": None,
    "broker_user": None,
    "broker_accounts": None,
    "broker_holdings": None,
    "broker_proposals": [],
}


def broker_status():
    return {
        "provider": "SnapTrade → Wealthsimple",
        "configured": _broker.configured,
        "transport": "snaptrade" if _broker.configured else "fake (demo)",
        "note": (None if _broker.configured else
                 "Runs on paper — add SnapTrade keys (env "
                 "OCTODESK_SNAPTRADE_CLIENT_ID / OCTODESK_SNAPTRADE_CONSUMER_KEY) "
                 "to connect Wealthsimple."),
        "trading": _guard.status(),
    }


def get_state():
    cfg = _ctx["config"]
    series, _ = prices.get_prices(live=False)
    if _ctx["last_run"]:
        px = _ctx["last_run"]["prices"]
    else:
        px = {s: round(series[s][-1], 2) for s in prices.UNIVERSE}
    portfolio = paper.load_portfolio()
    return {
        "portfolio": paper.stats(portfolio, px),
        "last_run": _ctx["last_run"],
        "prices": px,
        "wallet": {
            "watch_address": cfg["wallet"]["watch_address"],
            "balances": _ctx["wallet_balances"],
            "error": _ctx["wallet_error"],
            "walletconnect_ready": bool(cfg["wallet"]["walletconnect_project_id"]),
            "proposals": (wallet_mod.make_proposals(
                _ctx["last_run"], _ctx["wallet_balances"],
                cfg["wallet"]["walletconnect_project_id"])
                if _ctx["last_run"] else []),
        },
        "broker": broker_status() | {
            "accounts": _ctx["broker_accounts"],
            "holdings": _ctx["broker_holdings"],
            "proposals": _ctx["broker_proposals"],
        },
        "holdings": _ctx["holdings"],
        "paper_only": _guard.mode == "paper",
    }


def do_run(live=True):
    series, source = prices.get_prices(live=live)
    run = engine.run_desk(series, source=source)
    portfolio = paper.load_portfolio()
    run["paper"] = paper.record_run(portfolio, run, run["prices"])
    _ctx["last_run"] = run
    account = (_ctx["broker_accounts"][0]["id"]
               if _ctx["broker_accounts"] else "demo-account")
    _ctx["broker_proposals"] = _guard.issue_proposals(run, account)
    return run


def set_wallet(address):
    address = wallet_mod.validate_address(address)  # refuses keys/seeds
    _ctx["config"]["wallet"]["watch_address"] = address
    try:
        _ctx["wallet_balances"] = wallet_mod.read_balances(
            address, _ctx["config"]["wallet"]["rpc_url"])
        _ctx["wallet_error"] = None
    except Exception as exc:
        _ctx["wallet_balances"] = None
        _ctx["wallet_error"] = (f"Balance read failed ({exc.__class__.__name__}). "
                                "Address saved.")
    return {"watch_address": address, "balances": _ctx["wallet_balances"],
            "error": _ctx["wallet_error"]}


def broker_link():
    if _ctx["broker_user"] is None:
        _ctx["broker_user"] = _broker.register_user()
    return {"login_link": _broker.login_link(_ctx["broker_user"]),
            "configured": _broker.configured}


def broker_accounts():
    if _ctx["broker_user"] is None:
        _ctx["broker_user"] = _broker.register_user()
    accounts = _broker.list_accounts(_ctx["broker_user"])
    _ctx["broker_accounts"] = accounts
    holdings = None
    if accounts:
        holdings = _broker.get_holdings(_ctx["broker_user"], accounts[0]["id"])
        _ctx["broker_holdings"] = holdings
    if _guard.mode == "paper":
        _guard.set_mode("connected")
    return {"accounts": accounts, "holdings": holdings,
            "trading": _guard.status()}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, content_type="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self._send(200, _PAGE.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._send(200, get_state())
        elif self.path == "/api/broker/accounts":
            try:
                self._send(200, broker_accounts())
            except Exception as exc:
                self._send(400, {"error": str(exc)})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw or b"{}") if self.path != "/api/import" else {}
            if self.path == "/api/run":
                self._send(200, do_run(live=bool(payload.get("live", True))))
            elif self.path == "/api/wallet":
                self._send(200, set_wallet(payload.get("address", "")))
            elif self.path == "/api/import":
                result = wealthsimple.import_csv(raw.decode("utf-8", "replace"))
                _ctx["holdings"] = result
                self._send(200, result)
            elif self.path == "/api/broker/link":
                self._send(200, broker_link())
            elif self.path == "/api/mode":
                self._send(200, _guard.set_mode(payload.get("mode", "")))
            elif self.path == "/api/place":
                if _ctx["broker_user"] is None:
                    _ctx["broker_user"] = _broker.register_user()
                self._send(200, _guard.place(_ctx["broker_user"],
                                             payload.get("proposal_id", ""),
                                             payload.get("token", "")))
            elif self.path == "/api/kill":
                self._send(200, _guard.kill())
            elif self.path == "/api/kill/clear":
                self._send(200, _guard.clear_kill())
            else:
                self._send(404, {"error": "not found"})
        except Exception as exc:
            self._send(400, {"error": str(exc)})


def serve(host="127.0.0.1", port=8917):
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"OctoDesk is awake: http://{host}:{port}  "
          f"(mode: {_guard.mode} — release the Kraken)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
