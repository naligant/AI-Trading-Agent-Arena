import time
import requests

INFO = "https://api.hyperliquid.xyz/info"


def info(payload, timeout=60, retries=4):
    last = None
    for attempt in range(retries):
        try:
            r = requests.post(INFO, json=payload, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise last

def all_mids():
    return {k: float(v) for k, v in info({"type": "allMids"}).items()}

def candles(coin, interval, start_ms, end_ms, chunk_ms=7 * 24 * 60 * 60 * 1000):
    """Fetch candles in week-sized windows so Hyperliquid doesn't stall."""
    out, seen = [], set()
    t = start_ms
    while t < end_ms:
        chunk_end = min(t + chunk_ms, end_ms)
        rows = info({"type": "candleSnapshot", "req": {
            "coin": coin, "interval": interval,
            "startTime": t, "endTime": chunk_end}}) or []
        for row in rows:
            key = row.get("t")
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
        t = chunk_end
    out.sort(key=lambda r: r["t"])
    return out

def funding(coin, start_ms, end_ms=None, chunk_ms=7 * 24 * 60 * 60 * 1000):
    out, seen = [], set()
    t = start_ms
    stop = end_ms or int(time.time() * 1000)
    while t < stop:
        chunk_end = min(t + chunk_ms, stop)
        payload = {"type": "fundingHistory", "coin": coin, "startTime": t, "endTime": chunk_end}
        rows = info(payload) or []
        for row in rows:
            key = (row.get("time"), row.get("coin"))
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
        t = chunk_end
    return out