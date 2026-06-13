import { PILLARS } from "../../lib/scoring";

const COLORS = {
  authorship: "#3b82f6",
  collaboration: "#10b981",
  ownership: "#f59e0b",
  consistency: "#a855f7",
  influence: "#ef4444",
};

/*
  Weighted pillar contribution bar: shows how each pillar contributes to the
  composite under the *current* weights (pillar × weight / Σweight).
*/
export default function StackedBar({ pillars, weights, name, compact = false }) {
  const totalW = Object.values(weights).reduce((a, b) => a + b, 0) || 1;
  const segments = PILLARS.map((p) => ({
    ...p,
    contribution: ((pillars[p.key] ?? 0) * weights[p.key]) / totalW,
  }));
  const max = segments.reduce((a, s) => a + s.contribution, 0) || 1;
  const label =
    `Weighted contribution for ${name}: ` +
    segments.map((s) => `${s.label} ${s.contribution.toFixed(1)}`).join(", ");

  return (
    <div role="img" aria-label={label}>
      <div
        style={{ display: "flex", height: compact ? 8 : 22, borderRadius: compact ? 4 : 6, overflow: "hidden" }}
      >
        {segments.map((s) => (
          <div
            key={s.key}
            title={`${s.label}: ${s.contribution.toFixed(1)} pts`}
            style={{
              width: `${(s.contribution / max) * 100}%`,
              background: COLORS[s.key],
              transition: "width 400ms ease",
            }}
          />
        ))}
      </div>
      {!compact && (
        <ul
          style={{
            listStyle: "none",
            padding: 0,
            margin: "0.5rem 0 0",
            display: "flex",
            flexWrap: "wrap",
            gap: "0.35rem 0.9rem",
            fontSize: "0.72rem",
            color: "var(--muted)",
          }}
        >
          {segments.map((s) => (
            <li key={s.key} style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <span
                aria-hidden="true"
                style={{
                  width: 9,
                  height: 9,
                  borderRadius: 2,
                  background: COLORS[s.key],
                  display: "inline-block",
                }}
              />
              {s.label} · {s.contribution.toFixed(1)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export { COLORS };
