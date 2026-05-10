/**
 * “Why LectureKit” — two-column block with checklist + mock audit card (replaces Lumina scheduling).
 */

import Link from "next/link";
import { MarketingScrollReveal } from "./MarketingScrollReveal";

function CheckIcon(): JSX.Element {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="3"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-white"
      aria-hidden
    >
      <circle cx="12" cy="12" r="10" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  );
}

export function MarketingWhySection(): JSX.Element {
  return (
    <section className="bg-zinc-950 py-24" aria-labelledby="why-title">
      <div className="mx-auto grid max-w-6xl grid-cols-1 items-center gap-16 px-6 lg:grid-cols-2">
        <MarketingScrollReveal>
          <h2 id="why-title" className="mb-6 font-lk-serif text-4xl text-white md:text-5xl">
            Built for real
            <br />
            institutional value
          </h2>
          <p className="mb-8 leading-relaxed text-zinc-400">
            Universities sit on terabytes of recorded content that compounds no value. LectureKit unlocks it.
          </p>

          <div className="mb-8 space-y-4">
            <div className="flex items-center gap-3">
              <div className="flex h-5 w-5 items-center justify-center rounded-full bg-[#5e6ad2]/20">
                <CheckIcon />
              </div>
              <span className="text-sm text-zinc-300">Students compress 60 minutes into 15 minutes of active study</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="flex h-5 w-5 items-center justify-center rounded-full bg-[#5e6ad2]/20">
                <CheckIcon />
              </div>
              <span className="text-sm text-zinc-300">Faculty get private timestamped feedback before publishing</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="flex h-5 w-5 items-center justify-center rounded-full bg-[#5e6ad2]/20">
                <CheckIcon />
              </div>
              <span className="text-sm text-zinc-300">
                Provosts verify course delivery against accreditation requirements
              </span>
            </div>
          </div>

          <Link
            href="/app"
            className="inline-block rounded-full bg-[#5e6ad2] px-6 py-3 text-sm font-medium text-white transition-colors hover:bg-[#4f5ab8]"
          >
            Launch App
          </Link>
        </MarketingScrollReveal>

        <MarketingScrollReveal className="relative">
          <div className="rounded-3xl border border-white/10 bg-zinc-900/80 p-8 shadow-2xl backdrop-blur-sm">
            <div className="mb-6 flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-zinc-500">Faculty audit preview</span>
              <span className="rounded-full bg-[#5e6ad2]/20 px-3 py-1 text-xs font-medium text-[#5e6ad2]">
                Private
              </span>
            </div>
            <div className="mb-8 flex items-end gap-2">
              <span className="font-lk-serif text-6xl text-white">8</span>
              <span className="pb-2 text-2xl text-zinc-500">/10</span>
              <span className="pb-2 ml-2 text-sm text-zinc-400">overall lecture quality</span>
            </div>
            <div className="rounded-xl border border-white/5 bg-zinc-950/80 p-4">
              <div className="mb-2 text-xs font-medium uppercase tracking-wide text-[#5e6ad2]">Top priority fix</div>
              <p className="text-sm text-zinc-300">
                Reduce jargon in minutes 12–18 — add a plain-language recap of the three evaluation criteria before the
                worked example.
              </p>
              <div className="mt-3 flex gap-2 text-[10px] text-zinc-500">
                <span className="rounded bg-zinc-800 px-2 py-0.5">12:04</span>
                <span className="rounded bg-zinc-800 px-2 py-0.5">14:22</span>
                <span className="rounded bg-zinc-800 px-2 py-0.5">16:51</span>
              </div>
            </div>
          </div>
        </MarketingScrollReveal>
      </div>
    </section>
  );
}
