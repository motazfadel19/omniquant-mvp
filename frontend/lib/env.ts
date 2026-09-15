/**
 * Resolved runtime configuration.
 *
 * NEXT_PUBLIC_* variables are inlined at BUILD time. If they are missing the
 * old code produced `ws://undefined/ws/market` and the header silently showed
 * OFFLINE with no hint about why. These helpers fall back to the standard local
 * backend so a fresh clone works out of the box, and expose the resolved values
 * so the UI can show what it is actually trying to reach.
 */

export const DEFAULT_BACKEND_ORIGIN = "http://127.0.0.1:8000";
export const DEFAULT_BACKEND_PORT = 8000;

export const API_URL: string =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || DEFAULT_BACKEND_ORIGIN;

export const WS_URL: string = (() => {
  const raw = process.env.NEXT_PUBLIC_WS_URL?.replace(/\/$/, "");
  if (raw) return raw;
  if (typeof window !== "undefined") {
    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    return `${scheme}://${window.location.hostname}:${DEFAULT_BACKEND_PORT}`;
  }
  return `ws://127.0.0.1:${DEFAULT_BACKEND_PORT}`;
})();

export const AUTH_TOKEN: string = process.env.NEXT_PUBLIC_AUTH_TOKEN ?? "";

/** True when the operator forgot to copy `.env.example` to `.env.local`. */
export const usingFallbackConfig =
  !process.env.NEXT_PUBLIC_API_URL || !process.env.NEXT_PUBLIC_WS_URL;

/** True when the shared secret is still unset — every POST will 401. */
export const missingAuthToken = AUTH_TOKEN === "";

if (typeof window !== "undefined" && (usingFallbackConfig || missingAuthToken)) {
  console.warn(
    "[OmniQuant] frontend configuration is incomplete.\n" +
      `  API : ${API_URL}${usingFallbackConfig ? "   (fallback — create frontend/.env.local)" : ""}\n` +
      `  WS  : ${WS_URL}\n` +
      `  AUTH: ${missingAuthToken ? "MISSING — set NEXT_PUBLIC_AUTH_TOKEN, trading buttons will fail with 401" : "set"}\n` +
      "  Copy frontend/.env.example to frontend/.env.local and restart `npm run dev`."
  );
}
