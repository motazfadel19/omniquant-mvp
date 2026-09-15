"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertOctagon, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { useStore } from "@/store/useStore";
import { fmtMoney, fmtPct } from "@/lib/format";
import ConfirmModal from "./ConfirmModal";
import { useState } from "react";

export default function RiskPanel() {
  const qc = useQueryClient();
  const { account, positions } = useStore();
  const [confirmKill, setConfirmKill] = useState(false);

  const { data: risk } = useQuery({
    queryKey: ["risk-status"],
    queryFn: api.riskStatus,
    refetchInterval: 5000,
  });

  const kill = useMutation({
    mutationFn: () => api.riskKill("manual from UI"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["risk-status"] });
      setConfirmKill(false);
    },
  });

  const reset = useMutation({
    mutationFn: api.riskReset,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["risk-status"] }),
  });

  const balance = account?.balance ?? 0;
  const equity = account?.equity ?? 0;
  const margin = account?.margin ?? 0;
  const freeMargin = equity - margin;
  const marginLevel = margin > 0 ? (equity / margin) * 100 : 0;
  const floatPnl = positions.reduce((s, p) => s + p.profit, 0);
  const riskPct = balance > 0 ? (margin / balance) * 100 : 0;

  const Row = ({ label, value, color }: { label: string; value: string; color?: string }) => (
    <div className="flex items-center justify-between py-1.5 text-xs">
      <span className="text-text-secondary">{label}</span>
      <span className={`num font-semibold ${color ?? ""}`}>{value}</span>
    </div>
  );

  const killed = risk?.kill_switch ?? false;
  const mode = risk?.trading_mode ?? "?";

  return (
    <>
      <div className="panel-title flex items-center justify-between">
        <span>Risk Monitor</span>
        <span
          className={`normal-case tracking-normal text-[10px] px-2 py-0.5 rounded ${
            killed
              ? "bg-accent-red/20 text-accent-red"
              : mode === "live"
              ? "bg-accent-yellow/20 text-accent-yellow"
              : "bg-accent-green/20 text-accent-green"
          }`}
        >
          {killed ? "HALTED" : mode.toUpperCase()}
        </span>
      </div>

      <div className="flex-1 overflow-auto px-3 py-1">
        {killed && (
          <div className="my-2 rounded border border-accent-red/40 bg-accent-red/10 px-2 py-1.5 text-[11px] text-accent-red">
            {risk?.kill_reason || "Kill switch engaged"} — no new orders until reset.
          </div>
        )}

        <Row
          label="Float P&L"
          value={fmtMoney(floatPnl, account?.currency ?? "USD")}
          color={floatPnl >= 0 ? "text-accent-green" : "text-accent-red"}
        />
        <Row label="Free Margin" value={fmtMoney(freeMargin, account?.currency ?? "USD")} />
        <Row
          label="Margin Level"
          value={marginLevel > 0 ? `${marginLevel.toFixed(1)}%` : "—"}
          color={marginLevel > 0 && marginLevel < 200 ? "text-accent-red" : "text-text-primary"}
        />
        <Row
          label="Risk Usage"
          value={fmtPct(riskPct, 1)}
          color={riskPct > 30 ? "text-accent-yellow" : ""}
        />
        <div className="my-1 border-t border-white/5" />
        <Row
          label="Realized Today"
          value={fmtMoney(risk?.realized_today ?? 0, account?.currency ?? "USD")}
          color={(risk?.realized_today ?? 0) < 0 ? "text-accent-red" : "text-accent-green"}
        />
        <Row label="Trades Today" value={`${risk?.trades_today ?? 0} / ${risk?.limits?.max_trades_per_day ?? "?"}`} />
        <Row label="Open Trades" value={`${positions.length} / ${risk?.limits?.max_concurrent_positions ?? "?"}`} />
        <Row label="Leverage" value={account ? `1:${account.leverage}` : "—"} />

        <div className="mt-2 flex gap-2">
          <button
            onClick={() => setConfirmKill(true)}
            disabled={killed || kill.isPending}
            className="flex-1 flex items-center justify-center gap-1 rounded border border-accent-red/40 px-2 py-1.5 text-[11px] font-semibold text-accent-red hover:bg-accent-red/10 disabled:opacity-40"
          >
            <AlertOctagon size={12} /> KILL
          </button>
          <button
            onClick={() => reset.mutate()}
            disabled={!killed || reset.isPending}
            className="flex-1 flex items-center justify-center gap-1 rounded border border-accent-green/40 px-2 py-1.5 text-[11px] font-semibold text-accent-green hover:bg-accent-green/10 disabled:opacity-40"
          >
            <ShieldCheck size={12} /> RESET
          </button>
        </div>
      </div>

      <ConfirmModal
        open={confirmKill}
        title="Trip the kill switch?"
        message="The engine will stop sending orders immediately. Open positions are left untouched."
        confirmLabel="Halt trading"
        danger
        onConfirm={() => kill.mutate()}
        onCancel={() => setConfirmKill(false)}
      />
    </>
  );
}
