import { useState } from "react";
import { PILLARS, DEFAULT_WEIGHTS } from "../lib/scoring";
import { COLORS } from "./charts/StackedBar";
import WeightControls from "./WeightControls";

export default function RubricCard({ weights, setWeights }) {
  const [tuning, setTuning] = useState(false);
  const total = Object.values(weights).reduce((a, b) => a + b, 0) || 1;
  const customized = PILLARS.some((p) => weights[p.key] !== DEFAULT_WEIGHTS[p.key]);

  return (
    <aside className="aside">
      <div className="card" style={{ padding: "1rem 1.05rem" }}>
        <h2 style={{ margin: "0 0 .15rem", fontSize: "1rem" }}>How impact is scored</h2>
        <p style={{ margin: "0 0 .85rem", fontSize: ".8rem", color: "var(--muted)" }}>
          A weighted blend of five pillars, each a percentile rank within the cohort.
          {customized && (
            <span style={{ color: "var(--accent)" }}> Weights customized.</span>
          )}
        </p>

        <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: ".7rem" }}>
          {PILLARS.map((p) => {
            const pct = Math.round((weights[p.key] / total) * 100);
            return (
              <li key={p.key}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: ".88rem" }}>
                  <span aria-hidden="true" style={{ width: 11, height: 11, borderRadius: 3, background: COLORS[p.key], flexShrink: 0 }} />
                  <span style={{ fontWeight: 600 }}>{p.label}</span>
                  <span style={{ marginLeft: "auto", color: "var(--muted)", fontVariantNumeric: "tabular-nums", fontSize: ".82rem" }}>
                    {pct}%
                  </span>
                </div>
                <div style={{ height: 4, background: "var(--border)", borderRadius: 3, margin: ".3rem 0 .15rem 19px", overflow: "hidden" }}>
                  <div style={{ width: `${pct * 2}%`, maxWidth: "100%", height: "100%", background: COLORS[p.key], transition: "width 300ms ease" }} />
                </div>
                <p style={{ margin: "0 0 0 19px", fontSize: ".76rem", color: "var(--muted)" }}>{p.short}</p>
              </li>
            );
          })}
        </ol>

        <div style={{ borderTop: "1px solid var(--border)", marginTop: "1rem", paddingTop: ".85rem" }}>
          <button
            type="button"
            onClick={() => setTuning((t) => !t)}
            aria-expanded={tuning}
            aria-controls="weight-tuning"
            style={{
              width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center",
              background: "transparent", border: "none", color: "var(--muted)",
              cursor: "pointer", fontSize: ".82rem", padding: 0,
            }}
          >
            <span style={{ fontWeight: 600, color: "var(--text)" }}>Advanced · adjust weights</span>
            <span aria-hidden="true" style={{ transform: tuning ? "rotate(180deg)" : "none", transition: "transform .2s" }}>▾</span>
          </button>
          {tuning && (
            <div id="weight-tuning" style={{ marginTop: ".85rem" }}>
              <p style={{ margin: "0 0 .7rem", fontSize: ".76rem", color: "var(--muted)" }}>
                Rankings re-sort live as you drag — no re-analysis needed.
              </p>
              <WeightControls weights={weights} setWeights={setWeights} />
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
