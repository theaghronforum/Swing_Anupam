# Running the Swing app (frontend + backend)

The frontend (React/Vite) talks to the backend (FastAPI) over HTTP. You run two
processes: the API on port 8000, and the Vite dev server on port 5173. Vite
proxies `/api/*` calls to the backend, so there's no CORS setup to worry about.

```
frontend/      React UI (calls /api/... )
swing_engine/  the 30-engine package + server.py (the API)
```

## 1. Backend (API) — terminal 1
```powershell
cd swing_engine
pip install -r requirements.txt          # first time only (adds fastapi + uvicorn)
$env:PYTHONPATH = "."
python server.py                         # serves http://localhost:8000
```
(Windows shortcut: just double-click `swing_engine\run_backend.bat`.)

Check it works: open http://localhost:8000/api/health — you should see
`{"status":"ok", ...}`. And http://localhost:8000/api/symbols lists your symbols.

## 2. Frontend (UI) — terminal 2
```powershell
cd frontend
npm install                              # first time only
npm run dev                              # serves http://localhost:5173
```
Open http://localhost:5173. Pick an **asset** and **symbol**, click
**“Initiate the Process”**, and the dashboard runs the full 30-engine pipeline
on the backend and shows:
- the **trade card** (signal, entry, stop, targets, R:R, confidence, model probability), and
- the **selected engine’s** live output (click any engine in the sidebar).

## How they connect
- `frontend/src/api.js` calls `/api/run`, `/api/symbols`, `/api/engines`.
- `frontend/vite.config.js` proxies `/api` → `http://localhost:8000`.
- `swing_engine/server.py` loads your `raw_data/`, runs `Pipeline()`, and returns
  every engine's score/decision/outputs plus the Gatekeeper trade card. If
  `swing_model.joblib` is present it also returns a live model probability.

## API quick reference
| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/api/health` | liveness + whether a model is loaded |
| GET  | `/api/engines` | list of the 30 engines (id, name) |
| GET  | `/api/symbols` | `{STOCK:[...], FNO:[...], ...}` |
| POST | `/api/run` | body `{asset, symbol, capital?, risk_per_trade_pct?}` → full result |

## Production notes
- For a real deployment, build the frontend (`npm run build`) and serve the
  static files, and run the API with `uvicorn server:app --host 0.0.0.0 --port 8000`
  behind a reverse proxy; set `VITE_API_URL` to the API's public URL at build time.
- The API caches loaded instruments in memory; restart to pick up new data files.
- This is decision-support, not financial advice — keep a human approving trades.
