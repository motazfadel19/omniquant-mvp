"use client";
import { useEffect, useRef } from "react";
import { useStore } from "@/store/useStore";
import { WS_URL } from "@/lib/env";

export function useMarketSocket() {
  const setConnected = useStore((s) => s.setConnected);
  const setWsError = useStore((s) => s.setWsError);
  const applyTick = useStore((s) => s.applyTick);
  const retryRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    let ws: WebSocket | null = null;
    let stopped = false;

    const connect = () => {
      const url = `${WS_URL}/ws/market`;
      try {
        ws = new WebSocket(url);
      } catch (e) {
        setConnected(false);
        setWsError(`cannot open ${url}: ${(e as Error).message}`);
        if (!stopped) retryRef.current = setTimeout(connect, 3000);
        return;
      }

      ws.onopen = () => {
        setConnected(true);
        setWsError(null);
        console.log(`[OmniQuant] WS connected: ${url}`);
      };

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === "tick" || msg.type === "snapshot") {
            applyTick({
              account: msg.account,
              positions: msg.positions ?? [],
              ticks: msg.ticks ?? [],
            });
          }
        } catch (e) {
          console.error("WS parse error", e);
        }
      };

      ws.onclose = (ev) => {
        setConnected(false);
        setWsError(
          ev.code
            ? `websocket closed (code ${ev.code}) — is the backend running on ${WS_URL}?`
            : `cannot reach ${url}`
        );
        if (!stopped) retryRef.current = setTimeout(connect, 3000);
      };

      ws.onerror = () => {
        setWsError(`cannot reach ${url}`);
        ws?.close();
      };
    };

    connect();
    return () => {
      stopped = true;
      clearTimeout(retryRef.current);
      ws?.close();
    };
  }, [setConnected, setWsError, applyTick]);
}
