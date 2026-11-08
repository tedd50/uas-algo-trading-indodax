"""GET /api/logs?name=orders[&start=0&end=-1] — unduh log mentah (JSON) untuk audit. Read-only.

Log tidak berisi secret. name salah satu: calls, signals, orders, trades, equity, daily_equity,
errors, events, spreads, snapshots.
"""
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.store import LOG_NAMES, get_store, log_key  # noqa: E402
from core.web import query, send  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q = query(self)
        name = q.get("name")
        st = get_store()
        if name not in LOG_NAMES:
            return send(self, 200, {n: st.llen(log_key(n)) for n in LOG_NAMES})
        a = int(q.get("start", 0))
        b = int(q.get("end", -1))
        if name == "snapshots" and (b == -1 or b - a > 500):
            b = a + 500 - 1   # batasi ukuran respons; pakai paginasi
        rows = st.lrange(log_key(name), a, b)
        body = "[" + ",".join(rows) + "]"
        send(self, 200, body)
