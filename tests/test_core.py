"""Uji unit (offline, tanpa internet):  python3 -m unittest discover -s tests -v"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import config as C  # noqa: E402
from core import engine  # noqa: E402
from core.bot import tick  # noqa: E402
from core.execution import book_fill, walk_book, ceil_step, floor_step  # noqa: E402
from core.store import LocalStore, log_key, key  # noqa: E402
from core.strategy import compute_signals, ema, closed_bars  # noqa: E402


def synth(n, start=1_700_000_000 // 3600 * 3600, base=1000.0):
    """Deret harga deterministik (naik-turun) untuk uji, BUKAN untuk backtest."""
    import math
    out = []
    for i in range(n):
        c = base * (1 + 0.3 * math.sin(i / 25.0) + 0.002 * i)
        out.append({"t": start + i * 3600, "o": c * 0.999, "h": c * 1.004, "l": c * 0.996, "c": c, "v": 10.0})
    return out


class TestStrategy(unittest.TestCase):
    def test_ema_matches_definition(self):
        e = ema([1, 2, 3], 3)  # alpha 0.5
        self.assertEqual(e, [1, 1.5, 2.25])

    def test_window_independence(self):
        """Bot memakai ~1.900 bar terakhir, backtest memakai riwayat penuh: sinyal harus identik."""
        full = synth(6000)
        a = {r["t"]: r for r in compute_signals(full)}
        b = {r["t"]: r for r in compute_signals(full[-1950:])}
        for t in list(b)[-300:]:
            self.assertEqual((a[t]["buy"], a[t]["sell"]), (b[t]["buy"], b[t]["sell"]))
            self.assertAlmostEqual(a[t]["ema_trend"] / b[t]["ema_trend"], 1.0, places=7)
        self.assertTrue(any(r["buy"] for r in a.values()) and any(r["sell"] for r in a.values()))

    def test_gap_blocks_entry(self):
        cs = synth(400)
        del cs[350]
        rows = compute_signals(cs)
        self.assertFalse(rows[360]["window_ok"])
        self.assertTrue(rows[-1]["window_ok"] is False or len(cs) - 350 >= C.VALID_WINDOW)

    def test_closed_bars(self):
        cs = synth(3)
        self.assertEqual(len(closed_bars(cs, cs[-1]["t"] + 3599)), 2)
        self.assertEqual(len(closed_bars(cs, cs[-1]["t"] + 3600)), 3)


class TestExecution(unittest.TestCase):
    def test_walk_book_vwap(self):
        asks = [(100.0, 1.0), (101.0, 2.0)]
        q, cost, used = walk_book(asks, value=201.0)
        self.assertAlmostEqual(q, 2.0)
        self.assertAlmostEqual(cost, 201.0)
        self.assertEqual(used, 2)

    def test_buy_at_ask_sell_at_bid(self):
        bids, asks = [(99.0, 5.0), (98.0, 5.0)], [(100.0, 1.0), (102.0, 5.0)]
        f = book_fill(bids, asks, "buy", 1e-8, budget_idr=300.0)
        self.assertGreater(f["avg_price"], 100.0)   # level kedua ikut terpakai
        self.assertAlmostEqual(f["fee"], f["value"] * C.FEE_BUY)
        self.assertLessEqual(f["value"] + f["fee"], 300.0 + 1e-9)
        s = book_fill(bids, asks, "sell", 1e-8, qty=7.0)
        self.assertAlmostEqual(s["avg_price"], (99 * 5 + 98 * 2) / 7)
        self.assertAlmostEqual(s["fee"], s["value"] * C.FEE_SELL)

    def test_rounding(self):
        self.assertEqual(ceil_step(1001.2, 1000), 2000)
        self.assertEqual(floor_step(0.123456789, 1e-8), 0.12345678)


class TestRisk(unittest.TestCase):
    class Mkt:
        def __init__(self, px):
            self.px = px

        def mark(self, pair):
            return self.px

        def quote(self, pair):
            return self.px, self.px

        def fill(self, pair, side, budget_idr=None, qty=None):
            if side == "buy":
                q = budget_idr / (1 + C.FEE_BUY) / self.px
            else:
                q = qty
            return {"side": side, "qty": q, "avg_price": self.px, "value": q * self.px,
                    "fee": q * self.px * (C.FEE_BUY if side == "buy" else C.FEE_SELL),
                    "best_bid": self.px, "best_ask": self.px, "mid": self.px, "levels_used": 1, "partial": False}, None

    def sig(self, buy=False, sell=False, adx=30):
        return {"close": 100.0, "buy": buy, "sell": sell, "adx": adx, "window_ok": True, "liq_cap_idr": 1e12}

    def test_max_positions_and_size(self):
        st = engine.new_state()
        sigs = {"p%d" % i: self.sig(buy=True, adx=20 + i) for i in range(8)}
        ev = engine.step(st, 0, sigs, self.Mkt(100.0), 1_800_000_000)
        self.assertEqual(len(st["positions"]), C.MAX_POSITIONS)
        self.assertIn("p7", st["positions"])           # ADX tertinggi diprioritaskan
        for p in st["positions"].values():
            self.assertLessEqual(p["entry_value"] + p["entry_fee"], C.MAX_POSITION_PCT * C.INITIAL_CAPITAL + 1e-6)
        self.assertTrue(any(e["type"] == "reject" and "slot" in e["reason"] for e in ev))

    def test_killswitch_and_daily_loss(self):
        st = engine.new_state()
        ev = engine.step(st, 0, {"a": self.sig(buy=True)}, self.Mkt(100.0), 1_800_000_000, killswitch=True)
        self.assertEqual(st["positions"], {})
        self.assertTrue(any(e.get("reason") == "kill switch aktif" for e in ev))
        engine.step(st, 3600, {"a": self.sig(buy=True)}, self.Mkt(100.0), 1_800_000_000 + 60)
        self.assertIn("a", st["positions"])
        # harga jatuh 50% -> ekuitas turun > 3% -> entry baru diblokir hari itu
        ev = engine.step(st, 7200, {"b": self.sig(buy=True)}, self.Mkt(50.0), 1_800_000_000 + 120)
        self.assertNotIn("b", st["positions"])
        self.assertTrue(any(e["type"] == "daily_loss_halt" for e in ev))

    def test_wib_day_boundary(self):
        # 16:59:59 UTC masih hari sebelumnya di WIB; 17:00:00 UTC = 00.00 WIB hari berikutnya
        import calendar
        t = calendar.timegm((2026, 11, 5, 16, 59, 59))
        self.assertEqual(engine.wib_day(t), "2026-11-05")
        self.assertEqual(engine.wib_day(t + 1), "2026-11-06")


class FakeClient:
    """Klien palsu untuk uji idempotency (data sintetis, tanpa jaringan)."""

    def __init__(self, server):
        self.server = server
        self.n_requests = 0
        self.n_errors = 0
        self.log = None

    def server_time(self):
        return self.server

    def history_back(self, symbol, tf, start, to, max_pages=None, page_log=None):
        n = 2000
        first = (to // 3600) * 3600 - (n - 1) * 3600
        cs = synth(n, start=first)
        return [b for b in cs if b["t"] <= to]

    def depth(self, pair):
        return {"buy": [["99", "1000"]], "sell": [["100", "1000"]]}


class TestBot(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.st = LocalStore(self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_idempotent_same_candle(self):
        srv = 1_800_000_000 // 3600 * 3600 + 7 * 60
        r1 = tick(self.st, FakeClient(srv), trigger="t1")
        r2 = tick(self.st, FakeClient(srv + 60), trigger="t2")
        self.assertEqual(r1["status"], "ok")
        self.assertEqual(r2["status"], "already_processed")
        calls = [json.loads(x) for x in self.st.lrange(log_key("calls"))]
        self.assertEqual(len(calls), 2)

    def test_lock_blocks_concurrent(self):
        srv = 1_800_000_000 // 3600 * 3600 + 7 * 60
        bar = (srv // 3600) * 3600 - 3600
        self.st.set_nx(key("lock:%d" % bar), "other", 900)
        r = tick(self.st, FakeClient(srv), trigger="t")
        self.assertEqual(r["status"], "duplicate_locked")

    def test_catchup_marks_late(self):
        srv = 1_800_000_000 // 3600 * 3600 + 7 * 60
        tick(self.st, FakeClient(srv), trigger="t", now_fn=lambda: srv)
        later = srv + 3 * 3600
        r = tick(self.st, FakeClient(later), trigger="t", now_fn=lambda: later)
        self.assertEqual(len(r["bars_processed"]), 3)
        self.assertEqual(len(r["late_bars"]), 2)

    def test_killswitch_logged(self):
        self.st.set(key("killswitch"), "1")
        srv = 1_800_000_000 // 3600 * 3600 + 7 * 60
        tick(self.st, FakeClient(srv), trigger="t")
        evs = [json.loads(x)["type"] for x in self.st.lrange(log_key("events"))]
        self.assertIn("killswitch_on", evs)
        self.assertIn("killswitch_active", evs)


if __name__ == "__main__":
    unittest.main()
