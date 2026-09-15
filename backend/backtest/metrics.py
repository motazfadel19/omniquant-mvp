"""
Performance metrics that actually decide whether a strategy is tradeable.

v0.5 reported a win rate and nothing else. Win rate without payoff ratio and
drawdown is a vanity metric: 30% winners at 3R beats 60% winners at 0.8R.
"""
from __future__ import annotations

import math
from typing import Optional


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _stdev(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def equity_curve(trades: list[dict]) -> list[dict]:
    """Cumulative R, in exit order."""
    out, running = [], 0.0
    for t in trades:
        running += float(t.get("profit_r", 0) or 0)
        out.append({"time": t.get("exit_time"), "equity_r": round(running, 4)})
    return out


def max_drawdown(curve: list[dict]) -> tuple[float, float]:
    """Returns (max_dd_in_R, max_dd_in_percent_of_peak)."""
    peak = -1e18
    max_dd_r = 0.0
    max_dd_pct = 0.0
    for point in curve:
        eq = point["equity_r"]
        peak = max(peak, eq)
        dd = peak - eq
        if dd > max_dd_r:
            max_dd_r = dd
            if peak > 0:
                max_dd_pct = dd / peak * 100
    return round(max_dd_r, 4), round(max_dd_pct, 2)


def longest_streak(trades: list[dict], losing: bool = True) -> int:
    best = cur = 0
    for t in trades:
        r = float(t.get("profit_r", 0) or 0)
        hit = (r <= 0) if losing else (r > 0)
        cur = cur + 1 if hit else 0
        best = max(best, cur)
    return best


def compute_metrics(trades: list[dict]) -> dict:
    if not trades:
        return {
            "n_trades": 0,
            "verdict": "NO DATA — run a backtest first",
        }

    rs = [float(t.get("profit_r", 0) or 0) for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r < 0]
    flat = [r for r in rs if r == 0]

    n = len(rs)
    expectancy = _mean(rs)
    sd = _stdev(rs)
    t_stat = (expectancy / (sd / math.sqrt(n))) if sd > 0 and n > 1 else 0.0

    gross_profit = sum(wins)
    gross_loss = -sum(losses)
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    avg_win = _mean(wins)
    avg_loss = _mean(losses) if losses else 0.0
    payoff = (avg_win / abs(avg_loss)) if avg_loss else float("inf")
    breakeven_wr = (1 / (1 + payoff)) if payoff not in (float("inf"), 0) else 0.0
    win_rate = len(wins) / n

    curve = equity_curve(trades)
    dd_r, dd_pct = max_drawdown(curve)

    times = [t.get("exit_time", 0) for t in trades if t.get("exit_time")]
    span_days = (max(times) - min(times)) / 86400 if times and max(times) > min(times) else 0
    trades_per_year = (n / span_days * 365) if span_days > 0 else float(n)
    ann_factor = math.sqrt(max(trades_per_year, 1.0))
    sharpe = (expectancy / sd * ann_factor) if sd > 0 else 0.0

    downside = [r for r in rs if r < 0]
    dd_sd = _stdev(downside) if len(downside) > 1 else 0.0
    sortino = (expectancy / dd_sd * ann_factor) if dd_sd > 0 else 0.0

    total_cost_r = sum(float(t.get("cost_r", 0) or 0) for t in trades)
    gross_r_total = sum(float(t.get("gross_r", 0) or 0) for t in trades)

    # ---- aggregation helpers ----
    def _group(key: str) -> list[dict]:
        buckets: dict[str, list[float]] = {}
        for t in trades:
            k = str(t.get(key, "?"))
            buckets.setdefault(k, []).append(float(t.get("profit_r", 0) or 0))
        return [
            {
                "bucket": k,
                "count": len(v),
                "win_rate": round(sum(1 for x in v if x > 0) / len(v) * 100, 2),
                "avg_r": round(_mean(v), 4),
                "sum_r": round(sum(v), 3),
            }
            for k, v in sorted(buckets.items())
        ]

    # ---- honest verdict ----
    if expectancy <= 0:
        verdict = ("NEGATIVE EXPECTANCY — every additional trade loses money on average. "
                   "Do not fund this.")
    elif n < 100:
        verdict = (f"TOO FEW TRADES ({n}) — a sample this small cannot distinguish skill "
                   f"from luck, whatever the expectancy says")
    elif t_stat < 2.0:
        verdict = (f"NOT STATISTICALLY SIGNIFICANT — expectancy {expectancy:+.3f}R with "
                   f"t={t_stat:.2f} (need >= 2.0). Collect more trades or fewer parameters")
    elif profit_factor is not None and profit_factor < 1.3:
        verdict = (f"MARGINAL — profit factor {profit_factor:.2f} leaves no room for "
                   f"slippage, commission changes or regime shifts")
    else:
        verdict = ("EDGE CANDIDATE — now validate out-of-sample (walk-forward) and on "
                   "other symbols before funding it")

    return {
        "n_trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(flat),
        "win_rate": round(win_rate * 100, 2),
        "breakeven_win_rate": round(breakeven_wr * 100, 2),
        "expectancy_r": round(expectancy, 4),
        "expectancy_r_gross": round(_mean([float(t.get("gross_r", 0) or 0) for t in trades]), 4),
        "total_r": round(sum(rs), 3),
        "total_r_gross": round(gross_r_total, 3),
        "total_cost_r": round(total_cost_r, 3),
        "std_r": round(sd, 4),
        "t_stat": round(t_stat, 3),
        "profit_factor": round(profit_factor, 3) if profit_factor != float("inf") else None,
        "avg_win_r": round(avg_win, 4),
        "avg_loss_r": round(avg_loss, 4),
        "payoff_ratio": round(payoff, 3) if payoff != float("inf") else None,
        "max_drawdown_r": dd_r,
        "max_drawdown_pct": dd_pct,
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
        "longest_losing_streak": longest_streak(trades, losing=True),
        "avg_bars_held": round(_mean([float(t.get("bars_held", 0) or 0) for t in trades]), 2),
        "span_days": round(span_days, 1),
        "trades_per_year": round(trades_per_year, 1),
        "by_exit_reason": _group("exit_reason"),
        "by_direction": _group("direction"),
        "by_symbol": _group("symbol"),
        "equity_curve": curve,
        "verdict": verdict,
    }
