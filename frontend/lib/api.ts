const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

// Never ship a credential fallback in source: if the variable is missing the
// request simply 401s instead of silently authenticating against a default
// token that every clone of this repo shares.
export const AUTH_TOKEN = process.env.NEXT_PUBLIC_AUTH_TOKEN ?? "";

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

export type HeatmapItem = { symbol: string; change_pct: number; price: number };

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

export type RiskStatus = {
  trading_mode: string;
  kill_switch: boolean;
  kill_reason: string;
  day: string;
  day_start_balance: number;
  realized_today: number;
  trades_today: number;
  limits: Record<string, number | string | string[]>;
};

export type BacktestMetrics = {
  n_trades: number;
  win_rate: number;
  breakeven_win_rate: number;
  expectancy_r: number;
  total_r: number;
  total_cost_r: number;
  profit_factor: number | null;
  payoff_ratio: number | null;
  max_drawdown_r: number;
  sharpe: number;
  t_stat: number;
  longest_losing_streak: number;
  verdict: string;
  by_direction?: { bucket: string; count: number; win_rate: number; avg_r: number }[];
  by_exit_reason?: { bucket: string; count: number; win_rate: number; avg_r: number }[];
  equity_curve?: { time: number; equity_r: number }[];
};

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}

async function post<T>(path: string, body: object = {}): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Auth-Token": AUTH_TOKEN,
    },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail || `API ${res.status}: ${path}`);
  return data as T;
}

export const api = {
  health: () => get<{ status: string; trading_mode: string; kill_switch: boolean }>("/api/health"),
  config: () => get<Record<string, any>>("/api/config"),
  account: () => get<Account>("/api/account"),
  positions: () => get<{ positions: Position[] }>("/api/positions"),
  heatmap: () => get<{ items: HeatmapItem[] }>("/api/heatmap"),
  signals: (limit = 20) => get<{ signals: Signal[] }>(`/api/signals?limit=${limit}`),
  equity: () => get<{ curve: { time: number; equity: number }[] }>("/api/equity-curve"),
  candles: (symbol: string, tf = "H1", count = 500) =>
    get<{ candles: Candle[] }>(`/api/candles?symbol=${symbol}&timeframe=${tf}&count=${count}`),
  symbols: () => get<{ symbols: string[] }>("/api/symbols"),
  dataStats: () => get<Record<string, any>>("/api/data/stats"),

  // ---- AI engine ----
  aiStatus: () => get<any>("/api/ai/status"),
  aiAnalysis: () => get<{ analysis: Record<string, any> }>("/api/ai/analysis"),
  aiDecisions: (limit = 15) => get<{ decisions: any[] }>(`/api/ai/decisions?limit=${limit}`),
  aiStart: () => post("/api/ai/start"),
  aiStop: () => post("/api/ai/stop"),
  aiAuto: (enabled: boolean) => post("/api/ai/auto-execute", { enabled }),
  aiConfig: (payload: object) => post("/api/ai/config", payload),
  aiReloadMl: () => post("/api/ai/reload-ml"),

  // ---- risk ----
  riskStatus: () => get<RiskStatus>("/api/risk/status"),
  riskKill: (reason: string) => post("/api/risk/kill", { reason }),
  riskReset: () => post("/api/risk/reset"),
  riskAudit: (limit = 50) => post<{ items: any[] }>(`/api/risk/audit?limit=${limit}`),

  // ---- validation ----
  backtestRun: (payload: object) => post<BacktestMetrics & { run_id: string }>("/api/backtest/run", payload),
  backtestMetrics: (runId?: string) =>
    get<BacktestMetrics>(`/api/backtest/metrics${runId ? `?run_id=${runId}` : ""}`),
  walkForward: (payload: object) => post<any>("/api/backtest/walkforward", payload),
  monteCarlo: (payload: object) => post<any>("/api/backtest/montecarlo", payload),
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
  paper?: boolean;
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

export const tradingApi = {
  quote: (symbol: string) => get<Quote>(`/api/quote?symbol=${symbol}`),
  symbolInfo: (symbol: string) =>
    get<{
      symbol: string;
      digits: number;
      point: number;
      volume_min: number;
      volume_max: number;
      volume_step: number;
      stops_level: number;
      freeze_level: number;
      trade_mode: number;
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
    post<{ ok: boolean; closed: number; failed: number }>("/api/order/close-all", {}),
};
