import { PILLARS } from "../../lib/scoring";

// Lightweight SVG radar of the 5 pillar percentiles (0–100).
export default function Radar({ pillars, size = 200, name }) {
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 26;
  const n = PILLARS.length;

  const point = (i, value) => {
    const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
    const rad = (value / 100) * r;
    return [cx + rad * Math.cos(angle), cy + rad * Math.sin(angle)];
  };

  const axisPoint = (i, mult = 1) => {
    const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
    return [cx + r * mult * Math.cos(angle), cy + r * mult * Math.sin(angle)];
  };

  const dataPath =
    PILLARS.map((p, i) => point(i, pillars[p.key] ?? 0))
      .map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`)
      .join(" ") + " Z";

  const rings = [25, 50, 75, 100];
  const label = `Pillar radar for ${name}: ` +
    PILLARS.map((p) => `${p.label} ${Math.round(pillars[p.key] ?? 0)}`).join(", ");

  return (
    <svg
      viewBox={`0 0 ${size} ${size}`}
      width={size}
      height={size}
      role="img"
      aria-label={label}
    >
      {rings.map((ring) => (
        <polygon
          key={ring}
          points={PILLARS.map((_, i) => axisPoint(i, ring / 100).join(",")).join(" ")}
          fill="none"
          stroke="var(--border)"
          strokeWidth="1"
        />
      ))}
      {PILLARS.map((_, i) => {
        const [x, y] = axisPoint(i);
        return (
          <line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke="var(--border)" strokeWidth="1" />
        );
      })}
      <path
        d={dataPath}
        fill="var(--accent)"
        fillOpacity="0.25"
        stroke="var(--accent)"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      {PILLARS.map((p, i) => {
        const [x, y] = point(i, pillars[p.key] ?? 0);
        return <circle key={p.key} cx={x} cy={y} r="3" fill="var(--accent)" />;
      })}
      {PILLARS.map((p, i) => {
        const [x, y] = axisPoint(i, 1.18);
        return (
          <text
            key={p.key}
            x={x}
            y={y}
            fontSize="9"
            fill="var(--muted)"
            textAnchor="middle"
            dominantBaseline="middle"
          >
            {p.label}
          </text>
        );
      })}
    </svg>
  );
}
