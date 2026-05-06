import type { Config } from "tailwindcss";

/**
 * Tailwind theme extensions mapped from `/DESIGN.md` (Linear design system).
 * Canvas/surface/ink tokens mirror the YAML front matter; transitions use 150ms ease per product spec.
 */
const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: "#010102",
        surface: {
          1: "#0f1011",
          2: "#141516",
          3: "#18191a",
          4: "#191a1b",
        },
        hairline: {
          DEFAULT: "#23252a",
          strong: "#34343a",
          tertiary: "#3e3e44",
        },
        ink: {
          DEFAULT: "#f7f8f8",
          muted: "#d0d6e0",
          subtle: "#8a8f98",
          tertiary: "#62666d",
        },
        primary: {
          DEFAULT: "#5e6ad2",
          hover: "#828fff",
          focus: "#5e69d1",
        },
        onprimary: "#ffffff",
        success: "#27a644",
        /** Marketing page utilities — divider/muted per landing spec while canvas/primary stay DESIGN.md */
        marketing: {
          divider: "#1a1a1a",
          muted: "#6b7280",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        /** Landing headline — product brief specifies 48px bold; Inter substitutes Linear Display. */
        hero: ["48px", { lineHeight: "1.1", letterSpacing: "-0.02em", fontWeight: "700" }],
        /** Marketing homepage hero — Linear display scale via Inter */
        "display-marketing": [
          "clamp(2.75rem, 5vw, 3.5rem)",
          { lineHeight: "1.08", letterSpacing: "-0.03em", fontWeight: "600" },
        ],
        section: ["24px", { lineHeight: "1.25", letterSpacing: "-0.015em", fontWeight: "600" }],
        body: ["16px", { lineHeight: "1.5", letterSpacing: "-0.01em", fontWeight: "400" }],
        secondary: ["14px", { lineHeight: "1.5", letterSpacing: "0", fontWeight: "400" }],
        /** DESIGN.md `typography.eyebrow` — section taxonomy with slight positive tracking */
        eyebrow: ["13px", { lineHeight: "1.3", letterSpacing: "0.4px", fontWeight: "500" }],
        /** Step titles — between headline (28px token) and body */
        subhead: ["20px", { lineHeight: "1.4", letterSpacing: "-0.01em", fontWeight: "600" }],
        caption: ["12px", { lineHeight: "1.4", letterSpacing: "0", fontWeight: "500" }],
        button: ["14px", { lineHeight: "1.2", letterSpacing: "0", fontWeight: "500" }],
      },
      spacing: {
        xxs: "4px",
        xs: "8px",
        sm: "12px",
        md: "16px",
        lg: "24px",
        xl: "32px",
        xxl: "48px",
        section: "96px",
        /** Minimum vertical rhythm for marketing sections (120px) */
        "section-xl": "120px",
      },
      borderRadius: {
        linear: "8px",
        xs: "4px",
      },
      transitionDuration: {
        interaction: "150ms",
        enter: "300ms",
        /** Product preview hover scale — marketing spec */
        preview: "200ms",
      },
      maxWidth: {
        content: "1280px",
        preview: "900px",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        /** Hero glow pulse — inner gradient scale only (blur stays on outer wrapper). motion-safe in JSX. */
        "hero-glow-pulse": {
          "0%, 100%": { transform: "scale(1)" },
          "50%": { transform: "scale(1.08)" },
        },
        /**
         * Hero glow float — slow organic positional drift (no size/color/opacity changes).
         * Matches the marketing spec: translate between waypoints over an 8s loop.
         */
        "hero-glow-float": {
          "0%, 100%": { transform: "translate(0%, 10%) translateZ(0)" },
          "25%": { transform: "translate(15%, -5%) translateZ(0)" },
          "50%": { transform: "translate(-15%, -10%) translateZ(0)" },
          "75%": { transform: "translate(10%, 15%) translateZ(0)" },
        },
        /** Hero grid — vertical background-position drift (one 60px cell per loop, seamless repeat). */
        "hero-grid-scroll": {
          /**
           * Animate only the horizontal-line layer (first background-image) on Y.
           * Keep the vertical-line layer fixed so the motion reads as “forward travel”.
           */
          "0%": { backgroundPosition: "0px 0px, 0px 0px" },
          "100%": { backgroundPosition: "0px 60px, 0px 0px" },
        },
      },
      animation: {
        "fade-in": "fade-in var(--tw-duration, 300ms) ease-out forwards",
        "hero-glow-pulse": "hero-glow-pulse 4s ease-in-out infinite",
        "hero-glow-float": "hero-glow-float 8s ease-in-out infinite",
        "hero-grid-scroll": "hero-grid-scroll 3s linear infinite",
      },
      boxShadow: {
        /** Subtle lavender glow on focused inputs — aligns with focus ring emphasis in DESIGN.md */
        "focus-glow": "0 0 0 2px rgba(94, 105, 209, 0.45), 0 0 24px rgba(94, 106, 210, 0.22)",
      },
    },
  },
  plugins: [],
};
export default config;
