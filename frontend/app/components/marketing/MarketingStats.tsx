/**
 * Stats / social proof grid (replaces Lumina testimonials).
 */

import { MarketingScrollReveal } from "./MarketingScrollReveal";

function StarIcon(): JSX.Element {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="#eab308" aria-hidden>
      <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
    </svg>
  );
}

export function MarketingStats(): JSX.Element {
  return (
    <section className="bg-zinc-950 py-24" aria-labelledby="stats-title">
      <div className="mx-auto max-w-6xl px-6">
        <MarketingScrollReveal>
          <h2 id="stats-title" className="mb-16 text-center font-lk-serif text-4xl text-white">
            Performance at a glance
          </h2>

          <div className="grid grid-cols-1 items-end gap-6 md:grid-cols-3">
            <div className="rounded-3xl border border-white/5 bg-zinc-900/30 p-8">
              <div className="mb-2 font-lk-serif text-5xl text-white">142</div>
              <p className="text-sm text-zinc-500">Semantic chunks from a single 2.5hr lecture</p>
              <div className="mt-8 h-1 w-full overflow-hidden rounded-full bg-zinc-800">
                <div className="h-full w-[72%] rounded-full bg-zinc-400" />
              </div>
            </div>

            <div className="flex h-[400px] flex-col justify-center rounded-3xl border border-white/10 bg-gradient-to-b from-zinc-900 to-zinc-950 p-8 text-center shadow-inner">
              <div className="font-mono text-5xl font-light tracking-tight text-zinc-300">&lt;0.02s</div>
              <p className="mt-4 text-sm text-zinc-400">Median semantic search latency across indexed chunks</p>
              <div className="mt-8 mx-auto h-px w-24 bg-gradient-to-r from-transparent via-zinc-500/50 to-transparent" />
            </div>

            <div className="flex h-full flex-col justify-center rounded-3xl border border-white/5 bg-zinc-900/30 p-8">
              <div className="mb-4 text-4xl text-zinc-700">&ldquo;</div>
              <p className="mb-6 text-xl font-light italic text-zinc-200">
                LectureKit found the exact moment in the lecture that answered my question. Not keyword matching —
                actual semantic similarity.
              </p>
              <div className="flex gap-1">
                {Array.from({ length: 5 }).map((_, i) => (
                  <StarIcon key={i} />
                ))}
              </div>
            </div>
          </div>
        </MarketingScrollReveal>
      </div>
    </section>
  );
}
