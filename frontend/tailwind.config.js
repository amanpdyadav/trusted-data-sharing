/** Colours come from CSS variables in src/index.css (light by default, `.dark` for dark). */
import animate from "tailwindcss-animate";
const v = name => `hsl(var(--${name}) / <alpha-value>)`;
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ['"Archivo"', '"Arial Narrow"', "Arial", "sans-serif"],
        sans: ['"IBM Plex Sans"', '"Segoe UI"', "Arial", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "Menlo", "monospace"],
      },
      colors: {
        border: v("border"), input: v("input"), ring: v("ring"), background: v("background"), foreground: v("foreground"),
        primary: { DEFAULT: v("primary"), foreground: v("primary-foreground") },
        secondary: { DEFAULT: v("secondary"), foreground: v("secondary-foreground") },
        muted: { DEFAULT: v("muted"), foreground: v("muted-foreground") },
        accent: { DEFAULT: v("accent"), foreground: v("accent-foreground") },
        card: { DEFAULT: v("card"), foreground: v("card-foreground") },
        popover: { DEFAULT: v("popover"), foreground: v("popover-foreground") },
        destructive: { DEFAULT: v("destructive"), foreground: v("destructive-foreground") },
        risk: { DEFAULT: v("risk"), soft: v("risk-soft") },     // exposure in the raw data
        safe: { DEFAULT: v("safe"), soft: v("safe-soft") },     // protection
        warn: { DEFAULT: v("warn"), soft: v("warn-soft") },     // what an outsider may know; needs a decision
        ok: { DEFAULT: v("ok"), soft: v("ok-soft") },
      },
      borderRadius: { lg: "var(--radius)", md: "calc(var(--radius) - 2px)", sm: "calc(var(--radius) - 4px)" },
      keyframes: {
        reveal: { from: { opacity: "0", transform: "translateY(10px)" }, to: { opacity: "1", transform: "none" } },
        flow: { to: { strokeDashoffset: "-20" } },
      },
      animation: { reveal: "reveal .5s both", flow: "flow 1.4s linear infinite" },
    },
  },
  plugins: [animate],
};
