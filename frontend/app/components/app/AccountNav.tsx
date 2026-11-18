"use client";

/** "Library" + sign-in state, shown in the workspace navbar and on result pages. */

import Link from "next/link";

import { useAccount } from "../../../utils/account";

export function AccountNav({ compact = false }: { compact?: boolean }): JSX.Element | null {
  const { user, ready } = useAccount();
  if (!ready) return null;
  const link = "text-sm text-zinc-400 transition-colors hover:text-white";
  if (!user) {
    return (
      <Link href="/login" className={link}>
        Sign in
      </Link>
    );
  }
  return (
    <div className="flex items-center gap-4">
      <Link href="/library" className={link}>
        Library
      </Link>
      {compact ? null : (
        <Link href="/account" className={`${link} hidden max-w-[180px] truncate sm:inline`} title={user.email}>
          {user.email}
        </Link>
      )}
    </div>
  );
}
