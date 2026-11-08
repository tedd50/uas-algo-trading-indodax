"""Fungsi sinyal BERSAMA untuk backtest dan bot.

Satu-satunya pintu masuk: `compute_signals(candles)`. Backtest memanggilnya dengan
riwayat 3 tahun; bot memanggilnya dengan ~1.900 bar terakhir. Kode identik.

candles: list of dict {t (detik UTC, waktu buka bar), o, h, l, c, v (volume base)}
          terurut naik, hanya bar yang SUDAH tertutup.

Aturan (dihitung pada close bar t):
  BUY  = Cross(EMA_fast, EMA_slow) AND Close > EMA_trend AND ADX > MIN_ADX
  SELL = Cross(EMA_slow, EMA_fast)              (death cross, tanpa filter ADX)
  Cross(a,b) = a[t] > b[t] AND a[t-1] <= b[t-1]
Entry hanya boleh bila `window_ok` (jendela indikator lengkap & harga/volume > 0).
"""
from . import config as C


def ema(values, n):
    """EMA dengan alpha = 2/(n+1), seed = nilai pertama (sama dengan pandas ewm(span=n, adjust=False))."""
    a = 2.0 / (n + 1.0)
    out = []
    prev = None
    for x in values:
        prev = x if prev is None else prev + a * (x - prev)
        out.append(prev)
    return out


def wilder(values, n):
    """Smoothing Wilder = EMA alpha 1/n, seed nilai pertama (ewm(alpha=1/n, adjust=False))."""
    a = 1.0 / n
    out = []
    prev = None
    for x in values:
        prev = x if prev is None else prev + a * (x - prev)
        out.append(prev)
    return out


def adx(highs, lows, closes, n):
    m = len(closes)
    tr = [0.0] * m
    pdm = [0.0] * m
    ndm = [0.0] * m
    for i in range(m):
        if i == 0:
            tr[i] = highs[i] - lows[i]
            continue
        up = highs[i] - highs[i - 1]
        dn = lows[i - 1] - lows[i]
        pdm[i] = up if (up > dn and up > 0) else 0.0
        ndm[i] = dn if (dn > up and dn > 0) else 0.0
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    s_tr = wilder(tr, n)
    s_p = wilder(pdm, n)
    s_n = wilder(ndm, n)
    dx = []
    for i in range(m):
        if s_tr[i] <= 0:
            dx.append(0.0)
            continue
        pdi = 100.0 * s_p[i] / s_tr[i]
        ndi = 100.0 * s_n[i] / s_tr[i]
        tot = pdi + ndi
        dx.append(0.0 if tot <= 0 else 100.0 * abs(pdi - ndi) / tot)
    return wilder(dx, n)


def compute_signals(candles):
    """Kembalikan list baris sinyal, satu per candle (indeks sama dengan input)."""
    n = len(candles)
    if n == 0:
        return []
    t = [b["t"] for b in candles]
    o = [float(b["o"]) for b in candles]
    h = [float(b["h"]) for b in candles]
    l = [float(b["l"]) for b in candles]
    c = [float(b["c"]) for b in candles]
    v = [float(b["v"]) for b in candles]
    ef = ema(c, C.FAST)
    es = ema(c, C.SLOW)
    et = ema(c, C.TREND)
    ax = adx(h, l, c, C.ADX_N)

    # jumlah bar berturut-turut ke belakang yang kontigu & valid (untuk window_ok)
    run = [0] * n
    for i in range(n):
        good = o[i] > 0 and h[i] > 0 and l[i] > 0 and c[i] > 0 and v[i] > 0
        if not good:
            run[i] = 0
        elif i > 0 and t[i] - t[i - 1] == C.TF_SECONDS:
            run[i] = run[i - 1] + 1
        else:
            run[i] = 1

    turnover = [c[i] * v[i] for i in range(n)]
    out = []
    acc = 0.0
    for i in range(n):
        acc += turnover[i]
        if i >= C.LIQ_LOOKBACK:
            acc -= turnover[i - C.LIQ_LOOKBACK]
        if i == 0:
            buy = sell = False
        else:
            cross_up = ef[i] > es[i] and ef[i - 1] <= es[i - 1]
            cross_dn = es[i] > ef[i] and es[i - 1] <= ef[i - 1]
            buy = cross_up and c[i] > et[i] and ax[i] > C.MIN_ADX
            sell = cross_dn
        window_ok = run[i] >= C.VALID_WINDOW and i >= C.TREND
        out.append({
            "t": t[i],
            "close": c[i],
            "ema_fast": ef[i],
            "ema_slow": es[i],
            "ema_trend": et[i],
            "adx": ax[i],
            "buy": bool(buy),
            "sell": bool(sell),
            "window_ok": bool(window_ok),
            "liq_cap_idr": C.LIQ_CAP_PCT * acc if i >= C.LIQ_LOOKBACK - 1 else 0.0,
        })
    return out


def closed_bars(candles, server_time_s):
    """Buang bar yang belum tertutup: Time + durasi timeframe > server_time."""
    return [b for b in candles if b["t"] + C.TF_SECONDS <= server_time_s]
