import statistics

from octodesk import engine
from octodesk.prices import UNIVERSE, load_fixture


def _series(fn, n=126):
    return {s: [fn(s, i) for i in range(n)] for s in UNIVERSE}


def test_debate_deterministic():
    series = load_fixture()
    a = engine.run_desk(series, source="fixture")
    b = engine.run_desk(series, source="fixture")
    assert a == b
    assert len(a["basket"]) == 4
    assert set(a["round1"]) == set(engine.TENTACLES)


def test_aggregate_math():
    assert engine.aggregate([1.0] * 8) == {"M": 1.0, "A": 1.0, "C": 1.0}
    low = engine.aggregate([-1.0] * 8)
    assert low["M"] == 0.0 and low["C"] == 0.35
    keep = engine.aggregate([0.6] * 8)  # agreement 1, M 0.8 -> C 0.87
    assert keep["C"] >= engine.KEEP_THRESHOLD
    split = engine.aggregate([1.0, -1.0] * 4)  # pod at war: agreement sinks
    assert split["A"] < 0.2 and split["C"] < engine.KEEP_THRESHOLD


def test_gate_passes_calm_market():
    series = _series(lambda s, i: 100.0 * (1.001 ** i))
    basket = UNIVERSE[:4]
    gate = engine.check_gate(series, basket)
    assert gate["passed"], gate
    assert gate["failing"] is None


def test_gate_variance_failure():
    # violent alternating swings -> annualized variance blows the ceiling
    series = _series(lambda s, i: 100.0 if i % 2 == 0 else 130.0)
    gate = engine.check_gate(series, UNIVERSE[:4])
    assert not gate["metrics"]["variance"]["ok"]
    assert not gate["passed"]


def test_gate_drawdown_failure():
    def crash(s, i):
        return 100.0 if i < 60 else 65.0  # -35% cliff, stays down
    series = _series(crash)
    gate = engine.check_gate(series, UNIVERSE[:4])
    assert not gate["metrics"]["drawdown"]["ok"]
    assert gate["metrics"]["drawdown"]["value"] > engine.MAX_DRAWDOWN


def test_gate_cap_failure():
    series = _series(lambda s, i: 100.0 * (1.001 ** i))
    weights = {UNIVERSE[0]: 0.55, UNIVERSE[1]: 0.15,
               UNIVERSE[2]: 0.15, UNIVERSE[3]: 0.15}
    gate = engine.check_gate(series, UNIVERSE[:4], weights=weights)
    assert not gate["metrics"]["max_weight"]["ok"]
    assert gate["failing"] == "max_weight"
