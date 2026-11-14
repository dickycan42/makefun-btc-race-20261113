"""Dip-bounce scalper for the make.fun BTC race (agent-fun/bars-replay/v1).

Strategy, in one paragraph: the dev window falls 4.91% over 24 hours, so
trend-following and buy-and-hold both lose and every house baseline ends
negative. This bot therefore stays in cash almost all of the time and only
buys a sharp dip that is already bouncing: the close must sit 75-120 bps
below the highest close of the last 30 minutes AND have risen at least
15 bps over the last 3 minutes. It buys 700 USDC of cbBTC, then sells the
whole position as soon as it is 110 bps above its fill price, cuts it at
25 bps below, or after 40 minutes, whichever comes first. After any exit
it waits 30 minutes before looking for the next dip, so it never
re-enters the same falling knife twice in a row.

Everything is integer arithmetic on the raw price units the harness sends
(no floats, no clock, no network, no randomness), so two runs on the same
bars produce byte-identical replies.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"

# --- strategy parameters (basis points unless noted) -----------------------
LOOKBACK_BARS = 30        # rolling high window for the dip
DIP_MIN_BPS = 75          # dip must be at least this deep vs the 30-min high
DIP_MAX_BPS = 120         # ... but not deeper: very deep dips kept falling
RISE_3M_BPS = 15          # close must have risen this much over the last 3 min
SIZE_QUOTE_UNITS = 700_000_000   # 700 USDC per trade (quote scale 6)
TAKE_PROFIT_BPS = 110     # sell when the position is this far above its fill
STOP_LOSS_BPS = 25        # ... or this far below it
MAX_HOLD_BARS = 40        # ... or after this many bars, whichever is first
COOLDOWN_BARS = 30        # bars to wait after an exit before a new entry
MAX_SLIPPAGE_BPS = 200    # 2%: far above the ~15 bps a fill normally moves

# --- per-run state ----------------------------------------------------------
closes = []               # closes of CBBTC, oldest first, raw price units
entry_price = None        # raw fill price of the open position, if any
entry_seq = None          # seq of the batch in which the position opened
last_exit_seq = -10**9    # seq of the batch in which we last sold


def _bps(numerator, denominator):
    """(numerator / denominator - 1) in basis points, integer math."""
    return numerator * 10_000 // denominator - 10_000


def on_batch(state, batch):
    global entry_price, entry_seq, last_exit_seq

    for bar in batch["bars"]:
        if bar["symbol"] == SYMBOL:
            closes.append(int(bar["c"]))
    if len(closes) > 200:
        del closes[: len(closes) - 200]

    # Learn the exact fill price of a buy that landed in this batch, and
    # mark the bar a sell actually filled on. The cooldown is measured
    # from the fill, not from the decision: an order that is sent but
    # rejected (slippage, no bar) leaves the position open and must be
    # retried on the next bar, not treated as an exit.
    for fill in batch["fills"]:
        if fill["symbol"] != SYMBOL or fill["status"] != "filled":
            continue
        if fill["side"] == "buy":
            entry_price = int(fill["price"])
            entry_seq = int(fill["fill_bar"])
        elif fill["side"] == "sell":
            last_exit_seq = int(fill["fill_bar"])
            entry_price = None
            entry_seq = None

    held = state.positions.get(SYMBOL)
    if held is not None:
        if entry_price is None:
            # Fallback: derive the entry price from the position's cost.
            # cost (quote units) = qty * price * 10**quote_scale /
            #                      10**(qty_scale + price_scale)
            sym = state.symbols[SYMBOL]
            qscale = state.hello["capital"]["quote_scale"]
            entry_price = (
                held.cost * 10 ** (sym["qty_scale"] + sym["price_scale"])
                // (held.qty * 10**qscale)
            )
        if entry_seq is None:
            entry_seq = state.seq
        value = state.value(SYMBOL, held.qty)
        entry_value = state.value(SYMBOL, held.qty, price=entry_price)
        gain_bps = _bps(value, entry_value)
        hold_bars = state.seq - entry_seq
        if gain_bps >= TAKE_PROFIT_BPS or gain_bps <= -STOP_LOSS_BPS or hold_bars >= MAX_HOLD_BARS:
            # Do not clear entry tracking here: the sell may be rejected,
            # and the fill handler above is what records the real exit.
            return [
                {
                    "side": "sell",
                    "symbol": SYMBOL,
                    "qty": held.qty,
                    "max_slippage_bps": MAX_SLIPPAGE_BPS,
                }
            ]
        return []

    # Flat: reset entry tracking and look for the next dip.
    entry_price = None
    entry_seq = None
    if state.warming_up:
        return []
    if state.seq - last_exit_seq < COOLDOWN_BARS:
        return []
    if len(closes) < LOOKBACK_BARS + 4:
        return []

    high = max(closes[-LOOKBACK_BARS:])
    close = closes[-1]
    dip_bps = _bps(close, high)
    rise_bps = _bps(close, closes[-4])
    if not (-DIP_MAX_BPS <= dip_bps <= -DIP_MIN_BPS):
        return []
    if rise_bps < RISE_3M_BPS:
        return []

    spend = SIZE_QUOTE_UNITS
    if spend > state.cash:
        spend = state.cash
    min_notional = int(state.hello["fees"]["min_notional_quote_units"])
    if spend < min_notional:
        return []
    return [
        {
            "side": "buy",
            "symbol": SYMBOL,
            "notional_quote_units": spend,
            "max_slippage_bps": MAX_SLIPPAGE_BPS,
        }
    ]


makefun_bars.run(on_batch)
