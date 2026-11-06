"""Configuration loading with a hard safety rule.

OctoDesk never stores credentials. Any config key whose name even *looks*
like a secret (private key, seed phrase, mnemonic, password) fails the load
loudly instead of being quietly kept on disk.
"""

from __future__ import annotations

import json
from pathlib import Path

FORBIDDEN_KEY_PARTS = ("private_key", "privatekey", "seed", "mnemonic", "password")

DEFAULTS = {
    "port": 8917,
    "host": "127.0.0.1",
    "paper_start_nav": 100000.0,
    # Modes ladder: paper -> connected -> armed. SnapTrade keys NEVER live
    # here — they come from the environment only (see broker.py).
    "mode": "paper",
    "broker": {"max_order_usd": 100.0, "max_day_usd": 250.0},
    "wallet": {
        "watch_address": "",
        "rpc_url": "https://eth.llamarpc.com",
        # Future unlock: a Reown (WalletConnect) project id lets the user sign
        # proposals inside their own wallet. Empty = proposals are export-only.
        "walletconnect_project_id": "",
    },
}


class UnsafeConfigError(ValueError):
    """Raised when a config tries to store something that looks like a secret."""


def _check_keys(obj, trail="config"):
    if isinstance(obj, dict):
        for key, value in obj.items():
            lowered = str(key).lower()
            for bad in FORBIDDEN_KEY_PARTS:
                if bad in lowered:
                    raise UnsafeConfigError(
                        f"Refusing to load {trail}.{key}: OctoDesk never stores "
                        "private keys, seed phrases, mnemonics, or passwords. "
                        "Remove that key — the Kraken holds no secrets."
                    )
            _check_keys(value, f"{trail}.{key}")
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            _check_keys(value, f"{trail}[{i}]")


def _deep_merge(base, extra):
    out = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path=None):
    """Load config JSON (if it exists) merged over defaults, secrets refused."""
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy
    if path is None:
        return cfg
    p = Path(path)
    if not p.exists():
        return cfg
    raw = json.loads(p.read_text(encoding="utf-8"))
    _check_keys(raw)
    return _deep_merge(cfg, raw)
