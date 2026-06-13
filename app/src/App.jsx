import { useEffect, useMemo, useState } from "react";
import { DEFAULT_WEIGHTS, rankEngineers } from "./lib/scoring";
import RubricCard from "./components/RubricCard";
import Leaderboard from "./components/Leaderboard";
import ThemeToggle from "./components/ThemeToggle";

function Chip({ label, value }) {
  return (
    <span
      style={{
        fontSize: ".75rem", color: "var(--muted)",
        border: "1px solid var(--border)", borderRadius: 999,
        padding: ".15rem .6rem", whiteSpace: "nowrap",
      }}
    >
      {label}: <strong style={{ color: "var(--text)", fontWeight: 600 }}>{value}</strong>
    </span>
  );
}

export default function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [weights, setWeights] = useState({ ...DEFAULT_WEIGHTS });

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}engineers.json`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  const ranked = useMemo(
    () => (data ? rankEngineers(data.engineers, weights) : []),
    [data, weights]
  );

  const meta = data?.meta;
  const generated = meta?.generated_at
    ? new Date(meta.generated_at).toLocaleDateString(undefined, {
        year: "numeric", month: "short", day: "numeric",
      })
    : "—";

  return (
    <div style={{ minHeight: "100%", background: "var(--bg)" }}>
      <main
        style={{
          maxWidth: 1280, margin: "0 auto", padding: "1.75rem 1.5rem 4rem",
          display: "grid", gap: "1.25rem",
        }}
      >
        <header style={{ display: "grid", gap: ".75rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem" }}>
            <div>
              <h1 style={{ margin: 0, fontSize: "1.6rem", letterSpacing: "-0.02em" }}>
                Most Impactful Engineers
              </h1>
              <p style={{ margin: ".25rem 0 0", color: "var(--muted)", fontSize: ".92rem" }}>
                A weighted, evidence-backed view of engineering impact in{" "}
                <a
                  href="https://github.com/PostHog/posthog"
                  style={{ color: "var(--accent)" }}
                >
                  {meta?.repo ?? "PostHog/posthog"}
                </a>
                .
              </p>
            </div>
            <ThemeToggle />
          </div>

          {meta && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: ".4rem" }}>
              <Chip label="Cohort" value={meta.cohort_size} />
              <Chip label="Scoring window" value={`${meta.window_days}d`} />
              <Chip label="Ownership lookback" value={`${meta.ownership_lookback_days}d`} />
              <Chip label="Generated" value={generated} />
            </div>
          )}
        </header>

        {error && (
          <div
            role="alert"
            style={{
              padding: "1rem", border: "1px solid var(--border)",
              borderRadius: 10, background: "var(--surface)",
            }}
          >
            <strong>Couldn’t load engineers.json:</strong> {error}
          </div>
        )}

        {!error && !data && (
          <p style={{ color: "var(--muted)" }}>Loading analysis…</p>
        )}

        {data && (
          <>
            <div className="layout">
              <Leaderboard engineers={ranked} weights={weights} />
              <RubricCard weights={weights} setWeights={setWeights} />
            </div>

            {meta?.notes?.length > 0 && (
              <footer style={{ marginTop: ".5rem", fontSize: ".75rem", color: "var(--muted)" }}>
                <p style={{ margin: "0 0 .3rem", fontWeight: 600 }}>Methodology notes</p>
                <ul style={{ margin: 0, paddingLeft: "1.1rem" }}>
                  {meta.notes.map((n, i) => (
                    <li key={i}>{n}</li>
                  ))}
                </ul>
              </footer>
            )}
          </>
        )}
      </main>
    </div>
  );
}
