/**
 * Lumina-style hero — gradient serif headline, badge, dual capability cards, floating widgets.
 */

import Link from "next/link";
import { MarketingScrollReveal } from "./MarketingScrollReveal";

function ArrowRightIcon(): JSX.Element {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-white"
      aria-hidden
    >
      <path d="M5 12h14" />
      <path d="m12 5 7 7-7 7" />
    </svg>
  );
}

function UsersIcon(): JSX.Element {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-white"
      aria-hidden
    >
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  );
}

function ZapIcon(): JSX.Element {
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
      className="text-zinc-400"
      aria-hidden
    >
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  );
}

export function MarketingHero(): JSX.Element {
  return (
    <section
      aria-labelledby="marketing-hero-title"
      className="relative flex min-h-[90vh] flex-col items-center justify-center overflow-hidden bg-zinc-950 pb-20 pt-32"
    >
      <div className="pointer-events-none absolute left-1/2 top-0 h-[500px] w-full max-w-[800px] -translate-x-1/2 rounded-full bg-purple-600/10 blur-[120px]" />
      <div className="pointer-events-none absolute bottom-0 right-0 h-[600px] w-full max-w-[600px] rounded-full bg-blue-600/5 blur-[120px]" />

      <MarketingScrollReveal className="relative z-10 mx-auto max-w-5xl px-6 text-center">
        <div className="mb-8 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-zinc-300 backdrop-blur-sm">
          <span className="h-2 w-2 animate-pulse rounded-full bg-green-500" />
          Now live — Student, Faculty, and Provost modes
        </div>

        <h1
          id="marketing-hero-title"
          className="mb-8 bg-gradient-to-b from-white via-white to-zinc-500 bg-clip-text font-lk-serif text-5xl leading-[1.1] tracking-tight text-transparent md:text-7xl lg:text-8xl"
        >
          Turn Any Lecture Into
          <br />
          <span className="font-light italic">Intelligence</span>
        </h1>

        <p className="mx-auto mb-12 max-w-2xl text-lg font-light text-zinc-400">
          LectureKit transforms university lecture recordings into personalized study environments, private faculty audits,
          and curriculum coverage maps — powered by a multi-agent AI pipeline.
        </p>

        <div id="capabilities" className="flex flex-col items-center justify-center gap-6 sm:flex-row scroll-mt-24">
          <div className="group relative w-full rounded-2xl bg-gradient-to-b from-white/20 to-transparent p-px transition-all duration-500 hover:from-white/40 sm:w-64">
            <div className="relative flex h-full flex-col items-start overflow-hidden rounded-2xl bg-zinc-900/90 p-6 text-left backdrop-blur-xl">
              <div className="absolute right-0 top-0 p-4 opacity-20 transition-opacity group-hover:opacity-40">
                <ArrowRightIcon />
              </div>
              <span className="mb-2 text-xs uppercase tracking-wider text-zinc-500">For Students</span>
              <h3 className="mb-1 font-lk-serif text-xl text-white">Study Mode</h3>
              <p className="mb-4 text-xs text-zinc-400">
                Timestamped outlines, summaries, flashcards, and semantic search in 5 languages
              </p>
              <Link
                href="/app"
                className="mt-auto w-full rounded-full bg-zinc-100 px-6 py-2.5 text-center text-sm font-medium text-black transition-colors hover:bg-zinc-200"
              >
                Launch App
              </Link>
            </div>
          </div>

          <div className="group relative w-full rounded-2xl bg-gradient-to-b from-white/20 to-transparent p-px transition-all duration-500 hover:from-white/40 sm:w-64">
            <div className="relative flex h-full flex-col items-start overflow-hidden rounded-2xl bg-zinc-900/90 p-6 text-left backdrop-blur-xl">
              <div className="absolute right-0 top-0 p-4 opacity-20 transition-opacity group-hover:opacity-40">
                <UsersIcon />
              </div>
              <span className="mb-2 text-xs uppercase tracking-wider text-zinc-500">For Institutions</span>
              <h3 className="mb-1 font-lk-serif text-xl text-white">Faculty + Provost</h3>
              <p className="mb-4 text-xs text-zinc-400">
                Private lecture audits and curriculum coverage mapping for educators and leaders
              </p>
              <a
                href="#features"
                className="mt-auto w-full rounded-full border border-zinc-700 bg-transparent px-6 py-2.5 text-center text-sm font-medium text-white transition-colors hover:bg-white/5"
              >
                Learn More
              </a>
            </div>
          </div>
        </div>
      </MarketingScrollReveal>

      <div className="lk-float-slow absolute left-[5%] top-40 hidden xl:block">
        <div className="flex w-48 items-center gap-3 rounded-xl border border-white/10 bg-zinc-800/80 p-3 shadow-2xl backdrop-blur-md">
          <img
            src="https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=64&h=64"
            alt=""
            className="h-8 w-8 rounded-full object-cover"
            width={32}
            height={32}
          />
          <div>
            <div className="mb-1 h-2 w-20 rounded-full bg-zinc-600" />
            <div className="h-1.5 w-12 rounded-full bg-zinc-700" />
          </div>
        </div>
      </div>

      <div className="lk-float-delayed absolute bottom-20 right-[5%] hidden xl:block">
        <div className="flex w-48 items-center gap-3 rounded-xl border border-white/10 bg-zinc-800/80 p-3 shadow-2xl backdrop-blur-md">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-zinc-800">
            <ZapIcon />
          </div>
          <div>
            <div className="text-xs text-white">Lecture processed</div>
            <div className="text-[10px] text-zinc-400">Under 90s</div>
          </div>
        </div>
      </div>
    </section>
  );
}
