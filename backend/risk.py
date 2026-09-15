"""
Pre-trade risk guard + kill switch.

v0.5 had *no* hard guardrails: the only protection was a boolean in the UI and a
check that compared `len(set_of_symbols)` against `max_concurrent`, which with a
single-symbol watchlist could never fire.  Everything here is enforced on the
server before an order is ever built.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from core.config import Settings, get_settings
from database import get_conn, get_state, set_state, today_key


@dataclass
class Decision:
    ok: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.ok


class RiskGuard:
    def __init__(self, settings: Optional[Settings] = None):
        self.s = settings or get_settings()
        self.daily_start_balance: float = 0.0
        self._day: str = ""

    # ---------------- kill switch ----------------

    def trip(self, reason: str) -> None:
        set_state("kill_switch", "1")
        set_state("kill_reason", reason)
        print(f"[STOP] KILL SWITCH TRIPPED: {reason}")

    def reset(self) -> None:
        set_state("kill_switch", "0")
        set_state("kill_reason", "")

    def killed(self) -> tuple[bool, str]:
        if get_state("kill_switch", "0") == "1":
            return True, get_state("kill_reason", "") or "kill switch engaged"
        return False, ""

    # ---------------- daily counters ----------------

    def _roll_day(self, balance: float) -> None:
        day = today_key()
        if day != self._day:
            self._day = day
            stored = get_state(f"day_balance:{day}")
            if stored is None:
                set_state(f"day_balance:{day}", balance)
                self.daily_start_balance = balance
            else:
                self.daily_start_balance = float(stored)

    def trades_today(self) -> int:
        day = today_key()
        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS c FROM audit_log
                WHERE action='order.open' AND result LIKE '%"ok": true%'
                  AND ts >= strftime('%s', ?)
                """,
                (day,),
            ).fetchone()
        return int(row["c"]) if row else 0

    def realized_today(self) -> float:
        day = today_key()
        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(profit), 0) AS p FROM trades
                WHERE close_time IS NOT NULL
                  AND close_time >= strftime('%s', ?)
                """,
                (day,),
            ).fetchone()
        return float(row["p"]) if row else 0.0

    # ---------------- the actual gate ----------------

    def check(
        self,
        symbol: str,
        direction: str,
        volume: float,
        positions: list[dict],
        account: Optional[dict],
        symbol_info: Optional[dict],
        last_signal_ts: int = 0,
    ) -> Decision:
        symbol = symbol.upper()
        direction = direction.upper()

        killed, why = self.killed()
        if killed:
            return Decision(False, f"kill switch: {why}")

        if not self.s.is_symbol_allowed(symbol):
            return Decision(False, f"symbol not allowed: {symbol}")
        if not self.s.is_direction_allowed(direction):
            return Decision(False, f"direction not allowed: {direction}")

        if volume <= 0:
            return Decision(False, "volume must be positive")
        if volume > self.s.max_lot_size:
            return Decision(False, f"volume {volume} exceeds max {self.s.max_lot_size}")

        info = symbol_info or {}
        if info:
            vmin = info.get("volume_min", 0.01)
            vmax = info.get("volume_max", 100)
            vstep = info.get("volume_step", 0.01)
            if volume < vmin:
                return Decision(False, f"volume below minimum {vmin}")
            if volume > vmax:
                return Decision(False, f"volume above maximum {vmax}")
            if vstep > 0:
                rounded = round(volume / vstep) * vstep
                if abs(rounded - volume) > 1e-8:
                    return Decision(False, f"volume must be multiple of {vstep}")
            if info.get("trade_mode") == 0:
                return Decision(False, "trading disabled for symbol")
            spread = float(info.get("spread", 0) or 0)
            if spread > self.s.max_spread_points:
                return Decision(False, f"spread too high ({spread} pts)")

        # max concurrent is counted over POSITIONS, not over distinct symbols
        open_count = len([p for p in positions if p.get("symbol")])
        if open_count >= self.s.max_concurrent_positions:
            return Decision(False,
                            f"max_concurrent ({self.s.max_concurrent_positions}) reached")
        if any(p.get("symbol") == symbol for p in positions):
            return Decision(False, "already have a position on this symbol")

        if self.s.cooldown_seconds > 0 and last_signal_ts:
            waited = int(time.time()) - int(last_signal_ts)
            if waited < self.s.cooldown_seconds:
                return Decision(False,
                                f"cooldown: {self.s.cooldown_seconds - waited}s left")

        if self.trades_today() >= self.s.max_trades_per_day:
            return Decision(False, f"max_trades_per_day ({self.s.max_trades_per_day}) reached")

        # daily loss limits
        balance = float((account or {}).get("balance", 0) or 0)
        self._roll_day(balance)
        realized = self.realized_today()
        if balance > 0 and self.s.max_daily_loss_pct > 0:
            loss_pct = -realized / balance * 100
            if loss_pct >= self.s.max_daily_loss_pct:
                self.trip(f"daily loss {loss_pct:.2f}% >= {self.s.max_daily_loss_pct}%")
                return Decision(False, f"daily loss limit hit ({loss_pct:.2f}%)")
        if self.daily_start_balance > 0 and self.s.max_daily_loss_pct > 0:
            dd_pct = -(balance - self.daily_start_balance) / self.daily_start_balance * 100
            if dd_pct >= self.s.max_daily_loss_pct:
                self.trip(f"daily drawdown {dd_pct:.2f}%")
                return Decision(False, f"daily drawdown limit hit ({dd_pct:.2f}%)")

        return Decision(True)

    def status(self, account: Optional[dict] = None) -> dict:
        balance = float((account or {}).get("balance", 0) or 0)
        self._roll_day(balance)
        killed, why = self.killed()
        realized = self.realized_today()
        return {
            "trading_mode": self.s.trading_mode,
            "kill_switch": killed,
            "kill_reason": why,
            "day": self._day or today_key(),
            "day_start_balance": round(self.daily_start_balance, 2),
            "realized_today": round(realized, 2),
            "trades_today": self.trades_today(),
            "limits": {
                "max_concurrent_positions": self.s.max_concurrent_positions,
                "max_trades_per_day": self.s.max_trades_per_day,
                "max_daily_loss_pct": self.s.max_daily_loss_pct,
                "max_lot_size": self.s.max_lot_size,
                "cooldown_seconds": self.s.cooldown_seconds,
                "allowed_symbols": self.s.allowed_symbols,
                "allowed_directions": self.s.allowed_directions,
            },
        }


risk_guard = RiskGuard()
