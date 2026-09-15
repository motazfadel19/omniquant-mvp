"use client";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Activity, Dices, Play, Shuffle } from "lucide-react";
import { api } from "@/lib/api";
import { useStore } from "@/store/useStore";

const num = (v: number | null | undefined, d = 2) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : v.toFixed(d);

function Metric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded border border-white/5 bg-black/20 px-2 py-1.5">
      <div className="text-[9px] uppercase tracking-wider text-text-muted">{label}</div>
      <div className={`num text-sm font-semibold ${tone ?? "text-text-primary"}`}>{value}</div>
    </div>
  );
}

function Sparkline({ points }: { points: { time: number; equity_r: number }[] }) {
  if (!points || points.length < 2) return null;
  const ys = points.map((p) => p.equity_r);
  const min = Math.min(...ys, 0);
  const max = Math.max(...ys, 0);
  const span = max - min || 1;
  const w = 560;
  const h = 90;
  const d = points
    .map((p, i) => {
      const x = (i / (points.length - 1)) * w;
      const y = h - ((p.equity_r - min) / span) * h;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const zeroY = h - ((0 - min) / span) * h;

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-[90px]">
      <line x1="0" y1={zeroY} x2={w} y2={zeroY} stroke="rgba(255,255,255,0.15)" strokeDasharray="4 4" />
      <path d={d} fill="none" stroke="#22c55e" strokeWidth="1.6" />
    </svg>
  );
}

export default function ValidationPanel() {
  const { symbol, timeframe } = useStore();

  const { data: cached, refetch } = useQuery({
    queryKey: ["bt-metrics"],
    queryFn: () => api.backtestMetrics(),
    refetchInterval: 60_000,
  });

  const [lastRun, setLastRun] = useState<any>(null);

  const run = useMutation({
    mutationFn: () => api.backtestRun({ symbols: [symbol], timeframe }),
    onSuccess: (res) => {
      setLastRun(res);
      refetch();
    },
  });

  const wf = useMutation({
    mutationFn: () => api.walkForward({ symbol, timeframe, n_splits: 5, tune: false }),
  });

  const mc = useMutation({
    mutationFn: () => api.monteCarlo({ symbol, timeframe, n_sims: 300 }),
  });

  const m = lastRun ?? (run.data as any) ?? cached;

  return (
    <>
      <div className="panel-title flex items-center justify-between">
        <span className="flex items-center gap-1.5">
          <Activity size={12} /> Validation
        </span>
        <div className="flex gap-1.5">
          <button
            onClick={() => run.mutate()}
            disabled={run.isPending}
            className="flex items-center gap-1 rounded border border-white/10 px-2 py-0.5 text-[10px] hover:bg-white/10 disabled:opacity-40"
          >
            <Play size={10} /> {run.isPending ? "running…" : "backtest"}
          </button>
          <button
            onClick={() => wf.mutate()}
            disabled={wf.isPending}
            className="flex items-center gap-1 rounded border border-white/10 px-2 py-0.5 text-[10px] hover:bg-white/10 disabled:opacity-40"
          >
            <Shuffle size={10} /> {wf.isPending ? "running…" : "walk-forward"}
          </button>
          <button
            onClick={() => mc.mutate()}
            disabled={mc.isPending}
            className="flex items-center gap-1 rounded border border-white/10 px-2 py-0.5 text-[10px] hover:bg-white/10 disabled:opacity-40"
          >
            <Dices size={10} /> {mc.isPending ? "running…" : "vs random"}
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-3 space-y-3 text-xs">
        {run.isError && (
          <div className="rounded border border-accent-red/40 bg-accent-red/10 p-2 text-accent-red">
            {(run.error as Error).message}
          </div>
        )}

        {m && m.n_trades > 0 && (
          <>
            <div
              className={`rounded border px-2 py-1.5 ${
                String(m.verdict).startsWith("EDGE")
                  ? "border-accent-green/40 bg-accent-green/10 text-accent-green"
                  : String(m.verdict).startsWith("NEGATIVE")
                  ? "border-accent-red/40 bg-accent-red/10 text-accent-red"
                  : "border-accent-yellow/40 bg-accent-yellow/10 text-accent-yellow"
              }`}
            >
              {m.verdict}
            </div>

            <div className="grid grid-cols-4 gap-1.5">
              <Metric label="Trades" value={String(m.n_trades)} />
              <Metric
                label="Expectancy"
                value={`${num(m.expectancy_r, 3)}R`}
                tone={(m.expectancy_r ?? 0) > 0 ? "text-accent-green" : "text-accent-red"}
              />
              <Metric label="Win rate" value={`${num(m.win_rate, 1)}%`} />
              <Metric label="Break-even WR" value={`${num(m.breakeven_win_rate, 1)}%`} />
              <Metric label="Profit factor" value={num(m.profit_factor)} />
              <Metric label="Max DD" value={`${num(m.max_drawdown_r, 1)}R`} tone="text-accent-red" />
              <Metric label="Sharpe" value={num(m.sharpe)} />
              <Metric label="t-stat" value={num(m.t_stat)} />
              <Metric label="Total R" value={`${num(m.total_r, 1)}`} />
              <Metric label="Cost drag" value={`${num(m.total_cost_r, 1)}R`} tone="text-accent-yellow" />
              <Metric label="Avg win" value={`${num(m.avg_win_r, 2)}R`} />
              <Metric label="Worst streak" value={String(m.longest_losing_streak)} />
            </div>

            <Sparkline points={m.equity_curve ?? []} />

            {m.by_direction && (
              <div>
                <div className="mb-1 text-[10px] uppercase tracking-wider text-text-muted">
                  By direction
                </div>
                <table className="w-full text-[11px]">
                  <thead className="text-text-muted">
                    <tr>
                      <th className="text-left">Side</th>
                      <th className="text-right">N</th>
                      <th className="text-right">WR</th>
                      <th className="text-right">Avg R</th>
                    </tr>
                  </thead>
                  <tbody className="num">
                    {m.by_direction.map((r: any) => (
                      <tr key={r.bucket}>
                        <td className="text-left">{r.bucket}</td>
                        <td className="text-right">{r.count}</td>
                        <td className="text-right">{num(r.win_rate, 1)}%</td>
                        <td
                          className={`text-right ${
                            r.avg_r > 0 ? "text-accent-green" : "text-accent-red"
                          }`}
                        >
                          {num(r.avg_r, 3)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        {wf.data && (
          <div className="rounded border border-white/5 bg-black/20 p-2">
            <div className="mb-1 text-[10px] uppercase tracking-wider text-text-muted">
              Walk-forward (out-of-sample)
            </div>
            {wf.data.error ? (
              <div className="text-accent-red">{wf.data.error}</div>
            ) : (
              <>
                <div className="mb-1">
                  Aggregated OOS:{" "}
                  <span
                    className={
                      (wf.data.aggregated_oos?.expectancy_r ?? 0) > 0
                        ? "text-accent-green"
                        : "text-accent-red"
                    }
                  >
                    {num(wf.data.aggregated_oos?.expectancy_r, 3)}R
                  </span>{" "}
                  over {wf.data.aggregated_oos?.n_trades} trades ·{" "}
                  {wf.data.positive_folds}/{wf.data.n_splits} folds positive
                </div>
                <table className="w-full text-[11px]">
                  <tbody className="num">
                    {wf.data.folds.map((f: any) => (
                      <tr key={f.fold}>
                        <td className="text-left">fold {f.fold}</td>
                        <td className="text-right">{f.oos.n_trades} trades</td>
                        <td
                          className={`text-right ${
                            (f.oos.expectancy_r ?? 0) > 0 ? "text-accent-green" : "text-accent-red"
                          }`}
                        >
                          {num(f.oos.expectancy_r, 3)}R
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
        )}

        {mc.data && (
          <div className="rounded border border-white/5 bg-black/20 p-2">
            <div className="mb-1 text-[10px] uppercase tracking-wider text-text-muted">
              vs random entries (same exits)
            </div>
            {mc.data.error ? (
              <div className="text-accent-red">{mc.data.error}</div>
            ) : (
              <>
                <div>
                  Random baseline: {num(mc.data.mean_expectancy_r, 3)}R · yours{" "}
                  {num(mc.data.actual_expectancy_r, 3)}R · percentile{" "}
                  <b>{num(mc.data.percentile_of_actual, 1)}</b>
                </div>
                <div
                  className={
                    String(mc.data.verdict).startsWith("BEATS")
                      ? "text-accent-green"
                      : "text-accent-red"
                  }
                >
                  {mc.data.verdict}
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </>
  );
}
