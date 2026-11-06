from octodesk import cli, server, wealthsimple
from octodesk.prices import UNIVERSE, load_fixture

SAMPLE_CSV = """Date,Symbol,Quantity,Amount
2026-01-05,VFV,10,1500.00
2026-01-06,VFV,2.5,395.50
2026-01-07,XEQT,40,1324.00
"""


def test_fixture_completeness():
    data = load_fixture()
    assert set(data) == set(UNIVERSE)
    for series in data.values():
        assert len(series) >= 60
        assert all(v > 0 for v in series)


def test_csv_import_parses_sample_rows():
    result = wealthsimple.import_csv(SAMPLE_CSV)
    assert result["rows"] == 3
    by_sym = {h["symbol"]: h for h in result["holdings"]}
    assert by_sym["VFV"]["quantity"] == 12.5
    assert by_sym["VFV"]["amount"] == 1895.50
    assert result["total_amount"] == 3219.50


def test_state_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("OCTODESK_DATA", str(tmp_path))
    state = server.get_state()
    for key in ("portfolio", "last_run", "prices", "wallet", "broker",
                "holdings", "paper_only"):
        assert key in state, key
    assert state["broker"]["provider"].startswith("SnapTrade")
    assert state["broker"]["trading"]["mode"] == "paper"
    assert set(state["prices"]) == set(UNIVERSE)


def test_demo_exits_zero(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OCTODESK_DATA", str(tmp_path))
    assert cli.main(["demo"]) == 0
    out = capsys.readouterr().out
    assert "ROUND 1" in out and "THE BEAK JUDGES" in out
