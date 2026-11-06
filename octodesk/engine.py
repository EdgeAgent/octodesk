"""The Kraken's mind: tentacle debate, brain basket-picking, beak gate.

Honest labels, on purpose:
- The "quantum coprocessor" is classical enumeration standing in for
  QAOA p=2. No quantum hardware is involved anywhere in this app.
- Persona scores are deterministic heuristics over price features.
  They are a game with real math underneath — not financial advice.
"""

from __future__ import annotations

import itertools
import math
import statistics

from .prices import UNIVERSE

BASKET_SIZE = 4          # B = 4 of 12
Q_RISK = 0.40            # q: risk aversion in the basket objective
KEEP_THRESHOLD = 0.70    # swarm confidence needed to keep a candidate
MAX_VARIANCE = 0.035     # REA gate: annualized portfolio variance ceiling
MAX_DRAWDOWN = 0.08      # REA gate: trailing drawdown ceiling
MAX_WEIGHT = 0.25        # REA gate: single-asset weight ceiling

# name -> (weights over features, voice for verdict lines)
PERSONAS = {
    "Bull":      {"mom20": 0.9, "mom5": 0.5, "trend": 0.5, "meanrev": -0.3, "vol": 0.1},
    "Bear":      {"mom20": -0.9, "mom5": -0.5, "trend": -0.5, "meanrev": 0.3, "vol": -0.2},
    "Momentum":  {"mom20": 1.0, "mom5": 0.7, "trend": 0.4, "meanrev": 0.0, "vol": 0.0},
    "Value":     {"mom20": -0.2, "mom5": 0.0, "trend": 0.0, "meanrev": 0.9, "vol": -0.2},
    "Contrarian": {"mom20": -0.7, "mom5": -0.6, "trend": -0.3, "meanrev": 0.5, "vol": 0.2},
    "Sentiment": {"mom20": 0.5, "mom5": 0.9, "trend": 0.2, "meanrev": 0.0, "vol": 0.3},
    "News Hawk": {"mom20": 0.3, "mom5": 0.8, "trend": 0.1, "meanrev": 0.0, "vol": 0.5},
    "Risk":      {"mom20": 0.1, "mom5": 0.0, "trend": 0.2, "meanrev": 0.0, "vol": -1.0},
}
TENTACLES = list(PERSONAS.keys())

_VERB = {
    "Bull": "charges", "Bear": "growls at", "Momentum": "rides",
    "Value": "sniffs value in", "Contrarian": "fades the crowd on",
    "Sentiment": "feels the buzz around", "News Hawk": "circles",
    "Risk": "watches",
}


def _returns(closes):
    return [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]


def _sma(values, n):
    if len(values) < n:
        return statistics.fmean(values)
    return statistics.fmean(values[-n:])


def features(closes):
    """Deterministic price features for one asset. All roughly in [-1, 1]."""
    rets = _returns(closes)
    price = closes[-1]
    mom20 = price / closes[-21] - 1.0 if len(closes) > 21 else 0.0
    mom5 = price / closes[-6] - 1.0 if len(closes) > 6 else 0.0
    sma50 = _sma(closes, 50)
    sma20 = _sma(closes, 20)
    vol20 = statistics.pstdev(rets[-20:]) if len(rets) >= 20 else statistics.pstdev(rets)
    return {
        "mom20": max(-1.0, min(1.0, mom20 * 4)),
        "mom5": max(-1.0, min(1.0, mom5 * 6)),
        # negative when price stretched above its mean (Value likes the dip)
        "meanrev": max(-1.0, min(1.0, (sma50 - price) / sma50 * 8)) if sma50 else 0.0,
        "trend": max(-1.0, min(1.0, (sma20 - sma50) / sma50 * 10)) if sma50 else 0.0,
        # calm water reads positive for Risk after its negative weight
        "vol": max(-1.0, min(1.0, 1.0 - vol20 * 25)),
    }


def persona_stance(weights, feats):
    raw = sum(weights[k] * feats[k] for k in weights)
    return max(-1.0, min(1.0, raw))


def debate(feats_by_sym):
    """Two rounds. Round 2: every tentacle hardens 25% toward the pod's mean."""
    round1 = {name: {sym: persona_stance(PERSONAS[name], feats_by_sym[sym])
                     for sym in UNIVERSE} for name in TENTACLES}
    round2 = {}
    for name in TENTACLES:
        round2[name] = {}
        for sym in UNIVERSE:
            others = [round1[o][sym] for o in TENTACLES if o != name]
            round2[name][sym] = max(-1.0, min(1.0, 0.75 * round1[name][sym]
                                              + 0.25 * statistics.fmean(others)))
    return round1, round2


def aggregate(stances):
    """C = clip(0.65*M + 0.35*A, 0, 1). M: mean stance mapped to 0..1.
    A: agreement factor — tentacles pointing the same way raise it."""
    mean = statistics.fmean(stances)
    m = (mean + 1.0) / 2.0
    a = max(0.0, min(1.0, 1.0 - statistics.pstdev(stances)))
    c = max(0.0, min(1.0, 0.65 * m + 0.35 * a))
    return {"M": round(m, 4), "A": round(a, 4), "C": round(c, 4)}


def _portfolio_returns(series_by_sym, basket, weights):
    n = min(len(series_by_sym[s]) for s in basket)
    rets = {s: _returns(series_by_sym[s][-n:]) for s in basket}
    m = min(len(v) for v in rets.values())
    return [sum(weights[s] * rets[s][i] for s in basket) for i in range(m)]


def _basket_energy(series_by_sym, basket, feats_by_sym):
    """QUBO-style energy (lower wins): -mean(momentum) + q * variance.
    Classical enumeration over combinations stands in for QAOA p=2."""
    weights = {s: 1.0 / len(basket) for s in basket}
    prets = _portfolio_returns(series_by_sym, basket, weights)
    var = statistics.pvariance(prets) * 100 if len(prets) > 1 else 0.0
    mu = statistics.fmean(feats_by_sym[s]["mom20"] for s in basket)
    return -mu + Q_RISK * var


def pick_basket(series_by_sym, feats_by_sym, scores):
    kept = [s for s in UNIVERSE if scores[s]["C"] >= KEEP_THRESHOLD]
    if len(kept) >= BASKET_SIZE:
        pool = kept
    else:
        pool = sorted(UNIVERSE, key=lambda s: -scores[s]["C"])[:BASKET_SIZE]
    best, best_e = None, None
    for combo in itertools.combinations(sorted(pool), BASKET_SIZE):
        e = _basket_energy(series_by_sym, list(combo), feats_by_sym)
        if best_e is None or e < best_e:
            best, best_e = list(combo), e
    return best, round(best_e, 4), kept


def check_gate(series_by_sym, basket, weights=None):
    """THE BEAK — REA risk gate. Returns metrics + pass/fail + failing metric."""
    if weights is None:
        weights = {s: 1.0 / len(basket) for s in basket}
    prets = _portfolio_returns(series_by_sym, basket, weights)
    variance = statistics.pvariance(prets) * 252 if len(prets) > 1 else 0.0
    # trailing drawdown of the basket index
    index, peak, max_dd = 1.0, 1.0, 0.0
    for r in prets:
        index *= (1.0 + r)
        peak = max(peak, index)
        max_dd = max(max_dd, (peak - index) / peak if peak else 0.0)
    max_weight = max(weights.values())
    checks = {
        "variance": (round(variance, 4), MAX_VARIANCE, variance <= MAX_VARIANCE),
        "drawdown": (round(max_dd, 4), MAX_DRAWDOWN, max_dd <= MAX_DRAWDOWN),
        "max_weight": (round(max_weight, 4), MAX_WEIGHT, max_weight <= MAX_WEIGHT),
    }
    failing = [k for k, (_, _, ok) in checks.items() if not ok]
    return {
        "passed": not failing,
        "failing": failing[0] if failing else None,
        "metrics": {k: {"value": v, "limit": lim, "ok": ok}
                    for k, (v, lim, ok) in checks.items()},
        "weights": {s: round(weights[s], 4) for s in basket},
    }


def run_desk(series_by_sym, source="fixture"):
    """One full desk run. Pure function of the price series — deterministic."""
    feats = {sym: features(series_by_sym[sym]) for sym in UNIVERSE}
    round1, round2 = debate(feats)
    scores = {sym: aggregate([round2[t][sym] for t in TENTACLES]) for sym in UNIVERSE}
    basket, energy, kept = pick_basket(series_by_sym, feats, scores)
    gate = check_gate(series_by_sym, basket)

    def lines_for(rnd):
        out = {}
        for name in TENTACLES:
            st = rnd[name]
            top = max(st, key=st.get)
            bottom = min(st, key=st.get)
            out[name] = {
                "top_asset": top, "top_stance": round(st[top], 2),
                "bottom_asset": bottom, "bottom_stance": round(st[bottom], 2),
                "line": (f"{name} {_VERB[name]} {top} ({st[top]:+.2f})"
                         f" · fades {bottom} ({st[bottom]:+.2f})"),
                "stances": {s: round(st[s], 3) for s in UNIVERSE},
            }
        return out

    focus = basket[0] if basket else UNIVERSE[0]
    bull = max(TENTACLES, key=lambda t: round2[t][focus])
    bear = min(TENTACLES, key=lambda t: round2[t][focus])
    prices_now = {sym: round(series_by_sym[sym][-1], 2) for sym in UNIVERSE}
    return {
        "source": source,
        "prices": prices_now,
        "round1": lines_for(round1),
        "round2": lines_for(round2),
        "scores": {sym: {**scores[sym], "kept": scores[sym]["C"] >= KEEP_THRESHOLD}
                   for sym in UNIVERSE},
        "kept_candidates": kept,
        "basket": basket,
        "basket_energy": energy,
        "vs": {"asset": focus, "bull": bull, "bear": bear},
        "gate": gate,
        "decision": "PAPER FILL" if gate["passed"] else "REJECTED BY THE BEAK",
    }
