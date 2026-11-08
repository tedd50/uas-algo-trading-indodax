"""Metrik kinerja — satu implementasi dipakai backtest, dashboard Vercel, dan hitung_ulang."""

YEAR_S = 365.25 * 86400


def max_drawdown(curve):
    peak = None
    mdd = 0.0
    for _, v in curve:
        if peak is None or v > peak:
            peak = v
        if peak and peak > 0:
            mdd = min(mdd, v / peak - 1.0)
    return mdd


def total_return(curve, capital):
    if not curve:
        return 0.0
    return curve[-1][1] / capital - 1.0


def cagr(curve, capital, start_ts):
    if not curve:
        return None
    yrs = (curve[-1][0] - start_ts) / YEAR_S
    if yrs <= 0:
        return None
    end = curve[-1][1]
    return (end / capital) ** (1.0 / yrs) - 1.0 if end > 0 else -1.0


def trade_stats(trades):
    n = len(trades)
    wins = [t for t in trades if t["net_pnl"] > 0]
    losses = [t for t in trades if t["net_pnl"] <= 0]
    gp = sum(t["net_pnl"] for t in wins)
    gl = -sum(t["net_pnl"] for t in losses)
    fees = sum(t["fees"] for t in trades)
    spread = sum(t["spread_cost"] for t in trades)
    slip = sum(t["slippage_cost"] for t in trades)
    gross = sum(t["gross_pnl"] for t in trades)
    costs = fees + spread + slip
    return {
        "n_trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / n if n else None,
        "avg_win_idr": gp / len(wins) if wins else None,
        "avg_loss_idr": -gl / len(losses) if losses else None,
        "avg_win_pct": sum(t["ret_pct"] for t in wins) / len(wins) if wins else None,
        "avg_loss_pct": sum(t["ret_pct"] for t in losses) / len(losses) if losses else None,
        "profit_factor": (gp / gl) if gl > 0 else (None if gp == 0 else float("inf")),
        "net_pnl_closed": sum(t["net_pnl"] for t in trades),
        "gross_pnl": gross,
        "fees": fees,
        "spread_cost": spread,
        "slippage_cost": slip,
        "total_costs": costs,
        # porsi biaya = (fee + spread + slippage) / laba kotor (P&L mid-ke-mid sebelum biaya)
        "cost_share": costs / gross if gross > 0 else None,
        "avg_hold_hours": sum(t["hold_hours"] for t in trades) / n if n else None,
    }


def summarize(curve, capital, start_ts, trades, with_cagr=True):
    out = {
        "start_ts": start_ts,
        "end_ts": curve[-1][0] if curve else start_ts,
        "start_equity": capital,
        "end_equity": curve[-1][1] if curve else capital,
        "total_return": total_return(curve, capital),
        "max_drawdown": max_drawdown(curve),
    }
    if with_cagr:
        out["cagr"] = cagr(curve, capital, start_ts)
    out.update(trade_stats(trades))
    return out
