/**
 * Lumina “strategy” section — four How It Works cards with mock UI chrome.
 */

import { MarketingScrollReveal } from "./MarketingScrollReveal";

export function MarketingHowItWorks(): JSX.Element {
  return (
    <section id="how-it-works" className="scroll-mt-24 overflow-hidden bg-zinc-950 py-24" aria-labelledby="how-title">
      <div className="mx-auto max-w-6xl px-6">
        <MarketingScrollReveal className="mb-16 text-center">
          <span className="text-xs font-semibold uppercase tracking-widest text-zinc-500">How it works</span>
          <h2 id="how-title" className="mt-4 font-lk-serif text-4xl text-white md:text-5xl">
            From link to insight
            <br />
            in under a minute
          </h2>
        </MarketingScrollReveal>

        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          {/* Card 1: Paste URL */}
          <MarketingScrollReveal className="group relative overflow-hidden rounded-3xl border border-white/5 bg-zinc-900/30 p-8">
            <div className="mb-6 transform rounded-xl border border-white/10 bg-zinc-950 p-4 shadow-2xl transition-transform duration-500 group-hover:scale-[1.02]">
              <div className="mb-3 flex items-center gap-2 rounded-lg border border-white/10 bg-zinc-900/80 px-3 py-2">
                <span className="text-xs text-zinc-500">https://</span>
                <span className="truncate text-xs text-zinc-300">youtube.com/watch?v=…</span>
              </div>
              <div className="flex justify-between text-[10px] text-zinc-500">
                <span>Public lecture URL</span>
                <span className="rounded-full bg-[#5e6ad2]/20 px-2 py-0.5 text-[#5e6ad2]">Valid</span>
              </div>
            </div>
            <h3 className="mb-1 font-lk-serif text-xl text-white">Paste a YouTube URL</h3>
            <p className="text-sm text-zinc-500">Any public lecture — we preserve timestamps end-to-end.</p>
          </MarketingScrollReveal>

          {/* Card 2: Select role */}
          <MarketingScrollReveal className="group relative overflow-hidden rounded-3xl border border-white/5 bg-zinc-900/30 p-8">
            <div className="mb-6 flex gap-4">
              <div className="flex-1 transform rounded-xl border border-white/10 bg-zinc-950 p-4 shadow-xl transition-transform duration-500 delay-75 group-hover:-translate-y-1">
                <div className="mb-2 text-xs font-medium text-[#5e6ad2]">Student</div>
                <div className="text-[10px] text-zinc-500">Study kit &amp; search</div>
              </div>
              <div className="flex-1 transform rounded-xl border border-white/10 bg-zinc-950 p-4 shadow-xl transition-transform duration-500 group-hover:-translate-y-1">
                <div className="mb-2 text-xs font-medium text-zinc-300">Faculty</div>
                <div className="text-[10px] text-zinc-500">Private audit</div>
              </div>
            </div>
            <h3 className="mb-1 font-lk-serif text-xl text-white">Select your role</h3>
            <p className="text-sm text-zinc-500">Student, Faculty, or Provost — each path gets tailored outputs.</p>
          </MarketingScrollReveal>

          {/* Card 3: Agents */}
          <MarketingScrollReveal className="group relative overflow-hidden rounded-3xl border border-white/5 bg-zinc-900/30 p-8">
            <div className="mb-6 space-y-3">
              <div className="flex transform items-center gap-2 transition-transform group-hover:translate-x-1">
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-zinc-800">
                  <div className="h-full w-[88%] rounded-full bg-[#5e6ad2]" />
                </div>
                <span className="text-[10px] text-zinc-500">Agents</span>
              </div>
              <div className="flex transform items-center gap-2 transition-transform group-hover:translate-x-1">
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-zinc-800">
                  <div className="h-full w-full rounded-full bg-zinc-600 motion-safe:animate-pulse" />
                </div>
                <span className="text-[10px] text-zinc-500">&lt;90s</span>
              </div>
            </div>
            <h3 className="mb-1 font-lk-serif text-xl text-white">Agents process your lecture</h3>
            <p className="text-sm text-zinc-500">Multi-agent orchestration finishes in under 90 seconds.</p>
          </MarketingScrollReveal>

          {/* Card 4: Results */}
          <MarketingScrollReveal className="group relative overflow-hidden rounded-3xl border border-white/5 bg-zinc-900/30 p-8">
            <div className="mb-6 flex items-center gap-4 rounded-xl border border-white/10 bg-zinc-950 p-3 shadow-lg">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#5e6ad2]/20 text-sm font-medium text-[#5e6ad2]">
                ✓
              </div>
              <div className="flex-1">
                <div className="text-sm font-medium text-white">Results ready</div>
                <div className="text-xs text-zinc-500">Formatted for your role</div>
              </div>
            </div>
            <h3 className="mb-1 font-lk-serif text-xl text-white">Get results built for your role</h3>
            <p className="text-sm text-zinc-500">Study surfaces, audit reports, or coverage maps — not generic summaries.</p>
          </MarketingScrollReveal>
        </div>
      </div>
    </section>
  );
}
