"""Satu panggilan bot (/api/tick): baca state -> ambil data -> validasi -> sinyal -> eksekusi simulasi -> simpan.

Idempotency: candle diidentifikasi dengan waktu bukanya. state.last_bar menyimpan candle
terakhir yang sudah diproses; ditambah kunci `lock:<bar>` (SET NX EX) sehingga dua
panggilan bersamaan untuk candle yang sama tidak bisa sama-sama membeli.
"""
import json
import os
import time
import traceback
import uuid

from . import config as C
from .engine import new_state, step, equity
from .execution import LiveBookMarket, parse_depth
from .indodax import Client, ApiError
from .snapshot import make_snapshot, summary_only
from .store import LOG_NAMES, key, log_key
from .strategy import compute_signals, closed_bars

MAX_CATCHUP_BARS = 48


def killswitch_on(store):
    env = os.environ.get("KILL_SWITCH", "").strip().lower() in ("1", "true", "on", "yes")
    flag = (store.get(key("killswitch")) or "0").strip() == "1"
    return env or flag, {"env": env, "storage": flag}


def tick(store, client=None, trigger="unknown", now_fn=time.time):
    call_id = uuid.uuid4().hex[:12]
    t_start = now_fn()
    buf = {n: [] for n in LOG_NAMES}

    def log(name, rec):
        rec = dict(rec)
        rec.setdefault("call_id", call_id)
        buf[name].append(rec)

    client = client or Client(timeout=10.0, retries=3)
    client.log = lambda e: log("errors", dict(e, ts=int(now_fn())))
    call = {"type": "call", "call_id": call_id, "trigger": trigger, "ts_start": int(t_start),
            "status": "started", "bars_processed": [], "late_bars": []}
    state = None
    save_state = False
    lock_key = None
    try:
        server = client.server_time()
        call["server_time"] = server
        last_closed = (server // C.TF_SECONDS) * C.TF_SECONDS - C.TF_SECONDS
        call["last_closed_bar"] = last_closed

        raw = store.get(key("state"))
        if raw:
            state = json.loads(raw)
        else:
            state = new_state()
            log("events", {"type": "init", "ts": int(now_fn()), "capital": C.INITIAL_CAPITAL})
            save_state = True

        kill, kill_src = killswitch_on(store)
        call["killswitch"] = kill
        if kill != state.get("kill_last", False):
            log("events", {"type": "killswitch_" + ("on" if kill else "off"), "ts": int(now_fn()), "source": kill_src})
            state["kill_last"] = kill
            save_state = True
        if kill:
            log("events", {"type": "killswitch_active", "ts": int(now_fn()), "source": kill_src,
                           "effect": "entry baru diblokir; exit tetap diproses"})

        if state.get("last_bar") is not None and state["last_bar"] >= last_closed:
            call["status"] = "already_processed"
            return call
        lock_key = key("lock:%d" % last_closed)
        if not store.set_nx(lock_key, call_id, 900):
            lock_key = None
            call["status"] = "duplicate_locked"
            log("events", {"type": "duplicate_call", "ts": int(now_fn()), "bar": last_closed})
            return call

        universe = C.load_universe()
        meta = {u["pair"]: u for u in universe}
        pairs = [u["pair"] for u in universe]
        snap_pairs = pairs + ([C.BENCHMARK_PAIR] if C.BENCHMARK_PAIR not in pairs else [])

        # ---- data candle + validasi
        sigmap = {}
        entry_block = {}
        for pair in pairs:
            try:
                cs = client.history_back(meta[pair]["symbol"], C.TIMEFRAME,
                                         server - (C.BOT_HISTORY_PAGES * 660) * C.TF_SECONDS, server,
                                         max_pages=C.BOT_HISTORY_PAGES)
            except ApiError as e:
                entry_block[pair] = "candle gagal diambil"
                log("events", {"type": "validation", "ts": int(now_fn()), "pair": pair, "reason": "candle gagal diambil: %s" % e})
                sigmap[pair] = {}
                continue
            cs = closed_bars(cs, server)
            reasons = []
            if not cs:
                reasons.append("tidak ada candle tertutup")
            else:
                age = server - (cs[-1]["t"] + C.TF_SECONDS)
                if age > C.MAX_STALE_BARS * C.TF_SECONDS:
                    reasons.append("candle tertutup terakhir terlalu tua (%d detik)" % age)
                last = cs[-1]
                if min(last["o"], last["h"], last["l"], last["c"]) <= 0 or last["v"] <= 0:
                    reasons.append("harga/volume nol pada candle terakhir")
            rows = compute_signals(cs)
            sigmap[pair] = {r["t"]: r for r in rows}
            if rows and not rows[-1]["window_ok"]:
                reasons.append("ada candle hilang / nol di jendela indikator %d bar" % C.VALID_WINDOW)
            if reasons:
                entry_block[pair] = "; ".join(reasons)
                log("events", {"type": "validation", "ts": int(now_fn()), "pair": pair, "reason": entry_block[pair]})

        # ---- order book + snapshot
        books = {}
        bench_quote = None
        for pair in snap_pairs:
            try:
                d = client.depth(pair)
            except ApiError as e:
                if pair in meta:
                    entry_block[pair] = (entry_block.get(pair, "") + "; order book gagal diambil").strip("; ")
                    log("events", {"type": "validation", "ts": int(now_fn()), "pair": pair, "reason": "order book gagal: %s" % e})
                continue
            snap = make_snapshot(pair, d, int(now_fn()), "bot")
            log("snapshots", snap)
            log("spreads", summary_only(snap))
            bids, asks = parse_depth(d)
            if pair == C.BENCHMARK_PAIR and bids and asks:
                bench_quote = (bids[0][0], asks[0][0])
            if pair not in meta:
                continue
            reason = None
            if not bids or not asks:
                reason = "order book kosong"
            else:
                mid = (bids[0][0] + asks[0][0]) / 2.0
                spr = (asks[0][0] - bids[0][0]) / mid
                if spr > C.MAX_SPREAD:
                    reason = "spread bid-ask %.2f%% > %.0f%%" % (spr * 100, C.MAX_SPREAD * 100)
            books[pair] = (bids, asks) if (bids and asks) else None
            if reason:
                entry_block[pair] = (entry_block.get(pair, "") + "; " + reason).strip("; ")
                log("events", {"type": "validation", "ts": int(now_fn()), "pair": pair, "reason": reason})
        market = LiveBookMarket(books, meta)

        # ---- candle yang harus diproses (termasuk yang terlewat)
        if state.get("last_bar") is None:
            todo = [last_closed]
        else:
            todo = list(range(state["last_bar"] + C.TF_SECONDS, last_closed + 1, C.TF_SECONDS))
            if len(todo) > MAX_CATCHUP_BARS:
                log("events", {"type": "catchup_truncated", "ts": int(now_fn()), "skipped": len(todo) - MAX_CATCHUP_BARS})
                todo = todo[-MAX_CATCHUP_BARS:]
        for bt in todo:
            now = int(now_fn())
            late = now >= bt + 2 * C.TF_SECONDS
            sigs = {}
            for pair in pairs:
                r = sigmap.get(pair, {}).get(bt)
                sigs[pair] = r
                if r is None:
                    log("events", {"type": "validation", "ts": now, "pair": pair, "bar": bt, "reason": "candle hilang untuk bar ini"})
                    continue
                log("signals", {"bar": bt, "pair": pair, "close": r["close"], "ema_fast": r["ema_fast"],
                                "ema_slow": r["ema_slow"], "ema_trend": r["ema_trend"], "adx": r["adx"],
                                "buy": r["buy"], "sell": r["sell"], "window_ok": r["window_ok"],
                                "liq_cap_idr": r["liq_cap_idr"], "processed_at": now, "late": late})
            ev = step(state, bt, sigs, market, now, killswitch=kill, entry_block=entry_block)
            for e in ev:
                name = {"order": "orders", "trade": "trades", "daily_equity": "daily_equity"}.get(e["type"], "events")
                log(name, e)
            state["last_bar"] = bt
            call["bars_processed"].append(bt)
            if late:
                call["late_bars"].append(bt)

        eq = equity(state, market)
        pos_val = eq - state["cash"]
        log("equity", {"ts": int(now_fn()), "bar": last_closed, "equity": eq, "cash": state["cash"],
                       "positions_value": pos_val, "n_positions": len(state["positions"]),
                       "positions": {p: {"qty": v["qty"], "mark_bid": v.get("last_mark")} for p, v in state["positions"].items()},
                       "btc_bid": bench_quote[0] if bench_quote else None,
                       "btc_ask": bench_quote[1] if bench_quote else None})
        call["equity"] = eq
        call["status"] = "ok"
        save_state = True
    except Exception as e:  # noqa: BLE001
        call["status"] = "error"
        call["error"] = "%s: %s" % (type(e).__name__, e)
        log("errors", {"type": "tick_exception", "ts": int(now_fn()), "error": call["error"],
                       "trace": traceback.format_exc()[-2000:]})
        save_state = False
        if lock_key:
            try:
                store.delete(lock_key)   # izinkan panggilan berikutnya mencoba lagi
            except Exception:  # noqa: BLE001
                pass
    finally:
        call["ts_end"] = int(now_fn())
        call["duration_s"] = round(now_fn() - t_start, 3)
        call["n_requests"] = client.n_requests
        call["n_api_errors"] = client.n_errors
        log("calls", call)
        cmds = []
        if save_state and state is not None:
            cmds.append(["SET", key("state"), json.dumps(state)])
        for name, rows in buf.items():
            if rows:
                cmds.append(["RPUSH", log_key(name)] + [json.dumps(r) for r in rows])
        try:
            store.pipeline(cmds)
        except Exception as e:  # noqa: BLE001
            call["status"] = "error"
            call["error"] = "gagal simpan ke storage: %s" % e
    return call
