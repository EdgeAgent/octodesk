"""Command line: `octodesk` serves the Pit, `run-once` prints a debate,
`demo` runs the whole loop on fixture data (offline, exit 0)."""

from __future__ import annotations

import argparse
import json

from . import engine, paper, prices
from .config import load_config
from .server import serve


def _print_run(run):
    print(f"Prices: {run['source']} · focus asset {run['vs']['asset']} "
          f"— {run['vs']['bull']} (bull) vs {run['vs']['bear']} (bear)")
    print("\nROUND 1 — THE TENTACLES ARGUE")
    for name in engine.TENTACLES:
        print(" ", run["round1"][name]["line"])
    print("\nROUND 2 — POSITIONS HARDEN")
    for name in engine.TENTACLES:
        print(" ", run["round2"][name]["line"])
    print("\nTHE KRAKEN DECIDES")
    for sym in run["basket"]:
        print(f"  {sym}: swarm confidence {run['scores'][sym]['C']:.2f}")
    print(f"  basket energy {run['basket_energy']} (classical enumeration, q=0.40)")
    print("\nTHE BEAK JUDGES")
    for metric, m in run["gate"]["metrics"].items():
        print(f"  {metric}: {m['value']} (limit {m['limit']}) "
              f"{'OK' if m['ok'] else 'FAIL'}")
    print(f"  => {run['decision']}")
    if "paper" in run:
        print(f"  paper NAV now ${run['paper']['nav']:,.2f}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="octodesk",
                                     description="OctoDesk — Release the Kraken. Paper only.")
    parser.add_argument("--config", default=None, help="path to config JSON")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("serve", help="serve the Kraken Pit dashboard (default)")
    sub.add_parser("run-once", help="one desk run in the terminal (live prices, fixture fallback)")
    sub.add_parser("demo", help="one desk run on bundled fixture data, offline")
    args = parser.parse_args(argv)

    if args.cmd == "demo":
        series, source = prices.get_prices(live=False)
        run = engine.run_desk(series, source=source)
        portfolio = paper.load_portfolio()
        run["paper"] = paper.record_run(portfolio, run, run["prices"])
        _print_run(run)
        return 0
    if args.cmd == "run-once":
        series, source = prices.get_prices(live=True)
        run = engine.run_desk(series, source=source)
        portfolio = paper.load_portfolio()
        run["paper"] = paper.record_run(portfolio, run, run["prices"])
        _print_run(run)
        return 0
    cfg = load_config(args.config)
    serve(host=cfg["host"], port=cfg["port"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
