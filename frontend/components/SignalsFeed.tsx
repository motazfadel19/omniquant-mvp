"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { fmtNum, fmtTime } from "@/lib/format";
import { ArrowUp, ArrowDown } from "lucide-react";

export default function SignalsFeed() {
  const { data } = useQuery({
    queryKey: ["signals"],
    queryFn: () => api.signals(15),
    refetchInterval: 5000,
  });

  const signals = data?.signals ?? [];

  return (
    <>
      <div className="panel-title">Signals Feed</div>
      <div className="flex-1 overflow-auto divide-y divide-border">
        {signals.length === 0 && (
          <div className="text-center text-text-muted py-8 text-xs">
            No signals yet
          </div>
        )}
        {signals.map(s => {
          const up = s.direction === "BUY";
          return (
            <div key={s.id} className="px-3 py-2 flex items-center justify-between text-xs hover:bg-bg-hover transition">
              <div className="flex items-center gap-2">
                {up ? (
                  <ArrowUp className="w-3.5 h-3.5 text-accent-green" />
                ) : (
                  <ArrowDown className="w-3.5 h-3.5 text-accent-red" />
                )}
                <span className="font-mono font-semibold">{s.symbol}</span>
              </div>
              <div className="flex items-center gap-3 num text-[11px]">
                <span className="text-text-secondary">{fmtNum(s.price, 5)}</span>
                <span className={`${up ? "text-accent-green" : "text-accent-red"} font-semibold`}>
                  {s.direction}
                </span>
                <span className="text-text-muted">{fmtTime(s.created_at)}</span>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}