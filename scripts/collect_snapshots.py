"""Kumpulkan snapshot order book setiap pasangan universe (di laptop, masa persiapan).

  python3 scripts/collect_snapshots.py                 # sekali
  python3 scripts/collect_snapshots.py --every 3600 --count 48   # tiap jam, 48 kali

Snapshot mentah (semua level dari /api/depth) disimpan ke data/snapshots/YYYY-MM-DD.jsonl.
Selama forward test, bot menyimpan snapshot sendiri di storage (log 'snapshots').
"""
import argparse
import datetime as dt
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import config as C  # noqa: E402
from core.indodax import Client, ApiError  # noqa: E402
from core.snapshot import make_snapshot  # noqa: E402


def once(cl, pairs):
    now = cl.server_time()
    day = dt.datetime.utcfromtimestamp(now).strftime("%Y-%m-%d")
    path = os.path.join(C.ROOT, "data", "snapshots", day + ".jsonl")
    with open(path, "a") as f:
        for pair in pairs:
            try:
                d = cl.depth(pair)
            except ApiError as e:
                print("gagal", pair, e, file=sys.stderr)
                continue
            s = make_snapshot(pair, d, int(time.time()), "laptop_collector")
            f.write(json.dumps(s) + "\n")
            print("%s %s spread=%.4f%% slip_buy=%s" % (dt.datetime.utcnow().strftime("%H:%M:%S"), pair,
                  s.get("spread_pct", -1), s.get("slip_buy")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--every", type=int, default=0)
    ap.add_argument("--count", type=int, default=1)
    a = ap.parse_args()
    pairs = [u["pair"] for u in C.load_universe()]
    if C.BENCHMARK_PAIR not in pairs:
        pairs.append(C.BENCHMARK_PAIR)
    cl = Client()
    for i in range(a.count):
        once(cl, pairs)
        if i < a.count - 1 and a.every:
            time.sleep(a.every)


if __name__ == "__main__":
    main()
