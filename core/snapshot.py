"""Snapshot order book & ukuran spread/slippage (dipakai collector, bot, estimate_costs, hitung_ulang)."""
from . import config as C
from .execution import parse_depth, walk_book

REF_ORDER_IDR = C.POSITION_PCT * C.INITIAL_CAPITAL   # ukuran order acuan untuk slippage (Rp15 juta)


def impact(bids, asks, ref_idr=REF_ORDER_IDR):
    """half_spread = (ask-bid)/mid/2 ; slip_buy = harga rata2 beli ref_idr / best_ask - 1 ;
    slip_sell = 1 - harga rata2 jual (setara ref_idr) / best_bid. Semua relatif (bukan %)."""
    if not bids or not asks:
        return None
    bb, ba = bids[0][0], asks[0][0]
    if bb <= 0 or ba <= 0:
        return None
    mid = (bb + ba) / 2.0
    q, cost, _ = walk_book(asks, value=ref_idr)
    depth_buy_ok = cost >= ref_idr * 0.999
    slip_buy = (cost / q) / ba - 1.0 if q > 0 else None
    q_sell = ref_idr / bb
    q2, proc, _ = walk_book(bids, qty=q_sell)
    depth_sell_ok = q2 >= q_sell * 0.999
    slip_sell = 1.0 - (proc / q2) / bb if q2 > 0 else None
    return {
        "best_bid": bb, "best_ask": ba, "mid": mid,
        "spread_pct": (ba - bb) / mid * 100.0,
        "half_spread": (ba - bb) / mid / 2.0,
        "slip_buy": slip_buy, "slip_sell": slip_sell,
        "depth_ok": depth_buy_ok and depth_sell_ok,
    }


def make_snapshot(pair, depth_raw, ts, source):
    """Snapshot mentah (seluruh level yang dikirim API) + ringkasan."""
    bids, asks = parse_depth(depth_raw)
    rec = {"ts": ts, "pair": pair, "source": source,
           "bids": [[p, a] for p, a in bids], "asks": [[p, a] for p, a in asks]}
    m = impact(bids, asks)
    if m:
        rec.update({k: m[k] for k in ("best_bid", "best_ask", "spread_pct", "half_spread", "slip_buy", "slip_sell", "depth_ok")})
    return rec


def summary_only(snap):
    return {k: v for k, v in snap.items() if k not in ("bids", "asks")}
