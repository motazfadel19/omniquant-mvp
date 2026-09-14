const API = process.env.NEXT_PUBLIC_API_URL!;

export type Candle = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  tick_volume: number;
  spread: number;
};

export type Account = {
  login: number;
  balance: number;
  equity: number;
  margin: number;
  profit: number;
  currency: string;
  leverage: number;
};

export type Position = {
  ticket: number;
  symbol: string;
  type: "BUY" | "SELL";
  volume: number;
  open_price: number;
  sl: number;
  tp: number;
  profit: number;
  open_time: number;
  magic: number;
};

export type Tick = {
  symbol: string;
  bid: number;
  ask: number;
  time: number;
  volume: number;
};

export type HeatmapItem = {
  symbol: string;
  change_pct: number;
  price: number;
};

export type Signal = {
  id: number;
  symbol: string;
  direction: "BUY" | "SELL";
  price: number;
  sl: number;
  tp: number;
  confidence: number;
  source: string;
  created_at: number;
};

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}

export const api = {
  health:    () => get<{ status: string }>("/api/health"),
  account:   () => get<Account>("/api/account"),
  positions: () => get<{ positions: Position[] }>("/api/positions"),
  heatmap:   () => get<{ items: HeatmapItem[] }>("/api/heatmap"),
  signals:   (limit = 20) => get<{ signals: Signal[] }>(`/api/signals?limit=${limit}`),
  equity:    () => get<{ curve: { time: number; equity: number }[] }>("/api/equity-curve"),
  candles:   (symbol: string, tf = "H1", count = 500) =>
    get<{ candles: Candle[] }>(`/api/candles?symbol=${symbol}&timeframe=${tf}&count=${count}`),
  symbols:   () => get<{ symbols: string[] }>("/api/symbols"),
};

// ==================== Trading ====================

export type Quote = {
  symbol: string;
  bid: number;
  ask: number;
  time: number;
  digits: number;
  point: number;
};

export type OpenOrderPayload = {
  symbol: string;
  direction: "BUY" | "SELL";
  volume: number;
  sl_points?: number;
  tp_points?: number;
  magic?: number;
  comment?: string;
};

export type OpenOrderResult = {
  ok: boolean;
  ticket: number;
  price: number;
  sl: number;
  tp: number;
  retcode: number;
  comment: string;
};

export type CloseOrderResult = {
  ok: boolean;
  ticket: number;
  price: number;
  profit: number;
  retcode: number;
};

const AUTH_TOKEN =
  process.env.NEXT_PUBLIC_AUTH_TOKEN || "dev-local-token-change-me";

async function post<T>(path: string, body: object): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Auth-Token": AUTH_TOKEN,
    },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data?.detail || `API ${res.status}: ${path}`);
  }
  return data as T;
}

export const tradingApi = {
  quote: (symbol: string) => get<Quote>(`/api/quote?symbol=${symbol}`),
  symbolInfo: (symbol: string) =>
    get<{
      symbol: string; digits: number; point: number;
      volume_min: number; volume_max: number; volume_step: number;
      stops_level: number; freeze_level: number; trade_mode: number;
    }>(`/api/symbol-info?symbol=${symbol}`),

  openOrder: (payload: OpenOrderPayload) =>
    post<OpenOrderResult>("/api/order/open", payload),

  closeOrder: (ticket: number) =>
    post<CloseOrderResult>("/api/order/close", { ticket }),

  modifyOrder: (ticket: number, sl_points: number, tp_points: number) =>
    post<{ ok: boolean; ticket: number; sl: number; tp: number }>(
      "/api/order/modify",
      { ticket, sl_points, tp_points }
    ),

  closeAll: () =>
    post<{ ok: boolean; closed: number; failed: number }>(
      "/api/order/close-all",
      {}
    ),
};