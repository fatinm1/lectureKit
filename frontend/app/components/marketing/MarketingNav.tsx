"use client";

/**
 * Lumina-style marketing nav — fixed blur bar, desktop + mobile menu.
 */

import Link from "next/link";
import { useCallback, useState } from "react";

export function MarketingNav(): JSX.Element {
  const [mobileOpen, setMobileOpen] = useState(false);

  const closeMobile = useCallback(() => setMobileOpen(false), []);

  const launchClasses =
    "rounded-full bg-zinc-100 px-5 py-2 text-sm font-medium text-black transition-colors hover:bg-zinc-200";

  return (
    <nav className="fixed top-0 z-50 w-full border-b border-white/5 bg-zinc-950/80 backdrop-blur-md">
      <div className="mx-auto flex h-20 max-w-7xl items-center justify-between px-6">
        <Link href="/" className="font-lk-serif text-xl tracking-tight text-white" onClick={closeMobile}>
          LectureKit
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
          <Link href="/app" className={launchClasses}>
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
            <Link href="/app" className={`${launchClasses} block w-full py-2 text-center`} onClick={closeMobile}>
              Launch App
            </Link>
          </div>
        </div>
      </div>
    </nav>
  );
}
