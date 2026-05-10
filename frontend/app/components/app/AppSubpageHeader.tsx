/**
 * Subpage header — back to /app + serif title (study, report, curriculum).
 */

"use client";

import { useRouter } from "next/navigation";
import type { ReactNode } from "react";

type AppSubpageHeaderProps = {
  title: string;
  right?: ReactNode;
};

export function AppSubpageHeader({ title, right }: AppSubpageHeaderProps): JSX.Element {
  const router = useRouter();

  return (
    <header className="border-b border-white/5 bg-zinc-950/90 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-[1600px] items-center justify-between gap-4 px-6">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={() => router.push("/app")}
            className="shrink-0 rounded-full border border-zinc-700 bg-transparent px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-white/5"
          >
            ← Back
          </button>
          <span className="hidden text-zinc-600 sm:inline" aria-hidden>
            |
          </span>
          <h1 className="truncate font-lk-serif text-lg font-normal text-white md:text-xl">{title}</h1>
        </div>
        {right ? <div className="flex shrink-0 items-center gap-3">{right}</div> : null}
      </div>
    </header>
  );
}
