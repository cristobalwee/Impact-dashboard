import { PILLARS, DEFAULT_WEIGHTS } from "../lib/scoring";
import { COLORS } from "./charts/StackedBar";

// Compact, embeddable slider stack (lives inside the aside's rubric card).
export default function WeightControls({ weights, setWeights }) {
  const total = Object.values(weights).reduce((a, b) => a + b, 0) || 1;
  const atDefault = PILLARS.every((p) => weights[p.key] === DEFAULT_WEIGHTS[p.key]);

  return (
    <div style={{ display: "grid", gap: ".7rem" }}>
      {PILLARS.map((p) => (
        <div key={p.key}>
          <label
            htmlFor={`w-${p.key}`}
            style={{ display: "flex", justifyContent: "space-between", fontSize: ".8rem" }}
          >
            <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span aria-hidden="true" style={{ width: 9, height: 9, borderRadius: 2, background: COLORS[p.key] }} />
              {p.label}
            </span>
            <span style={{ color: "var(--muted)", fontVariantNumeric: "tabular-nums" }}>
              {Math.round((weights[p.key] / total) * 100)}%
            </span>
          </label>
          <input
            id={`w-${p.key}`}
            type="range"
            min="0"
            max="50"
            step="1"
            value={weights[p.key]}
            aria-label={`${p.label} weight`}
            onChange={(e) => setWeights({ ...weights, [p.key]: Number(e.target.value) })}
            style={{ width: "100%", accentColor: COLORS[p.key], marginTop: 2 }}
          />
        </div>
      ))}
      <button
        type="button"
        onClick={() => setWeights({ ...DEFAULT_WEIGHTS })}
        disabled={atDefault}
        style={{
          fontSize: ".78rem", padding: ".35rem .7rem", borderRadius: 7,
          border: "1px solid var(--border)", background: "transparent",
          color: atDefault ? "var(--muted)" : "var(--text)",
          cursor: atDefault ? "default" : "pointer", opacity: atDefault ? 0.6 : 1,
          justifySelf: "start",
        }}
      >
        Reset to defaults
      </button>
    </div>
  );
}
