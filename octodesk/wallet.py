"""Watch-only crypto wallet.

The Kraken looks at your treasure cave; it never enters it. You give it a
public address, it reads balances from a public JSON-RPC endpoint. It refuses
— loudly — anything that looks like a private key or seed phrase. It never
signs, never broadcasts, never holds keys. Trade proposals are unsigned
export-only dicts until the owner adds their own WalletConnect (Reown)
project id and signs inside their own wallet.
"""

from __future__ import annotations

import json
import re
import urllib.request

ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_HEXKEY_RE = re.compile(r"^(0x)?[0-9a-fA-F]{64}$")

# ERC-20 tokens tracked on Ethereum mainnet: symbol -> (contract, decimals)
TOKENS = {
    "USDT": ("0xdAC17F958D2ee523a2206206994597C13D831ec7", 6),
    "USDC": ("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", 6),
    "WETH": ("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", 18),
}


class SecretRefusedError(ValueError):
    """Raised when someone tries to hand the app a key or seed phrase."""


def ensure_not_secret(value):
    """Raise SecretRefusedError if `value` looks like a private key or seed."""
    text = str(value).strip()
    if _HEXKEY_RE.match(text):
        raise SecretRefusedError(
            "That looks like a private key. OctoDesk NEVER takes private keys. "
            "Give it a public address (starts with 0x, 42 characters) instead.")
    words = text.split()
    if len(words) >= 11 and all(w.isalpha() for w in words):
        raise SecretRefusedError(
            "That looks like a seed phrase. OctoDesk NEVER takes seed phrases. "
            "Give it a public address (starts with 0x, 42 characters) instead.")
    return value


def validate_address(value):
    ensure_not_secret(value)
    text = str(value).strip()
    if not ADDRESS_RE.match(text):
        raise ValueError(
            f"Not an EVM address: {value!r}. Expected 0x + 40 hex characters.")
    return text


def _rpc(url, method, params, timeout=8):
    body = json.dumps({"jsonrpc": "2.0", "id": 1,
                       "method": method, "params": params}).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "OctoDesk/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if "error" in payload:
        raise ValueError(f"RPC error: {payload['error']}")
    return payload["result"]


def read_balances(address, rpc_url):
    """Read ETH + tracked ERC-20 balances for a public address (read-only)."""
    address = validate_address(address)
    out = {}
    wei = int(_rpc(rpc_url, "eth_getBalance", [address, "latest"]), 16)
    out["ETH"] = round(wei / 1e18, 6)
    for sym, (contract, decimals) in TOKENS.items():
        data = "0x70a08231" + address[2:].rjust(64, "0")  # balanceOf(address)
        raw = _rpc(rpc_url, "eth_call", [{"to": contract, "data": data}, "latest"])
        out[sym] = round(int(raw, 16) / (10 ** decimals), 4)
    return out


def make_proposals(run, balances=None, walletconnect_project_id=""):
    """Unsigned, export-only trade proposals from a gate-passed basket.

    These dicts deliberately contain NO key, signature, or transaction fields —
    nothing here can move funds. Signing (a future unlock) happens inside the
    owner's own wallet via WalletConnect, one signature per transaction.
    """
    if not run["gate"]["passed"]:
        return []
    proposals = []
    usd_each = 250.0  # illustrative paper-sized slice, labelled as such
    for sym in run["basket"]:
        proposals.append({
            "asset": sym,
            "side": "BUY",
            "approx_usd": usd_each,
            "reason": (f"Swarm confidence {run['scores'][sym]['C']:.2f} "
                       f"(>= 0.70 keeps) and the basket passed the Beak gate."),
            "status": "UNSIGNED — export only",
            "signing": ("via your own wallet (WalletConnect) once you add "
                        "your Reown project id" if walletconnect_project_id
                        else "disabled — add your own Reown (WalletConnect) "
                             "project id to enable in-wallet signing"),
        })
    return proposals
