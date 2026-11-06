import { useEffect, useRef, useState } from "react";

// Width of an element, kept current with a ResizeObserver, so D3 charts redraw at phone and desktop widths.
export function useWidth(fallback = 640) {
  const ref = useRef(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    if (!ref.current) return undefined;
    const el = ref.current;
    setWidth(el.clientWidth || fallback);
    const ro = new ResizeObserver((entries) => {
      const w = Math.round(entries[0].contentRect.width);
      if (w > 0) setWidth(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [fallback]);
  return [ref, width];
}

export function useHash(defaultView) {
  const read = () => (window.location.hash || "").replace(/^#/, "") || defaultView;
  const [hash, setHash] = useState(read);
  useEffect(() => {
    const on = () => setHash(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  });
  return hash;
}
