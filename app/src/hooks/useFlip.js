import { useLayoutEffect, useRef } from "react";

const prefersReducedMotion = () =>
  typeof window !== "undefined" &&
  window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/*
  FLIP animation for list reordering without a dependency.
  Register each row via ref={flip.register(key)}. On every render whose `deps`
  changed, rows that moved slide from their previous position to the new one.
  Honors prefers-reduced-motion (no transform animation).
*/
export function useFlip(deps) {
  const nodes = useRef(new Map());
  const positions = useRef(new Map());

  const register = (key) => (el) => {
    if (el) nodes.current.set(key, el);
    else nodes.current.delete(key);
  };

  useLayoutEffect(() => {
    const reduce = prefersReducedMotion();
    nodes.current.forEach((el, key) => {
      const prevTop = positions.current.get(key);
      const newTop = el.getBoundingClientRect().top;
      if (prevTop != null && !reduce) {
        const dy = prevTop - newTop;
        if (Math.abs(dy) > 1) {
          el.style.transition = "transform 0s";
          el.style.transform = `translateY(${dy}px)`;
          requestAnimationFrame(() => {
            el.style.transition = "transform 480ms cubic-bezier(.2,.8,.2,1)";
            el.style.transform = "";
          });
        }
      }
    });
    const next = new Map();
    nodes.current.forEach((el, key) =>
      next.set(key, el.getBoundingClientRect().top)
    );
    positions.current = next;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { register };
}
