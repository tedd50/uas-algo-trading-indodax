"""Hitung median spread & slippage per pasangan dari snapshot order book -> data/costs.json.

Sumber: data/snapshots/*.jsonl (collector laptop) dan, bila ada, logs/snapshots.jsonl (bot).
--until ISO: hanya snapshot sebelum waktu itu (untuk backtest sebelum freeze).

Model backtest: beli = open x (1 + half_spread + slip_buy), jual = open x (1 - half_spread - slip_sell),
lalu dibulatkan ke kenaikan harga pasangan. Ukuran order acuan = Rp15 juta (15% x modal awal).
"""
import argparse
import datetime as dt
import glob
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import config as C  # noqa: E402
from core.snapshot import REF_ORDER_IDR  # noqa: E402


def ts(iso):
    return int(dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp())


def load_snapshots(until=None, include_bot=True):
    files = sorted(glob.glob(os.path.join(C.ROOT, "data", "snapshots", "*.jsonl")))
    bot = os.path.join(C.ROOT, "logs", "snapshots.jsonl")
    if include_bot and os.path.exists(bot):
        files.append(bot)
    out = []
    for fp in files:
        with open(fp) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                s = json.loads(line)
                if until is not None and s["ts"] >= until:
                    continue
                out.append(s)
    return out


def summarize(snaps, pairs):
    res = {}
    for pair in pairs:
        ss = [s for s in snaps if s["pair"] == pair and s.get("half_spread") is not None
              and s.get("slip_buy") is not None and s.get("slip_sell") is not None]
        if not ss:
            continue
        res[pair] = {
            "n": len(ss),
            "first_ts": min(s["ts"] for s in ss),
            "last_ts": max(s["ts"] for s in ss),
            "half_spread": statistics.median(s["half_spread"] for s in ss),
            "spread_pct_median": statistics.median(s["spread_pct"] for s in ss),
            "spread_pct_p90": sorted(s["spread_pct"] for s in ss)[int(0.9 * (len(ss) - 1))],
            "slip_buy": statistics.median(s["slip_buy"] for s in ss),
            "slip_sell": statistics.median(s["slip_sell"] for s in ss),
            "depth_ok_share": sum(1 for s in ss if s.get("depth_ok")) / len(ss),
        }
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", default=None)
    ap.add_argument("--no-bot", action="store_true")
    a = ap.parse_args()
    until = ts(a.until) if a.until else None
    pairs = [u["pair"] for u in C.load_universe()] + [C.BENCHMARK_PAIR]
    pairs = list(dict.fromkeys(pairs))
    snaps = load_snapshots(until, include_bot=not a.no_bot)
    res = summarize(snaps, pairs)
    missing = [p for p in pairs if p not in res]
    if missing:
        sys.exit("tidak ada snapshot untuk: %s (jalankan scripts/collect_snapshots.py)" % missing)
    out = {"ref_order_idr": REF_ORDER_IDR, "until": a.until,
           "generated_utc": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
           "n_snapshots_total": len(snaps), "pairs": res}
    with open(C.COSTS_FILE, "w") as f:
        json.dump(out, f, indent=2)
    for p, r in res.items():
        print("%-10s n=%3d spread_med=%.4f%% slip_buy=%.4f%% slip_sell=%.4f%%" % (
            p, r["n"], r["spread_pct_median"], r["slip_buy"] * 100, r["slip_sell"] * 100))


if __name__ == "__main__":
    main()
