"""GET /api/health — uji koneksi Vercel -> Indodax dan Vercel -> storage. Dilindungi CRON_SECRET. Tidak bertransaksi."""
import os
import sys
import time
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import config as C  # noqa: E402
from core.indodax import Client  # noqa: E402
from core.store import get_store, key  # noqa: E402
from core.web import authorized, deny, send  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not authorized(self):
            return deny(self)
        out = {"ts": int(time.time())}
        cl = Client(retries=2)
        try:
            out["indodax_server_time"] = cl.server_time()
            d = cl.depth(C.BENCHMARK_PAIR)
            out["indodax_depth_levels"] = [len(d.get("buy", [])), len(d.get("sell", []))]
            h = cl.history("BTCIDR", C.TIMEFRAME, out["indodax_server_time"] - 86400, out["indodax_server_time"])
            out["indodax_history_bars"] = len(h)
            out["indodax_ok"] = True
        except Exception as e:  # noqa: BLE001
            out["indodax_ok"] = False
            out["indodax_error"] = str(e)
        try:
            st = get_store()
            out["store_type"] = type(st).__name__
            out["state_present"] = st.get(key("state")) is not None
            out["store_ok"] = True
        except Exception as e:  # noqa: BLE001
            out["store_ok"] = False
            out["store_error"] = str(e)
        send(self, 200 if out.get("indodax_ok") and out.get("store_ok") else 500, out)
