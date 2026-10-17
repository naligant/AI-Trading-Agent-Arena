from dataclasses import dataclass, field

from hyper_liquid_api import candles as fetch_candles, funding as fetch_funding


@dataclass
class Account:
    cash: float
    pos: dict = field(default_factory=dict)    # coin -> signed size
    entry: dict = field(default_factory=dict)  # coin -> avg entry price
    fees: float = 0.0
    halted: bool = False

def equity(a, px):
    return a.cash + sum(sz * (px[c] - a.entry[c]) for c, sz in a.pos.items() if c in px)

def trade(a, coin, size, px, fee_bps=4.5):   # fee is a placeholder; check Hyperliquid's schedule
    pos, entry = a.pos.get(coin, 0.0), a.entry.get(coin, px)
    if pos and (pos > 0) != (size > 0):      # realize PnL on the closing part
        closed = min(abs(size), abs(pos))
        a.cash += closed * (px - entry) * (1 if pos > 0 else -1)
    new = pos + size
    if abs(new) < 1e-12:
        a.pos.pop(coin, None); a.entry.pop(coin, None)
    else:
        if pos == 0 or (pos > 0) == (size > 0):
            a.entry[coin] = (entry * abs(pos) + px * abs(size)) / abs(new)
        elif abs(size) > abs(pos):           # position flipped
            a.entry[coin] = px
        a.pos[coin] = new
    fee = abs(size) * px * fee_bps / 1e4
    a.cash -= fee; a.fees += fee

def rebalance(a, targets, px, max_lev=3.0, slip_bps=5):
    gross = sum(abs(t) for t in targets.values())
    if gross > max_lev:
        targets = {c: t * max_lev / gross for c, t in targets.items()}
    eq = equity(a, px)
    for coin in set(targets) | set(a.pos):   # coins not mentioned go flat
        want = targets.get(coin, 0.0) * eq / px[coin]
        delta = want - a.pos.get(coin, 0.0)
        if abs(delta) * px[coin] < 1e-3 * eq: continue   # ignore dust
        side = 1 if delta > 0 else -1
        trade(a, coin, delta, px[coin] * (1 + side * slip_bps / 1e4))


def apply_funding(a, px, rates):
    """Perp funding: long pays positive rate, short receives it."""
    for coin, sz in list(a.pos.items()):
        rate = rates.get(coin, 0.0) if rates else 0.0
        if not rate or coin not in px:
            continue
        a.cash -= sz * px[coin] * rate


def make_obs(closed_bars, account, last_close_px):
    """What the agent may see: only candles that have already closed."""
    return {
        "candles": closed_bars,
        "account": account,
        "prices": last_close_px,
        "equity": equity(account, last_close_px) if last_close_px else account.cash,
    }


def load_market(coins, interval, start_ms, end_ms):
    """Align Hyperliquid candles + funding onto one timeline."""
    raw = {c: fetch_candles(c, interval, start_ms, end_ms) for c in coins}
    by_t = {}
    for coin, rows in raw.items():
        for row in rows:
            by_t.setdefault(row["t"], {})[coin] = row

    times = sorted(t for t, m in by_t.items() if all(c in m for c in coins))

    fund_at = {c: {} for c in coins}
    for coin in coins:
        for h in fetch_funding(coin, start_ms, end_ms):
            fund_at[coin][h["time"]] = float(h["fundingRate"])

    bars, open_px, close_px, funding = [], [], [], []
    for t in times:
        row = by_t[t]
        o = {c: float(row[c]["o"]) for c in coins}
        cl = {c: float(row[c]["c"]) for c in coins}
        f = {c: fund_at[c].get(t, 0.0) for c in coins}
        bars.append(row)
        open_px.append(o)
        close_px.append(cl)
        funding.append(f)
    return bars, open_px, close_px, funding


def run(agent, coins, interval, start_ms, end_ms, cash=10_000.0, warmup=50):
    candles, open_px, close_px, funding = load_market(coins, interval, start_ms, end_ms)
    n = len(candles)
    if n <= warmup:
        raise ValueError(f"need more than {warmup} aligned bars, got {n}")

    account = Account(cash=cash)
    curve = []

    for i in range(warmup, n):
        obs = make_obs(candles[:i], account, close_px[i - 1])  # only CLOSED candles before i
        targets = agent.decide(obs)
        rebalance(account, targets, open_px[i])                 # fills at candle i's open
        apply_funding(account, open_px[i], funding[i])
        curve.append(equity(account, close_px[i]))              # mark to market at close

    return account, curve


if __name__ == "__main__":
    import time
    from agents import HoldAgent

    end_ms = int(time.time() * 1000)
    start_ms = end_ms - 60 * 24 * 60 * 60 * 1000  # ~60 days of 1h bars
    agent = HoldAgent({"BTC": 0.5, "ETH": 0.5})
    account, curve = run(agent, ["BTC", "ETH"], "1h", start_ms, end_ms)
    print(f"bars={len(curve)} start={curve[0]:.2f} end={curve[-1]:.2f} fees={account.fees:.2f}")