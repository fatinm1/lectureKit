/**
 * Lumina-style features grid — three capability cards (Student / Faculty / Provost).
 */

import { MarketingScrollReveal } from "./MarketingScrollReveal";

function ArrowRightSmall(): JSX.Element {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M5 12h14" />
      <path d="m12 5 7 7-7 7" />
    </svg>
  );
}

function SparklesLarge(): JSX.Element {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="96"
      height="96"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-white"
      aria-hidden
    >
      <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z" />
    </svg>
  );
}

export function MarketingFeatures(): JSX.Element {
  return (
    <section id="features" className="scroll-mt-24 bg-zinc-950 py-24" aria-labelledby="features-title">
      <div className="mx-auto max-w-6xl px-6">
        <MarketingScrollReveal className="mb-16 text-center">
          <span className="text-xs font-semibold uppercase tracking-widest text-zinc-500">Features &amp; Benefits</span>
          <h2 id="features-title" className="mt-4 font-lk-serif text-4xl text-white md:text-5xl">
            Capabilities for every
            <br />
            role on campus
          </h2>
        </MarketingScrollReveal>

        <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
          <MarketingScrollReveal className="group flex min-h-[300px] flex-col justify-between rounded-3xl border border-white/5 bg-zinc-900/50 p-8 transition-colors hover:border-white/10">
            <div>
              <h3 className="text-2xl font-light leading-snug text-white">
                An easy to <br />
                <span className="font-lk-serif italic text-zinc-400">STUDY</span> <br />
                flow for every <br />
                <span className="rounded-sm bg-zinc-700 px-1 text-lg font-bold text-white">learner</span>
              </h3>
              <p className="mt-6 text-sm leading-relaxed text-zinc-400">
                Student — Compress 60 minutes of lecture into 15 minutes of active study. Timestamped outline,
                three-depth summaries, flashcards, semantic search, and bilingual support in 5 languages.
              </p>
            </div>
            <div className="mt-8 flex items-center gap-2">
              <a
                href="/study"
                className="flex items-center gap-2 rounded-full bg-zinc-100 px-6 py-2.5 text-sm font-medium text-black transition-colors hover:bg-zinc-200"
              >
                Study Mode <ArrowRightSmall />
              </a>
            </div>
          </MarketingScrollReveal>

          <MarketingScrollReveal className="relative flex min-h-[300px] flex-col items-center justify-center overflow-hidden rounded-3xl border border-white/5 bg-zinc-900/50 p-8 text-center transition-colors hover:border-white/10">
            <div className="absolute inset-0 z-10 bg-gradient-to-t from-black/80 to-transparent" />
            <h1 className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 select-none font-lk-serif text-[120px] text-zinc-800">
              AI
            </h1>
            <div className="relative z-20">
              <h3 className="mb-2 font-lk-serif text-2xl text-white">Faculty</h3>
              <p className="max-w-[220px] text-sm text-zinc-400">
                A private report scoring your lecture across pedagogical quality, accessibility, equity, and clarity with
                timestamped suggested rewrites.
              </p>
            </div>
          </MarketingScrollReveal>

          <MarketingScrollReveal className="group relative flex min-h-[300px] flex-col justify-between overflow-hidden rounded-3xl border border-white/5 bg-zinc-900/50 p-8 transition-colors hover:border-white/10">
            <div className="absolute right-0 top-0 p-8 opacity-20">
              <div className="transition-transform duration-700 group-hover:rotate-12">
                <SparklesLarge />
              </div>
            </div>
            <div className="relative z-10 mt-auto">
              <div className="mb-4 flex -space-x-2">
                <img
                  className="h-8 w-8 rounded-full border-2 border-zinc-900"
                  src="https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=64&h=64"
                  alt=""
                  width={32}
                  height={32}
                />
                <img
                  className="h-8 w-8 rounded-full border-2 border-zinc-900"
                  src="https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=64&h=64"
                  alt=""
                  width={32}
                  height={32}
                />
                <div className="flex h-8 w-8 items-center justify-center rounded-full border-2 border-zinc-900 bg-zinc-800 text-[10px] text-white">
                  +5
                </div>
              </div>
              <h3 className="mb-1 font-lk-serif text-xl text-white">Provost</h3>
              <p className="text-sm text-zinc-400">
                Paste multiple lecture URLs and your learning objectives. See which objectives were covered, which were
                missed, and what to fix.
              </p>
            </div>
          </MarketingScrollReveal>
        </div>
      </div>
    </section>
  );
}
