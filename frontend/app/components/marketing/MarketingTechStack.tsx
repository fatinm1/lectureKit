/**
 * Floating glass pills — LectureKit tech stack (Lumina integrations styling).
 */

import { MarketingScrollReveal } from "./MarketingScrollReveal";

const STACK: readonly { label: string; delay: string; duration: string; className: string }[] = [
  {
    label: "Claude Sonnet",
    delay: "0s",
    duration: "6s",
    className:
      "bg-gradient-to-br from-white/10 to-gray-500/10 backdrop-blur-md border border-white/10 text-zinc-200",
  },
  {
    label: "sentence-transformers",
    delay: "1.2s",
    duration: "7s",
    className:
      "bg-gradient-to-br from-purple-500/20 to-pink-500/20 backdrop-blur-md border border-purple-500/20 text-pink-100",
  },
  {
    label: "ChromaDB",
    delay: "0.5s",
    duration: "5.5s",
    className:
      "bg-gradient-to-br from-orange-500/20 to-red-500/20 backdrop-blur-md border border-orange-500/20 text-orange-100",
  },
  {
    label: "Supadata API",
    delay: "2.1s",
    duration: "8s",
    className:
      "bg-gradient-to-br from-indigo-500/20 to-purple-500/20 backdrop-blur-md border border-indigo-500/20 text-indigo-100",
  },
  {
    label: "FastAPI",
    delay: "1.5s",
    duration: "6.5s",
    className:
      "bg-gradient-to-br from-blue-400/20 to-blue-600/20 backdrop-blur-md border border-blue-400/20 text-blue-100",
  },
  {
    label: "Next.js",
    delay: "0.8s",
    duration: "7.2s",
    className:
      "bg-gradient-to-br from-emerald-500/20 to-green-500/20 backdrop-blur-md border border-emerald-500/20 text-emerald-100",
  },
  {
    label: "Vercel",
    delay: "2.5s",
    duration: "6.8s",
    className:
      "bg-gradient-to-br from-cyan-500/20 to-blue-500/20 backdrop-blur-md border border-cyan-500/20 text-cyan-100",
  },
  {
    label: "Railway",
    delay: "0.3s",
    duration: "5.8s",
    className:
      "bg-gradient-to-br from-zinc-600/20 to-zinc-800/20 backdrop-blur-md border border-zinc-600/20 text-zinc-200",
  },
  {
    label: "Python",
    delay: "1.8s",
    duration: "7.5s",
    className:
      "bg-gradient-to-br from-blue-500/20 to-indigo-500/20 backdrop-blur-md border border-blue-500/20 text-blue-100",
  },
  {
    label: "TypeScript",
    delay: "1s",
    duration: "6.2s",
    className:
      "bg-gradient-to-br from-indigo-400/20 to-violet-500/20 backdrop-blur-md border border-indigo-400/20 text-indigo-100",
  },
];

export function MarketingTechStack(): JSX.Element {
  return (
    <section className="border-t border-white/5 bg-zinc-950 py-24">
      <div className="mx-auto max-w-4xl px-6 text-center">
        <MarketingScrollReveal>
          <span className="text-xs font-semibold uppercase tracking-widest text-zinc-500">Stack</span>
          <h2 className="mb-12 mt-4 font-lk-serif text-4xl text-white">
            Built with tools you
            <br />
            can trust
          </h2>

          <div className="flex flex-wrap justify-center gap-5 py-8">
            {STACK.map((item) => (
              <div
                key={item.label}
                className={`lk-float-slow cursor-default rounded-full border px-6 py-3 text-sm font-medium shadow-lg transition-transform duration-300 hover:scale-110 ${item.className}`}
                style={{
                  animationDelay: item.delay,
                  animationDuration: item.duration,
                }}
              >
                {item.label}
              </div>
            ))}
          </div>
        </MarketingScrollReveal>
      </div>
    </section>
  );
}
