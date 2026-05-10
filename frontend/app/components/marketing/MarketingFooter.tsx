/**
 * Lumina-style footer — CTA band, link columns, attribution.
 */

import Link from "next/link";
import { MarketingScrollReveal } from "./MarketingScrollReveal";

const GITHUB = "https://github.com/fatinm1/lectureKit";

function SparklesIcon(): JSX.Element {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="black"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z" />
    </svg>
  );
}

export function MarketingFooter(): JSX.Element {
  return (
    <footer className="relative overflow-hidden bg-zinc-950 pt-20 pb-10">
      <div className="pointer-events-none absolute left-1/2 top-0 h-[300px] w-[120%] -translate-x-1/2 -translate-y-1/2 rounded-[100%] bg-zinc-900/50 blur-3xl" />

      <div className="relative z-10 mx-auto max-w-4xl px-6 text-center">
        <MarketingScrollReveal>
          <span className="text-xs font-semibold uppercase tracking-widest text-zinc-500">Get Started</span>
          <h2 className="mb-8 mt-6 font-lk-serif text-5xl text-white md:text-6xl">
            Ready to unlock your
            <br />
            lecture recordings?
          </h2>
          <p className="mx-auto mb-10 max-w-xl text-zinc-400">
            One app. Three roles. Powered by real AI agent orchestration.
          </p>

          <div className="mb-20 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <Link
              href="/app"
              className="w-full rounded-full bg-zinc-100 px-6 py-2.5 text-center text-sm font-medium text-black transition-colors hover:bg-zinc-200 sm:w-auto"
            >
              Launch App
            </Link>
            <a
              href={GITHUB}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-full border border-zinc-700 bg-transparent px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-white/5"
            >
              View on GitHub
            </a>
          </div>
        </MarketingScrollReveal>
      </div>

      <div className="mx-auto grid max-w-7xl grid-cols-2 gap-8 border-t border-white/5 px-6 pt-12 md:grid-cols-4">
        <div className="col-span-2 md:col-span-1">
          <div className="mb-4 flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded-full bg-zinc-100">
              <SparklesIcon />
            </div>
            <span className="font-lk-serif tracking-tight text-white">LectureKit</span>
          </div>
          <p className="text-xs text-zinc-500">
            © {new Date().getFullYear()} LectureKit
            <br />
            All rights reserved.
          </p>
        </div>

        <div>
          <h4 className="mb-4 text-sm font-medium text-white">Product</h4>
          <ul className="space-y-2 text-xs text-zinc-500">
            <li>
              <a href="#features" className="hover:text-zinc-300">
                Features
              </a>
            </li>
            <li>
              <a href="#how-it-works" className="hover:text-zinc-300">
                How It Works
              </a>
            </li>
            <li>
              <Link href="/app" className="hover:text-zinc-300">
                Launch App
              </Link>
            </li>
            <li>
              <a href={GITHUB} target="_blank" rel="noopener noreferrer" className="hover:text-zinc-300">
                GitHub
              </a>
            </li>
          </ul>
        </div>

        <div>
          <h4 className="mb-4 text-sm font-medium text-white">Capabilities</h4>
          <ul className="space-y-2 text-xs text-zinc-500">
            <li>
              <Link href="/study" className="hover:text-zinc-300">
                Student Mode
              </Link>
            </li>
            <li>
              <Link href="/report" className="hover:text-zinc-300">
                Faculty Mode
              </Link>
            </li>
            <li>
              <Link href="/curriculum" className="hover:text-zinc-300">
                Provost Mode
              </Link>
            </li>
          </ul>
        </div>

        <div>
          <h4 className="mb-4 text-sm font-medium text-white">Built by</h4>
          <p className="text-xs leading-relaxed text-zinc-500">
            Fatin Mojumder
            <br />
            UMBC
            <br />
            <a href="mailto:fatinm1@umbc.edu" className="hover:text-zinc-300">
              fatinm1@umbc.edu
            </a>
          </p>
        </div>
      </div>
    </footer>
  );
}
