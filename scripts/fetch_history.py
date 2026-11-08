"""Tarik candle 1 jam historis Indodax (di laptop, BUKAN di Vercel).

history_v2 hanya mengembalikan ~650 bar terakhir sebelum `to`, jadi data ditarik MUNDUR:
mulai dari to = sekarang, geser `to` ke bar paling awal yang didapat, ulangi sampai
HISTORY_START. Jeda <= 3 request/detik, tanpa paralel.

Output: data/candles/<pair>.csv  (t,o,h,l,c,v) hanya bar yang sudah tertutup.

Pemakaian:
  python3 scripts/fetch_history.py                     # semua pasangan universe + btcidr
  python3 scripts/fetch_history.py --start 2026-10-01T00:00:00Z --end 2026-11-20T00:00:00Z --out data/forward_candles
"""
import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import config as C  # noqa: E402
from core.indodax import Client  # noqa: E402
from core.strategy import closed_bars  # noqa: E402
from core.dataio import save_csv  # noqa: E402


def ts(iso):
    return int(dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=C.HISTORY_START)
    ap.add_argument("--end", default=None, help="ISO UTC; default = server_time sekarang")
    ap.add_argument("--out", default=os.path.join(C.ROOT, "data", "candles"))
    ap.add_argument("--pairs", default=None, help="koma; default universe + benchmark")
    a = ap.parse_args()
    cl = Client()
    now = cl.server_time()
    end = min(now, ts(a.end)) if a.end else now
    uni = {u["pair"]: u for u in C.load_universe()}
    pairs = a.pairs.split(",") if a.pairs else list(uni) + ([C.BENCHMARK_PAIR] if C.BENCHMARK_PAIR not in uni else [])
    for pair in pairs:
        symbol = uni[pair]["symbol"] if pair in uni else pair.upper()
        bars = cl.history_back(symbol, C.TIMEFRAME, ts(a.start), end,
                               page_log=lambda n, ch: print("  %s halaman %d: %d bar" % (pair, n, len(ch)), file=sys.stderr) if n % 10 == 0 else None)
        bars = closed_bars(bars, end)
        save_csv(os.path.join(a.out, pair + ".csv"), bars)
        first = dt.datetime.utcfromtimestamp(bars[0]["t"]) if bars else None
        last = dt.datetime.utcfromtimestamp(bars[-1]["t"]) if bars else None
        print("%s: %d bar, %s -> %s (request total %d)" % (pair, len(bars), first, last, cl.n_requests))


if __name__ == "__main__":
    main()
