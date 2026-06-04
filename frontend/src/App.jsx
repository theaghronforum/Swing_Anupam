import { useEffect, useState, Fragment } from "react";
import { getSymbols, runPipeline } from "./api";

const engines = [
  "Swing Trader Suitability",
  "Multi-Asset Swing Access",
  "Capital Allocation & Risk Budget",
  "Swing Market Regime",
  "Trend Strength Detection",
  "Price Structure Intelligence",
  "Support & Resistance Mapping",
  "Breakout Validation",
  "Pullback Quality",
  "Momentum Continuation",
  "Reversal Probability",
  "Volume Confirmation",
  "Smart Money Accumulation",
  "Sector & Index Alignment",
  "Cross-Asset Correlation",
  "Stocks Swing Selection",
  "Index Swing Direction",
  "Commodity Cycle Intelligence",
  "Forex Macro Swing",
  "F&O Confirmation",
  "Volatility Expansion",
  "Event & News Risk",
  "Global Market Impact",
  "Entry Timing",
  "Stop-Loss Placement",
  "Target Projection",
  "Trailing Exit",
  "Position Holding Period",
  "Swing Trade Rebalancing",
  "Final Strategy & Execution Gatekeeper",
];

const sidebarIcons = [
  "person","layers","pie_chart","trending_up","show_chart",
  "auto_graph","map","verified","tune","speed",
  "swap_vert","bar_chart","account_balance","grid_view","hub",
  "candlestick_chart","arrow_upward","grain","language","receipt_long",
  "bolt","event","public","schedule","shield",
  "track_changes","flag","timer","refresh","gavel",
];

const ASSETS = ["STOCK", "FNO", "INDEX", "FOREX", "COMMODITY"];

// pretty-print a single output value
function renderValue(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") return Number.isInteger(v) ? v : v.toFixed(2);
  if (Array.isArray(v)) return v.map(renderValue).join(", ");
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export default function App() {
  const [activeIdx, setActiveIdx] = useState(0);
  const [symbols, setSymbols] = useState({});
  const [asset, setAsset] = useState("STOCK");
  const [symbol, setSymbol] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const active = engines[activeIdx];
  const activeId = activeIdx + 1; // engine ids are 1..30 in order

  // load symbol lists once
  useEffect(() => {
    getSymbols()
      .then((s) => {
        setSymbols(s);
        const first = (s[asset] || [])[0] || "";
        setSymbol(first);
      })
      .catch((e) => setError(`Could not reach backend: ${e.message}`));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // when asset changes, default to its first symbol
  useEffect(() => {
    const list = symbols[asset] || [];
    if (list.length && !list.includes(symbol)) setSymbol(list[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asset, symbols]);

  const handleRun = async () => {
    if (!symbol) return;
    setLoading(true);
    setError("");
    try {
      const r = await runPipeline(asset, symbol);
      setResult(r);
    } catch (e) {
      setError(`Run failed: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const eng = result?.engines?.[activeId];
  const card = result?.trade_card;
  const symbolList = symbols[asset] || [];

  return (
    <div style={{ display: "flex", height: "100vh", fontFamily: "'Inter', 'Segoe UI', Arial, sans-serif", overflow: "hidden" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        @import url('https://fonts.googleapis.com/icon?family=Material+Icons');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #9C6B4A; border-radius: 4px; }

        .sidebar { width: 300px; min-width: 300px; height: 100vh; background: #7B4F2E; border-right: 1px solid #6a4226; display: flex; flex-direction: column; overflow: hidden; }
        .sidebar-brand { padding: 20px 20px 14px; border-bottom: 1px solid #6a4226; }
        .sidebar-brand-title { font-size: 16px; font-weight: 700; color: #F9F3EC; letter-spacing: -0.2px; }
        .sidebar-brand-sub { font-size: 11.5px; color: #d4b896; margin-top: 2px; }
        .sidebar-scroll { flex: 1; overflow-y: auto; padding: 6px 0 16px; }
        .home-item { display: flex; align-items: center; gap: 10px; padding: 9px 20px; font-size: 13.5px; color: #F9F3EC; cursor: pointer; transition: background 0.13s; }
        .home-item:hover { background: #9C6B4A; border-radius: 8px; }
        .home-icon { font-family: 'Material Icons'; font-size: 17px; color: #F9F3EC; line-height: 1; }
        .nav-item { display: flex; align-items: flex-start; gap: 10px; width: 100%; padding: 9px 20px; font-size: 13px; font-weight: 400; color: #F9F3EC; background: transparent; border: none; text-align: left; cursor: pointer; line-height: 1.45; transition: background 0.13s, color 0.13s; border-radius: 8px; }
        .nav-item:hover { background: #9C6B4A; color: #F9F3EC; border-radius: 8px; }
        .nav-item.active { background: #8B5E3C; color: #ffffff; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        .nav-icon { font-family: 'Material Icons'; font-size: 16px; line-height: 1; margin-top: 1px; color: #F9F3EC; flex-shrink: 0; }
        .nav-item.active .nav-icon { color: #ffffff; }

        .main-area { flex: 1; background: #f5efe6; overflow-y: auto; }
        .main-content { padding: 36px 52px; max-width: 1060px; }
        .page-title { font-size: 26px; font-weight: 700; color: #111827; letter-spacing: -0.4px; line-height: 1.25; margin-bottom: 6px; }
        .page-sub { font-size: 13px; color: #6b7280; margin-bottom: 24px; }

        .controls { display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap; margin-bottom: 26px; }
        .ctl-label { font-size: 11.5px; color: #6b5640; font-weight: 600; display: block; margin-bottom: 5px; text-transform: uppercase; letter-spacing: .3px; }
        .ctl-select { padding: 10px 12px; border: 1px solid #d8cdbf; border-radius: 7px; background: #fff; font-size: 14px; min-width: 150px; font-family: inherit; color:#111827; }
        .initiate-main-btn { display: inline-flex; align-items: center; gap: 8px; padding: 11px 26px; background: #a07040; color: #fff; border: none; border-radius: 7px; font-size: 14.5px; font-weight: 600; cursor: pointer; transition: background 0.18s; }
        .initiate-main-btn:hover { background: #8a5d2e; }
        .initiate-main-btn:disabled { background: #c4a585; cursor: not-allowed; }

        .err { background:#fef2f2; border:1px solid #f3c4c4; color:#b91c1c; padding:10px 14px; border-radius:8px; font-size:13px; margin-bottom:18px; }

        .card-banner { background:#fff; border:1px solid #e2d9ce; border-radius:12px; padding:20px 24px; margin-bottom:24px; }
        .banner-top { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px; margin-bottom:14px; }
        .banner-sym { font-size:18px; font-weight:700; color:#111827; }
        .banner-sym small { font-weight:500; color:#6b7280; font-size:12.5px; margin-left:8px; }
        .pill { padding:5px 13px; border-radius:999px; font-size:12.5px; font-weight:600; text-transform:capitalize; }
        .pill.execute,.pill.approved { background:#dcfce7; color:#15803d; }
        .pill.monitor,.pill.conditionally-approved { background:#fef9c3; color:#a16207; }
        .pill.protect,.pill.hedge-required { background:#ffedd5; color:#c2410c; }
        .pill.avoid,.pill.rejected,.pill.wait { background:#fee2e2; color:#b91c1c; }
        .metrics { display:grid; grid-template-columns: repeat(auto-fit,minmax(120px,1fr)); gap:14px; }
        .metric { background:#faf7f2; border:1px solid #ece3d6; border-radius:9px; padding:11px 13px; }
        .metric .k { font-size:11px; color:#8a7355; text-transform:uppercase; letter-spacing:.3px; }
        .metric .v { font-size:16px; font-weight:700; color:#111827; margin-top:3px; }

        .engine-card { background:#fff; border:1px solid #e2d9ce; border-radius:12px; overflow:hidden; }
        .engine-head { display:flex; align-items:center; justify-content:space-between; padding:16px 22px; border-bottom:1px solid #ede8e1; background:#fafafa; flex-wrap:wrap; gap:10px; }
        .engine-title { font-size:15px; font-weight:700; color:#111827; }
        .score-badge { font-size:13px; font-weight:700; padding:5px 12px; border-radius:8px; background:#eef2ff; color:#3730a3; }
        .decision-line { padding:14px 22px; font-size:13.5px; color:#374151; border-bottom:1px solid #f0ebe4; }
        .decision-line b { color:#111827; text-transform:capitalize; }
        .kv { display:grid; grid-template-columns: 240px 1fr; }
        .kv > div { padding:10px 22px; border-bottom:1px solid #f4efe8; font-size:13px; }
        .kv .k { color:#6b7280; background:#fcfaf7; font-weight:500; }
        .kv .v { color:#111827; word-break:break-word; }
        .warn { padding:10px 22px; font-size:12.5px; color:#b45309; background:#fffbeb; border-bottom:1px solid #fde9c8; }
        .empty { background:#fff; border:1px dashed #d8cdbf; border-radius:12px; padding:40px; text-align:center; color:#8a7355; font-size:14px; }

        @keyframes fadeUp { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:translateY(0); } }
        .fade-up { animation: fadeUp 0.22s ease forwards; }
      `}</style>

      {/* SIDEBAR */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="sidebar-brand-title">Swing Trading</div>
          <div className="sidebar-brand-sub">System Dashboard</div>
        </div>
        <div className="sidebar-scroll">
          <div className="home-item"><span className="home-icon">home</span><span>Home</span></div>
          {engines.map((engName, i) => (
            <button
              key={engName}
              className={`nav-item${activeIdx === i ? " active" : ""}`}
              onClick={() => setActiveIdx(i)}
            >
              <span className="nav-icon">{sidebarIcons[i]}</span>
              <span>{engName}</span>
            </button>
          ))}
        </div>
      </aside>

      {/* MAIN */}
      <main className="main-area">
        <div className="main-content fade-up" key={activeIdx}>
          <h1 className="page-title">{active}</h1>
          <div className="page-sub">Engine {activeId} of 30 · pick an instrument and run the live pipeline</div>

          {/* CONTROLS */}
          <div className="controls">
            <div>
              <label className="ctl-label">Asset</label>
              <select className="ctl-select" value={asset} onChange={(e) => setAsset(e.target.value)}>
                {ASSETS.map((a) => (
                  <option key={a} value={a}>{a} ({(symbols[a] || []).length})</option>
                ))}
              </select>
            </div>
            <div>
              <label className="ctl-label">Symbol</label>
              <select className="ctl-select" value={symbol} onChange={(e) => setSymbol(e.target.value)}>
                {symbolList.length === 0 && <option value="">—</option>}
                {symbolList.map((s) => (<option key={s} value={s}>{s}</option>))}
              </select>
            </div>
            <button className="initiate-main-btn" onClick={handleRun} disabled={loading || !symbol}>
              <span className="material-icons" style={{ fontFamily: "Material Icons", fontSize: 18 }}>
                {loading ? "hourglass_top" : "play_arrow"}
              </span>
              {loading ? "Running pipeline…" : "Initiate the Process"}
            </button>
          </div>

          {error && <div className="err">{error}</div>}

          {/* TRADE CARD BANNER */}
          {result && card && (
            <div className="card-banner">
              <div className="banner-top">
                <div className="banner-sym">
                  {result.symbol}
                  <small>{result.asset} · as of {result.as_of} · last {result.last_close}</small>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <span className={`pill ${(result.final_action || "").replace(/\s+/g, "-")}`}>
                    {result.final_action}
                  </span>
                  <span className={`pill ${(result.approval_status || "").replace(/\s+/g, "-")}`}>
                    {result.approval_status}
                  </span>
                </div>
              </div>
              <div className="metrics">
                <div className="metric"><div className="k">Signal</div><div className="v" style={{ textTransform: "capitalize" }}>{card.signal || "—"}</div></div>
                <div className="metric"><div className="k">Entry</div><div className="v">{renderValue(card.entry)}</div></div>
                <div className="metric"><div className="k">Stop loss</div><div className="v">{renderValue(card.stop_loss)}</div></div>
                <div className="metric"><div className="k">Target 1</div><div className="v">{renderValue(card.target_1)}</div></div>
                <div className="metric"><div className="k">Target 2</div><div className="v">{renderValue(card.target_2)}</div></div>
                <div className="metric"><div className="k">R:R</div><div className="v">{renderValue(card.risk_reward)}</div></div>
                <div className="metric"><div className="k">Confidence</div><div className="v">{renderValue(card.confidence)}</div></div>
                <div className="metric"><div className="k">Hold (days)</div><div className="v">{renderValue(card.holding_period_days)}</div></div>
                {result.model_probability != null && (
                  <div className="metric"><div className="k">Model prob</div><div className="v">{(result.model_probability * 100).toFixed(1)}%</div></div>
                )}
              </div>
            </div>
          )}

          {/* SELECTED ENGINE RESULT */}
          {result && eng ? (
            <div className="engine-card">
              <div className="engine-head">
                <div className="engine-title">{eng.name}</div>
                <div className="score-badge">score {eng.score}</div>
              </div>
              <div className="decision-line">Decision: <b>{eng.decision || "—"}</b></div>
              {eng.warnings?.length > 0 && (
                <div className="warn">⚠ {eng.warnings.join(" · ")}</div>
              )}
              <div className="kv">
                {Object.entries(eng.outputs || {}).map(([k, v]) => (
                  <Fragment key={k}>
                    <div className="k">{k}</div>
                    <div className="v">{renderValue(v)}</div>
                  </Fragment>
                ))}
              </div>
            </div>
          ) : (
            <div className="empty">
              {loading ? "Running the 30-engine pipeline…" :
                "Choose an asset and symbol, then click “Initiate the Process” to run the live pipeline. The selected engine’s output appears here."}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
