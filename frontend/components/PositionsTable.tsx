"use client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useStore } from "@/store/useStore";
import { tradingApi } from "@/lib/api";
import { fmtMoney, fmtNum } from "@/lib/format";
import { X, Loader2 } from "lucide-react";

export default function PositionsTable() {
  const qc = useQueryClient();
  const { positions, ticks, account } = useStore();
  const [closing, setClosing] = useState<number | null>(null);

  const closeMutation = useMutation({
    mutationFn: (ticket: number) => tradingApi.closeOrder(ticket),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["positions"] });
      setClosing(null);
    },
    onError: () => setClosing(null),
  });

  const rows = positions.map((p) => {
    const t = ticks[p.symbol];
    const cur = t ? (p.type === "BUY" ? t.bid : t.ask) : p.open_price;
    return { ...p, current: cur };
  });

  const totalPnl = rows.reduce((s, r) => s + r.profit, 0);

  const handleClose = (ticket: number) => {
    if (!confirm(`Close position #${ticket}?`)) return;
    setClosing(ticket);
    closeMutation.mutate(ticket);
  };

  return (
    <>
      <div className="panel-title flex items-center justify-between">
        <span>Open Positions ({rows.length})</span>
        <span
          className={`num text-xs ${
            totalPnl >= 0 ? "text-accent-green" : "text-accent-red"
          }`}
        >
          {fmtMoney(totalPnl, account?.currency ?? "USD")}
        </span>
      </div>

      <div className="flex-1 overflow-auto">
        <table className="w-full text-xs num">
          <thead className="sticky top-0 bg-bg-panel z-10">
            <tr className="text-text-muted text-[10px] uppercase tracking-wider">
              <th className="text-left px-3 py-2">Symbol</th>
              <th className="text-left px-2 py-2">Type</th>
              <th className="text-right px-2 py-2">Vol</th>
              <th className="text-right px-2 py-2">Open</th>
              <th className="text-right px-2 py-2">Current</th>
              <th className="text-right px-2 py-2">P&L</th>
              <th className="w-8"></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} className="text-center text-text-muted py-8 text-xs">
                  No open positions
                </td>
              </tr>
            )}
            {rows.map((r) => (
              <tr
                key={r.ticket}
                className="border-t border-border hover:bg-bg-hover transition group"
              >
                <td className="px-3 py-2 font-mono">{r.symbol}</td>
                <td
                  className={`px-2 py-2 font-semibold ${
                    r.type === "BUY" ? "text-accent-green" : "text-accent-red"
                  }`}
                >
                  {r.type}
                </td>
                <td className="text-right px-2 py-2">{fmtNum(r.volume, 2)}</td>
                <td className="text-right px-2 py-2 text-text-secondary">
                  {fmtNum(r.open_price, 5)}
                </td>
                <td className="text-right px-2 py-2">{fmtNum(r.current, 5)}</td>
                <td
                  className={`text-right px-2 py-2 font-semibold ${
                    r.profit >= 0 ? "text-accent-green" : "text-accent-red"
                  }`}
                >
                  {fmtMoney(r.profit, account?.currency ?? "USD")}
                </td>
                <td className="pr-2 py-1">
                  <button
                    onClick={() => handleClose(r.ticket)}
                    disabled={closing === r.ticket}
                    className="opacity-0 group-hover:opacity-100 transition w-6 h-6 flex items-center justify-center rounded hover:bg-accent-red/20 text-accent-red"
                    title="Close position"
                  >
                    {closing === r.ticket ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <X className="w-3.5 h-3.5" />
                    )}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}