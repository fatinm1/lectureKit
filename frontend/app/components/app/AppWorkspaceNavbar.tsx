/**
 * Fixed workspace navbar — matches landing Lumina chrome (LectureKit + sparkles).
 */

import Link from "next/link";

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

export function AppWorkspaceNavbar(): JSX.Element {
  return (
    <nav className="fixed top-0 z-50 w-full border-b border-white/5 bg-zinc-950/80 backdrop-blur-md">
      <div className="mx-auto flex h-20 max-w-7xl items-center justify-between px-6">
        <Link href="/" className="group flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[#5e6ad2] transition-transform duration-300 group-hover:rotate-12">
            <SparklesIcon className="text-white" />
          </div>
          <span className="font-lk-serif text-xl tracking-tight text-white">LectureKit</span>
        </Link>
        <span className="text-xs font-medium uppercase tracking-widest text-zinc-500">App</span>
      </div>
    </nav>
  );
}
