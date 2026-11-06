from octodesk.broker import FakeTransport, SnapTradeClient
from octodesk.trades import TradingGuard

RUN = {"gate": {"passed": True},
       "basket": ["NVDA", "AAPL", "MSFT", "V"],
       "scores": {s: {"C": 0.8} for s in ("NVDA", "AAPL", "MSFT", "V")}}


def _guard(mode="paper", **kw):
    client = SnapTradeClient(FakeTransport())
    guard = TradingGuard(client, mode=mode, **kw)
    user = client.register_user()
    proposals = guard.issue_proposals(RUN, "acct-1")
    return guard, client, user, proposals


def test_fake_transport_flow():
    client = SnapTradeClient(FakeTransport())
    user = client.register_user()
    assert user["user_id"] == "demo-user"
    assert "snaptrade.com" in client.login_link(user)
    accounts = client.list_accounts(user)
    assert len(accounts) == 1 and accounts[0]["balance"] == 5230.55
    holdings = client.get_holdings(user, "acct-1")
    assert {p["symbol"] for p in holdings["positions"]} == {"VFV", "XEQT"}
    result = client.place_order(user, "acct-1",
                                {"symbol": "VFV", "action": "BUY", "notional": 50})
    assert result["order_id"] == "demo-order-1"


def test_unconfigured_client_falls_back_to_fake(monkeypatch):
    monkeypatch.delenv("OCTODESK_SNAPTRADE_CLIENT_ID", raising=False)
    monkeypatch.delenv("OCTODESK_SNAPTRADE_CONSUMER_KEY", raising=False)
    client = SnapTradeClient()
    assert client.configured is False
    assert isinstance(client.transport, FakeTransport)


def test_placement_refused_in_paper_mode():
    guard, client, user, proposals = _guard("paper")
    res = guard.place(user, proposals[0]["proposal_id"], proposals[0]["confirm_token"])
    assert not res["ok"] and "PAPER" in res["reason"]


def test_placement_refused_in_connected_mode():
    guard, client, user, proposals = _guard("connected")
    res = guard.place(user, proposals[0]["proposal_id"], proposals[0]["confirm_token"])
    assert not res["ok"] and "CONNECTED" in res["reason"]


def test_placement_refused_without_confirmation_token():
    guard, client, user, proposals = _guard("armed")
    res = guard.place(user, proposals[0]["proposal_id"], "")
    assert not res["ok"] and "confirmation token" in res["reason"]
    res2 = guard.place(user, proposals[0]["proposal_id"], "wrong-token")
    assert not res2["ok"]


def test_placement_refused_over_per_order_cap():
    guard, client, user, proposals = _guard("armed", max_order_usd=50.0)
    res = guard.place(user, proposals[0]["proposal_id"], proposals[0]["confirm_token"])
    assert not res["ok"] and "per-order cap" in res["reason"]


def test_placement_refused_over_daily_cap():
    guard, client, user, proposals = _guard("armed", max_order_usd=100.0,
                                            max_day_usd=150.0)
    first = guard.place(user, proposals[0]["proposal_id"], proposals[0]["confirm_token"])
    assert first["ok"]
    second = guard.place(user, proposals[1]["proposal_id"], proposals[1]["confirm_token"])
    assert not second["ok"] and "Daily cap" in second["reason"]


def test_placement_refused_after_kill_switch():
    guard, client, user, proposals = _guard("armed")
    guard.kill()
    res = guard.place(user, proposals[0]["proposal_id"], proposals[0]["confirm_token"])
    assert not res["ok"] and "Kill switch" in res["reason"]
    assert guard.mode == "paper"
    rearm = guard.set_mode("armed")
    assert not rearm["ok"], "kill switch must block re-arming until cleared"
    guard.clear_kill()
    assert guard.set_mode("armed")["ok"]


def test_placement_allowed_exactly_once_when_armed_and_confirmed():
    guard, client, user, proposals = _guard("armed")
    p = proposals[0]
    res = guard.place(user, p["proposal_id"], p["confirm_token"])
    assert res["ok"], res
    order = res["order"]
    assert order["order_id"] == "demo-order-1"
    assert order["symbol"] == p["symbol"] and order["notional"] == 100.0
    assert order["raw"]["request"]["action"] == "BUY"
    again = guard.place(user, p["proposal_id"], p["confirm_token"])
    assert not again["ok"] and "already placed" in again["reason"]
    assert len(client.transport.placed_orders) == 1
