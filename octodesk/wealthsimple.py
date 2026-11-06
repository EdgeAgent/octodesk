"""Wealthsimple holdings import — READ-ONLY, CSV only.

Wealthsimple offers no public trading API, and OctoDesk will never ask for
Wealthsimple credentials. What it can do: read an activity/holdings CSV you
export yourself and show the holdings next to the Kraken's pit.
"""

from __future__ import annotations

import csv
import io

_SYMBOL_KEYS = ("symbol", "ticker", "security", "name")
_QTY_KEYS = ("quantity", "shares", "units", "qty")
_AMOUNT_KEYS = ("market value", "amount", "total", "value", "book value")


def _pick(row, keys):
    lowered = {str(k).strip().lower(): v for k, v in row.items() if k}
    for key in keys:
        for col, val in lowered.items():
            if key in col:
                return val
    return None


def _num(value):
    if value is None:
        return 0.0
    text = str(value).replace("$", "").replace(",", "").replace("(", "-").replace(")", "").strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


def import_csv(text):
    """Parse a Wealthsimple-style CSV export into an aggregated holdings view."""
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("That file does not look like a CSV export.")
    holdings = {}
    rows = 0
    for row in reader:
        symbol = _pick(row, _SYMBOL_KEYS)
        if not symbol or not str(symbol).strip():
            continue
        symbol = str(symbol).strip().upper()
        qty = _num(_pick(row, _QTY_KEYS))
        amount = _num(_pick(row, _AMOUNT_KEYS))
        entry = holdings.setdefault(symbol, {"symbol": symbol, "quantity": 0.0,
                                             "amount": 0.0})
        entry["quantity"] += qty
        entry["amount"] += amount
        rows += 1
    return {
        "source": "wealthsimple-csv",
        "rows": rows,
        "holdings": [dict(h, quantity=round(h["quantity"], 4),
                          amount=round(h["amount"], 2))
                     for h in sorted(holdings.values(), key=lambda x: x["symbol"])],
        "total_amount": round(sum(h["amount"] for h in holdings.values()), 2),
        "note": "Read-only import. Wealthsimple has no public trading API; "
                "OctoDesk never asks for Wealthsimple credentials.",
    }
