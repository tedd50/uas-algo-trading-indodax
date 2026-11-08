"""Engine portofolio BERSAMA (backtest & bot): sizing, risk management, eksekusi.

`step()` memproses satu candle tertutup untuk semua pasangan:
  1. pergantian hari WIB -> catat equity harian, reset daily loss limit
  2. jual (death cross / pending exit)
  3. cek daily loss limit
  4. beli (ranking ADX tertinggi), dibatasi kill switch, daily loss, validasi data,
     jumlah posisi, ukuran maksimum per posisi, kas, likuiditas, minimum order
Semua state adalah dict biasa agar bisa disimpan sebagai JSON di storage.
"""
from . import config as C


def new_state(capital=C.INITIAL_CAPITAL):
    return {
        "cash": float(capital),
        "positions": {},
        "day_key": None,
        "day_start_equity": None,
        "halted_day": None,
        "trade_seq": 0,
        "order_seq": 0,
        "last_bar": None,
    }


def wib_day(ts):
    import datetime as _dt
    return _dt.datetime.utcfromtimestamp(int(ts) + C.WIB_OFFSET).strftime("%Y-%m-%d")


def equity(state, market):
    eq = state["cash"]
    for pair, p in state["positions"].items():
        m = market.mark(pair)
        if m is None:
            m = p.get("last_mark", p["entry_price"])
        else:
            p["last_mark"] = m
        eq += p["qty"] * m
    return eq


def _costs(fill):
    q = fill["qty"]
    if fill["side"] == "buy":
        spread = q * (fill["best_ask"] - fill["mid"])
        slip = q * (fill["avg_price"] - fill["best_ask"])
    else:
        spread = q * (fill["mid"] - fill["best_bid"])
        slip = q * (fill["best_bid"] - fill["avg_price"])
    return spread, slip


def _order_record(state, fill, pair, bar_t, sig_price, now_ts, reason):
    state["order_seq"] += 1
    spread, slip = _costs(fill)
    return {
        "type": "order",
        "order_id": state["order_seq"],
        "ts": now_ts,
        "signal_bar": bar_t,
        "pair": pair,
        "side": fill["side"],
        "qty": fill["qty"],
        "best_bid": fill["best_bid"],
        "best_ask": fill["best_ask"],
        "mid": fill["mid"],
        "avg_price": fill["avg_price"],
        "value": fill["value"],
        "fee": fill["fee"],
        "spread_cost": spread,
        "slippage_cost": slip,
        "signal_price": sig_price,
        "diff_vs_signal_pct": (fill["avg_price"] / sig_price - 1.0) * 100.0 if sig_price else None,
        "levels_used": fill["levels_used"],
        "partial": fill["partial"],
        "reason": reason,
    }


def step(state, bar_t, sigs, market, now_ts, killswitch=False, entry_block=None):
    """Proses candle `bar_t`. sigs: pair -> baris sinyal (core.strategy) atau None.

    Mengembalikan list event (order, trade, reject, daily_equity, daily_loss_halt).
    """
    entry_block = entry_block or {}
    ev = []
    pos = state["positions"]

    # 1. pergantian hari WIB
    day = wib_day(now_ts)
    if state["day_key"] != day:
        eq = equity(state, market)
        state["day_key"] = day
        state["day_start_equity"] = eq
        state["halted_day"] = None
        ev.append({"type": "daily_equity", "day": day, "ts": now_ts, "bar": bar_t, "equity": eq,
                   "cash": state["cash"], "n_positions": len(pos)})

    # 2. jual
    for pair in sorted(list(pos.keys())):
        p = pos[pair]
        s = sigs.get(pair)
        want = (s is not None and s["sell"]) or p.get("pending_exit")
        if not want:
            continue
        reason = "death cross EMA%d/EMA%d" % (C.SLOW, C.FAST) if (s and s["sell"]) else "retry pending exit"
        fill, err = market.fill(pair, "sell", qty=p["qty"])
        if fill is None or fill["value"] < C.MIN_ORDER_IDR:
            p["pending_exit"] = True
            ev.append({"type": "reject", "ts": now_ts, "bar": bar_t, "pair": pair, "side": "sell",
                       "reason": err or "nilai jual < minimum order"})
            continue
        sig_price = s["close"] if s else None
        o = _order_record(state, fill, pair, bar_t, sig_price, now_ts, reason)
        ev.append(o)
        frac = fill["qty"] / p["qty"]
        entry_value = p["entry_value"] * frac
        entry_fee = p["entry_fee"] * frac
        net = fill["value"] - fill["fee"] - entry_value - entry_fee
        state["cash"] += fill["value"] - fill["fee"]
        state["trade_seq"] += 1
        ev.append({
            "type": "trade",
            "trade_id": state["trade_seq"],
            "pair": pair,
            "entry_bar": p["entry_bar"], "exit_bar": bar_t,
            "entry_ts": p["entry_ts"], "exit_ts": now_ts,
            "qty": fill["qty"],
            "entry_price": p["entry_price"], "exit_price": fill["avg_price"],
            "entry_mid": p["entry_mid"], "exit_mid": fill["mid"],
            "entry_value": entry_value, "exit_value": fill["value"],
            "fees": entry_fee + fill["fee"],
            "spread_cost": p["entry_spread"] * frac + o["spread_cost"],
            "slippage_cost": p["entry_slip"] * frac + o["slippage_cost"],
            "gross_pnl": fill["qty"] * (fill["mid"] - p["entry_mid"]),
            "net_pnl": net,
            "ret_pct": net / (entry_value + entry_fee) * 100.0,
            "hold_hours": (now_ts - p["entry_ts"]) / 3600.0,
        })
        if fill["partial"] and p["qty"] - fill["qty"] > 0:
            p["qty"] -= fill["qty"]
            p["entry_value"] -= entry_value
            p["entry_fee"] -= entry_fee
            p["entry_spread"] *= (1 - frac)
            p["entry_slip"] *= (1 - frac)
            p["pending_exit"] = True
        else:
            del pos[pair]

    # 3. daily loss limit
    eq = equity(state, market)
    if state["halted_day"] != day and state["day_start_equity"]:
        if eq <= state["day_start_equity"] * (1.0 - C.DAILY_LOSS_LIMIT):
            state["halted_day"] = day
            ev.append({"type": "daily_loss_halt", "ts": now_ts, "bar": bar_t, "day": day, "equity": eq,
                       "day_start_equity": state["day_start_equity"],
                       "loss_pct": (eq / state["day_start_equity"] - 1) * 100.0})

    # 4. beli
    cands = [(pair, s) for pair, s in sigs.items() if s is not None and s["buy"] and pair not in pos]
    cands.sort(key=lambda x: (-x[1]["adx"], x[0]))
    for pair, s in cands:
        reason = None
        if killswitch:
            reason = "kill switch aktif"
        elif state["halted_day"] == day:
            reason = "daily loss limit tercapai"
        elif entry_block.get(pair):
            reason = "data tidak valid: " + entry_block[pair]
        elif not s["window_ok"]:
            reason = "jendela indikator tidak lengkap / harga-volume nol"
        elif len(pos) >= C.MAX_POSITIONS:
            reason = "slot posisi penuh (%d)" % C.MAX_POSITIONS
        budget = 0.0
        if reason is None:
            eq = equity(state, market)
            budget = min(C.POSITION_PCT * eq, C.MAX_POSITION_PCT * eq, state["cash"], s["liq_cap_idr"])
            if budget < C.MIN_ORDER_IDR:
                reason = "ukuran order < minimum Rp%d" % C.MIN_ORDER_IDR
        if reason is None:
            fill, err = market.fill(pair, "buy", budget_idr=budget)
            if fill is None:
                reason = err
            elif fill["value"] < C.MIN_ORDER_IDR:
                reason = "nilai terisi < minimum order"
        if reason is not None:
            ev.append({"type": "reject", "ts": now_ts, "bar": bar_t, "pair": pair, "side": "buy", "reason": reason})
            continue
        o = _order_record(state, fill, pair, bar_t, s["close"], now_ts, "golden cross EMA%d/EMA%d + filter" % (C.FAST, C.SLOW))
        ev.append(o)
        state["cash"] -= fill["value"] + fill["fee"]
        pos[pair] = {
            "qty": fill["qty"],
            "entry_bar": bar_t,
            "entry_ts": now_ts,
            "entry_price": fill["avg_price"],
            "entry_mid": fill["mid"],
            "entry_value": fill["value"],
            "entry_fee": fill["fee"],
            "entry_spread": o["spread_cost"],
            "entry_slip": o["slippage_cost"],
            "last_mark": fill["best_bid"],
            "pending_exit": False,
        }
    return ev
