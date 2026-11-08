"""Utilitas HTTP untuk fungsi Vercel (api/*.py)."""
import hmac
import json
import os
from urllib.parse import parse_qs, urlparse


def authorized(handler):
    """Wajib header `Authorization: Bearer <CRON_SECRET>`. Fail-closed bila CRON_SECRET belum diisi.
    (Vercel Cron otomatis mengirim header ini bila env CRON_SECRET ada.)"""
    secret = os.environ.get("CRON_SECRET", "")
    if len(secret) < 16:
        return False
    got = handler.headers.get("Authorization", "")
    return hmac.compare_digest(got.encode(), ("Bearer " + secret).encode())


def query(handler):
    return {k: v[-1] for k, v in parse_qs(urlparse(handler.path).query).items()}


def send(handler, code, body, ctype="application/json"):
    if not isinstance(body, (bytes, str)):
        body = json.dumps(body, indent=1, default=str)
    if isinstance(body, str):
        body = body.encode()
    handler.send_response(code)
    handler.send_header("Content-Type", ctype + "; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def deny(handler):
    send(handler, 401, {"error": "unauthorized"})
