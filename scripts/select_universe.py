"""Pilih universe berdasarkan likuiditas PADA AWAL PERIODE BACKTEST (bukan hari ini).

Kriteria (ditetapkan sebelum melihat hasil backtest):
  1. Kandidat: semua pasangan IDR di /api/pairs, kecuali aset ber-peg (stablecoin & token emas)
     karena strategi tren tidak bermakna untuk aset yang harganya dipatok.
  2. Pasangan harus sudah aktif diperdagangkan di jendela ukur 90 hari
     (2023-08-03 s.d. 2023-10-31 UTC): >= 85 candle harian dengan volume > 0.
  3. Ranking: median nilai transaksi harian IDR (close x volume) pada jendela itu.
  4. Ambil 6 teratas.
Output: data/universe.json (+ data/universe_ranking.csv berisi seluruh kandidat).

Catatan bias: /api/pairs hanya memuat pasangan yang masih ada hari ini, sehingga pasangan
yang sudah delisting tidak ikut kandidat. Ini dicatat di README sebagai bias sisa.
"""
import csv
import datetime as dt
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import config as C  # noqa: E402
from core.indodax import Client, ApiError  # noqa: E402

PEGGED = {"usdt", "usdc", "dai", "busd", "tusd", "idrt", "bidr", "usdp", "fdusd", "pyusd", "usdd",
          "xaut", "paxg", "eurt", "usde", "ausd", "rlusd", "usd1", "xsgd"}
TOP_N = 6
MIN_DAYS = 85


def ts(iso):
    return int(dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp())


def main():
    cl = Client()
    pairs = cl.pairs()
    incs = cl.price_increments()
    start = ts(C.UNIVERSE_LOOKBACK_START)
    end = ts(C.BACKTEST_START)
    rows = []
    cands = [p for p in pairs if p["base_currency"] == "idr" and p["traded_currency"].lower() not in PEGGED]
    print("kandidat:", len(cands), file=sys.stderr)
    for i, p in enumerate(cands):
        try:
            bars = cl.history(p["symbol"], "1D", start, end - 1, allow_empty=True)
        except ApiError as e:
            bars = []
            print("  gagal", p["id"], e, file=sys.stderr)
        bars = [b for b in bars if start <= b["t"] < end]
        traded = [b for b in bars if b["v"] > 0 and b["c"] > 0]
        turn = [b["c"] * b["v"] for b in traded]
        med = statistics.median(turn) if turn else 0.0
        rows.append({"pair": p["id"], "symbol": p["symbol"], "ticker_id": p["ticker_id"],
                     "days_traded": len(traded), "median_daily_idr": med,
                     "eligible": len(traded) >= MIN_DAYS})
        if i % 25 == 0:
            print("  %d/%d" % (i, len(cands)), file=sys.stderr)
    rows.sort(key=lambda r: (-int(r["eligible"]), -r["median_daily_idr"]))
    for k, r in enumerate(rows, 1):
        r["rank"] = k
    with open(os.path.join(C.ROOT, "data", "universe_ranking.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    chosen = [r for r in rows if r["eligible"]][:TOP_N]
    meta = {p["id"]: p for p in pairs}
    out = {
        "criteria": {
            "measure_window_utc": [C.UNIVERSE_LOOKBACK_START, C.BACKTEST_START],
            "min_days_traded": MIN_DAYS,
            "rank_by": "median daily IDR turnover (close x volume), candle 1D history_v2",
            "excluded_pegged": sorted(PEGGED),
            "top_n": TOP_N,
            "selected_at_utc": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "pairs": [{
            "pair": r["pair"],
            "symbol": r["symbol"],
            "ticker_id": r["ticker_id"],
            "price_increment": float(incs.get(r["ticker_id"], meta[r["pair"]].get("pricescale", 1)) or 1),
            "quantity_increment": float(meta[r["pair"]].get("quantity_increment") or 1e-8),
            "median_daily_idr_2023": r["median_daily_idr"],
            "days_traded_2023": r["days_traded"],
        } for r in chosen],
    }
    with open(C.UNIVERSE_FILE, "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
