"use client";
import { useStore } from "@/store/useStore";
import { fmtMoney, fmtPct } from "@/lib/format";

export default function RiskPanel() {
  const { account, positions } = useStore();

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

  return (
    <>
      <div className="panel-title">Risk Monitor</div>
      <div className="flex-1 overflow-auto px-3 py-1">
        <Row
          label="Float P&L"
          value={fmtMoney(floatPnl, account?.currency ?? "USD")}
          color={floatPnl >= 0 ? "text-accent-green" : "text-accent-red"}
        />
        <Row label="Free Margin" value={fmtMoney(freeMargin, account?.currency ?? "USD")} />
        <Row
          label="Margin Level"
          value={marginLevel > 0 ? `${marginLevel.toFixed(1)}%` : "—"}
          color={
            marginLevel > 0 && marginLevel < 200
              ? "text-accent-red"
              : "text-text-primary"
          }
        />
        <Row
          label="Risk Usage"
          value={fmtPct(riskPct, 1)}
          color={riskPct > 30 ? "text-accent-yellow" : ""}
        />
        <Row label="Leverage" value={account ? `1:${account.leverage}` : "—"} />
        <Row label="Open Trades" value={String(positions.length)} />
      </div>
    </>
  );
}