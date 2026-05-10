"use client";

/**
 * Lumina-style marketing nav — fixed blur bar, desktop + mobile menu.
 */

import Link from "next/link";
import { useCallback, useState } from "react";

function SparklesIcon({ className }: { className?: string }): JSX.Element {
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
      className={className}
      aria-hidden
    >
      <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z" />
    </svg>
  );
}

export function MarketingNav(): JSX.Element {
  const [mobileOpen, setMobileOpen] = useState(false);

  const closeMobile = useCallback(() => setMobileOpen(false), []);

  return (
    <nav className="fixed top-0 z-50 w-full border-b border-white/5 bg-zinc-950/80 backdrop-blur-md">
      <div className="mx-auto flex h-20 max-w-7xl items-center justify-between px-6">
        <Link href="/" className="group flex items-center gap-2" onClick={closeMobile}>
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[#5e6ad2] transition-transform duration-300 group-hover:rotate-12">
            <SparklesIcon className="text-white" />
          </div>
          <span className="font-lk-serif text-xl tracking-tight text-white">LectureKit</span>
        </Link>

        <div className="hidden items-center gap-8 text-sm text-zinc-400 md:flex">
          <a href="#features" className="transition-colors hover:text-white">
            Features
          </a>
          <a href="#how-it-works" className="transition-colors hover:text-white">
            How It Works
          </a>
          <a href="#capabilities" className="transition-colors hover:text-white">
            Capabilities
          </a>
        </div>

        <div className="hidden items-center gap-4 md:flex">
          <Link
            href="/app"
            className="rounded-full bg-[#5e6ad2] px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-[#4f5ab8]"
          >
            Launch App
          </Link>
        </div>

        <button
          type="button"
          aria-expanded={mobileOpen}
          aria-controls="marketing-mobile-menu"
          className="p-2 text-white md:hidden"
          onClick={() => setMobileOpen((o) => !o)}
        >
          {mobileOpen ? (
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
              aria-hidden
            >
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
          ) : (
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
              aria-hidden
            >
              <line x1="4" x2="20" y1="12" y2="12" />
              <line x1="4" x2="20" y1="6" y2="6" />
              <line x1="4" x2="20" y1="18" y2="18" />
            </svg>
          )}
        </button>
      </div>

      <div
        id="marketing-mobile-menu"
        className={`absolute w-full border-b border-white/10 bg-zinc-950 p-6 md:hidden ${mobileOpen ? "block" : "hidden"}`}
      >
        <div className="flex flex-col space-y-4">
          <a href="#features" className="block text-zinc-400 hover:text-white" onClick={closeMobile}>
            Features
          </a>
          <a href="#how-it-works" className="block text-zinc-400 hover:text-white" onClick={closeMobile}>
            How It Works
          </a>
          <a href="#capabilities" className="block text-zinc-400 hover:text-white" onClick={closeMobile}>
            Capabilities
          </a>
          <div className="flex flex-col gap-3 border-t border-white/10 pt-4">
            <Link
              href="/app"
              className="w-full rounded-full bg-[#5e6ad2] py-2 text-center font-medium text-white"
              onClick={closeMobile}
            >
              Launch App
            </Link>
          </div>
        </div>
      </div>
    </nav>
  );
}
