#!/usr/bin/env python3
"""
fetch_opensky.py  —  writes data-opensky.json for the Aviation tab.

WHY A FETCHER (not a browser call):
  OpenSky's REST API returns `access-control-allow-origin: https://opensky-network.org`,
  so a browser fetch from GitHub Pages is blocked by CORS. Pulling server-side (here,
  in a GitHub Action) avoids CORS, keeps you within the free/non-commercial terms, and
  matches the repo's existing "Python fetcher -> static JSON snapshot" pattern.

USAGE:
  python fetch_opensky.py                      # anonymous (~400 calls/day, lower res)
  OPENSKY_CLIENT_ID=... OPENSKY_CLIENT_SECRET=... python fetch_opensky.py   # OAuth2, higher limits

OUTPUT: data-opensky.json  (the Live Traffic tile reads this)
LICENSE NOTE: OpenSky data is free for research / non-commercial use only.
"""
import os, json, time, urllib.request, urllib.parse
from collections import Counter

API = "https://opensky-network.org/api/states/all"
TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
OUT = os.path.join(os.path.dirname(__file__), "data-opensky.json")
UA = "btc-eth-etf-dashboard/aviation-tab (non-commercial)"


def get_token():
    cid, sec = os.getenv("OPENSKY_CLIENT_ID"), os.getenv("OPENSKY_CLIENT_SECRET")
    if not (cid and sec):
        return None
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials", "client_id": cid, "client_secret": sec
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=data,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r).get("access_token")


def fetch():
    headers = {"User-Agent": UA}
    tok = get_token()
    if tok:
        headers["Authorization"] = "Bearer " + tok
    req = urllib.request.Request(API, headers=headers)
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.load(r)


def summarize(d):
    sv = [s for s in (d.get("states") or []) if s]
    air = [s for s in sv if len(s) > 8 and s[8] is False]
    ground = [s for s in sv if len(s) > 8 and s[8] is True]
    bands = {"0–10k ft": 0, "10–20k ft": 0, "20–30k ft": 0, "30–40k ft": 0, "40k+ ft": 0}
    for s in air:
        alt = s[7]
        if alt is None:
            continue
        ft = alt * 3.28084
        key = ("0–10k ft" if ft < 10000 else "10–20k ft" if ft < 20000 else
               "20–30k ft" if ft < 30000 else "30–40k ft" if ft < 40000 else "40k+ ft")
        bands[key] += 1
    ts = d.get("time") or int(time.time())
    return {
        "ts": ts,
        "tstr": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(ts)),
        "tracked": len(sv),
        "airborne": len(air),
        "ground": len(ground),
        "byCountry": Counter(s[2].strip() for s in sv if s[2]).most_common(8),
        "byAlt": list(bands.items()),
        "note": ("OpenSky coverage is a sample of global traffic from volunteer ADS-B "
                 "receivers, densest over US/Europe."),
    }


def main():
    snap = summarize(fetch())
    with open(OUT, "w") as f:
        json.dump(snap, f)
    print(f"wrote {OUT}: {snap['airborne']:,} airborne / {snap['tracked']:,} tracked @ {snap['tstr']}")


if __name__ == "__main__":
    main()
