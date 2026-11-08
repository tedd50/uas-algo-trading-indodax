"""/api/admin — kill switch & catatan perbaikan bug, tanpa deploy ulang. Dilindungi CRON_SECRET.

  POST /api/admin?action=kill_on            -> nyalakan kill switch (entry baru diblokir)
  POST /api/admin?action=kill_off           -> matikan kill switch
  GET  /api/admin?action=status             -> status kill switch & state
  POST /api/admin?action=note&msg=...       -> catat perbaikan bug / kejadian ke log events
Setiap aksi tercatat di log `events`.
"""
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.bot import killswitch_on  # noqa: E402
from core.store import get_store, key, log_key  # noqa: E402
from core.web import authorized, deny, query, send  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def _run(self, write):
        if not authorized(self):
            return deny(self)
        q = query(self)
        st = get_store()
        act = q.get("action", "status")
        now = int(time.time())
        if act == "status":
            kill, src = killswitch_on(st)
            raw = st.get(key("state"))
            return send(self, 200, {"killswitch": kill, "source": src, "state": json.loads(raw) if raw else None})
        if not write:
            return send(self, 405, {"error": "gunakan POST"})
        if act in ("kill_on", "kill_off"):
            st.set(key("killswitch"), "1" if act == "kill_on" else "0")
            ev = {"type": "killswitch_set", "ts": now, "state": act == "kill_on", "via": "api/admin"}
        elif act == "note":
            msg = q.get("msg", "")[:500]
            if not msg:
                return send(self, 400, {"error": "msg kosong"})
            ev = {"type": "note", "ts": now, "msg": msg, "via": "api/admin"}
        else:
            return send(self, 400, {"error": "action tidak dikenal"})
        st.pipeline([["RPUSH", log_key("events"), json.dumps(ev)]])
        send(self, 200, ev)

    def do_GET(self):
        self._run(False)

    def do_POST(self):
        self._run(True)
