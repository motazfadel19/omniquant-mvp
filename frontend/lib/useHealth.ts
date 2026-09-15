"use client";
import { useEffect } from "react";
import { useStore } from "@/store/useStore";
import { API_URL, missingAuthToken } from "@/lib/env";

/**
 * Polls /api/health so the UI can tell "backend is down" apart from
 * "websocket is down" — two very different problems that used to look
 * identical (a single red OFFLINE dot).
 */
export function useHealth(intervalMs = 8000) {
  const setApi = useStore((s) => s.setApi);

  useEffect(() => {
    let cancelled = false;

    const probe = async () => {
      try {
        const res = await fetch(`${API_URL}/api/health`, { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!cancelled) {
          setApi({
            apiUp: true,
            apiError: null,
            tradingMode: data.trading_mode ?? "?",
            killSwitch: Boolean(data.kill_switch),
            authConfigured: !missingAuthToken,
          });
        }
      } catch (e) {
        if (!cancelled) {
          setApi({
            apiUp: false,
            apiError: `${(e as Error).message} @ ${API_URL}/api/health`,
            tradingMode: null,
            killSwitch: false,
            authConfigured: !missingAuthToken,
          });
        }
      }
    };

    probe();
    const id = setInterval(probe, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [intervalMs, setApi]);
}
