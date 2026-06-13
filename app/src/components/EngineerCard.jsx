import { PILLARS } from "../lib/scoring";
import Radar from "./charts/Radar";
import StackedBar, { COLORS } from "./charts/StackedBar";
import Sparkline from "./charts/Sparkline";

const SHORT = { authorship: "A", collaboration: "C", ownership: "O", consistency: "K", influence: "I" };

// Labeled pillar percentiles, readable at a glance (A 98 · C 97 · ...).
function PillarChips({ pillars }) {
  return (
    <ul
      aria-label="Pillar percentiles"
      style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexWrap: "wrap", gap: ".3rem .7rem" }}
    >
      {PILLARS.map((p) => (
        <li
          key={p.key}
          title={`${p.label}: ${Math.round(pillars[p.key] ?? 0)}th percentile`}
          style={{ display: "flex", alignItems: "center", gap: 5, fontSize: ".74rem", color: "var(--muted)", fontVariantNumeric: "tabular-nums" }}
        >
          <span aria-hidden="true" style={{ width: 8, height: 8, borderRadius: 2, background: COLORS[p.key] }} />
          <abbr title={p.label} style={{ textDecoration: "none", fontWeight: 600, color: "var(--text)" }}>{SHORT[p.key]}</abbr>
          {Math.round(pillars[p.key] ?? 0)}
        </li>
      ))}
    </ul>
  );
}

function Avatar({ engineer, size = 40 }) {
  const initials = (engineer.name || engineer.login || "?")
    .split(/\s+/).map((s) => s[0]).slice(0, 2).join("").toUpperCase();
  if (engineer.avatar_url) {
    return <img src={engineer.avatar_url} alt="" width={size} height={size} loading="lazy" style={{ borderRadius: "50%", flexShrink: 0 }} />;
  }
  return (
    <div aria-hidden="true" style={{ width: size, height: size, borderRadius: "50%", flexShrink: 0, background: "var(--border)", color: "var(--muted)", display: "grid", placeItems: "center", fontSize: size * 0.36, fontWeight: 600 }}>
      {initials}
    </div>
  );
}

const STAT_FIELDS = [
  ["merged_prs", "Merged PRs"],
  ["reviews_substantive", "Substantive reviews"],
  ["distinct_reviewed", "Authors reviewed"],
  ["effective_churn", "Effective churn"],
  ["survival_rate", "Code survival"],
  ["owned_critical_files", "Owned hot files"],
  ["active_weeks", "Active weeks"],
  ["commits", "Commits"],
];

export default function EngineerCard({ engineer, weights, featured, expanded, onToggle }) {
  const e = engineer;
  const panelId = `eng-panel-${e.id}`;
  const btnId = `eng-btn-${e.id}`;

  return (
    <article className="card" style={{ overflow: "hidden" }}>
      <button
        id={btnId}
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        aria-controls={panelId}
        style={{
          width: "100%", textAlign: "left", cursor: "pointer",
          background: "transparent", border: "none", color: "inherit",
          padding: featured ? "0.95rem 1.1rem" : "0.8rem 1.1rem",
          display: "grid",
          gridTemplateColumns: "auto auto 1fr auto",
          columnGap: "0.95rem", rowGap: ".5rem", alignItems: "center",
        }}
      >
        {/* rank */}
        <span
          aria-hidden="true"
          style={{
            fontVariantNumeric: "tabular-nums", fontWeight: 700,
            fontSize: featured ? "1.35rem" : "1rem",
            color: e.liveRank <= 3 ? "var(--accent)" : "var(--muted)",
            minWidth: featured ? 30 : 22, textAlign: "center", alignSelf: "start",
            marginTop: featured ? 2 : 0,
          }}
        >
          {e.liveRank}
        </span>

        <span style={{ alignSelf: "start" }}>
          <Avatar engineer={e} size={featured ? 46 : 38} />
        </span>

        {/* content */}
        <span style={{ minWidth: 0, display: "grid", gap: featured ? ".45rem" : ".4rem" }}>
          <span style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontWeight: 600, fontSize: featured ? "1.08rem" : ".96rem" }}>{e.name}</span>
            {e.login && <span style={{ color: "var(--muted)", fontSize: ".8rem" }}>@{e.login}</span>}
          </span>

          {e.evidence?.[0] && (
            <span style={{ color: "var(--muted)", fontSize: ".82rem", lineHeight: 1.35 }}>
              {e.evidence[0]}
            </span>
          )}

          <StackedBar pillars={e.pillars} weights={weights} name={e.name} compact />
          <PillarChips pillars={e.pillars} />
        </span>

        {/* score */}
        <span style={{ display: "flex", alignItems: "center", gap: ".5rem", alignSelf: "start", marginTop: featured ? 2 : 0 }}>
          <span style={{ display: "grid", justifyItems: "end" }}>
            <span style={{ fontVariantNumeric: "tabular-nums", fontWeight: 700, fontSize: featured ? "1.55rem" : "1.15rem", lineHeight: 1 }}>
              {e.score.toFixed(1)}
            </span>
            <span style={{ fontSize: ".66rem", color: "var(--muted)", textTransform: "uppercase", letterSpacing: ".04em" }}>impact</span>
          </span>
          <span aria-hidden="true" style={{ color: "var(--muted)", transform: expanded ? "rotate(180deg)" : "none", transition: "transform .2s" }}>▾</span>
        </span>
      </button>

      {expanded && (
        <div
          id={panelId}
          role="region"
          aria-labelledby={btnId}
          style={{
            padding: "1rem 1.1rem 1.15rem",
            display: "grid",
            gridTemplateColumns: "minmax(180px, 220px) 1fr",
            gap: "1.25rem",
            borderTop: "1px solid var(--border)",
          }}
        >
          <div style={{ display: "grid", placeItems: "center" }}>
            <Radar pillars={e.pillars} name={e.name} size={200} />
          </div>

          <div>
            <h3 style={{ margin: "0 0 .4rem", fontSize: ".85rem", color: "var(--muted)" }}>
              Weighted contribution to composite
            </h3>
            <StackedBar pillars={e.pillars} weights={weights} name={e.name} />

            {e.evidence?.length > 0 && (
              <ul style={{ margin: ".9rem 0 0", paddingLeft: "1.1rem", fontSize: ".88rem", lineHeight: 1.5 }}>
                {e.evidence.slice(0, 4).map((s, i) => <li key={i}>{s}</li>)}
              </ul>
            )}

            <div style={{ marginTop: ".9rem" }}>
              <h3 style={{ margin: "0 0 .25rem", fontSize: ".85rem", color: "var(--muted)" }}>
                Weekly activity (commits · reviews)
              </h3>
              <Sparkline data={e.sparkline} name={e.name} />
            </div>

            <dl style={{ marginTop: ".9rem", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: ".5rem .9rem" }}>
              {STAT_FIELDS.map(([k, label]) => {
                let v = e.stats?.[k];
                if (v == null) return null;
                if (k === "survival_rate") v = `${Math.round(v * 100)}%`;
                else if (typeof v === "number") v = v.toLocaleString();
                return (
                  <div key={k}>
                    <dt style={{ fontSize: ".7rem", color: "var(--muted)" }}>{label}</dt>
                    <dd style={{ margin: 0, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{v}</dd>
                  </div>
                );
              })}
            </dl>
          </div>
        </div>
      )}
    </article>
  );
}
