"""Eksekusi simulasi: walk order book, pembulatan harga/kuantitas, fee.

Dua "market":
  * LiveBookMarket  (bot)      -> beli di ask, jual di bid dari order book live,
                                   menghabiskan level berikutnya bila perlu (harga rata-rata).
  * ModelMarket     (backtest) -> open bar berikutnya +/- (setengah spread + slippage)
                                   hasil pengukuran snapshot (data/costs.json).
Keduanya dipanggil oleh engine yang sama (core/engine.py).
"""
import math

from . import config as C


def floor_step(x, step):
    if step <= 0:
        return x
    return math.floor(x / step + 1e-9) * step


def ceil_step(x, step):
    if step <= 0:
        return x
    return math.ceil(x / step - 1e-9) * step


def walk_book(levels, qty=None, value=None):
    """Habiskan level (harga terbaik dulu) sampai `qty` koin atau `value` IDR terpenuhi.

    levels: list of (price, amount). Kembalikan (qty_filled, cost_idr, levels_used).
    """
    rem_q = qty
    rem_v = value
    got_q = 0.0
    cost = 0.0
    used = 0
    for price, amount in levels:
        if price <= 0 or amount <= 0:
            continue
        if rem_q is not None:
            take = min(amount, rem_q)
        else:
            take = min(amount, rem_v / price)
        if take <= 0:
            break
        got_q += take
        cost += take * price
        used += 1
        if rem_q is not None:
            rem_q -= take
            if rem_q <= 1e-15:
                break
        else:
            rem_v -= take * price
            if rem_v <= 1e-9:
                break
    return got_q, cost, used


def parse_depth(depth, max_levels=150):
    bids = [(float(p), float(a)) for p, a in depth.get("buy", [])[:max_levels]]
    asks = [(float(p), float(a)) for p, a in depth.get("sell", [])[:max_levels]]
    bids.sort(key=lambda x: -x[0])
    asks.sort(key=lambda x: x[0])
    return bids, asks


def book_fill(bids, asks, side, qty_step, budget_idr=None, qty=None):
    """Isi order taker dari order book. Beli: budget IDR (termasuk fee). Jual: qty koin."""
    best_bid = bids[0][0] if bids else 0.0
    best_ask = asks[0][0] if asks else 0.0
    if side == "buy":
        value = budget_idr / (1.0 + C.FEE_BUY)
        q, _, _ = walk_book(asks, value=value)
        q = floor_step(q, qty_step)
        if q <= 0:
            return None
        q2, cost, used = walk_book(asks, qty=q)
        fee = cost * C.FEE_BUY
        partial = q2 + 1e-12 < q
        q = q2
    else:
        q2, cost, used = walk_book(bids, qty=qty)
        if q2 <= 0:
            return None
        fee = cost * C.FEE_SELL
        partial = q2 + 1e-12 < qty
        q = q2
    return {
        "side": side,
        "qty": q,
        "avg_price": cost / q,
        "value": cost,
        "fee": fee,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid": (best_bid + best_ask) / 2.0,
        "levels_used": used,
        "partial": partial,
    }


class LiveBookMarket:
    """Market untuk bot: order book live per pasangan (sudah diambil di awal tick)."""

    def __init__(self, books, meta):
        self.books = books          # pair -> (bids, asks) atau None bila tidak valid
        self.meta = meta            # pair -> {price_increment, quantity_increment}

    def mark(self, pair):
        b = self.books.get(pair)
        return b[0][0][0] if b and b[0] else None

    def quote(self, pair):
        b = self.books.get(pair)
        if not b or not b[0] or not b[1]:
            return None
        return b[0][0][0], b[1][0][0]

    def fill(self, pair, side, budget_idr=None, qty=None):
        b = self.books.get(pair)
        if not b or not b[0] or not b[1]:
            return None, "order book kosong/tidak valid"
        f = book_fill(b[0], b[1], side, self.meta[pair]["quantity_increment"], budget_idr, qty)
        if f is None:
            return None, "kuantitas 0 setelah pembulatan"
        return f, None


class ModelMarket:
    """Market untuk backtest: open bar eksekusi (t+1) +/- biaya terukur."""

    def __init__(self, meta, costs):
        self.meta = meta
        self.costs = costs        # pair -> {half_spread, slip_buy, slip_sell}
        self.ref = {}             # pair -> open bar eksekusi
        self.marks = {}           # pair -> close terakhir (untuk penilaian ekuitas)

    def set_prices(self, opens, closes):
        self.ref = opens
        self.marks = closes

    def _bid_ask(self, pair, px):
        k = self.costs[pair]
        tick = self.meta[pair]["price_increment"]
        return floor_step(px * (1 - k["half_spread"]), tick), ceil_step(px * (1 + k["half_spread"]), tick)

    def mark(self, pair):
        px = self.marks.get(pair)
        if px is None:
            return None
        return self._bid_ask(pair, px)[0]

    def quote(self, pair):
        px = self.marks.get(pair)
        return None if px is None else self._bid_ask(pair, px)

    def fill(self, pair, side, budget_idr=None, qty=None):
        px = self.ref.get(pair)
        if px is None or px <= 0:
            return None, "tidak ada bar eksekusi"
        k = self.costs[pair]
        tick = self.meta[pair]["price_increment"]
        step = self.meta[pair]["quantity_increment"]
        bid, ask = self._bid_ask(pair, px)
        if side == "buy":
            price = ceil_step(px * (1 + k["half_spread"] + k["slip_buy"]), tick)
            q = floor_step(budget_idr / (1.0 + C.FEE_BUY) / price, step)
            if q <= 0:
                return None, "kuantitas 0 setelah pembulatan"
            fee = q * price * C.FEE_BUY
        else:
            price = floor_step(px * (1 - k["half_spread"] - k["slip_sell"]), tick)
            q = qty
            fee = q * price * C.FEE_SELL
        return {
            "side": side, "qty": q, "avg_price": price, "value": q * price, "fee": fee,
            "best_bid": bid, "best_ask": ask, "mid": px, "levels_used": 0, "partial": False,
        }, None
