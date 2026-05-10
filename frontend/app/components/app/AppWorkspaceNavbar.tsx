/**
 * Fixed workspace navbar — matches landing Lumina chrome.
 */

import Link from "next/link";

export function AppWorkspaceNavbar(): JSX.Element {
  return (
    <nav className="fixed top-0 z-50 w-full border-b border-white/5 bg-zinc-950/80 backdrop-blur-md">
      <div className="mx-auto flex h-20 max-w-7xl items-center justify-between px-6">
        <div className="flex items-center gap-6">
          <Link href="/" className="font-lk-serif text-xl tracking-tight text-white">
            LectureKit
          </Link>
          <Link
            href="/diagram"
            className="rounded-full border border-zinc-800 bg-transparent px-4 py-2 text-sm font-medium text-zinc-300 transition-colors hover:border-zinc-600 hover:text-white hover:bg-white/5"
          >
            Diagram
          </Link>
        </div>
        <span className="text-xs font-medium uppercase tracking-widest text-zinc-500">App</span>
      </div>
    </nav>
  );
}
