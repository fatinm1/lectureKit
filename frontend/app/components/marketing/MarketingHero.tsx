/**
 * Marketing hero — full-viewport storyfold with dual CTAs, credibility stats,
 * and a contained perspective grid + pulsing lavender/indigo glow (pure CSS / Tailwind).
 *
 * Purpose: Sell LectureKit; conversion routes to `/app`. Background motion stays subtle so
 * typography and CTAs remain the focal layer (z-index stacking + hero overflow clipping).
 */

import Link from "next/link";

const STATS = ["3 AI Agents", "Instant Results", "5 Languages"] as const;

/** Primary stroke for hero grid lines (#5e6ad2 at top of 0.12–0.15 visibility band). */
const GRID_LINE = "rgba(94, 106, 210, 0.35)";

export function MarketingHero(): JSX.Element {
  /**
   * Present hero narrative over layered atmospheric chrome.
   *
   * Steps:
   * 1. Clip all decorative layers with `overflow-hidden` so effects never bleed past the hero.
   * 2. Stack glow (z-0), vignette (z-[1]), grid (z-[2]) so the canvas vignette never paints over lines.
   * 3. Grid uses repeating gradients + `perspective(800px) rotateX(35deg) translateZ(0)`, mask fade.
   * 4. Grid: motion-safe `hero-grid-scroll` shifts background-position Y only; glow inner uses motion-safe scale pulse. No opacity animations on hero chrome.
   */
  return (
    <section
      aria-labelledby="marketing-hero-title"
      className="relative isolate flex min-h-screen flex-col overflow-hidden pt-14"
    >
      {/* Decorative stack — pointer-events none so anchors remain clickable */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
        {/*
          Radial glow — concentrated purple orb (blur on wrapper keeps the core brighter).
        */}
        <div className="absolute bottom-[-12%] left-1/2 z-0 -translate-x-1/2 blur-3xl">
          <div
            className="h-[600px] w-[600px] rounded-full bg-purple-600 opacity-25 motion-safe:animate-hero-glow-float motion-reduce:animate-none"
            aria-hidden
          />
        </div>

        {/* Bottom vignette — sits above glow but below grid so it cannot erase the mesh */}
        <div className="absolute inset-x-0 bottom-0 z-[1] h-[28%] bg-gradient-to-t from-canvas via-canvas/55 to-transparent" />

        {/* Perspective grid — purple lines over glow + vignette, behind headline */}
        <div className="absolute inset-x-0 bottom-0 top-0 z-[2] flex items-end justify-center overflow-hidden">
          <div className="flex h-full w-full items-end justify-center">
            <div
              className="relative h-[76%] w-[230%] max-w-none origin-bottom motion-safe:animate-hero-grid-scroll motion-reduce:animate-none [will-change:transform]"
              style={{
                transform: "perspective(800px) rotateX(35deg) translateZ(0)",
                transformOrigin: "center bottom",
                backgroundImage: `repeating-linear-gradient(to bottom, transparent 0px, transparent 59px, ${GRID_LINE} 59px, ${GRID_LINE} 60px), repeating-linear-gradient(to right, transparent 0px, transparent 59px, ${GRID_LINE} 59px, ${GRID_LINE} 60px)`,
                backgroundSize: "60px 60px",
                /*
                  Fade toward top so copy stays crisp; keep lower mask strength so the floor plane
                  stays visible near the bottom (the prior mask fully erased the convergence zone).
                */
                maskImage:
                  "linear-gradient(to bottom, transparent 0%, rgba(0,0,0,0.85) 24%, black 55%, rgba(0,0,0,0.55) 88%, rgba(0,0,0,0.2) 100%)",
                WebkitMaskImage:
                  "linear-gradient(to bottom, transparent 0%, rgba(0,0,0,0.85) 24%, black 55%, rgba(0,0,0,0.55) 88%, rgba(0,0,0,0.2) 100%)",
              }}
            >
              {/* Subtle center glow overlay above grid lines */}
              <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(94,106,210,0.25)_0%,transparent_70%)]" />
            </div>
          </div>
        </div>
      </div>

      <div className="relative z-10 flex flex-1 flex-col items-center justify-center px-md py-section-xl">
        <div className="relative mx-auto max-w-4xl text-center">
          <h1
            id="marketing-hero-title"
            className="text-display-marketing text-balance text-ink transition-opacity duration-interaction ease-out"
          >
            Every lecture. Instantly understood.
          </h1>
          <p className="mx-auto mt-lg max-w-2xl text-body text-marketing-muted">
            Paste any YouTube lecture and get an instant study kit — summaries, flashcards, and semantic
            search. Built for students who learn fast.
          </p>

          <div className="mt-xl flex flex-col items-center justify-center gap-sm sm:flex-row sm:gap-md">
            <Link
              href="/app"
              className="inline-flex min-h-[44px] items-center justify-center rounded-linear bg-primary px-[14px] py-[8px] text-button font-medium text-onprimary transition duration-interaction ease-out hover:bg-primary-hover active:bg-primary-focus"
            >
              Get Started Free
            </Link>
            <a
              href="#features"
              className="inline-flex min-h-[44px] items-center justify-center rounded-linear border border-marketing-divider px-[14px] py-[8px] text-button font-medium text-marketing-muted transition duration-interaction ease-out hover:border-primary hover:text-ink"
            >
              See how it works
            </a>
          </div>

          <div
            className="mt-xxl flex flex-wrap items-center justify-center gap-x-md gap-y-xs text-caption font-medium uppercase tracking-[0.16em] text-marketing-muted"
            aria-label="Product highlights"
          >
            {STATS.map((label, index) => (
              <span key={label} className="flex items-center gap-x-md">
                {index > 0 ? (
                  <span aria-hidden className="hidden text-marketing-divider sm:inline">
                    ·
                  </span>
                ) : null}
                <span>{label}</span>
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
