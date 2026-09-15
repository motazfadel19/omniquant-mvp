"use client";
import { create } from "zustand";
import type { Account, Position, Tick } from "@/lib/api";

type ApiState = {
  apiUp: boolean;
  apiError: string | null;
  tradingMode: string | null;
  killSwitch: boolean;
  authConfigured: boolean;
};

type State = {
  // connection
  connected: boolean;
  setConnected: (v: boolean) => void;

  // websocket diagnostics
  wsError: string | null;
  setWsError: (v: string | null) => void;

  // backend health
  api: ApiState;
  setApi: (v: Partial<ApiState>) => void;

  // active symbol
  symbol: string;
  setSymbol: (s: string) => void;

  timeframe: string;
  setTimeframe: (t: string) => void;

  // live data
  account: Account | null;
  positions: Position[];
  ticks: Record<string, Tick>;

  // actions
  applyTick: (payload: {
    account: Account | null;
    positions: Position[];
    ticks: Tick[];
  }) => void;
};

export const useStore = create<State>((set) => ({
  connected: false,
  setConnected: (v) => set({ connected: v }),

  wsError: null,
  setWsError: (v) => set({ wsError: v }),

  api: {
    apiUp: false,
    apiError: null,
    tradingMode: null,
    killSwitch: false,
    authConfigured: false,
  },
  setApi: (v) => set((state) => ({ api: { ...state.api, ...v } })),

  symbol: "XAUUSD",
  setSymbol: (s) => set({ symbol: s }),

  timeframe: "H1",
  setTimeframe: (t) => set({ timeframe: t }),

  account: null,
  positions: [],
  ticks: {},

  applyTick: ({ account, positions, ticks }) =>
    set((state) => {
      const next = { ...state.ticks };
      for (const t of ticks) next[t.symbol] = t;
      return { account: account ?? state.account, positions, ticks: next };
    }),
}));
