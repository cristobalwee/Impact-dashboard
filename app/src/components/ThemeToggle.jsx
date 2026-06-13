import { useEffect, useState } from "react";

// Manual light/dark override on top of prefers-color-scheme.
export default function ThemeToggle() {
  const [theme, setTheme] = useState(
    () => document.documentElement.getAttribute("data-theme") || "auto"
  );

  useEffect(() => {
    const el = document.documentElement;
    if (theme === "auto") el.removeAttribute("data-theme");
    else el.setAttribute("data-theme", theme);
  }, [theme]);

  const next = theme === "auto" ? "light" : theme === "light" ? "dark" : "auto";
  const labels = { auto: "Auto", light: "Light", dark: "Dark" };
  const icons = { auto: "🌗", light: "☀️", dark: "🌙" };

  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      aria-label={`Theme: ${labels[theme]}. Switch to ${labels[next]}.`}
      title={`Theme: ${labels[theme]} — click for ${labels[next]}`}
      style={{
        border: "1px solid var(--border)",
        background: "var(--surface)",
        color: "var(--text)",
        borderRadius: 8,
        padding: ".4rem .7rem",
        cursor: "pointer",
        fontSize: ".85rem",
        display: "inline-flex",
        gap: 6,
        alignItems: "center",
      }}
    >
      <span aria-hidden="true">{icons[theme]}</span>
      {labels[theme]}
    </button>
  );
}
