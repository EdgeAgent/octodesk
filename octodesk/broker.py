"""Broker layer: Wealthsimple via SnapTrade — the sanctioned route.

Wealthsimple has no official API. SnapTrade is the aggregator Wealthsimple
supports for third-party access ("Read and Trade" in SnapTrade's Broker
Access Guide, once a Production Access Application is approved). Users
connect through SnapTrade's hosted Connection Portal, so this app NEVER
sees Wealthsimple credentials — there is no password field anywhere here,
on purpose. Unofficial password-based libraries are a ban risk and are
deliberately not used or offered.

Credentials: consumer key + client id are read ONLY from the environment
(OCTODESK_SNAPTRADE_CLIENT_ID / OCTODESK_SNAPTRADE_CONSUMER_KEY). They are
never read from config files and never logged.

Transport is injectable: the default transport speaks HTTPS to SnapTrade
with its signed-request scheme (see docs.snaptrade.com — HMAC-SHA256 over a
sorted {content, path, query} payload, sent as the Signature header).
Tests and demo mode use FakeTransport with canned data.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.request

API_BASE = "https://api.snaptrade.com/api/v1"

ENV_CLIENT_ID = "OCTODESK_SNAPTRADE_CLIENT_ID"
ENV_CONSUMER_KEY = "OCTODESK_SNAPTRADE_CONSUMER_KEY"


class BrokerNotConfigured(RuntimeError):
    pass


# ------------------------------- transports -------------------------------

class UrllibTransport:
    """Real SnapTrade transport: signed HTTPS requests via stdlib urllib."""

    def __init__(self, client_id, consumer_key, base=API_BASE):
        self.client_id = client_id
        self.consumer_key = consumer_key
        self.base = base

    def _signature(self, content, path, query):
        sig_object = {
            "content": content,
            "path": path,
            "query": "&".join(f"{k}={query[k]}" for k in sorted(query)),
        }
        sig_content = json.dumps(sig_object, separators=(",", ":"), sort_keys=True)
        digest = hmac.new(self.consumer_key.encode(), sig_content.encode(),
                          hashlib.sha256).digest()
        return base64.b64encode(digest).decode()

    def request(self, method, path, body=None, query=None):
        query = dict(query or {})
        query["clientId"] = self.client_id
        query["timestamp"] = str(int(time.time()))
        content = json.dumps(body, separators=(",", ":"), sort_keys=True) if body is not None else ""
        signature = self._signature(body, path, query)
        url = self.base + path + "?" + "&".join(f"{k}={query[k]}" for k in sorted(query))
        data = content.encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Content-Type": "application/json",
            "Snaptrade-Consumer-Key": self.consumer_key,
            "Signature": signature,
            "User-Agent": "OctoDesk/0.1",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


class FakeTransport:
    """Canned SnapTrade-shaped responses for tests and demo mode."""

    def __init__(self):
        self.placed_orders = []

    def request(self, method, path, body=None, query=None):
        if path == "/snapTrade/registerUser":
            return {"userId": "demo-user", "userSecret": "demo-secret"}
        if path == "/snapTrade/login":
            return {"loginLink": "https://app.snaptrade.com/snapTrade/redeemToken"
                                  "?token=DEMO&connectionType=trade"}
        if path == "/accounts":
            return [{"id": "acct-1", "name": "Wealthsimple · Personal (demo)",
                     "number": "••1234", "balance": {"total": {"amount": 5230.55,
                                                                "currency": "CAD"}}}]
        if path.startswith("/accounts/") and path.endswith("/holdings"):
            return {"positions": [
                {"symbol": {"symbol": "VFV"}, "units": 12.5,
                 "price": 158.20, "market_value": 1977.50},
                {"symbol": {"symbol": "XEQT"}, "units": 40.0,
                 "price": 33.10, "market_value": 1324.00},
            ], "balances": [{"currency": "CAD", "cash": 1929.05}]}
        if path.startswith("/accounts/") and path.endswith("/orders"):
            order = {"brokerage_order_id": f"demo-order-{len(self.placed_orders) + 1}",
                     "status": "ACCEPTED (demo transport — no real broker touched)",
                     "request": body}
            self.placed_orders.append(order)
            return order
        return {}


# ------------------------------- client -------------------------------

def _sym(item):
    s = item.get("symbol")
    return s.get("symbol") if isinstance(s, dict) else s


class SnapTradeClient:
    """Normalized SnapTrade client over an injectable transport."""

    def __init__(self, transport=None):
        if transport is not None:
            self.transport = transport
            self.configured = isinstance(transport, UrllibTransport)
            return
        client_id = os.environ.get(ENV_CLIENT_ID, "")
        consumer_key = os.environ.get(ENV_CONSUMER_KEY, "")
        if client_id and consumer_key:
            self.transport = UrllibTransport(client_id, consumer_key)
            self.configured = True
        else:
            # No keys: demo transport so the app still shows its shape,
            # but `configured` stays False and the UI says so plainly.
            self.transport = FakeTransport()
            self.configured = False

    def register_user(self, user_id="octodesk-user"):
        raw = self.transport.request("POST", "/snapTrade/registerUser",
                                     body={"userId": user_id})
        return {"user_id": raw.get("userId", user_id),
                "user_secret": raw.get("userSecret", "")}

    def login_link(self, user):
        raw = self.transport.request(
            "POST", "/snapTrade/login",
            body={"userId": user["user_id"], "userSecret": user["user_secret"],
                  "connectionType": "trade", "broker": "Wealthsimple"})
        return raw.get("loginLink", "")

    def list_accounts(self, user):
        raw = self.transport.request(
            "GET", "/accounts",
            query={"userId": user["user_id"], "userSecret": user["user_secret"]})
        return [{"id": a.get("id"), "name": a.get("name"),
                 "number": a.get("number"),
                 "balance": (a.get("balance") or {}).get("total", {}).get("amount")}
                for a in raw]

    def get_holdings(self, user, account_id):
        raw = self.transport.request(
            "GET", f"/accounts/{account_id}/holdings",
            query={"userId": user["user_id"], "userSecret": user["user_secret"]})
        return {
            "account": account_id,
            "positions": [{"symbol": _sym(p), "units": p.get("units"),
                           "price": p.get("price"),
                           "market_value": p.get("market_value")}
                          for p in raw.get("positions", [])],
            "cash": [b.get("cash") for b in raw.get("balances", [])],
        }

    def place_order(self, user, account_id, order):
        """order: {symbol, action, units|notional, type}. Normalized echo out."""
        body = {"userId": user["user_id"], "userSecret": user["user_secret"],
                "accountId": account_id,
                "action": order.get("action", "BUY"),
                "symbol": order.get("symbol"),
                "orderType": order.get("type", "Market"),
                "timeInForce": order.get("time_in_force", "Day")}
        if order.get("notional") is not None:
            body["notionalValue"] = order["notional"]
        if order.get("units") is not None:
            body["units"] = order["units"]
        raw = self.transport.request("POST", f"/accounts/{account_id}/orders", body=body)
        return {"order_id": raw.get("brokerage_order_id"),
                "status": raw.get("status"), "symbol": order.get("symbol"),
                "action": body["action"],
                "notional": order.get("notional"), "raw": raw}
