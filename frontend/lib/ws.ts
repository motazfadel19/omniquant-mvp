"use client";
import { useEffect, useRef } from "react";
import { useStore } from "@/store/useStore";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL!;

export function useMarketSocket() {
  const setConnected = useStore((s) => s.setConnected);
  const applyTick = useStore((s) => s.applyTick);
  const retryRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    let ws: WebSocket | null = null;
    let stopped = false;

    const connect = () => {
      ws = new WebSocket(`${WS_URL}/ws/market`);

      ws.onopen = () => {
        setConnected(true);
        console.log("🟢 WS connected");
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

      ws.onclose = () => {
        setConnected(false);
        if (!stopped) retryRef.current = setTimeout(connect, 2000);
      };

      ws.onerror = () => ws?.close();
    };

    connect();
    return () => {
      stopped = true;
      clearTimeout(retryRef.current);
      ws?.close();
    };
  }, [setConnected, applyTick]);
}