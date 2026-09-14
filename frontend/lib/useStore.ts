"use client";
import { create } from "zustand";
import type { Account, Position, Tick } from "@/lib/api";

type State = {
  // connection
  connected: boolean;
  setConnected: (v: boolean) => void;

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