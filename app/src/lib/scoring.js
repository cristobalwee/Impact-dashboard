// Pure client-side reweighting. Pillar scores are precomputed by score.py;
// changing weights only re-blends and re-sorts — never re-runs the pipeline.

export const PILLARS = [
  { key: "authorship", label: "Authorship", short: "Durable, meaningful code" },
  { key: "collaboration", label: "Collaboration", short: "How much you enable others" },
  { key: "ownership", label: "Ownership", short: "Load-bearing code you own" },
  { key: "consistency", label: "Consistency", short: "Sustained engagement" },
  { key: "influence", label: "Influence", short: "Position in the collab graph" },
];

export const DEFAULT_WEIGHTS = {
  authorship: 25,
  collaboration: 25,
  ownership: 20,
  consistency: 15,
  influence: 15,
};

export function composite(pillars, weights) {
  const total = Object.values(weights).reduce((a, b) => a + b, 0) || 1;
  let sum = 0;
  for (const k of Object.keys(weights)) sum += (pillars[k] ?? 0) * weights[k];
  return sum / total;
}

// Returns engineers with a recomputed `score`, sorted desc, with a fresh `liveRank`.
export function rankEngineers(engineers, weights) {
  const scored = engineers.map((e) => ({
    ...e,
    score: composite(e.pillars, weights),
  }));
  scored.sort((a, b) => b.score - a.score || a.name.localeCompare(b.name));
  scored.forEach((e, i) => (e.liveRank = i + 1));
  return scored;
}
