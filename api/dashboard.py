"""GET / (rewrite) atau /api/dashboard — dashboard publik yang membaca log dari storage.

Bagian gap menjalankan ulang backtest di jendela forward test memakai candle Indodax yang
diambil ulang (dengan pemanasan indikator). Hasil HTML di-cache 20 menit di storage.
?refresh=1 memaksa hitung ulang.
"""
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import config as C  # noqa: E402
from core.build import build, forward_window  # noqa: E402
from core.indodax import Client  # noqa: E402
from core.report import render  # noqa: E402
from core.store import LOG_NAMES, get_store, key, read_log  # noqa: E402
from core.strategy import closed_bars  # noqa: E402
from core.web import query, send  # noqa: E402

CACHE_S = 1200


def fetch_window_candles(start, end, now):
    cl = Client(retries=2)
    server = cl.server_time()
    stop = min(end or server, server)
    out = {}
    for u in C.load_universe():
        frm = start - (C.BOT_HISTORY_PAGES * 660) * C.TF_SECONDS
        pages = int((stop - frm) / (640 * C.TF_SECONDS)) + 2
        cs = cl.history_back(u["symbol"], C.TIMEFRAME, frm, stop, max_pages=pages)
        out[u["pair"]] = closed_bars(cs, server)
    return out


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        st = get_store()
        q = query(self)
        ck = key("dash_cache")
        if q.get("refresh") != "1":
            raw = st.get(ck)
            if raw:
                c = json.loads(raw)
                if time.time() - c["ts"] < CACHE_S:
                    return send(self, 200, c["html"], "text/html")
        now = int(time.time())
        logs = {n: read_log(st, n) for n in LOG_NAMES if n != "snapshots"}
        with open(os.path.join(C.ROOT, "results", "backtest_summary.json")) as f:
            bt = json.load(f)
        refl = None
        rp = os.path.join(C.ROOT, "REFLEKSI.md")
        if os.path.exists(rp):
            with open(rp) as f:
                refl = f.read()
        start, end = forward_window(logs, now)
        candles = None
        note = "log storage (Upstash Redis) + candle Indodax live"
        if start:
            try:
                candles = fetch_window_candles(start, end, now)
            except Exception as e:  # noqa: BLE001
                note += " (gagal ambil candle untuk gap: %s)" % e
        html = render(build(logs, bt, candles, now, note, reflection=refl))
        try:
            st.set(ck, json.dumps({"ts": now, "html": html}))
        except Exception:  # noqa: BLE001
            pass
        send(self, 200, html, "text/html")
