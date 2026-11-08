"""Jalankan satu tick bot di laptop (data Indodax live, storage lokal .localstore/ kecuali env Redis diisi).

  python3 scripts/run_tick_local.py            # sekali
  python3 scripts/run_tick_local.py --twice    # dua kali berturut-turut (uji idempotency)
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.bot import tick  # noqa: E402
from core.store import get_store  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--twice", action="store_true")
    a = ap.parse_args()
    st = get_store()
    print("store:", type(st).__name__)
    for _ in range(2 if a.twice else 1):
        r = tick(st, trigger="local")
        print(json.dumps(r, indent=1))


if __name__ == "__main__":
    main()
