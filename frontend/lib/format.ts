export const fmtMoney = (n: number, currency = "USD") =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n);

export const fmtNum = (n: number, digits = 2) =>
  n.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });

export const fmtPct = (n: number, digits = 2) =>
  `${n >= 0 ? "+" : ""}${n.toFixed(digits)}%`;

export const fmtTime = (ts: number) =>
  new Date(ts * 1000).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });