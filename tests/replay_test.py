"""Uji integrasi REPLAY (bukan data forward test!): jalankan kode bot jam demi jam di atas
candle historis asli, dengan order book tiruan di sekitar harga close, lalu jalankan
analisis gap/hitung_ulang. Tujuannya membuktikan pipa log -> dashboard bekerja dan
sinyal bot == sinyal backtest. Output ditulis ke folder sementara, BUKAN ke logs/.

  python3 tests/replay_test.py --hours 120 --out /tmp/replay
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import config as C  # noqa: E402
from core.bot import tick  # noqa: E402
from core.build import build  # noqa: E402
from core.dataio import load_csv  # noqa: E402
from core.report import render  # noqa: E402
from core.store import LOG_NAMES, LocalStore, read_log  # noqa: E402


class ReplayClient:
    def __init__(self, candles, costs, server):
        self.c = candles
        self.costs = costs
        self.server = server
        self.n_requests = 0
        self.n_errors = 0
        self.log = None

    def server_time(self):
        return self.server

    def history_back(self, symbol, tf, start, to, max_pages=None, page_log=None):
        pair = symbol.lower()
        cs = [b for b in self.c[pair] if b["t"] <= to]
        return cs[-(max_pages or 3) * 649:]

    def depth(self, pair):
        cs = [b for b in self.c[pair] if b["t"] + 3600 <= self.server]
        px = cs[-1]["c"]
        hs = self.costs[pair]["half_spread"]
        bid, ask = px * (1 - hs), px * (1 + hs)
        return {"buy": [[str(bid * (1 - i * 0.001)), str(5e7 / px)] for i in range(20)],
                "sell": [[str(ask * (1 + i * 0.001)), str(5e7 / px)] for i in range(20)]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=120)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    pairs = [u["pair"] for u in C.load_universe()] + [C.BENCHMARK_PAIR]
    candles = {p: load_csv(os.path.join(C.ROOT, "data", "candles", p + ".csv")) for p in set(pairs)}
    costs = json.load(open(C.COSTS_FILE))["pairs"]
    st = LocalStore(os.path.join(a.out, "store"))
    last = candles[C.BENCHMARK_PAIR][-1]["t"] + 3600
    first = last - a.hours * 3600
    for h in range(first, last + 1, 3600):
        if h % (3600 * 7) == 0:
            continue   # sengaja melewatkan sebagian jam -> uji catch-up & uptime
        server = h + 7 * 60
        tick(st, ReplayClient(candles, costs, server), trigger="replay", now_fn=lambda s=server: s, forward_start=None)
    logs = {n: read_log(st, n) for n in LOG_NAMES if n != "snapshots"}
    bt = json.load(open(os.path.join(C.ROOT, "results", "backtest_summary.json")))
    R = build(logs, bt, {p: candles[p] for p in pairs if p in costs}, last + 3600, "REPLAY TEST (bukan forward test)",
              window=(first + 7 * 60, None))
    with open(os.path.join(a.out, "replay_dashboard.html"), "w") as f:
        f.write(render(R))
    g = R["gap"]
    print("calls", len(logs["calls"]), "orders", len(logs["orders"]), "trades", len(logs["trades"]))
    print("signal match %.4f (%d/%d), orders matched %d, only bot %d, only bt %d" % (
        g["signal_match_rate"], g["signals_identical"], g["signals_compared"], g["orders_matched"], g["orders_only_bot"], g["orders_only_backtest"]))
    print("uptime", R["ops"]["uptime"], "late", R["ops"]["processed_late"], "missed", R["ops"]["missed"])
    print("fwd ret", R["forward"]["metrics"]["total_return"], "rerun ret", g["rerun_metrics"]["total_return"])
    for r in g["orders"][:12]:
        print(r)


if __name__ == "__main__":
    main()
