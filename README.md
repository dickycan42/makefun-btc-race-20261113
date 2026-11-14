# Dip-Bounce Scalper — BTC Race 24h

A trading bot for the make.fun `btc-race-24h-20261113-2314` competition:
it trades cbBTC/USDC on 1-minute on-chain bars, long only, starting from
1,000 USDC of paper money.

## Why this strategy

The published dev window falls 4.91% from first close to last, and only 9
of its 24 hours close up. Every baseline the kit ships loses on it
(momentum −49.23, RSI-Bollinger −65.83, EMA-cross −109.38, ADX-momentum
−50.31 USDC), and buy-and-hold loses with the market. A full-size round
trip costs roughly 26 bps in fees, slippage and price impact, so a trade
has to catch a move clearly larger than that. The bot therefore stays in
cash most of the time and only buys a sharp dip that is already bouncing.

## Rules

**Entry** (all must hold, evaluated on each bar's close, filled at the
next bar's open):

- The close is **75–120 bps below the highest close of the last
  30 minutes** — a real dip, but not a free-fall (dips deeper than 120 bps
  kept falling on the dev window).
- The close has **risen at least 15 bps over the last 3 minutes** — the
  bounce has already started.
- At least **30 minutes since the last exit** — never re-enter the same
  falling knife twice in a row.
- Buy **700 USDC** of cbBTC (one position at a time, long only).

**Exit** (the whole position, first trigger wins):

- **Take profit:** +110 bps above the fill price.
- **Stop loss:** −25 bps below the fill price.
- **Time stop:** 40 minutes after entry.

Orders cap their slippage at 200 bps, far above the ~15 bps a fill
normally moves, so a fill is essentially never refused for slippage.

## Dev-window result (local grade)

Graded locally with the kit's own grader
(`node cli/makefun.mjs grade-local --kit . --bot <repo> --driver process`):

- Net PnL: **+6.51 USDC** (3 trades, max drawdown 0.51%)
- The profit comes from two V-bounces (06:05 and 15:47 UTC) and one small
  stop-loss; the same parameters also make money on each 12-hour half of
  the window on its own (+3.67 / +2.84 USDC).

## Implementation notes

- `main.py` is Python 3.13, standard library only, plus the kit's Python
  SDK shim copied byte-for-byte into `vendor/makefun_bars.py`.
- All arithmetic is integer math on the raw price units the harness sends:
  no floats, no wall clock, no network, no randomness. Two runs on the
  same bars produce byte-identical replies.
- The entry price is read from the fill the harness reports, so the
  take-profit / stop-loss are measured against the real fill, not the
  decision close.
