"""POST/GET /api/tick — dipanggil penjadwal (GitHub Actions / cron-job.org / Vercel Cron). Dilindungi CRON_SECRET."""
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.bot import tick  # noqa: E402
from core.store import get_store  # noqa: E402
from core.web import authorized, deny, query, send  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def _run(self):
        if not authorized(self):
            return deny(self)
        src = query(self).get("src", "")[:32] or ("vercel-cron" if "vercel-cron" in self.headers.get("User-Agent", "") else "unknown")
        res = tick(get_store(), trigger=src)
        send(self, 200 if res["status"] != "error" else 500, res)

    def do_GET(self):
        self._run()

    def do_POST(self):
        self._run()
