"use client";
import { useStore } from "@/store/useStore";
import { fmtMoney, fmtPct } from "@/lib/format";
import { Activity } from "lucide-react";

const TIMEFRAMES = ["M5", "M15", "H1", "H4", "D1"];

export default function Header() {
  const { account, connected, symbol, setSymbol, timeframe, setTimeframe } = useStore();

  const pnlPct = account && account.balance > 0
    ? ((account.equity - account.balance) / account.balance) * 100
    : 0;

  return (
    <header className="panel flex items-center justify-between px-4 py-3 h-14 shrink-0">
      {/* Left: logo + status */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <Activity className="w-5 h-5 text-accent-green" />
          <span className="font-bold tracking-wide">OMNI<span className="text-accent-green">QUANT</span></span>
        </div>

        <div className="flex items-center gap-1.5 text-[11px] text-text-secondary">
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              connected ? "bg-accent-green animate-pulse-dot" : "bg-accent-red"
            }`}
          />
          {connected ? "LIVE" : "OFFLINE"}
        </div>
      </div>

      {/* Center: symbol + timeframe */}
      <div className="flex items-center gap-4">
        <select
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          className="bg-bg-card border border-border rounded-md px-3 py-1.5 text-sm font-mono outline-none focus:border-accent-blue"
        >
          {["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"].map(s => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>

        <div className="flex items-center gap-0.5 bg-bg-card border border-border rounded-md p-0.5">
          {TIMEFRAMES.map(tf => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={`px-2.5 py-1 text-[11px] font-mono rounded transition ${
                timeframe === tf
                  ? "bg-accent-blue text-white"
                  : "text-text-secondary hover:text-text-primary"
              }`}
            >
              {tf}
            </button>
          ))}
        </div>
      </div>

      {/* Right: account */}
      <div className="flex items-center gap-6 num text-sm">
        <div className="text-right">
          <div className="text-[10px] text-text-secondary uppercase tracking-wider">Balance</div>
          <div className="font-semibold">
            {account ? fmtMoney(account.balance, account.currency) : "—"}
          </div>
        </div>

        <div className="text-right">
          <div className="text-[10px] text-text-secondary uppercase tracking-wider">Equity</div>
          <div className="font-semibold">
            {account ? fmtMoney(account.equity, account.currency) : "—"}
          </div>
        </div>

        <div className="text-right">
          <div className="text-[10px] text-text-secondary uppercase tracking-wider">P&L</div>
          <div className={`font-semibold ${
            pnlPct >= 0 ? "text-accent-green" : "text-accent-red"
          }`}>
            {account ? fmtPct(pnlPct) : "—"}
          </div>
        </div>
      </div>
    </header>
  );
}