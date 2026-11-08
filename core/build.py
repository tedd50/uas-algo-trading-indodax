"""Rakit semua angka dashboard dari log mentah + hasil backtest. Dipakai Vercel & hitung_ulang."""
import datetime as dt
import os

from . import config as C
from .analysis import forward_metrics, gap_analysis, ops_metrics, rerun_window, spread_compare, window_logs


def parse_iso(s):
    return int(dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp()) if s else None


def forward_window(logs, now):
    start = parse_iso(C.FORWARD_START_UTC)
    end = parse_iso(C.FORWARD_END_UTC)
    if start is None:
        ok = [c["ts_start"] for c in logs.get("calls", []) if c.get("status") == "ok"]
        start = min(ok) if ok else None
    return start, end


def build(logs, backtest_summary, fwd_candles, now, source, reflection=None, check=None):
    start, end = forward_window(logs, now)
    R = {"generated": dt.datetime.utcfromtimestamp(now).strftime("%Y-%m-%d %H:%M UTC"), "source": source,
         "backtest": backtest_summary, "reflection": reflection, "check": check,
         "freeze": {"freeze_utc": C.FREEZE_UTC, "commit": os.environ.get("VERCEL_GIT_COMMIT_SHA", "")[:10] or os.environ.get("GIT_COMMIT", ""),
                    "start_ts": start, "end_ts": end}}
    if start is None:
        return R
    wl = window_logs(logs, start, end)
    fwd = forward_metrics(wl, start, end, now)
    R["forward"] = fwd
    R["ops"] = ops_metrics(wl, start, end, now)
    R["fwd_trades"] = wl.get("trades", [])
    R["fwd_orders"] = wl.get("orders", [])
    R["spreads"] = spread_compare(wl, backtest_summary["costs_used"])
    if fwd_candles:
        meta = {u["pair"]: u for u in C.load_universe()}
        costs = {p: backtest_summary["costs_used"]["pairs"][p] for p in meta}
        stop = min(end or now, now)
        rerun = rerun_window(fwd_candles, meta, costs, start, stop)
        R["gap"] = gap_analysis(wl, rerun, fwd)
    return R
