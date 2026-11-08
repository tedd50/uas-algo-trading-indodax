"""Backtest event-driven per candle 1 jam, memakai fungsi sinyal & engine yang SAMA dengan bot.

Urutan waktu per candle t (waktu buka):
  - sinyal dihitung pada close t (core.strategy.compute_signals)
  - keputusan diproses saat candle t tertutup (now = t + 1 jam), ekuitas dinilai di bid model
  - order terisi di open candle berikutnya +/- spread & slippage terukur (ModelMarket)
"""
from . import config as C
from .engine import new_state, step, equity
from .execution import ModelMarket, floor_step, ceil_step
from .strategy import compute_signals


def run_backtest(candles, meta, costs, start_ts, end_ts=None, capital=C.INITIAL_CAPITAL,
                 keep_signals_from=None):
    """candles: pair -> list bar (termasuk pemanasan sebelum start_ts).
    meta: pair -> {price_increment, quantity_increment}; costs: pair -> {half_spread, slip_buy, slip_sell}.
    Mengembalikan dict berisi equity curve, order, trade, event, sinyal (opsional), state akhir.
    """
    sig = {}
    bars = {}
    nxt = {}
    for pair, cs in candles.items():
        rows = compute_signals(cs)
        sig[pair] = {r["t"]: r for r in rows}
        bars[pair] = {b["t"]: b for b in cs}
        # bar eksekusi = bar berikutnya yang tersedia
        ts_sorted = [b["t"] for b in cs]
        nxt[pair] = {ts_sorted[i]: cs[i + 1] for i in range(len(cs) - 1)}

    times = sorted({t for pair in candles for t in bars[pair] if t >= start_ts and (end_ts is None or t + C.TF_SECONDS <= end_ts)})
    state = new_state(capital)
    market = ModelMarket(meta, costs)
    curve = []
    events = []
    signals_log = []
    last_close = {}
    for t in times:
        sigs = {}
        opens = {}
        for pair in candles:
            b = bars[pair].get(t)
            if b is not None:
                last_close[pair] = b["c"]
                sigs[pair] = sig[pair][t]
                nb = nxt[pair].get(t)
                if nb is not None and (end_ts is None or nb["t"] < end_ts):
                    opens[pair] = nb["o"]
            else:
                sigs[pair] = None
        market.set_prices(opens, dict(last_close))
        now = t + C.TF_SECONDS
        ev = step(state, t, sigs, market, now)
        for e in ev:
            events.append(e)
        state["last_bar"] = t
        curve.append((now, equity(state, market)))
        if keep_signals_from is not None and t >= keep_signals_from:
            for pair, s in sigs.items():
                if s is not None:
                    signals_log.append(dict(s, pair=pair))
    return {
        "start_ts": start_ts,
        "end_ts": curve[-1][0] if curve else start_ts,
        "capital": capital,
        "curve": curve,
        "orders": [e for e in events if e["type"] == "order"],
        "trades": [e for e in events if e["type"] == "trade"],
        "events": [e for e in events if e["type"] not in ("order", "trade")],
        "signals": signals_log,
        "state": state,
    }


def buy_and_hold(candles, meta, cost, start_ts, end_ts=None, capital=C.INITIAL_CAPITAL):
    """Benchmark buy & hold (mis. BTC/IDR): beli di open bar pertama + biaya model, nilai di bid model."""
    cs = [b for b in candles if b["t"] >= start_ts and (end_ts is None or b["t"] + C.TF_SECONDS <= end_ts)]
    if not cs:
        return {"curve": [], "total_return": None}
    tick, step_q = meta["price_increment"], meta["quantity_increment"]
    px = ceil_step(cs[0]["o"] * (1 + cost["half_spread"] + cost["slip_buy"]), tick)
    qty = floor_step(capital / (1 + C.FEE_BUY) / px, step_q)
    cash = capital - qty * px * (1 + C.FEE_BUY)
    curve = [(b["t"] + C.TF_SECONDS, cash + qty * floor_step(b["c"] * (1 - cost["half_spread"]), tick)) for b in cs]
    return {"curve": curve, "entry_price": px, "qty": qty}
