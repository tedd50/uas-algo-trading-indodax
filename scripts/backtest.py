"""Backtest >= 3 tahun dengan data historis asli Indodax (data/candles/*.csv).

  python3 scripts/backtest.py            # tulis results/backtest_summary.json, *_trades.csv, *_equity.csv
  python3 scripts/backtest.py --check    # jalankan ulang & bandingkan dengan backtest_summary.json (tanpa menulis)

Memakai core.strategy.compute_signals dan core.engine.step yang sama dengan bot.
"""
import argparse
import csv
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import config as C  # noqa: E402
from core.backtest import buy_and_hold, run_backtest  # noqa: E402
from core.metrics import max_drawdown, summarize, cagr  # noqa: E402
from core.dataio import load_csv  # noqa: E402

SUMMARY = os.path.join(C.ROOT, "results", "backtest_summary.json")


def ts(iso):
    return int(dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp())


def iso(t):
    return dt.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d %H:%M")


def daily(curve):
    out = {}
    for t, v in curve:
        out[dt.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d")] = (t, v)
    return [list(out[k]) for k in sorted(out)]


def data_report(candles, start):
    rep = {}
    for pair, cs in candles.items():
        cs2 = [b for b in cs if b["t"] >= start]
        gaps = sum(1 for i in range(1, len(cs2)) if cs2[i]["t"] - cs2[i - 1]["t"] != C.TF_SECONDS)
        missing = sum((cs2[i]["t"] - cs2[i - 1]["t"]) // C.TF_SECONDS - 1 for i in range(1, len(cs2)))
        rep[pair] = {"bars": len(cs2), "first": iso(cs2[0]["t"]) if cs2 else None, "last": iso(cs2[-1]["t"]) if cs2 else None,
                     "gaps": gaps, "missing_bars": int(missing), "zero_volume_bars": sum(1 for b in cs2 if b["v"] <= 0),
                     "warmup_bars_before_start": sum(1 for b in cs if b["t"] < start)}
    return rep


def compute(end_ts=None):
    uni = C.load_universe()
    meta = {u["pair"]: u for u in uni}
    costs = C.load_costs()
    candles = {p: load_csv(os.path.join(C.ROOT, "data", "candles", p + ".csv")) for p in meta}
    start = ts(C.BACKTEST_START)
    res = run_backtest(candles, meta, {p: costs["pairs"][p] for p in meta}, start, end_ts)
    m = summarize(res["curve"], C.INITIAL_CAPITAL, start, res["trades"])
    # benchmark buy & hold BTC/IDR, periode yang sama
    btc = load_csv(os.path.join(C.ROOT, "data", "candles", C.BENCHMARK_PAIR + ".csv"))
    bmeta = meta.get(C.BENCHMARK_PAIR) or {"price_increment": 1000.0, "quantity_increment": 1e-8}
    bh = buy_and_hold(btc, bmeta, costs["pairs"][C.BENCHMARK_PAIR], start, res["end_ts"])
    bench = {"total_return": bh["curve"][-1][1] / C.INITIAL_CAPITAL - 1, "cagr": cagr(bh["curve"], C.INITIAL_CAPITAL, start),
             "max_drawdown": max_drawdown(bh["curve"])}
    annual = {}
    prev = C.INITIAL_CAPITAL
    for t, v in daily(res["curve"]):
        y = dt.datetime.utcfromtimestamp(t).strftime("%Y")
        annual.setdefault(y, [prev, v])
        annual[y][1] = v
        prev = v
    rej = {}
    for e in res["events"]:
        if e["type"] == "reject":
            k = e["reason"].split(":")[0]
            rej[k] = rej.get(k, 0) + 1
    return {
        "generated_utc": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "strategy": C.STRATEGY_NAME,
        "params": {"fast": C.FAST, "slow": C.SLOW, "trend": C.TREND, "adx_n": C.ADX_N, "min_adx": C.MIN_ADX,
                   "timeframe_min": int(C.TIMEFRAME), "max_positions": C.MAX_POSITIONS, "position_pct": C.POSITION_PCT,
                   "max_position_pct": C.MAX_POSITION_PCT, "liq_cap_pct": C.LIQ_CAP_PCT,
                   "daily_loss_limit": C.DAILY_LOSS_LIMIT, "fee_buy": C.FEE_BUY, "fee_sell": C.FEE_SELL,
                   "min_order_idr": C.MIN_ORDER_IDR, "initial_capital": C.INITIAL_CAPITAL},
        "universe": [u["pair"] for u in uni],
        "costs_used": costs,
        "period": {"start": iso(start), "end": iso(res["end_ts"]), "start_ts": start, "end_ts": res["end_ts"],
                   "years": (res["end_ts"] - start) / (365.25 * 86400)},
        "metrics": m,
        "benchmark_btc_bh": bench,
        "annual_returns": {y: v[1] / v[0] - 1 for y, v in annual.items()},
        "curve_daily": daily(res["curve"]),
        "bench_curve_daily": daily(bh["curve"]),
        "rejects_by_reason": rej,
        "daily_loss_halts": sum(1 for e in res["events"] if e["type"] == "daily_loss_halt"),
        "open_positions_end": res["state"]["positions"],
        "data_report": data_report(candles, start),
        "trades": res["trades"],
    }, res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--end", default=None, help="ISO UTC; default = akhir data")
    a = ap.parse_args()
    summ, res = compute(ts(a.end) if a.end else None)
    m = summ["metrics"]
    print("periode %s -> %s (%.2f th)" % (summ["period"]["start"], summ["period"]["end"], summ["period"]["years"]))
    print("return %.2f%%  CAGR %.2f%%  MDD %.2f%%  trades %d  win %.1f%%  PF %s  porsi biaya %s" % (
        m["total_return"] * 100, m["cagr"] * 100, m["max_drawdown"] * 100, m["n_trades"],
        (m["win_rate"] or 0) * 100, m["profit_factor"], m["cost_share"]))
    b = summ["benchmark_btc_bh"]
    print("BTC B&H return %.2f%% CAGR %.2f%% MDD %.2f%%" % (b["total_return"] * 100, b["cagr"] * 100, b["max_drawdown"] * 100))
    if a.check:
        with open(SUMMARY) as f:
            old = json.load(f)
        keys = ["total_return", "cagr", "max_drawdown", "n_trades", "win_rate", "profit_factor", "cost_share"]
        bad = [k for k in keys if old["metrics"][k] != m[k]]
        print("CEK ULANG:", "IDENTIK" if not bad else "BERBEDA pada %s" % bad)
        sys.exit(1 if bad else 0)
    os.makedirs(os.path.join(C.ROOT, "results"), exist_ok=True)
    with open(SUMMARY, "w") as f:
        json.dump(summ, f, indent=1)
    with open(os.path.join(C.ROOT, "results", "backtest_trades.csv"), "w", newline="") as f:
        if res["trades"]:
            w = csv.DictWriter(f, fieldnames=list(res["trades"][0].keys()))
            w.writeheader()
            w.writerows(res["trades"])
    with open(os.path.join(C.ROOT, "results", "backtest_orders.csv"), "w", newline="") as f:
        if res["orders"]:
            w = csv.DictWriter(f, fieldnames=list(res["orders"][0].keys()))
            w.writeheader()
            w.writerows(res["orders"])
    with open(os.path.join(C.ROOT, "results", "backtest_equity.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ts", "utc", "equity"])
        for t, v in res["curve"]:
            w.writerow([t, iso(t), round(v, 2)])
    print("tersimpan:", SUMMARY)


if __name__ == "__main__":
    main()
