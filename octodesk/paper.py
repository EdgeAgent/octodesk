"""The treasure chest: a paper portfolio with a JSONL ledger.

Simulated money only. Fills happen exclusively when the Beak (risk gate)
says yes. State lives in the user's data dir (~/.octodesk by default,
OCTODESK_DATA overrides — tests use a temp dir).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

START_NAV = 100000.0


def data_dir():
    d = Path(os.environ.get("OCTODESK_DATA", Path.home() / ".octodesk"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _state_path():
    return data_dir() / "portfolio.json"


def _ledger_path():
    return data_dir() / "ledger.jsonl"


def load_portfolio():
    p = _state_path()
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    state = {
        "start_nav": START_NAV,
        "cash": START_NAV,
        "positions": {},          # sym -> {"shares": float, "avg_price": float}
        "runs": 0,
        "passes": 0,
        "level": 1,
        "streak": 0,              # consecutive gate passes (flame counter)
        "best_streak": 0,
        "nav_history": [{"ts": time.time(), "nav": START_NAV}],
    }
    save_portfolio(state)
    return state


def save_portfolio(state):
    _state_path().write_text(json.dumps(state, indent=1), encoding="utf-8")


def _append_ledger(entry):
    with _ledger_path().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def nav(state, prices):
    total = state["cash"]
    for sym, pos in state["positions"].items():
        if sym in prices:
            total += pos["shares"] * prices[sym]
    return round(total, 2)


def record_run(state, run, prices):
    """Apply a desk run to the paper portfolio. Fills only on a gate pass:
    each basket asset gets an equal 25%-of-NAV target weight (the gate's cap),
    topped up from cash. Returns a summary dict."""
    state["runs"] += 1
    filled = []
    if run["gate"]["passed"]:
        state["passes"] += 1
        state["streak"] += 1
        state["best_streak"] = max(state["best_streak"], state["streak"])
        current_nav = nav(state, prices)
        target_value = current_nav * 0.25
        for sym in run["basket"]:
            pos = state["positions"].get(sym, {"shares": 0.0, "avg_price": 0.0})
            held_value = pos["shares"] * prices[sym]
            buy_value = max(0.0, min(target_value - held_value, state["cash"]))
            if buy_value >= 1.0:
                shares = buy_value / prices[sym]
                total_shares = pos["shares"] + shares
                pos["avg_price"] = ((pos["avg_price"] * pos["shares"]
                                      + prices[sym] * shares) / total_shares)
                pos["shares"] = total_shares
                state["positions"][sym] = pos
                state["cash"] = round(state["cash"] - buy_value, 2)
                filled.append({"asset": sym, "side": "BUY (paper)",
                               "usd": round(buy_value, 2),
                               "price": prices[sym]})
                _append_ledger({"ts": time.time(), "type": "fill", **filled[-1]})
    else:
        state["streak"] = 0
        _append_ledger({"ts": time.time(), "type": "reject",
                        "failing": run["gate"]["failing"],
                        "basket": run["basket"]})
    state["level"] = 1 + state["runs"] // 3  # cosmetic game level
    current = nav(state, prices)
    state["nav_history"].append({"ts": time.time(), "nav": current})
    save_portfolio(state)
    return {"filled": filled, "nav": current}


def stats(state, prices):
    current = nav(state, prices)
    history = state["nav_history"]
    best_day = 0.0
    for prev, cur in zip(history, history[1:]):
        if prev["nav"]:
            best_day = max(best_day, (cur["nav"] / prev["nav"] - 1.0) * 100)
    return {
        "nav": current,
        "start_nav": state["start_nav"],
        "gain_pct": round((current / state["start_nav"] - 1.0) * 100, 2),
        "cash": round(state["cash"], 2),
        "positions": {s: {"shares": round(p["shares"], 4),
                          "avg_price": round(p["avg_price"], 2),
                          "value": round(p["shares"] * prices.get(s, p["avg_price"]), 2)}
                      for s, p in state["positions"].items()},
        "runs": state["runs"],
        "passes": state["passes"],
        "pass_rate": round(state["passes"] / state["runs"] * 100, 1) if state["runs"] else 0.0,
        "streak": state["streak"],
        "best_streak": state["best_streak"],
        "best_day_pct": round(best_day, 2),
        "level": state["level"],
        "nav_history": history[-60:],
    }
