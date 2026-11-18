/** Shown on a result page opened from someone's share link. */

import Link from "next/link";

export function SharedBanner({ title }: { title?: string }): JSX.Element {
  return (
    <div className="border-b border-[#5e6ad2]/20 bg-[#5e6ad2]/10">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-2 px-6 py-2 text-xs">
        <span className="text-zinc-300">
          Shared with you{title ? <> · <span className="text-white">{title}</span></> : null} · read-only
        </span>
        <Link href="/app" className="text-[#9ca3f5] underline-offset-2 hover:underline">
          Make your own with LectureKit →
        </Link>
      </div>
    </div>
  );
}
