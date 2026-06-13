import { useState } from "react";
import { useFlip } from "../hooks/useFlip";
import EngineerCard from "./EngineerCard";

const FEATURED = 5;

export default function Leaderboard({ engineers, weights }) {
  const [expanded, setExpanded] = useState(() => new Set());
  const [showAll, setShowAll] = useState(false);

  // Re-run FLIP whenever the ranking order changes.
  const orderKey = engineers.map((e) => e.id).join(",");
  const flip = useFlip([orderKey]);

  const toggle = (id) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const featured = engineers.slice(0, FEATURED);
  const rest = engineers.slice(FEATURED);

  const Row = (e, isFeatured) => (
    <div key={e.id} ref={flip.register(e.id)} style={{ willChange: "transform" }}>
      <EngineerCard
        engineer={e}
        weights={weights}
        featured={isFeatured}
        expanded={expanded.has(e.id)}
        onToggle={() => toggle(e.id)}
      />
    </div>
  );

  return (
    <section aria-labelledby="leaderboard-heading">
      <h2 id="leaderboard-heading" style={{ fontSize: "1rem", margin: "0 0 .75rem" }}>
        Leaderboard
        <span style={{ color: "var(--muted)", fontWeight: 400, fontSize: ".82rem", marginLeft: 8 }}>
          {engineers.length} engineers · click a row for the breakdown
        </span>
      </h2>

      <div style={{ display: "grid", gap: ".6rem" }}>
        {featured.map((e) => Row(e, true))}
      </div>

      {rest.length > 0 && (
        <div style={{ marginTop: ".9rem" }}>
          <button
            type="button"
            onClick={() => setShowAll((s) => !s)}
            aria-expanded={showAll}
            style={{
              width: "100%", padding: ".55rem", borderRadius: 9,
              border: "1px dashed var(--border)", background: "transparent",
              color: "var(--muted)", cursor: "pointer", fontSize: ".85rem",
            }}
          >
            {showAll ? "Hide" : `Show all ${engineers.length}`} — ranks {FEATURED + 1}–{engineers.length}
          </button>

          {showAll && (
            <div style={{ display: "grid", gap: ".45rem", marginTop: ".6rem" }}>
              {rest.map((e) => Row(e, false))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
