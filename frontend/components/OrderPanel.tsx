"use client";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { tradingApi, Position } from "@/lib/api";
import { useStore } from "@/store/useStore";
import { fmtNum } from "@/lib/format";
import { Loader2, AlertCircle } from "lucide-react";
import ConfirmModal from "./ConfirmModal";

const VOLUME_PRESETS = [0.01, 0.05, 0.10, 0.50];
const MAX_LOT = 0.5;

export default function OrderPanel() {
  const qc = useQueryClient();
  const { symbol, positions } = useStore();

  const [direction, setDirection] = useState<"BUY" | "SELL">("BUY");
  const [volume, setVolume] = useState(0.10);
  const [useSl, setUseSl] = useState(true);
  const [useTp, setUseTp] = useState(true);
  const [slPoints, setSlPoints] = useState(300);
  const [tpPoints, setTpPoints] = useState(600);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // نحدّث الـ volume إذا الرمز تغيّر
  useEffect(() => {
    setError(null);
  }, [symbol]);

  const { data: quote } = useQuery({
    queryKey: ["quote", symbol],
    queryFn: () => tradingApi.quote(symbol),
    refetchInterval: 1000,
  });

  const { data: symbolInfo } = useQuery({
    queryKey: ["symbolInfo", symbol],
    queryFn: () => tradingApi.symbolInfo(symbol),
    staleTime: 60_000,
  });

  const openMutation = useMutation({
    mutationFn: () =>
      tradingApi.openOrder({
        symbol,
        direction,
        volume,
        sl_points: useSl ? slPoints : 0,
        tp_points: useTp ? tpPoints : 0,
      }),
    onSuccess: (res) => {
      setSuccessMsg(
        `✅ ${direction} ${symbol} opened @ ${fmtNum(res.price, 5)} (Ticket #${res.ticket})`
      );
      setConfirmOpen(false);
      qc.invalidateQueries({ queryKey: ["positions"] });
      setTimeout(() => setSuccessMsg(null), 4000);
    },
    onError: (e: Error) => {
      setError(e.message);
      setConfirmOpen(false);
    },
  });

  // نتحقق من صحة الإدخال
  const validate = (): string | null => {
    if (volume <= 0) return "Volume must be positive";
    if (volume > MAX_LOT) return `Volume exceeds max ${MAX_LOT}`;
    const step = symbolInfo?.volume_step ?? 0.01;
    if (Math.abs(volume / step - Math.round(volume / step)) > 1e-6)
      return `Volume must be multiple of ${step}`;
    const stopsLevel = symbolInfo?.stops_level ?? 0;
    if (useSl && slPoints < stopsLevel) return `SL below min ${stopsLevel} pts`;
    if (useTp && tpPoints < stopsLevel) return `TP below min ${stopsLevel} pts`;
    return null;
  };

  const validationError = validate();
  const canSubmit = !validationError && !openMutation.isPending;

  const handleSubmit = () => {
    setError(null);
    const err = validate();
    if (err) {
      setError(err);
      return;
    }
    setConfirmOpen(true);
  };

  const slPrice =
    quote && useSl
      ? direction === "BUY"
        ? quote.ask - slPoints * quote.point
        : quote.bid + slPoints * quote.point
      : null;
  const tpPrice =
    quote && useTp
      ? direction === "BUY"
        ? quote.ask + tpPoints * quote.point
        : quote.bid - tpPoints * quote.point
      : null;

  return (
    <>
      <div className="panel-title flex items-center justify-between">
        <span>New Order</span>
        {quote && (
          <span className="text-text-muted normal-case tracking-normal text-[10px] num">
            {quote.bid.toFixed(quote.digits)} / {quote.ask.toFixed(quote.digits)}
          </span>
        )}
      </div>

      <div className="flex-1 overflow-auto p-3 space-y-3">
        {/* Direction */}
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={() => setDirection("BUY")}
            className={`py-2 rounded text-xs font-semibold transition ${
              direction === "BUY"
                ? "bg-accent-green/20 border border-accent-green text-accent-green"
                : "bg-bg-card border border-border text-text-secondary hover:text-text-primary"
            }`}
          >
            BUY
          </button>
          <button
            onClick={() => setDirection("SELL")}
            className={`py-2 rounded text-xs font-semibold transition ${
              direction === "SELL"
                ? "bg-accent-red/20 border border-accent-red text-accent-red"
                : "bg-bg-card border border-border text-text-secondary hover:text-text-primary"
            }`}
          >
            SELL
          </button>
        </div>

        {/* Volume */}
        <div>
          <label className="text-[10px] uppercase tracking-wider text-text-secondary block mb-1">
            Volume (lot)
          </label>
          <div className="flex items-center gap-2">
            <input
              type="number"
              step={symbolInfo?.volume_step ?? 0.01}
              min={symbolInfo?.volume_min ?? 0.01}
              max={MAX_LOT}
              value={volume}
              onChange={(e) => setVolume(parseFloat(e.target.value) || 0)}
              className="flex-1 bg-bg-card border border-border rounded px-2 py-1.5 text-sm num outline-none focus:border-accent-blue"
            />
            <div className="flex gap-1">
              {VOLUME_PRESETS.map((v) => (
                <button
                  key={v}
                  onClick={() => setVolume(v)}
                  className={`px-1.5 py-1 text-[10px] rounded num transition ${
                    volume === v
                      ? "bg-accent-blue/20 text-accent-blue border border-accent-blue/50"
                      : "bg-bg-card border border-border text-text-muted hover:text-text-primary"
                  }`}
                >
                  {v}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* SL */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-text-secondary cursor-pointer">
              <input
                type="checkbox"
                checked={useSl}
                onChange={(e) => setUseSl(e.target.checked)}
                className="accent-accent-red"
              />
              Stop Loss
            </label>
            {slPrice !== null && quote && (
              <span className="text-[10px] num text-text-muted">
                @ {slPrice.toFixed(quote.digits)}
              </span>
            )}
          </div>
          {useSl && (
            <input
              type="number"
              value={slPoints}
              onChange={(e) => setSlPoints(parseInt(e.target.value) || 0)}
              className="w-full bg-bg-card border border-border rounded px-2 py-1.5 text-sm num outline-none focus:border-accent-red"
              placeholder="points"
            />
          )}
        </div>

        {/* TP */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-text-secondary cursor-pointer">
              <input
                type="checkbox"
                checked={useTp}
                onChange={(e) => setUseTp(e.target.checked)}
                className="accent-accent-green"
              />
              Take Profit
            </label>
            {tpPrice !== null && quote && (
              <span className="text-[10px] num text-text-muted">
                @ {tpPrice.toFixed(quote.digits)}
              </span>
            )}
          </div>
          {useTp && (
            <input
              type="number"
              value={tpPoints}
              onChange={(e) => setTpPoints(parseInt(e.target.value) || 0)}
              className="w-full bg-bg-card border border-border rounded px-2 py-1.5 text-sm num outline-none focus:border-accent-green"
              placeholder="points"
            />
          )}
        </div>

        {/* Errors */}
        {validationError && (
          <div className="flex items-center gap-1.5 text-[10px] text-accent-yellow">
            <AlertCircle className="w-3 h-3" />
            {validationError}
          </div>
        )}
        {error && (
          <div className="flex items-center gap-1.5 text-[10px] text-accent-red">
            <AlertCircle className="w-3 h-3" />
            {error}
          </div>
        )}
        {successMsg && (
          <div className="text-[10px] text-accent-green">{successMsg}</div>
        )}

        {/* Submit */}
        <button
          disabled={!canSubmit}
          onClick={handleSubmit}
          className={`w-full py-2.5 rounded text-sm font-semibold transition flex items-center justify-center gap-2 ${
            !canSubmit
              ? "bg-bg-card text-text-muted cursor-not-allowed"
              : direction === "BUY"
              ? "bg-accent-green text-black hover:bg-accent-green/90"
              : "bg-accent-red text-white hover:bg-accent-red/90"
          }`}
        >
          {openMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
          {direction} {volume} {symbol}
        </button>

        {/* Close All */}
        {positions.length > 0 && (
          <button
            onClick={async () => {
              if (!confirm(`Close ALL ${positions.length} positions?`)) return;
              try {
                const r = await tradingApi.closeAll();
                setSuccessMsg(`✅ Closed ${r.closed}, failed ${r.failed}`);
                qc.invalidateQueries({ queryKey: ["positions"] });
                setTimeout(() => setSuccessMsg(null), 4000);
              } catch (e: any) {
                setError(e.message);
              }
            }}
            className="w-full py-1.5 rounded text-[10px] font-semibold border border-accent-red/40 text-accent-red hover:bg-accent-red/10 transition"
          >
            ⚠ Close All Positions
          </button>
        )}
      </div>

      {/* Confirm Modal */}
      <ConfirmModal
        open={confirmOpen}
        title={`Confirm ${direction} Order`}
        message={
          <div className="space-y-1">
            <div>
              You are about to open a <strong>{direction}</strong> position:
            </div>
            <div className="num bg-bg-card rounded p-2 mt-2 text-xs">
              <div className="flex justify-between">
                <span className="text-text-secondary">Symbol:</span>
                <span>{symbol}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Volume:</span>
                <span>{volume} lots</span>
              </div>
              {quote && (
                <div className="flex justify-between">
                  <span className="text-text-secondary">Price:</span>
                  <span>
                    {(direction === "BUY" ? quote.ask : quote.bid).toFixed(
                      quote.digits
                    )}
                  </span>
                </div>
              )}
              {useSl && slPrice !== null && (
                <div className="flex justify-between">
                  <span className="text-text-secondary">Stop Loss:</span>
                  <span className="text-accent-red">
                    {slPrice.toFixed(quote?.digits ?? 5)} ({slPoints} pts)
                  </span>
                </div>
              )}
              {useTp && tpPrice !== null && (
                <div className="flex justify-between">
                  <span className="text-text-secondary">Take Profit:</span>
                  <span className="text-accent-green">
                    {tpPrice.toFixed(quote?.digits ?? 5)} ({tpPoints} pts)
                  </span>
                </div>
              )}
            </div>
            <div className="text-accent-yellow text-[10px] mt-2">
              ⚠ This action is irreversible. Confirm only if you are sure.
            </div>
          </div>
        }
        confirmLabel={`Yes, ${direction}`}
        danger={direction === "SELL"}
        onConfirm={() => openMutation.mutate()}
        onCancel={() => setConfirmOpen(false)}
      />
    </>
  );
}