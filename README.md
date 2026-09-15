# OmniQuant MVP

A research terminal for systematic trading on MetaTrader 5: an SMC-style signal
engine, a cost-aware backtester, an ML signal filter, a risk guard with a kill
switch, and a real-time Next.js dashboard.

> **Read this first.** This is a *research prototype*, not a money-making bot.
> The bundled strategy has **not** been shown to have an edge — the previous
> version's own artefacts reported a 29.5% win rate against a 37.5% break-even
> requirement at 1.5R/2.5R exits, i.e. negative expectancy even before costs.
> Everything added in v0.6 exists to let you *prove or disprove* an edge rather
> than assume one. Do not fund this until `walk-forward` and `vs random` say so.

---

## Architecture

```
                 ┌──────────────────────────── Next.js 14 (TS, Tailwind) ─┐
                 │  Chart · Validation · Order · AI Engine · Positions ·  │
                 │  Signals · Risk (kill switch) · Heatmap · 3D sphere     │
                 └─────────────── REST + WebSocket ────────────────────────┘
                                        │
┌───────────────────────────────────────▼────────────────────────────────────┐
│ FastAPI backend                                                            │
│                                                                            │
│  main.py ──► analyzer.py (AI engine loop) ──► strategy/smc.py (signals)     │
│     │              │                                                        │
│     │              └──► risk.py (guard + kill switch) ──► mt5_bridge.py     │
│     │                                                        │              │
│     ├──► backtest/engine.py   (cost-aware, parity with live)  │              │
│     │    backtest/metrics.py  (expectancy, PF, DD, Sharpe, t) │              │
│     │    backtest/walkforward.py (out-of-sample folds)        │              │
│     │    backtest/montecarlo.py  (random-entry benchmark)     │              │
│     │                                                        ▼              │
│     ├──► ml/ (features → xgboost filter)              MetaTrader5 terminal  │
│     └──► database.py (SQLite, WAL, audit log)                               │
└────────────────────────────────────────────────────────────────────────────┘
```

**Design rule:** the backtest and the live engine read the *same* settings
object (`core/config.py`). Any threshold that exists in one place only is a bug.

---

## Quick start

Requirements: **Windows** (the `MetaTrader5` python package drives the desktop
terminal), Python 3.10+, Node 20+.

```bash
# ---- backend ----
cd backend
python -m venv .venv
.venv\Scripts\activate                 # Windows
pip install -r requirements.txt
pip install -r requirements-mt5.txt    # Windows-only wheel
cp .env.example .env                   # then edit AUTH_TOKEN

python download_history.py             # cache candles (needed for backtests)
uvicorn main:app --reload --port 8000

# ---- frontend ----
cd frontend
npm install
cp .env.example .env.local             # must match backend AUTH_TOKEN
npm run dev                            # http://localhost:3000
```

Then open:

- <http://127.0.0.1:8000/docs> — interactive API
- <http://127.0.0.1:8000/api/health> — mode, kill-switch state
- <http://localhost:3000> — dashboard

Run the tests (no MT5 needed — the module is stubbed on Linux/macOS):

```bash
cd backend && pytest            # 62 tests, ~6s
```

---

## Validating the strategy (the part that matters)

Run these in order. Stop as soon as a step fails — there is no point tuning
parameters on top of a strategy with no edge.

```bash
# 1. cache at least a year of candles for several symbols
python download_history.py

# 2. in-sample backtest WITH costs — read `verdict`, not `win_rate`
curl -X POST http://127.0.0.1:8000/api/backtest/run \
  -H "X-Auth-Token: $AUTH_TOKEN" -H "Content-Type: application/json" \
  -d '{"symbols":["XAUUSD"],"timeframe":"H1"}'

# 3. out-of-sample walk-forward (5 expanding folds)
curl -X POST http://127.0.0.1:8000/api/backtest/walkforward \
  -H "X-Auth-Token: $AUTH_TOKEN" -H "Content-Type: application/json" \
  -d '{"symbol":"XAUUSD","timeframe":"H1","n_splits":5}'

# 4. is the entry logic better than random entries with identical exits?
curl -X POST http://127.0.0.1:8000/api/backtest/montecarlo \
  -H "X-Auth-Token: $AUTH_TOKEN" -H "Content-Type: application/json" \
  -d '{"symbol":"XAUUSD","n_sims":500}'

# 5. only then consider the ML filter
python -m ml.train --symbol XAUUSD --min-samples 1000
python -m ml.train --symbol XAUUSD --report-only      # threshold ladder
```

### What the metrics mean

| Metric | Why it matters |
|---|---|
| `expectancy_r` | Average profit per trade in units of risk. **The** number. |
| `breakeven_win_rate` | Win rate you need at your payoff ratio. Compare with `win_rate`. |
| `profit_factor` | Gross profit ÷ gross loss. < 1.3 leaves no room for error. |
| `t_stat` | Expectancy ÷ its standard error. < 2.0 means "not distinguishable from noise". |
| `max_drawdown_r` | Worst peak-to-trough in R. Decide your account size from this. |
| `total_cost_r` | How much spread + commission cost you in total. |
| `verdict` | Plain-English reading of the above. |

The Monte-Carlo step answers a question most backtests never ask: *is my entry
logic better than entering at random with the same stop/target rules?* If your
expectancy sits near the median of that distribution, you are not trading a
signal — you are trading the exit rule and the market's drift.

---

## Configuration

All settings live in `backend/.env` (see `.env.example`) and are read once by
`core/config.py`.

| Group | Keys |
|---|---|
| Mode | `TRADING_MODE` (`paper`\|`live`), `AUTH_TOKEN` |
| Instruments | `STREAM_SYMBOLS`, `HEATMAP_SYMBOLS`, `ALLOWED_SYMBOLS`, `ALLOWED_DIRECTIONS` |
| Sizing | `MAX_LOT_SIZE`, `DEFAULT_LOT_SIZE` |
| Strategy | `MIN_SCORE`, `MIN_CONFLUENCES`, `STRONGER_BY`, `MIN_CONFIDENCE`, `SL_ATR_MULT`, `TP_ATR_MULT`, `MAX_BARS_HELD` |
| Costs | `SPREAD_POINTS`, `COMMISSION_R`, `SLIPPAGE_POINTS` |
| Risk | `MAX_CONCURRENT_POSITIONS`, `COOLDOWN_SECONDS`, `MAX_TRADES_PER_DAY`, `MAX_DAILY_LOSS_PCT`, `MAX_SPREAD_POINTS` |
| ML | `USE_ML`, `ML_THRESHOLD`, `ML_MIN_SAMPLES` |

`TRADING_MODE=paper` never reaches the broker: order functions return a
simulated fill and write it to the audit log, so the whole stack (engine, risk,
UI, ML) can be exercised safely. Switching to `live` with the default token is
refused at startup.

---

## Safety

Server-side, always enforced before an order is built:

- **Kill switch** — `POST /api/risk/kill` stops all new orders immediately; the
  state survives restarts. `POST /api/risk/reset` re-arms.
- **Daily loss limit** — trips the kill switch at `MAX_DAILY_LOSS_PCT` of the
  day's starting balance or at `-MAX_DAILY_LOSS_R`.
- **Position & trade caps** — `MAX_CONCURRENT_POSITIONS` counts *positions*
  (the old code counted distinct symbols, so it could never fire on a
  single-symbol watchlist), plus `MAX_TRADES_PER_DAY`.
- **Cooldown, spread filter, volume validation, per-symbol de-duplication.**
- **Audit log** — every order attempt, accepted or rejected.

---

## What changed in v0.6

Correctness

- Backtest now charges the spread (half on entry, half on exit) and a
  commission in R. The old engine defined `SPREAD_PIPS` and never used it.
- Backtest position management matches live: concurrent-position cap, cooldown
  between entries, direction allow-list, one confidence threshold.
- `max_concurrent` counted distinct symbols; it now counts positions.
- Removed the hardcoded `if signal != "BUY": return` from the engine and the
  backtest — direction filtering is configuration.
- ML: the live path fed the model the signal bar itself (one-bar look-ahead)
  while training excluded it; both now use the 50 candles *before* the bar.
- All blocking MT5 calls moved off the asyncio loop (`asyncio.to_thread`) —
  they used to freeze every WebSocket client.
- SQLite: one persistent WAL connection per thread (the old code opened a new
  connection per backtest trade), versioned schema, audit and risk tables.
- `ML_MIN_SAMPLES` guard, purged/embargoed splits, permutation-tested AUC, and
  a threshold ladder — the model report now says whether the filter is worth
  anything instead of just printing an accuracy figure.

New

- `backtest/metrics.py` — expectancy, profit factor, payoff, break-even win
  rate, max drawdown, Sharpe/Sortino, longest losing streak, t-statistic, and a
  plain-English verdict.
- `backtest/walkforward.py` — expanding-window out-of-sample validation.
- `backtest/montecarlo.py` — random-entry benchmark with a percentile rank.
- `risk.py` + `/api/risk/*` — kill switch, daily limits, audit log.
- `TRADING_MODE=paper` with simulated fills.
- `Validation` tab in the UI; `Risk` tab with kill/reset.
- 62 tests and a GitHub Actions workflow.

Repository hygiene: removed committed `__pycache__`, a stale 382-line copy of
an old `smc.py`, `status.txt`, `New Text Document.txt`, an empty `frontend/0`,
`tsconfig.tsbuildinfo`, a committed `.env.local`, and a duplicated zustand
store. Pinned Next.js to a patched release.

---

## Known limitations

- Windows-only: MT5's python package does not run elsewhere. The backend
  imports are stubbed in tests so CI can run on Linux.
- Backtest fills stops/targets at the exact level — no partial fills, no
  gap-through-slippage beyond the configurable spread, no swap.
- One timeframe for the signal engine (H1); multi-timeframe confluence is the
  obvious next feature.
- Live trades are journalled from MT5 deal history, so the equity curve is only
  as complete as that window (`TRADE_LOGGER_LOOKBACK_DAYS`).
- The ML filter can only re-weight signals the strategy already produces. If
  the underlying expectancy is negative, no model will fix it.

## Roadmap

1. Multi-symbol, multi-timeframe validation before any live deployment.
2. Realistic slippage model + variable spread by session.
3. Parameter-free regime filter instead of hand-tuned confluence weights.
4. Portfolio-level risk (correlated exposure, per-symbol allocation).
5. Export backtest reports to HTML/PDF for a research journal.
