"""The modes ladder + trade placement guard.

paper     -> nothing real can happen (default, and where the kill switch lands)
connected -> SnapTrade data is shown; placement still impossible
armed     -> placement is possible, but ONLY for a proposal this server issued
             from a gate-passed run, ONLY with that proposal's confirmation
             token (the human's per-order confirm), ONLY inside the caps,
             and NEVER after the kill switch fires.

v1 live still means a human confirms every single order. Unattended
auto-trading is deliberately not in v1.
"""

from __future__ import annotations

import secrets
import time

MODES = ("paper", "connected", "armed")


class TradingGuard:
    def __init__(self, broker, mode="paper", max_order_usd=100.0, max_day_usd=250.0):
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode!r}")
        self.broker = broker
        self.mode = mode
        self.max_order_usd = float(max_order_usd)
        self.max_day_usd = float(max_day_usd)
        self.killed = False
        self._proposals = {}      # proposal_id -> record
        self._spend = {}          # "YYYY-MM-DD" -> usd placed
        self.placed = []          # audit trail of successful placements

    # ---------------- modes & kill switch ----------------
    def set_mode(self, mode):
        if mode not in MODES:
            return {"ok": False, "reason": f"unknown mode {mode!r}"}
        if self.killed and mode == "armed":
            return {"ok": False,
                    "reason": "Kill switch has fired. Re-arming is a manual, "
                              "deliberate act: clear the kill switch first."}
        self.mode = mode
        return {"ok": True, "mode": self.mode}

    def clear_kill(self):
        self.killed = False
        return {"ok": True, "mode": self.mode, "killed": False}

    def kill(self):
        """Big red button: drop to paper and block placement until cleared."""
        self.killed = True
        self.mode = "paper"
        return {"ok": True, "mode": "paper", "killed": True}

    # ---------------- proposals ----------------
    def issue_proposals(self, run, account_id):
        """Register proposals from a gate-passed run. Each gets an id and a
        one-shot confirmation token. Returns public proposal dicts (token
        included because this is a local app and the token IS the confirm)."""
        if not run["gate"]["passed"]:
            return []
        issued = []
        for sym in run["basket"]:
            pid = f"{sym}-{int(time.time())}-{secrets.token_hex(3)}"
            token = secrets.token_urlsafe(12)
            record = {
                "proposal_id": pid, "account": account_id, "symbol": sym,
                "action": "BUY", "notional": 100.0, "token": token,
                "consumed": False,
                "reason": f"Swarm confidence {run['scores'][sym]['C']:.2f}; "
                          f"basket passed the Beak gate.",
            }
            self._proposals[pid] = record
            issued.append({k: record[k] for k in
                           ("proposal_id", "account", "symbol", "action",
                            "notional", "reason")} | {"confirm_token": token})
        return issued

    def spent_today(self):
        return self._spend.get(time.strftime("%Y-%m-%d"), 0.0)

    # ---------------- placement ----------------
    def place(self, user, proposal_id, token):
        def refuse(reason):
            return {"ok": False, "reason": reason}

        if self.killed:
            return refuse("Kill switch has fired — placement is blocked until "
                          "it is manually cleared and the app is re-armed.")
        if self.mode == "paper":
            return refuse("Mode is PAPER — simulated money only. Connect a "
                          "broker and arm the app to place real orders.")
        if self.mode == "connected":
            return refuse("Mode is CONNECTED — read-only. Placement requires "
                          "ARMED mode.")
        record = self._proposals.get(proposal_id)
        if record is None:
            return refuse("Unknown proposal. Orders can only be placed for "
                          "proposals this server issued from a gate-passed run.")
        if record["consumed"]:
            return refuse("That proposal was already placed. One confirmation, "
                          "one order — run the desk again for a new proposal.")
        if not token or not secrets.compare_digest(str(token), record["token"]):
            return refuse("Missing or wrong confirmation token. A human must "
                          "confirm this exact order in the app.")
        amount = float(record["notional"])
        if amount > self.max_order_usd:
            return refuse(f"Order ${amount:,.0f} exceeds the per-order cap "
                          f"of ${self.max_order_usd:,.0f}.")
        if self.spent_today() + amount > self.max_day_usd:
            return refuse(f"Daily cap reached: ${self.spent_today():,.0f} of "
                          f"${self.max_day_usd:,.0f} already placed today.")
        result = self.broker.place_order(user, record["account"], {
            "symbol": record["symbol"], "action": record["action"],
            "notional": amount, "type": "Market"})
        record["consumed"] = True
        day = time.strftime("%Y-%m-%d")
        self._spend[day] = self.spent_today() + amount
        entry = {"ok": True, "order": result, "proposal_id": proposal_id,
                 "spent_today": self._spend[day]}
        self.placed.append(entry)
        return entry

    def status(self):
        return {"mode": self.mode, "killed": self.killed,
                "max_order_usd": self.max_order_usd,
                "max_day_usd": self.max_day_usd,
                "spent_today": self.spent_today(),
                "open_proposals": sum(1 for p in self._proposals.values()
                                      if not p["consumed"])}
