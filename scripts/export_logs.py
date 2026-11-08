"""Ekspor log mentah forward test ke logs/<nama>.jsonl (untuk dikumpulkan & hitung_ulang).

  python3 scripts/export_logs.py --url https://<proyek>.vercel.app   # lewat endpoint publik /api/logs
  python3 scripts/export_logs.py                                       # langsung dari storage (butuh env KV_REST_API_*)
"""
import argparse
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import config as C  # noqa: E402
from core.indodax import _SSL  # noqa: E402
from core.store import LOG_NAMES, get_store, log_key  # noqa: E402


def fetch_url(base, name, a, b):
    u = "%s/api/logs?name=%s&start=%d&end=%d" % (base.rstrip("/"), name, a, b)
    with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "uas-export/1.0"}), timeout=60, context=_SSL) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None)
    ap.add_argument("--out", default=os.path.join(C.ROOT, "logs"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    st = None if a.url else get_store()
    for name in LOG_NAMES:
        rows = []
        page = 500
        i = 0
        while True:
            if a.url:
                chunk = fetch_url(a.url, name, i, i + page - 1)
            else:
                chunk = [json.loads(x) for x in st.lrange(log_key(name), i, i + page - 1)]
            rows.extend(chunk)
            if len(chunk) < page:
                break
            i += page
        with open(os.path.join(a.out, name + ".jsonl"), "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        print("%-13s %6d baris" % (name, len(rows)))


if __name__ == "__main__":
    main()
