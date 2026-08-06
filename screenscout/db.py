"""Thin Supabase REST helpers (paginated load, insert, delete, counts)."""
import json
import requests
from . import config


def _h():
    url, key = config.get()
    return url, {"apikey": key, "Authorization": f"Bearer {key}",
                 "Content-Type": "application/json", "Prefer": "return=minimal"}


def load(select="*", where=""):
    url, h = _h()
    rows, off = [], 0
    while True:
        r = requests.get(f"{url}/rest/v1/prices?select={select}{where}",
                         headers={**h, "Range": f"{off}-{off+999}"}, timeout=90)
        r.raise_for_status()
        d = r.json(); rows += d
        if len(d) < 1000:
            break
        off += 1000
    return rows


def count(where=""):
    url, h = _h()
    r = requests.get(f"{url}/rest/v1/prices?select=id{where}",
                     headers={**h, "Prefer": "count=exact", "Range": "0-0"}, timeout=60)
    return int(r.headers.get("content-range", "0-0/0").split("/")[-1])


def insert(rows):
    if not rows:
        return 0
    url, h = _h()
    for i in range(0, len(rows), 200):
        r = requests.post(f"{url}/rest/v1/prices", headers=h,
                          data=json.dumps(rows[i:i+200]), timeout=120)
        r.raise_for_status()
    return len(rows)


def delete_ids(ids):
    if not ids:
        return 0
    url, h = _h()
    ids = list(ids)
    for i in range(0, len(ids), 100):
        inlist = "(" + ",".join(str(x) for x in ids[i:i+100]) + ")"
        r = requests.delete(f"{url}/rest/v1/prices?id=in.{inlist}", headers=h, timeout=60)
        r.raise_for_status()
    return len(ids)
