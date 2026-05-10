/**
 * Stats / social proof grid (replaces Lumina testimonials).
 */

import { MarketingScrollReveal } from "./MarketingScrollReveal";

function StarIcon(): JSX.Element {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="#eab308"
      stroke="#eab308"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z" />
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
                <div className="h-full w-[72%] rounded-full bg-[#5e6ad2]" />
              </div>
            </div>

            <div className="flex h-[400px] flex-col justify-center rounded-3xl border border-white/10 bg-gradient-to-b from-zinc-900 to-zinc-950 p-8 text-center shadow-inner">
              <div className="font-mono text-5xl font-light tracking-tight text-[#5e6ad2]">&lt;0.02s</div>
              <p className="mt-4 text-sm text-zinc-400">Median semantic search latency across indexed chunks</p>
              <div className="mt-8 mx-auto h-px w-24 bg-gradient-to-r from-transparent via-[#5e6ad2]/50 to-transparent" />
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
