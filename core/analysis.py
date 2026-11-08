"""Analisis forward test dari LOG MENTAH + perbandingan dengan backtest di jendela yang sama.

Dipakai oleh dashboard Vercel (api/dashboard.py) dan scripts/hitung_ulang.py, sehingga
angka di kedua tempat berasal dari fungsi yang sama.
"""
import statistics

from . import config as C
from .backtest import run_backtest
from .metrics import max_drawdown, summarize


def _in(ts, a, b):
    return (a is None or ts >= a) and (b is None or ts < b)


def first_window_bar(start):
    """Candle pertama forward test = candle yang TERTUTUP pada/sesudah `start`."""
    return ((start + C.TF_SECONDS - 1) // C.TF_SECONDS) * C.TF_SECONDS - C.TF_SECONDS


def _bar_in(bar, start, end):
    close = bar + C.TF_SECONDS
    return close >= start and (end is None or close <= end)


def window_logs(logs, start, end):
    """Saring log ke jendela forward test [start, end)."""
    out = {}
    for name, rows in logs.items():
        if name == "signals":
            out[name] = [r for r in rows if _bar_in(r["bar"], start, end)]
        elif name == "trades":
            out[name] = [r for r in rows if _in(r["entry_ts"], start, end)]
        else:
            out[name] = [r for r in rows if _in(r.get("ts", r.get("ts_start", 0)), start, end)]
    return out


def forward_metrics(logs, start, end, now):
    eq = sorted(logs.get("equity", []), key=lambda r: r["ts"])
    curve = [(start, C.INITIAL_CAPITAL)] + [(r["ts"], r["equity"]) for r in eq]
    m = summarize(curve, C.INITIAL_CAPITAL, start, logs.get("trades", []), with_cagr=False)
    m["n_open_positions"] = eq[-1]["n_positions"] if eq else 0
    m["unrealized_value"] = eq[-1]["positions_value"] if eq else 0.0
    # benchmark buy & hold BTC/IDR: beli di best ask panggilan pertama (+fee), nilai di best bid
    bq = [r for r in eq if r.get("btc_ask") and r.get("btc_bid")]
    bench = None
    if bq:
        qty = C.INITIAL_CAPITAL / (1 + C.FEE_BUY) / bq[0]["btc_ask"]
        bcurve = [(start, C.INITIAL_CAPITAL)] + [(r["ts"], qty * r["btc_bid"]) for r in bq]
        bench = {"curve": bcurve, "total_return": bcurve[-1][1] / C.INITIAL_CAPITAL - 1,
                 "max_drawdown": max_drawdown(bcurve), "entry_ask": bq[0]["btc_ask"], "last_bid": bq[-1]["btc_bid"]}
    return {"metrics": m, "curve": curve, "bench": bench}


def ops_metrics(logs, start, end, now):
    """Uptime = candle yang diproses sebelum candle berikutnya tertutup / jumlah candle forward test."""
    stop = min(end, now) if end else now
    expected = [b for b in range(first_window_bar(start), stop, C.TF_SECONDS) if b + C.TF_SECONDS <= stop]
    calls = logs.get("calls", [])
    processed = {}
    for c in calls:
        for b in c.get("bars_processed", []):
            processed[b] = min(processed.get(b, 1e18), c.get("ts_end", c["ts_start"]))
    on_time = [b for b in expected if b in processed and processed[b] < b + 2 * C.TF_SECONDS]
    late = [b for b in expected if b in processed and processed[b] >= b + 2 * C.TF_SECONDS]
    missed = [b for b in expected if b not in processed]
    delays = sorted((processed[b] - (b + C.TF_SECONDS)) / 60.0 for b in expected if b in processed)
    status = {}
    trig = {}
    for c in calls:
        status[c["status"]] = status.get(c["status"], 0) + 1
        trig[c.get("trigger", "?")] = trig.get(c.get("trigger", "?"), 0) + 1
    ev = logs.get("events", [])
    errs = logs.get("errors", [])
    return {
        "expected_candles": len(expected),
        "processed_on_time": len(on_time),
        "processed_late": len(late),
        "missed": len(missed),
        "missed_bars": missed[:200],
        "uptime": len(on_time) / len(expected) if expected else None,
        "delay_min_median": statistics.median(delays) if delays else None,
        "delay_min_p90": delays[int(0.9 * (len(delays) - 1))] if delays else None,
        "delay_min_max": delays[-1] if delays else None,
        "calls_total": len(calls),
        "calls_by_status": status,
        "calls_by_trigger": trig,
        "api_errors": sum(1 for e in errs if e.get("type") == "api_error"),
        "tick_exceptions": sum(1 for e in errs if e.get("type") == "tick_exception"),
        "killswitch_events": [e for e in ev if str(e.get("type", "")).startswith("killswitch")],
        "killswitch_active_calls": sum(1 for e in ev if e.get("type") == "killswitch_active"),
        "daily_loss_halts": [e for e in ev if e.get("type") == "daily_loss_halt"],
        "validation_events": sum(1 for e in ev if e.get("type") == "validation"),
        "duplicate_calls": sum(1 for e in ev if e.get("type") == "duplicate_call"),
        "rejects": [e for e in ev if e.get("type") == "reject"],
        "notes": [e for e in ev if e.get("type") == "note"],
        "daily_equity": logs.get("daily_equity", []),
    }


def spread_compare(logs, costs):
    out = {}
    for pair, k in costs["pairs"].items():
        ss = [s for s in logs.get("spreads", []) if s["pair"] == pair and s.get("half_spread") is not None]
        row = {"backtest_spread_pct": k["half_spread"] * 200.0, "backtest_slip_buy_pct": k["slip_buy"] * 100,
               "backtest_slip_sell_pct": k["slip_sell"] * 100, "backtest_n": k["n"]}
        if ss:
            row.update({"forward_n": len(ss),
                        "forward_spread_pct": statistics.median(s["spread_pct"] for s in ss),
                        "forward_slip_buy_pct": statistics.median(s["slip_buy"] for s in ss if s.get("slip_buy") is not None) * 100,
                        "forward_slip_sell_pct": statistics.median(s["slip_sell"] for s in ss if s.get("slip_sell") is not None) * 100})
        out[pair] = row
    return out


def rerun_window(candles, meta, costs, start, end):
    """Backtest dijalankan ulang di jendela forward test dengan candle yang sama, modal & state awal sama."""
    fb = first_window_bar(start)
    return run_backtest(candles, meta, costs, fb, end, keep_signals_from=fb)


def gap_analysis(logs, rerun, fwd):
    # --- sinyal candle demi candle
    bot = {(r["pair"], r["bar"]): r for r in logs.get("signals", [])}
    bt = {(r["pair"], r["t"]): r for r in rerun["signals"]}
    common = sorted(set(bot) & set(bt))
    same = 0
    mism = []
    max_rel = 0.0
    for k in common:
        a, b = bot[k], bt[k]
        if a["buy"] == b["buy"] and a["sell"] == b["sell"]:
            same += 1
        else:
            mism.append({"pair": k[0], "bar": k[1], "bot": [a["buy"], a["sell"]], "backtest": [b["buy"], b["sell"]],
                         "bot_close": a["close"], "bt_close": b["close"]})
        for f in ("ema_fast", "ema_slow", "ema_trend"):
            if b[f]:
                max_rel = max(max_rel, abs(a[f] / b[f] - 1))
    bot_events = sum(1 for k in common if bot[k]["buy"] or bot[k]["sell"])
    # --- order: cocokkan (pair, side, signal_bar)
    bo = {(o["pair"], o["side"], o["signal_bar"]): o for o in logs.get("orders", [])}
    ro = {(o["pair"], o["side"], o["signal_bar"]): o for o in rerun["orders"]}
    rows = []
    for k in sorted(set(bo) | set(ro), key=lambda x: (x[2], x[0], x[1])):
        a, b = bo.get(k), ro.get(k)
        r = {"pair": k[0], "side": k[1], "signal_bar": k[2], "in_bot": a is not None, "in_backtest": b is not None}
        if a and b:
            sgn = 1 if k[1] == "buy" else -1
            # selisih harga fill (positif = lebih buruk bagi bot)
            r["bot_fill"] = a["avg_price"]
            r["bt_fill"] = b["avg_price"]
            r["total_pct"] = sgn * (a["avg_price"] / b["avg_price"] - 1) * 100
            r["delay_pct"] = sgn * (a["mid"] / b["mid"] - 1) * 100            # pergerakan harga: open t+1 -> mid saat bot jalan
            bot_sp = (a["best_ask"] / a["mid"] - 1) if sgn > 0 else (1 - a["best_bid"] / a["mid"])
            bt_sp = (b["best_ask"] / b["mid"] - 1) if sgn > 0 else (1 - b["best_bid"] / b["mid"])
            r["spread_pct"] = (bot_sp - bt_sp) * 100
            bot_sl = (a["avg_price"] / a["best_ask"] - 1) if sgn > 0 else (1 - a["avg_price"] / a["best_bid"])
            bt_sl = (b["avg_price"] / b["best_ask"] - 1) if sgn > 0 else (1 - b["avg_price"] / b["best_bid"])
            r["slippage_pct"] = (bot_sl - bt_sl) * 100
            r["residual_pct"] = r["total_pct"] - r["delay_pct"] - r["spread_pct"] - r["slippage_pct"]
            r["delay_min"] = (a["ts"] - (k[2] + C.TF_SECONDS)) / 60.0
            r["qty_bot"] = a["qty"]
            r["qty_bt"] = b["qty"]
        rows.append(r)
    matched = [r for r in rows if r["in_bot"] and r["in_backtest"]]

    def avg(f):
        return sum(r[f] for r in matched) / len(matched) if matched else None
    rm = summarize(rerun["curve"], C.INITIAL_CAPITAL, rerun["start_ts"], rerun["trades"], with_cagr=False)
    fm = fwd["metrics"]
    return {
        "signals_compared": len(common),
        "signals_identical": same,
        "signal_match_rate": same / len(common) if common else None,
        "signal_events_bot": bot_events,
        "signal_mismatches": mism[:100],
        "bars_only_in_bot": len(set(bot) - set(bt)),
        "bars_only_in_backtest": len(set(bt) - set(bot)),
        "max_rel_ema_diff": max_rel,
        "orders": rows,
        "orders_matched": len(matched),
        "orders_only_bot": sum(1 for r in rows if r["in_bot"] and not r["in_backtest"]),
        "orders_only_backtest": sum(1 for r in rows if r["in_backtest"] and not r["in_bot"]),
        "avg_fill_gap_pct": avg("total_pct"),
        "avg_delay_pct": avg("delay_pct"),
        "avg_spread_pct": avg("spread_pct"),
        "avg_slippage_pct": avg("slippage_pct"),
        "avg_delay_min": avg("delay_min"),
        "rerun_metrics": rm,
        "rerun_curve": rerun["curve"],
        "rerun_trades": rerun["trades"],
        "return_gap": fm["total_return"] - rm["total_return"],
        "mdd_gap": fm["max_drawdown"] - rm["max_drawdown"],
    }
