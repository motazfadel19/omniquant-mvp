"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fmtTime } from "@/lib/format";
import { api } from "@/lib/api";
import {
  Brain, Play, Square, Zap, AlertTriangle, CheckCircle2, XCircle, Database,
} from "lucide-react";

export default function AIEnginePanel() {
  const qc = useQueryClient();
  const [confirmAuto, setConfirmAuto] = useState(false);

  // ==== Queries ====

  const { data: status } = useQuery({
    queryKey: ["ai-status"],
    queryFn: api.aiStatus,
    refetchInterval: 3000,
  });

  const { data: analysis } = useQuery({
    queryKey: ["ai-analysis"],
    queryFn: api.aiAnalysis,
    refetchInterval: 5000,
  });

  const { data: decisions } = useQuery({
    queryKey: ["ai-decisions"],
    queryFn: () => api.aiDecisions(15),
    refetchInterval: 5000,
  });

  // ✅ اسم مختلف — لا تعارض
  const { data: dataStats } = useQuery({
    queryKey: ["data-stats"],
    queryFn: api.dataStats,
    refetchInterval: 30_000,
  });

  // ==== Mutations ====

  const { data: risk } = useQuery({
    queryKey: ["risk-status-ai"],
    queryFn: api.riskStatus,
    refetchInterval: 10_000,
  });

  const toggle = useMutation({
    mutationFn: (running: boolean) => (running ? api.aiStop() : api.aiStart()),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ai-status"] }),
  });

  const toggleAuto = useMutation({
    mutationFn: (enabled: boolean) =>
      api.aiAuto(enabled),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ai-status"] });
      setConfirmAuto(false);
    },
  });

  // ==== Derived ====

  const running = status?.running ?? false;
  const auto = status?.auto_execute ?? false;
  const aiStats = status?.stats ?? {};        // ✅ اسم أوضح
  const analysisList = Object.values(analysis?.analysis ?? {});

  return (
    <>
      <div className="panel-title flex items-center justify-between">
        <span className="flex items-center gap-1.5">
          <Brain className="w-3 h-3" />
          AI Engine
        </span>
        <span
          className={`text-[10px] normal-case tracking-normal ${
            running ? "text-accent-green" : "text-text-muted"
          }`}
        >
          {running ? "● analyzing" : "idle"}
        </span>
      </div>

      <div className="flex-1 overflow-auto p-2 space-y-2 text-xs">
        {/* Controls */}
        <div className="grid grid-cols-2 gap-1.5">
          <button
            onClick={() => toggle.mutate(running)}
            className={`py-1.5 rounded text-[11px] font-semibold flex items-center justify-center gap-1 transition ${
              running
                ? "bg-accent-red/20 text-accent-red border border-accent-red/40 hover:bg-accent-red/30"
                : "bg-accent-green/20 text-accent-green border border-accent-green/40 hover:bg-accent-green/30"
            }`}
          >
            {running ? (
              <>
                <Square className="w-3 h-3" /> Stop
              </>
            ) : (
              <>
                <Play className="w-3 h-3" /> Start
              </>
            )}
          </button>

          <button
            onClick={() => {
              if (!auto) setConfirmAuto(true);
              else toggleAuto.mutate(false);
            }}
            className={`py-1.5 rounded text-[11px] font-semibold flex items-center justify-center gap-1 transition ${
              auto
                ? "bg-accent-yellow/20 text-accent-yellow border border-accent-yellow/40"
                : "bg-bg-card border border-border text-text-secondary hover:text-text-primary"
            }`}
          >
            <Zap className="w-3 h-3" />
            {auto ? "Auto ON" : "Auto OFF"}
          </button>
        </div>

        {/* AI Cycle Stats */}
        <div className="grid grid-cols-3 gap-1.5 text-[10px]">
          <div className="bg-bg-card rounded p-1.5">
            <div className="text-text-muted">Signals</div>
            <div className="num font-semibold text-accent-blue">
              {aiStats.signals_generated ?? 0}
            </div>
          </div>
          <div className="bg-bg-card rounded p-1.5">
            <div className="text-text-muted">Executed</div>
            <div className="num font-semibold text-accent-green">
              {aiStats.signals_executed ?? 0}
            </div>
          </div>
          <div className="bg-bg-card rounded p-1.5">
            <div className="text-text-muted">Rejected</div>
            <div className="num font-semibold text-accent-red">
              {aiStats.signals_rejected ?? 0}
            </div>
          </div>
        </div>

        {/* ML Data progress */}
        {dataStats && (
          <div className="bg-bg-card rounded p-2">
            <div className="flex items-center justify-between mb-1">
              <span className="flex items-center gap-1 text-[10px] text-text-muted">
                <Database className="w-3 h-3" />
                ML Data
              </span>
              <span className="text-[10px] num text-text-secondary">
                {dataStats.backtest_trades ?? 0}/{dataStats.ml_min_samples ?? 1000}
              </span>
            </div>
            <div className="h-1 bg-bg-base rounded-full overflow-hidden">
              <div
                className={`h-full transition-all ${
                  dataStats.ml_ready ? "bg-accent-green" : "bg-accent-blue"
                }`}
                style={{ width: `${Math.min(dataStats.progress_pct ?? 0, 100)}%` }}
              />
            </div>
            <div className="flex items-center justify-between mt-1 text-[9px] text-text-muted">
              <span>
                Signals: <span className="num">{dataStats.signals ?? 0}</span>
              </span>
              <span>
                Live trades: <span className="num">{dataStats.trades ?? 0}</span>
              </span>
              <span>
                Candles:{" "}
                <span className="num">
                  {Math.round((dataStats.candles ?? 0) / 1000)}k
                </span>
              </span>
            </div>
            {dataStats.ml_ready && (
              <div className="mt-1 text-[9px] text-accent-green text-center">
                ✅ Ready for ML training
              </div>
            )}
          </div>
        )}

        {/* Analysis per symbol */}
        <div className="space-y-1 max-h-[90px] overflow-auto">
          {analysisList.length === 0 && (
            <div className="text-center text-text-muted py-2 text-[10px]">
              {running ? "Analyzing…" : "Start engine to analyze"}
            </div>
          )}
          {analysisList.map((a: any) => {
            const conf = a.confidence ?? 0;
            const dir = a.signal;
            return (
              <div
                key={a.symbol}
                className="flex items-center justify-between bg-bg-card rounded px-2 py-1 text-[10px]"
              >
                <span className="font-mono">{a.symbol}</span>
                {dir ? (
                  <div className="flex items-center gap-1.5">
                    <span
                      className={`font-semibold ${
                        dir === "BUY" ? "text-accent-green" : "text-accent-red"
                      }`}
                    >
                      {dir}
                    </span>
                    <span className="num text-text-secondary">
                      {(conf * 100).toFixed(0)}%
                    </span>
                  </div>
                ) : (
                  <span className="text-text-muted">no signal</span>
                )}
              </div>
            );
          })}
        </div>

        {/* Recent decisions */}
        <div className="border-t border-border pt-1.5">
          <div className="text-[10px] text-text-muted mb-1">Recent Decisions</div>
          <div className="space-y-0.5 max-h-[80px] overflow-auto">
            {(decisions?.decisions ?? []).length === 0 && (
              <div className="text-center text-text-muted py-1 text-[10px]">
                none
              </div>
            )}
            {(decisions?.decisions ?? []).map((d, i) => (
              <div key={i} className="flex items-center gap-1.5 text-[9px] py-0.5">
                {d.executed ? (
                  <CheckCircle2 className="w-2.5 h-2.5 text-accent-green shrink-0" />
                ) : d.reason_rejected ? (
                  <XCircle className="w-2.5 h-2.5 text-accent-red shrink-0" />
                ) : (
                  <AlertTriangle className="w-2.5 h-2.5 text-accent-yellow shrink-0" />
                )}
                <span className="font-mono">{d.symbol}</span>
                <span
                  className={
                    d.direction === "BUY"
                      ? "text-accent-green"
                      : "text-accent-red"
                  }
                >
                  {d.direction}
                </span>
                <span className="num text-text-muted">
                  {(d.confidence * 100).toFixed(0)}%
                </span>
                <span className="text-text-muted text-[8px] ml-auto">
                  {fmtTime(d.ts)}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Auto-execute confirm modal */}
      {confirmAuto && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
          onClick={() => setConfirmAuto(false)}
        >
          <div
            className="bg-bg-panel border border-accent-yellow/40 rounded-lg w-[400px] p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-2 mb-3">
              <AlertTriangle className="w-5 h-5 text-accent-yellow" />
              <h3 className="font-semibold">Enable Auto-Execution?</h3>
            </div>
            <div className="text-xs text-text-secondary mb-4 leading-relaxed">
              The AI engine will{" "}
              <strong className="text-accent-yellow">
                automatically open positions
              </strong>{" "}
              when confidence exceeds{" "}
              <strong>
                {((status?.min_confidence ?? 0.65) * 100).toFixed(0)}%
              </strong>
              .
              <br />
              <br />
              Max concurrent:{" "}
              <strong>{risk?.limits?.max_concurrent_positions ?? "—"}</strong> positions
              <br />
              Lot size: <strong>{status?.lot_size ?? 0.01}</strong>
              <br />
              Mode:{" "}
              <strong
                className={
                  status?.trading_mode === "live"
                    ? "text-accent-red"
                    : "text-accent-green"
                }
              >
                {String(status?.trading_mode ?? "?").toUpperCase()}
              </strong>
              <br />
              <br />
              {status?.trading_mode === "live" ? (
                <span className="text-accent-red">This trades real money.</span>
              ) : (
                <span className="text-accent-green">
                  Paper mode: orders are simulated, nothing reaches the broker.
                </span>
              )}{" "}
              Always test on demo first.
            </div>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setConfirmAuto(false)}
                className="px-4 py-2 text-xs rounded border border-border hover:bg-bg-hover"
              >
                Cancel
              </button>
              <button
                onClick={() => toggleAuto.mutate(true)}
                className="px-4 py-2 text-xs rounded bg-accent-yellow text-black font-semibold hover:bg-accent-yellow/90"
              >
                I Understand, Enable
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}