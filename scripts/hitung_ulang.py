"""hitung_ulang — hasilkan ulang SEMUA angka dashboard dari data mentah.

Input : logs/*.jsonl (log mentah bot, dari scripts/export_logs.py)
        data/candles/*.csv (candle historis Indodax untuk backtest)
        data/forward_candles/*.csv (candle jendela forward + pemanasan; --fetch untuk menarik)
        data/costs.json (median spread/slippage dari snapshot)
Output: results/hitung_ulang_metrics.json  dan  dashboard/dashboard_offline.html

  python3 scripts/hitung_ulang.py --fetch
"""
import argparse
import datetime as dt
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import config as C  # noqa: E402
from core.build import build, forward_window  # noqa: E402
from core.dataio import load_csv, load_jsonl, save_csv  # noqa: E402
from core.indodax import Client  # noqa: E402
from core.report import render  # noqa: E402
from core.store import LOG_NAMES  # noqa: E402
from core.strategy import closed_bars  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest import compute  # noqa: E402  (scripts/backtest.py)


def _clean(o):
    if isinstance(o, float) and (math.isinf(o) or math.isnan(o)):
        return str(o)
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", default=os.path.join(C.ROOT, "logs"))
    ap.add_argument("--fwd-candles", default=os.path.join(C.ROOT, "data", "forward_candles"))
    ap.add_argument("--fetch", action="store_true", help="tarik candle jendela forward dari Indodax bila belum ada")
    ap.add_argument("--out", default=os.path.join(C.ROOT, "dashboard", "dashboard_offline.html"))
    a = ap.parse_args()
    now = int(time.time())

    # 1) backtest dihitung ulang dari candle mentah & dibandingkan dengan results/backtest_summary.json
    bt_new, _ = compute()
    with open(os.path.join(C.ROOT, "results", "backtest_summary.json")) as f:
        bt_old = json.load(f)
    keys = ["total_return", "cagr", "max_drawdown", "n_trades", "win_rate", "profit_factor", "cost_share", "avg_win_idr", "avg_loss_idr"]
    diff = [k for k in keys if bt_old["metrics"].get(k) != bt_new["metrics"].get(k)]
    check = {"Backtest dihitung ulang vs results/backtest_summary.json": "IDENTIK" if not diff else "BERBEDA: %s" % diff}

    # 2) log mentah forward
    logs = {n: load_jsonl(os.path.join(a.logs, n + ".jsonl")) for n in LOG_NAMES if n != "snapshots"}
    check["Jumlah baris log"] = ", ".join("%s=%d" % (n, len(v)) for n, v in logs.items())
    start, end = forward_window(logs, now)

    # 3) candle jendela forward untuk backtest ulang
    candles = None
    if start:
        stop = min(end or now, now)
        uni = C.load_universe()
        paths = {u["pair"]: os.path.join(a.fwd_candles, u["pair"] + ".csv") for u in uni}
        if a.fetch and not all(os.path.exists(p) for p in paths.values()):
            cl = Client()
            server = cl.server_time()
            for u in uni:
                frm = start - (C.BOT_HISTORY_PAGES * 660) * C.TF_SECONDS
                pages = int((min(stop, server) - frm) / (640 * C.TF_SECONDS)) + 2
                cs = closed_bars(cl.history_back(u["symbol"], C.TIMEFRAME, frm, min(stop, server), max_pages=pages), server)
                save_csv(paths[u["pair"]], cs)
                print("candle forward %s: %d bar" % (u["pair"], len(cs)))
        if all(os.path.exists(p) for p in paths.values()):
            candles = {k: load_csv(p) for k, p in paths.items()}

    refl = None
    rp = os.path.join(C.ROOT, "REFLEKSI.md")
    if os.path.exists(rp):
        with open(rp) as f:
            refl = f.read()
    R = build(logs, bt_new, candles, now, "hitung_ulang dari log mentah (offline)", reflection=refl, check=check)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        f.write(render(R))
    slim = {k: v for k, v in R.items() if k not in ("reflection",)}
    slim["backtest"] = {k: v for k, v in bt_new.items() if k not in ("curve_daily", "bench_curve_daily", "trades")}
    with open(os.path.join(C.ROOT, "results", "hitung_ulang_metrics.json"), "w") as f:
        json.dump(_clean(slim), f, indent=1, default=str)

    bm = bt_new["metrics"]
    print("BACKTEST  return %.2f%% CAGR %.2f%% MDD %.2f%% trade %d" % (bm["total_return"] * 100, bm["cagr"] * 100, bm["max_drawdown"] * 100, bm["n_trades"]))
    if R.get("forward"):
        fm = R["forward"]["metrics"]
        print("FORWARD   return %.2f%% MDD %.2f%% trade %d (mulai %s)" % (fm["total_return"] * 100, fm["max_drawdown"] * 100, fm["n_trades"],
              dt.datetime.utcfromtimestamp(start).strftime("%Y-%m-%d %H:%M UTC")))
        o = R["ops"]
        print("UPTIME    %s (%d/%d)" % ("-" if o["uptime"] is None else "%.1f%%" % (o["uptime"] * 100), o["processed_on_time"], o["expected_candles"]))
    if R.get("gap"):
        g = R["gap"]
        print("SINYAL    %s identik (%d/%d)" % ("-" if g["signal_match_rate"] is None else "%.2f%%" % (g["signal_match_rate"] * 100),
              g["signals_identical"], g["signals_compared"]))
    for k, v in check.items():
        print("CEK", k, ":", v)
    print("tertulis:", a.out)


if __name__ == "__main__":
    main()
