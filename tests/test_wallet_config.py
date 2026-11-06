import json

import pytest

from octodesk import wallet
from octodesk.config import UnsafeConfigError, load_config

GOOD = "0x" + "a1" * 20


def test_address_validation():
    assert wallet.validate_address(GOOD) == GOOD
    with pytest.raises(ValueError):
        wallet.validate_address("0x123")
    with pytest.raises(ValueError):
        wallet.validate_address("not-an-address")


def test_secret_refusal():
    with pytest.raises(wallet.SecretRefusedError):
        wallet.validate_address("ab" * 32)  # 64 hex chars = private-key shape
    with pytest.raises(wallet.SecretRefusedError):
        wallet.ensure_not_secret(
            "legal winner thank year wave sausage worth useful legal winner thank yellow")


def test_proposals_are_unsigned_only():
    run = {"gate": {"passed": True}, "basket": ["NVDA", "AAPL"],
           "scores": {"NVDA": {"C": 0.81}, "AAPL": {"C": 0.77}}}
    proposals = wallet.make_proposals(run)
    assert len(proposals) == 2
    banned = ("key", "seed", "signature", "signed", "tx", "raw_transaction")
    for p in proposals:
        assert p["status"].startswith("UNSIGNED")
        for field in p:
            assert not any(b in field.lower() for b in banned), field
    run["gate"]["passed"] = False
    assert wallet.make_proposals(run) == []


def test_config_rejects_secrets(tmp_path):
    bad = tmp_path / "cfg.json"
    bad.write_text(json.dumps({"wallet": {"private_key": "nope"}}))
    with pytest.raises(UnsafeConfigError):
        load_config(bad)
    nested = tmp_path / "cfg2.json"
    nested.write_text(json.dumps({"a": {"b": {"Seed Phrase": "nope"}}}))
    with pytest.raises(UnsafeConfigError):
        load_config(nested)


def test_config_defaults_modes_and_caps():
    cfg = load_config()
    assert cfg["mode"] == "paper"
    assert cfg["broker"]["max_order_usd"] == 100
    assert cfg["broker"]["max_day_usd"] == 250
    assert cfg["port"] == 8917
