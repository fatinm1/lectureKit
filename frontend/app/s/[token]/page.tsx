"use client";

/**
 * Share link (`/s/<token>`): look up what was shared and open it read-only on the usual page.
 */

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ApiError, getShared, itemHref } from "../../../utils/account";

export default function SharedLinkPage(): JSX.Element {
  const router = useRouter();
  const { token } = useParams<{ token: string }>();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getShared(token)
      .then((item) => router.replace(itemHref(item.kind, { share: token })))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Couldn't open this link."));
  }, [token, router]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-zinc-950 px-6 text-center">
      {error ? (
        <>
          <p className="text-sm text-zinc-300">{error}</p>
          <Link href="/app" className="text-sm text-zinc-500 underline-offset-2 hover:text-white hover:underline">
            Make your own study kit
          </Link>
        </>
      ) : (
        <p className="font-mono text-sm text-zinc-500">Opening shared link…</p>
      )}
    </div>
  );
}
