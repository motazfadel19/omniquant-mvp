"use client";
import { useStore } from "@/store/useStore";
import { fmtMoney, fmtPct } from "@/lib/format";
import { Activity, KeyRound } from "lucide-react";
import { API_URL, WS_URL } from "@/lib/env";

const TIMEFRAMES = ["M5", "M15", "H1", "H4", "D1"];

type Status = {
  label: string;
  dot: string;
  text: string;
  title: string;
};

function useStatus(): Status {
  const connected = useStore((s) => s.connected);
  const wsError = useStore((s) => s.wsError);
  const api = useStore((s) => s.api);

  if (connected) {
    const mode = (api.tradingMode ?? "?").toUpperCase();
    const halted = api.killSwitch;
    return {
      label: halted ? "HALTED" : "LIVE",
      dot: halted ? "bg-accent-red" : "bg-accent-green animate-pulse-dot",
      text: halted ? "text-accent-red" : "text-accent-green",
      title: [
        `WebSocket: connected (${WS_URL}/ws/market)`,
        `API: ${API_URL}`,
        `Mode: ${mode}`,
        halted ? "Kill switch: ENGAGED" : "Kill switch: clear",
      ].join("\n"),
    };
  }

  if (api.apiUp) {
    return {
      label: "API ONLY",
      dot: "bg-accent-yellow animate-pulse-dot",
      text: "text-accent-yellow",
      title: [
        "The REST API answers but the websocket is not connected.",
        `API: ${API_URL} (ok)`,
        `WS target: ${WS_URL}/ws/market`,
        wsError ?? "",
      ].join("\n"),
    };
  }

  return {
    label: "OFFLINE",
    dot: "bg-accent-red",
    text: "text-accent-red",
    title: [
      "Cannot reach the backend.",
      `Tried: ${API_URL}/api/health`,
      api.apiError ?? "",
      "",
      "Start it with:  cd backend && uvicorn main:app --port 8000",
    ].join("\n"),
  };
}

export default function Header() {
  const { account, symbol, setSymbol, timeframe, setTimeframe } = useStore();
  const authConfigured = useStore((s) => s.api.authConfigured);
  const status = useStatus();

  const pnlPct =
    account && account.balance > 0
      ? ((account.equity - account.balance) / account.balance) * 100
      : 0;

  return (
    <header className="panel flex items-center justify-between px-4 py-3 h-14 shrink-0">
      {/* Left: logo + status */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <Activity className="w-5 h-5 text-accent-green" />
          <span className="font-bold tracking-wide">
            OMNI<span className="text-accent-green">QUANT</span>
          </span>
        </div>

        <div
          className={`flex items-center gap-1.5 text-[11px] cursor-help ${status.text}`}
          title={status.title}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${status.dot}`} />
          {status.label}
        </div>

        {!authConfigured && (
          <div
            className="flex items-center gap-1 text-[10px] text-accent-yellow cursor-help"
            title={
              "NEXT_PUBLIC_AUTH_TOKEN is not set in frontend/.env.local.\n" +
              "Every trading / backtest button will fail with HTTP 401.\n" +
              "It must match AUTH_TOKEN in backend/.env."
            }
          >
            <KeyRound size={11} /> NO TOKEN
          </div>
        )}
      </div>

      {/* Center: symbol + timeframe */}
      <div className="flex items-center gap-4">
        <select
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          className="bg-bg-card border border-border rounded-md px-3 py-1.5 text-sm font-mono outline-none focus:border-accent-blue"
        >
          {["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"].map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>

        <div className="flex items-center gap-0.5 bg-bg-card border border-border rounded-md p-0.5">
          {TIMEFRAMES.map((tf) => (
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
          <div
            className={`font-semibold ${pnlPct >= 0 ? "text-accent-green" : "text-accent-red"}`}
          >
            {account ? fmtPct(pnlPct) : "—"}
          </div>
        </div>
      </div>
    </header>
  );
}
