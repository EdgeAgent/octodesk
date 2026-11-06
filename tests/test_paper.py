import json

from octodesk import paper


def _run(passed):
    return {"gate": {"passed": passed, "failing": None if passed else "variance"},
            "basket": ["NVDA", "AAPL", "MSFT", "V"]}


PRICES = {"NVDA": 180.0, "AAPL": 260.0, "MSFT": 520.0, "V": 350.0}


def test_fill_only_on_gate_pass(tmp_path, monkeypatch):
    monkeypatch.setenv("OCTODESK_DATA", str(tmp_path))
    state = paper.load_portfolio()
    summary = paper.record_run(state, _run(True), PRICES)
    assert summary["filled"], "gate pass must produce paper fills"
    assert state["positions"], "positions must be held after a pass"
    assert state["streak"] == 1

    before = dict(state["positions"])
    paper.record_run(state, _run(False), PRICES)
    assert state["positions"] == before, "a rejected run must not trade"
    assert state["streak"] == 0, "a rejection breaks the flame streak"


def test_ledger_written(tmp_path, monkeypatch):
    monkeypatch.setenv("OCTODESK_DATA", str(tmp_path))
    state = paper.load_portfolio()
    paper.record_run(state, _run(True), PRICES)
    paper.record_run(state, _run(False), PRICES)
    lines = (tmp_path / "ledger.jsonl").read_text().strip().splitlines()
    kinds = [json.loads(l)["type"] for l in lines]
    assert "fill" in kinds and "reject" in kinds
