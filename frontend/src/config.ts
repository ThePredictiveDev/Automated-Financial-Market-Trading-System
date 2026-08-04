/**
 * Backend base URL for REST + WebSocket.
 * Set VITE_API_URL on Vercel to your Render URL, e.g. https://your-app.onrender.com
 * Locally, leave unset to use http://127.0.0.1:8000
 */
const raw = (import.meta.env.VITE_API_URL as string | undefined)?.trim().replace(/\/$/, '');

export const API_BASE = raw && raw.length > 0 ? raw : 'http://127.0.0.1:8000';

export function apiUrl(path: string): string {
  const p = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE}${p}`;
}

/** Convert http(s) API base to ws(s) for WebSocket endpoints. */
export function wsUrl(path: string): string {
  const p = path.startsWith('/') ? path : `/${path}`;
  if (API_BASE.startsWith('https://')) {
    return `wss://${API_BASE.slice('https://'.length)}${p}`;
  }
  if (API_BASE.startsWith('http://')) {
    return `ws://${API_BASE.slice('http://'.length)}${p}`;
  }
  // Fallback if someone set a host without scheme
  return `ws://${API_BASE}${p}`;
}
