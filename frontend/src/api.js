// Tiny API client for the swing backend.
// In dev, calls go to "/api/..." and Vite proxies them to http://localhost:8000
// (see vite.config.js). Set VITE_API_URL to point elsewhere in production.
const BASE = import.meta.env.VITE_API_URL || "";

async function json(res) {
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json();
}

export async function getEngines() {
  return json(await fetch(`${BASE}/api/engines`));
}

export async function getSymbols() {
  return json(await fetch(`${BASE}/api/symbols`));
}

export async function runPipeline(asset, symbol, opts = {}) {
  return json(
    await fetch(`${BASE}/api/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ asset, symbol, ...opts }),
    })
  );
}
