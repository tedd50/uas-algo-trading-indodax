"""Render dashboard HTML mandiri (tanpa CDN/internet) dari hasil analisis.

Semua angka berasal dari argumen `R` yang dihitung oleh core.analysis + backtest_summary
— tidak ada angka hasil yang ditulis tangan di file ini.
"""
import datetime as dt
import html
import json
import math

from . import config as C


def esc(x):
    return html.escape(str(x))


def iso(t, fmt="%Y-%m-%d %H:%M"):
    return dt.datetime.utcfromtimestamp(int(t)).strftime(fmt) if t is not None else "-"


def wib(t):
    return iso(int(t) + C.WIB_OFFSET) + " WIB" if t is not None else "-"


def pct(x, d=2):
    return "-" if x is None else ("%+.*f%%" % (d, x * 100))


def pcu(x, d=1):
    return "-" if x is None else ("%.*f%%" % (d, x * 100))


def pctv(x, d=3):
    return "-" if x is None else ("%.*f%%" % (d, x))


def num(x, d=2):
    if x is None:
        return "-"
    if isinstance(x, float) and math.isinf(x):
        return "∞"
    return "%.*f" % (d, x)


def idr(x):
    return "-" if x is None else "Rp" + "{:,.0f}".format(x).replace(",", ".")


def line_chart(series, title, height=260, log=False):
    """series: list of (label, color_var, [(ts, value), ...])."""
    pts = [p for _, _, s in series for p in s if p[1] is not None and p[1] > 0]
    if len(pts) < 2:
        return '<div class="empty">%s: belum ada data</div>' % esc(title)
    W, H, L, R, T, B = 900, height, 70, 10, 10, 26
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    f = (lambda v: math.log10(v)) if log else (lambda v: v)
    y0, y1 = min(f(p[1]) for p in pts), max(f(p[1]) for p in pts)
    if y1 == y0:
        y1 = y0 + 1
    pad = (y1 - y0) * 0.05
    y0, y1 = y0 - pad, y1 + pad
    if x1 == x0:
        x1 = x0 + 1

    def X(t):
        return L + (t - x0) / (x1 - x0) * (W - L - R)

    def Y(v):
        return T + (1 - (f(v) - y0) / (y1 - y0)) * (H - T - B)
    out = ['<svg viewBox="0 0 %d %d" class="chart" role="img" aria-label="%s">' % (W, H, esc(title))]
    for i in range(5):
        yv = y0 + (y1 - y0) * i / 4
        v = 10 ** yv if log else yv
        yy = Y(v)
        out.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" class="grid"/>' % (L, W - R, yy, yy))
        lab = ("%.0fjt" % (v / 1e6)) if abs(v) >= 1e6 else ("%.3g" % v)
        out.append('<text x="%d" y="%.1f" class="ax" text-anchor="end">%s</text>' % (L - 6, yy + 4, lab))
    for i in range(6):
        t = x0 + (x1 - x0) * i / 5
        out.append('<text x="%.1f" y="%d" class="ax" text-anchor="middle">%s</text>' % (
            X(t), H - 6, iso(t, "%d %b %y" if x1 - x0 > 20 * 86400 else "%d %b %H:%M")))
    for label, color, s in series:
        s = [p for p in s if p[1] is not None and p[1] > 0]
        if len(s) < 2:
            continue
        step = max(1, len(s) // 1500)
        s2 = s[::step] + ([s[-1]] if (len(s) - 1) % step else [])
        d = "M" + " L".join("%.1f,%.1f" % (X(t), Y(v)) for t, v in s2)
        out.append('<path d="%s" fill="none" stroke="var(%s)" stroke-width="1.8"/>' % (d, color))
    out.append("</svg>")
    leg = "".join('<span class="lg"><i style="background:var(%s)"></i>%s</span>' % (c, esc(lbl)) for lbl, c, _ in series)
    return '<figure><figcaption>%s</figcaption>%s<div class="legend">%s</div></figure>' % (esc(title), "".join(out), leg)


def kv_table(rows):
    return '<table class="kv">' + "".join("<tr><th>%s</th><td>%s</td></tr>" % (esc(k), v) for k, v in rows) + "</table>"


def table(headers, rows, cls=""):
    h = "".join("<th>%s</th>" % esc(x) for x in headers)
    b = "".join("<tr>" + "".join("<td>%s</td>" % c for c in r) + "</tr>" for r in rows)
    return '<div class="tw"><table class="%s"><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>' % (cls, h, b or '<tr><td colspan="%d" class="empty">tidak ada</td></tr>' % len(headers))


def card(label, value, sub=""):
    return '<div class="card"><div class="lbl">%s</div><div class="val">%s</div><div class="sub">%s</div></div>' % (esc(label), value, sub)


CSS = """
:root{--bg:#f6f7f9;--fg:#15181d;--mut:#5d6675;--card:#fff;--bd:#dde1e7;--s1:#2563eb;--s2:#d97706;--s3:#059669;--neg:#dc2626;--pos:#059669}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#0e1117;--fg:#e6e9ef;--mut:#9aa4b2;--card:#161b22;--bd:#2a313c;--s1:#60a5fa;--s2:#fbbf24;--s3:#34d399;--neg:#f87171;--pos:#34d399}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;font-variant-numeric:tabular-nums}
main{max-width:1180px;margin:0 auto;padding:20px 16px 60px}h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:32px 0 10px;border-bottom:1px solid var(--bd);padding-bottom:6px}
h3{font-size:13px;color:var(--mut);text-transform:uppercase;letter-spacing:.05em;margin:16px 0 8px}.mut{color:var(--mut)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px}.card{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:10px 12px}
.lbl{font-size:12px;color:var(--mut)}.val{font-size:20px;font-weight:600}.sub{font-size:11px;color:var(--mut)}
.tw{overflow-x:auto;background:var(--card);border:1px solid var(--bd);border-radius:10px}table{border-collapse:collapse;width:100%;font-size:12.5px}
th,td{padding:5px 8px;border-bottom:1px solid var(--bd);text-align:left;white-space:nowrap}thead th{background:var(--bg);position:sticky;top:0}
table.kv{background:var(--card);border:1px solid var(--bd);border-radius:10px}table.kv th{width:45%;color:var(--mut);font-weight:500;white-space:normal}table.kv td{white-space:normal}
figure{margin:10px 0;background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:10px}figcaption{font-weight:600;margin-bottom:4px}
.chart{width:100%;height:auto}.chart .grid{stroke:var(--bd);stroke-width:1}.chart .ax{fill:var(--mut);font-size:11px}
.legend{font-size:12px;color:var(--mut)}.lg{margin-right:14px}.lg i{display:inline-block;width:12px;height:3px;margin-right:5px;vertical-align:middle}
.pos{color:var(--pos)}.neg{color:var(--neg)}.empty{color:var(--mut);padding:10px}.two{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:760px){.two{grid-template-columns:1fr}}pre{white-space:pre-wrap;background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:12px;font:13px/1.55 system-ui,sans-serif}
.badge{display:inline-block;border:1px solid var(--bd);border-radius:99px;padding:1px 9px;font-size:12px;margin-right:6px}
"""


def render(R):
    bt = R["backtest"]
    bm = bt["metrics"]
    bb = bt["benchmark_btc_bh"]
    fw = R.get("forward")
    gap = R.get("gap")
    ops = R.get("ops")
    p = []
    p.append("<h1>Bot Dry Run Indodax — Backtest vs Forward Test</h1>")
    p.append('<div class="mut">%s · universe: %s · timeframe 1 jam · dibuat %s · sumber: %s</div>' % (
        esc(C.STRATEGY_NAME), esc(", ".join(bt["universe"])), esc(R["generated"]), esc(R["source"])))
    fz = R.get("freeze") or {}
    p.append('<div style="margin-top:8px"><span class="badge">Freeze: %s</span><span class="badge">Commit: %s</span><span class="badge">Forward: %s → %s</span></div>' % (
        esc(fz.get("freeze_utc") or "belum dibekukan"), esc(fz.get("commit") or "-"),
        esc(wib(fz["start_ts"]) if fz.get("start_ts") else "-"), esc(wib(fz["end_ts"]) if fz.get("end_ts") else "-")))

    # ---- KPI backtest
    p.append("<h2>Backtest (%s → %s, %.2f tahun, data historis asli Indodax)</h2>" % (bt["period"]["start"], bt["period"]["end"], bt["period"]["years"]))
    p.append('<div class="grid">' + "".join([
        card("Return total", pct(bm["total_return"])), card("CAGR", pct(bm["cagr"])), card("Max drawdown", pct(bm["max_drawdown"])),
        card("Profit factor", num(bm["profit_factor"])), card("Win rate", pcu(bm["win_rate"])), card("Jumlah trade", str(bm["n_trades"])),
        card("Rata-rata untung/trade", idr(bm["avg_win_idr"]), pctv(bm["avg_win_pct"], 2)),
        card("Rata-rata rugi/trade", idr(bm["avg_loss_idr"]), pctv(bm["avg_loss_pct"], 2)),
        card("Porsi biaya", pcu(bm["cost_share"]), "(fee+spread+slippage) ÷ laba kotor"),
        card("BTC/IDR buy & hold", pct(bb["total_return"]), "CAGR %s · MDD %s" % (pct(bb["cagr"]), pct(bb["max_drawdown"]))),
    ]) + "</div>")
    p.append(line_chart([("Strategi", "--s1", bt["curve_daily"]), ("BTC/IDR buy & hold", "--s2", bt["bench_curve_daily"])],
                        "Ekuitas backtest (skala log)", log=True))
    ar = bt.get("annual_returns", {})
    p.append("<h3>Return per tahun kalender</h3>" + table(["Tahun"] + list(ar), [["Return"] + [pct(v) for v in ar.values()]]))
    p.append("<h3>Biaya backtest</h3>" + kv_table([
        ("Fee", idr(bm["fees"])), ("Spread", idr(bm["spread_cost"])), ("Slippage (+ pembulatan tick)", idr(bm["slippage_cost"])),
        ("Laba kotor (mid-ke-mid, trade tertutup)", idr(bm["gross_pnl"])), ("Laba bersih trade tertutup", idr(bm["net_pnl_closed"])),
        ("Sinyal beli yang ditolak (per alasan)", "<br>".join("%s: %d" % (esc(k), v) for k, v in bt.get("rejects_by_reason", {}).items()) or "-"),
        ("Daily loss limit terpicu", str(bt.get("daily_loss_halts"))),
    ]))

    # ---- KPI forward
    p.append("<h2>Forward test (dry run live di Vercel)</h2>")
    if not fw:
        p.append('<div class="empty">Belum ada log forward test.</div>')
    else:
        fm = fw["metrics"]
        fb = fw.get("bench") or {}
        p.append('<div class="grid">' + "".join([
            card("Return total", pct(fm["total_return"]), "ekuitas %s" % idr(fm["end_equity"])), card("Max drawdown", pct(fm["max_drawdown"])),
            card("Profit factor", num(fm["profit_factor"])), card("Win rate", pcu(fm["win_rate"])), card("Jumlah trade (tertutup)", str(fm["n_trades"])),
            card("Rata-rata untung/trade", idr(fm["avg_win_idr"]), pctv(fm["avg_win_pct"], 2)),
            card("Rata-rata rugi/trade", idr(fm["avg_loss_idr"]), pctv(fm["avg_loss_pct"], 2)),
            card("Porsi biaya", pcu(fm["cost_share"]), "(fee+spread+slippage) ÷ laba kotor"),
            card("Posisi terbuka", str(fm["n_open_positions"]), "nilai di best bid %s" % idr(fm["unrealized_value"])),
            card("BTC/IDR buy & hold", pct(fb.get("total_return")), "MDD %s" % pct(fb.get("max_drawdown"))),
        ]) + "</div>")
        p.append('<div class="mut">CAGR tidak ditampilkan untuk forward test (10 hari tidak bermakna).</div>')
        ser = [("Bot (forward)", "--s1", fw["curve"])]
        if gap:
            ser.append(("Backtest ulang jendela sama", "--s3", gap["rerun_curve"]))
        if fb.get("curve"):
            ser.append(("BTC/IDR buy & hold", "--s2", fb["curve"]))
        p.append(line_chart(ser, "Ekuitas forward test vs backtest ulang vs BTC"))

    # ---- gap
    p.append("<h2>Gap backtest vs forward (jendela & candle yang sama)</h2>")
    if not gap:
        p.append('<div class="empty">Belum bisa dihitung (butuh log forward dan candle jendela forward).</div>')
    else:
        rm = gap["rerun_metrics"]
        p.append('<div class="grid">' + "".join([
            card("Kecocokan sinyal", pcu(gap["signal_match_rate"], 2) if gap["signal_match_rate"] is not None else "-",
                 "%d/%d candle×pasangan identik" % (gap["signals_identical"], gap["signals_compared"])),
            card("Return forward", pct(fw["metrics"]["total_return"])), card("Return backtest ulang", pct(rm["total_return"])),
            card("Gap return", pct(gap["return_gap"]), "forward − backtest"),
            card("MDD forward / backtest", "%s / %s" % (pct(fw["metrics"]["max_drawdown"]), pct(rm["max_drawdown"]))),
            card("Trade forward / backtest", "%d / %d" % (fw["metrics"]["n_trades"], rm["n_trades"])),
            card("Order cocok", str(gap["orders_matched"]), "hanya bot %d · hanya backtest %d" % (gap["orders_only_bot"], gap["orders_only_backtest"])),
            card("Rata2 selisih fill", pctv(gap["avg_fill_gap_pct"]), "delay %s · spread %s · slippage %s" % (
                pctv(gap["avg_delay_pct"]), pctv(gap["avg_spread_pct"]), pctv(gap["avg_slippage_pct"]))),
            card("Rata2 keterlambatan eksekusi", num(gap["avg_delay_min"], 1) + " mnt", "dari close candle sinyal"),
            card("Selisih EMA maks (relatif)", "%.2e" % gap["max_rel_ema_diff"], "bot vs backtest"),
        ]) + "</div>")
        rows = []
        for r in gap["orders"]:
            rows.append([wib(r["signal_bar"] + C.TF_SECONDS), esc(r["pair"]), esc(r["side"]),
                         "ya" if r["in_bot"] else "<b>tidak</b>", "ya" if r["in_backtest"] else "<b>tidak</b>",
                         num(r.get("bot_fill"), 6) if r.get("bot_fill") else "-", num(r.get("bt_fill"), 6) if r.get("bt_fill") else "-",
                         pctv(r.get("total_pct")), pctv(r.get("delay_pct")), pctv(r.get("spread_pct")), pctv(r.get("slippage_pct")),
                         pctv(r.get("residual_pct")), num(r.get("delay_min"), 1)])
        p.append("<h3>Selisih harga fill per order (positif = lebih buruk untuk bot)</h3>" + table(
            ["Candle sinyal tutup", "Pair", "Sisi", "Bot", "Backtest", "Fill bot", "Fill backtest", "Total", "Delay jadwal", "Spread", "Slippage", "Sisa", "Telat (mnt)"], rows))
        if gap["signal_mismatches"]:
            p.append("<h3>Sinyal yang berbeda</h3>" + table(["Bar", "Pair", "Bot [buy,sell]", "Backtest [buy,sell]", "Close bot", "Close backtest"],
                     [[wib(m["bar"]), esc(m["pair"]), esc(m["bot"]), esc(m["backtest"]), num(m["bot_close"], 4), num(m["bt_close"], 4)] for m in gap["signal_mismatches"]]))

    # ---- operasional
    p.append("<h2>Panel operasional</h2>")
    if ops:
        p.append('<div class="grid">' + "".join([
            card("Uptime", pcu(ops["uptime"]) if ops["uptime"] is not None else "-", "%d / %d candle tepat waktu" % (ops["processed_on_time"], ops["expected_candles"])),
            card("Candle terlambat / terlewat", "%d / %d" % (ops["processed_late"], ops["missed"])),
            card("Panggilan terlaksana", str(ops["calls_total"]), esc(", ".join("%s=%d" % kv for kv in ops["calls_by_status"].items()))),
            card("Delay median / p90", "%s / %s mnt" % (num(ops["delay_min_median"], 1), num(ops["delay_min_p90"], 1)), "maks %s mnt" % num(ops["delay_min_max"], 1)),
            card("Error API (retry)", str(ops["api_errors"]), "exception tick: %d" % ops["tick_exceptions"]),
            card("Kill switch", str(len(ops["killswitch_events"])) + " event", "%d panggilan saat aktif" % ops["killswitch_active_calls"]),
            card("Daily loss limit", str(len(ops["daily_loss_halts"])) + "×"),
            card("Panggilan duplikat ditolak", str(ops["duplicate_calls"]), "idempotency"),
            card("Event validasi data", str(ops["validation_events"])),
        ]) + "</div>")
        p.append("<h3>Pemicu panggilan</h3>" + kv_table([(k, str(v)) for k, v in ops["calls_by_trigger"].items()]))
        p.append("<h3>Equity harian (panggilan pertama setelah 00.00 WIB, dinilai di best bid)</h3>" + table(
            ["Hari WIB", "Waktu", "Ekuitas", "Kas", "Posisi"],
            [[esc(d["day"]), wib(d["ts"]), idr(d["equity"]), idr(d["cash"]), str(d["n_positions"])] for d in ops["daily_equity"]]))
        if ops["killswitch_events"] or ops["daily_loss_halts"] or ops["notes"]:
            p.append("<h3>Kill switch, daily loss, catatan perbaikan</h3>" + table(["Waktu", "Jenis", "Detail"],
                     [[wib(e["ts"]), esc(e["type"]), esc(json.dumps({k: v for k, v in e.items() if k not in ("ts", "type", "call_id")}, ensure_ascii=False))]
                      for e in ops["killswitch_events"] + ops["daily_loss_halts"] + ops["notes"]]))
        if ops["missed_bars"]:
            p.append('<div class="mut">Candle terlewat: %s</div>' % esc(", ".join(wib(b + C.TF_SECONDS) for b in ops["missed_bars"][:50])))

    # ---- trade & order forward
    if fw:
        p.append("<h2>Trade & order forward test</h2>")
        p.append(table(["#", "Pair", "Masuk", "Keluar", "Qty", "Harga masuk", "Harga keluar", "Fee", "Spread", "Slippage", "P&L bersih", "Return"],
                       [[str(t["trade_id"]), esc(t["pair"]), wib(t["entry_ts"]), wib(t["exit_ts"]), num(t["qty"], 8), num(t["entry_price"], 4),
                         num(t["exit_price"], 4), idr(t["fees"]), idr(t["spread_cost"]), idr(t["slippage_cost"]),
                         '<span class="%s">%s</span>' % ("pos" if t["net_pnl"] > 0 else "neg", idr(t["net_pnl"])), pctv(t["ret_pct"], 2)]
                        for t in R["fwd_trades"]]))
        p.append("<h3>Semua order simulasi</h3>" + table(
            ["Waktu", "Pair", "Sisi", "Qty", "Best bid", "Best ask", "Fill rata2", "Level", "Fee", "Harga sinyal", "Selisih vs sinyal"],
            [[wib(o["ts"]), esc(o["pair"]), esc(o["side"]), num(o["qty"], 8), num(o["best_bid"], 4), num(o["best_ask"], 4), num(o["avg_price"], 4),
              str(o["levels_used"]), idr(o["fee"]), num(o["signal_price"], 4), pctv(o["diff_vs_signal_pct"])] for o in R["fwd_orders"]]))

    # ---- spread
    if R.get("spreads"):
        p.append("<h2>Spread & slippage: angka backtest vs seluruh snapshot forward</h2>")
        p.append(table(["Pair", "Spread backtest", "Spread forward", "Slip beli bt / fw", "Slip jual bt / fw", "n snapshot bt / fw"],
                       [[esc(k), pctv(v["backtest_spread_pct"], 4), pctv(v.get("forward_spread_pct"), 4),
                         "%s / %s" % (pctv(v["backtest_slip_buy_pct"], 4), pctv(v.get("forward_slip_buy_pct"), 4)),
                         "%s / %s" % (pctv(v["backtest_slip_sell_pct"], 4), pctv(v.get("forward_slip_sell_pct"), 4)),
                         "%s / %s" % (v["backtest_n"], v.get("forward_n", 0))] for k, v in R["spreads"].items()]))

    # ---- metodologi
    p.append("<h2>Aturan, biaya, dan sumber</h2>")
    pr = bt["params"]
    p.append('<div class="two">' + kv_table([
        ("Entry", "Cross(EMA%d, EMA%d) ∧ Close > EMA%d ∧ ADX(%d) > %g, pada close candle 1 jam tertutup" % (pr["fast"], pr["slow"], pr["trend"], pr["adx_n"], pr["min_adx"])),
        ("Exit", "Cross(EMA%d, EMA%d) (death cross)" % (pr["slow"], pr["fast"])),
        ("Sizing", "%.0f%% ekuitas per posisi, maks %d posisi, ≤ %.0f%% nilai transaksi 24 jam" % (pr["position_pct"] * 100, pr["max_positions"], pr["liq_cap_pct"] * 100)),
        ("Daily loss limit", "%.0f%% dari ekuitas awal hari WIB" % (pr["daily_loss_limit"] * 100)),
        ("Modal awal", idr(pr["initial_capital"])),
    ]) + kv_table([
        ("Fee taker beli / jual", "%.5f%% / %.5f%% (all-in, halaman resmi; API: %.2f%%)" % (pr["fee_buy"] * 100, pr["fee_sell"] * 100, C.FEE_API_TAKER * 100)),
        ("Sumber fee", "help.indodax.com — Rincian Biaya Transaksi di INDODAX (diakses 8 Nov 2026) & indodax.com/api/pairs"),
        ("Minimum order", idr(pr["min_order_idr"])),
        ("Eksekusi bot", "beli di ask, jual di bid, walk order book (harga rata-rata)"),
        ("Eksekusi backtest", "open candle berikutnya ± median setengah spread & slippage dari %d snapshot" % bt["costs_used"]["n_snapshots_total"]),
    ]) + "</div>")
    if R.get("reflection"):
        p.append("<h2>Refleksi</h2><pre>%s</pre>" % esc(R["reflection"]))
    if R.get("check"):
        p.append("<h2>Cek hitung ulang</h2>" + kv_table([(k, esc(v)) for k, v in R["check"].items()]))
    body = "\n".join(p)
    return ('<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Dashboard Bot Indodax</title><style>%s</style></head><body><main>%s</main></body></html>' % (CSS, body))
