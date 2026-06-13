// Weekly activity sparkline: commits (area) + reviews (line) across the window.
export default function Sparkline({ data, width = 240, height = 44, name }) {
  if (!data || data.length === 0) return null;
  const pad = 3;
  const maxC = Math.max(1, ...data.map((d) => d.commits));
  const maxR = Math.max(1, ...data.map((d) => d.reviews));
  const stepX = (width - pad * 2) / Math.max(1, data.length - 1);
  const x = (i) => pad + i * stepX;
  const yC = (v) => height - pad - (v / maxC) * (height - pad * 2);
  const yR = (v) => height - pad - (v / maxR) * (height - pad * 2);

  const commitArea =
    `M ${x(0)},${height - pad} ` +
    data.map((d, i) => `L ${x(i).toFixed(1)},${yC(d.commits).toFixed(1)}`).join(" ") +
    ` L ${x(data.length - 1)},${height - pad} Z`;
  const reviewLine = data
    .map((d, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)},${yR(d.reviews).toFixed(1)}`)
    .join(" ");

  const totalC = data.reduce((a, d) => a + d.commits, 0);
  const totalR = data.reduce((a, d) => a + d.reviews, 0);

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      height={height}
      role="img"
      aria-label={`Weekly activity for ${name} over ${data.length} weeks: ${totalC} commits, ${totalR} reviews`}
      preserveAspectRatio="none"
    >
      <path d={commitArea} fill="var(--accent)" fillOpacity="0.18" stroke="none" />
      <path
        d={data
          .map((d, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)},${yC(d.commits).toFixed(1)}`)
          .join(" ")}
        fill="none"
        stroke="var(--accent)"
        strokeWidth="1.5"
      />
      <path d={reviewLine} fill="none" stroke="#10b981" strokeWidth="1.5" strokeDasharray="3 2" />
    </svg>
  );
}
