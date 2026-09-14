"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { fmtPct } from "@/lib/format";

function colorFor(pct: number) {
  const a = Math.min(Math.abs(pct) / 2, 1);
  return pct >= 0
    ? `rgba(0, 224, 143, ${0.15 + a * 0.55})`
    : `rgba(255, 61, 92, ${0.15 + a * 0.55})`;
}

export default function Heatmap() {
  const { data } = useQuery({
    queryKey: ["heatmap"],
    queryFn: api.heatmap,
    refetchInterval: 15_000,
  });

  const items = data?.items ?? [];

  return (
    <>
      <div className="panel-title">Session Heatmap</div>
      <div className="flex-1 p-2 grid grid-cols-3 grid-rows-3 gap-1.5">
        {items.slice(0, 9).map(it => (
          <div
            key={it.symbol}
            className="rounded-md flex flex-col justify-between p-2 transition border border-border/50 hover:border-border-bright"
            style={{ background: colorFor(it.change_pct) }}
          >
            <div className="text-[10px] font-mono text-text-primary/90">
              {it.symbol}
            </div>
            <div className="num text-sm font-bold">
              {fmtPct(it.change_pct, 2)}
            </div>
            <div className="num text-[10px] text-text-secondary">
              {it.price.toFixed(4)}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}