"""Storage persisten: Upstash Redis (REST) di Vercel, atau folder lokal untuk uji di laptop.

Env (Vercel Marketplace > Upstash Redis mengisi otomatis salah satu pasangan ini):
  KV_REST_API_URL / KV_REST_API_TOKEN   atau   UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN
  KEY_PREFIX (opsional, default "uas") — namespace kunci; ganti untuk uji coba agar log forward test bersih.
Tanpa env Redis -> LocalStore di folder .localstore/ (hanya untuk pengembangan).
"""
import json
import os
import time
import urllib.request

from .indodax import _SSL


class RedisStore:
    def __init__(self, url, token, timeout=10.0, retries=3):
        self.url = url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.retries = retries

    def _post(self, path, payload):
        last = None
        for attempt in range(self.retries):
            try:
                req = urllib.request.Request(self.url + path, data=json.dumps(payload).encode(),
                                             headers={"Authorization": "Bearer " + self.token,
                                                      "Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=self.timeout, context=_SSL) as r:
                    return json.loads(r.read())
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(0.5 * (attempt + 1))
        raise RuntimeError("storage gagal: %s" % last)

    def cmd(self, *args):
        r = self._post("", [str(a) for a in args])
        if isinstance(r, dict) and r.get("error"):
            raise RuntimeError("redis: %s" % r["error"])
        return r.get("result")

    def pipeline(self, cmds):
        if not cmds:
            return []
        r = self._post("/pipeline", [[str(a) for a in c] for c in cmds])
        errs = [x.get("error") for x in r if isinstance(x, dict) and x.get("error")]
        if errs:
            raise RuntimeError("redis pipeline: %s" % errs)
        return [x.get("result") for x in r]

    def get(self, k):
        return self.cmd("GET", k)

    def set(self, k, v):
        return self.cmd("SET", k, v)

    def set_nx(self, k, v, ex):
        return self.cmd("SET", k, v, "NX", "EX", int(ex)) == "OK"

    def lrange(self, k, a=0, b=-1):
        return self.cmd("LRANGE", k, a, b) or []

    def delete(self, k):
        return self.cmd("DEL", k)

    def llen(self, k):
        return int(self.cmd("LLEN", k) or 0)


class LocalStore:
    """Implementasi berbasis file dengan antarmuka yang sama (untuk uji lokal)."""

    def __init__(self, root):
        self.root = root
        os.makedirs(root, exist_ok=True)

    def _p(self, k):
        return os.path.join(self.root, k.replace(":", "__"))

    def get(self, k):
        p = self._p(k) + ".val"
        if not os.path.exists(p):
            return None
        with open(p) as f:
            d = json.load(f)
        if d.get("exp") and d["exp"] < time.time():
            os.remove(p)
            return None
        return d["v"]

    def set(self, k, v, ex=None):
        with open(self._p(k) + ".val", "w") as f:
            json.dump({"v": v, "exp": time.time() + ex if ex else None}, f)
        return "OK"

    def set_nx(self, k, v, ex):
        if self.get(k) is not None:
            return False
        self.set(k, v, ex)
        return True

    def delete(self, k):
        p = self._p(k) + ".val"
        if os.path.exists(p):
            os.remove(p)

    def rpush(self, k, *vals):
        with open(self._p(k) + ".list", "a") as f:
            for v in vals:
                f.write(v.replace("\n", " ") + "\n")

    def lrange(self, k, a=0, b=-1):
        p = self._p(k) + ".list"
        if not os.path.exists(p):
            return []
        with open(p) as f:
            rows = [x.rstrip("\n") for x in f if x.strip()]
        b = len(rows) if b == -1 else b + 1
        return rows[a:b]

    def llen(self, k):
        return len(self.lrange(k))

    def pipeline(self, cmds):
        out = []
        for c in cmds:
            op = c[0].upper()
            if op == "RPUSH":
                self.rpush(c[1], *c[2:])
                out.append(None)
            elif op == "SET":
                out.append(self.set(c[1], c[2]))
            elif op == "GET":
                out.append(self.get(c[1]))
            else:
                raise ValueError(op)
        return out


def get_store():
    url = os.environ.get("KV_REST_API_URL") or os.environ.get("UPSTASH_REDIS_REST_URL")
    tok = os.environ.get("KV_REST_API_TOKEN") or os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    if url and tok:
        return RedisStore(url, tok)
    from . import config as C
    return LocalStore(os.environ.get("LOCAL_STORE_DIR", os.path.join(C.ROOT, ".localstore")))


def prefix():
    return os.environ.get("KEY_PREFIX", "uas")


LOG_NAMES = ["calls", "signals", "orders", "trades", "equity", "daily_equity", "errors", "events", "spreads", "snapshots"]


def key(name):
    return "%s:%s" % (prefix(), name)


def log_key(name):
    return "%s:log:%s" % (prefix(), name)


def read_log(store, name):
    return [json.loads(x) for x in store.lrange(log_key(name), 0, -1)]
