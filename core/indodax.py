"""Klien API publik Indodax (tanpa API key) dengan timeout, retry terbatas, dan jeda.

Batas Indodax 180 request/menit; kita memberi jeda minimal 0,34 detik antar request
(<= 3 request/detik) dan tidak pernah paralel.
"""
import json
import ssl
import time
import urllib.error
import urllib.request

BASE = "https://indodax.com"
UA = "uas-dryrun/1.0 (public API, no key)"


try:  # python.org di macOS tidak membawa CA bundle; Vercel memakai CA sistem
    import certifi
    _SSL = ssl.create_default_context(cafile=certifi.where())
except Exception:  # pragma: no cover
    _SSL = ssl.create_default_context()


class ApiError(Exception):
    pass


class Client:
    def __init__(self, timeout=10.0, retries=3, min_interval=0.34, log=None):
        self.timeout = timeout
        self.retries = retries            # total percobaan = retries
        self.min_interval = min_interval
        self._last = 0.0
        self.log = log                    # callable(dict) untuk mencatat error/retry
        self.n_requests = 0
        self.n_errors = 0

    def _pace(self):
        dt = time.time() - self._last
        if dt < self.min_interval:
            time.sleep(self.min_interval - dt)
        self._last = time.time()

    def get(self, path, params=None, allow_empty=False):
        url = BASE + path
        if params:
            url += "?" + "&".join("%s=%s" % (k, v) for k, v in params.items())
        last_err = None
        for attempt in range(1, self.retries + 1):
            self._pace()
            self.n_requests += 1
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=self.timeout, context=_SSL) as r:
                    body = r.read()
                if not body or not body.strip():
                    raise ApiError("respons kosong")
                data = json.loads(body)
                if data is None or data == [] or data == {}:
                    if allow_empty and data == []:
                        return []
                    raise ApiError("respons kosong (JSON)")
                if isinstance(data, dict) and data.get("error"):
                    raise ApiError("error API: %s" % data.get("error"))
                return data
            except (urllib.error.URLError, TimeoutError, ApiError, ValueError, OSError) as e:
                last_err = e
                self.n_errors += 1
                if self.log:
                    self.log({"type": "api_error", "url": url, "attempt": attempt, "error": "%s: %s" % (type(e).__name__, e)})
                if attempt < self.retries:
                    time.sleep(min(4.0, 1.0 * 2 ** (attempt - 1)))
        raise ApiError("gagal setelah %d percobaan: %s (%s)" % (self.retries, url, last_err))

    # ---- endpoint
    def server_time(self):
        return int(self.get("/api/server_time")["server_time"]) // 1000

    def depth(self, pair):
        return self.get("/api/depth/%s" % pair)

    def pairs(self):
        return self.get("/api/pairs")

    def price_increments(self):
        return self.get("/api/price_increments")["increments"]

    def history(self, symbol, tf, frm, to, allow_empty=False):
        data = self.get("/tradingview/history_v2", {"symbol": symbol, "tf": tf, "from": int(frm), "to": int(to)},
                        allow_empty=allow_empty)
        out = []
        for b in data:
            out.append({"t": int(b["Time"]), "o": float(b["Open"]), "h": float(b["High"]),
                        "l": float(b["Low"]), "c": float(b["Close"]), "v": float(b["Volume"])})
        out.sort(key=lambda x: x["t"])
        return out

    def history_back(self, symbol, tf, start, to, max_pages=None, page_log=None):
        """Tarik mundur: mulai dari `to`, geser `to` ke bar paling awal yang didapat, ulangi."""
        bars = {}
        cur_to = int(to)
        pages = 0
        while True:
            chunk = self.history(symbol, tf, start, cur_to)
            pages += 1
            new = [b for b in chunk if b["t"] not in bars]
            for b in chunk:
                bars[b["t"]] = b
            if page_log:
                page_log(pages, chunk)
            if not chunk or not new:
                break
            earliest = chunk[0]["t"]
            if earliest <= start:
                break
            if max_pages and pages >= max_pages:
                break
            cur_to = earliest - 1
        return [bars[k] for k in sorted(bars) if k >= start]
