"use client";

/**
 * Library (`/library`): everything the signed-in user has generated, newest first.
 * Open, rename, share (copy a read-only link / turn the link off) and delete.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppWorkspaceNavbar } from "../components/app/AppWorkspaceNavbar";
import {
  ApiError,
  deleteLibraryItem,
  itemHref,
  listLibrary,
  renameLibraryItem,
  shareLibraryItem,
  shareUrl,
  unshareLibraryItem,
  useAccount,
  type LibraryItem,
  type LibraryKind,
} from "../../utils/account";
import { copyText } from "../../utils/clipboard";

const KIND_LABEL: Record<LibraryKind, string> = { student: "Study kit", faculty: "Faculty audit", provost: "Curriculum map" };
const KIND_STYLE: Record<LibraryKind, string> = {
  student: "border-[#5e6ad2]/40 text-[#9ca3f5]",
  faculty: "border-amber-500/40 text-amber-300",
  provost: "border-emerald-500/40 text-emerald-300",
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export default function LibraryPage(): JSX.Element {
  const router = useRouter();
  const { user, ready } = useAccount();
  const [items, setItems] = useState<LibraryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<LibraryKind | "all">("all");

  const load = useCallback(() => {
    listLibrary()
      .then(setItems)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Couldn't load your library."));
  }, []);

  useEffect(() => {
    if (!ready) return;
    if (!user) {
      router.replace("/login?next=/library");
      return;
    }
    load();
  }, [ready, user, router, load]);

  const replace = (next: LibraryItem) => setItems((prev) => prev?.map((i) => (i.id === next.id ? next : i)) ?? null);
  const shown = items?.filter((i) => filter === "all" || i.kind === filter) ?? [];

  return (
    <div className="relative min-h-screen bg-zinc-950 text-zinc-200">
      <AppWorkspaceNavbar />
      <main className="relative z-10 mx-auto max-w-4xl px-6 pb-24 pt-32">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-lk-serif text-3xl text-white">Your library</h1>
            <p className="mt-1 text-sm text-zinc-500">Everything you generate while signed in is saved here.</p>
          </div>
          <Link
            href="/app"
            className="rounded-full bg-zinc-100 px-5 py-2 text-sm font-medium text-black transition-colors hover:bg-zinc-200"
          >
            New lecture
          </Link>
        </div>

        {items && items.length > 0 ? (
          <div className="mt-8 flex flex-wrap gap-2" role="tablist" aria-label="Filter by type">
            {(["all", "student", "faculty", "provost"] as const).map((k) => (
              <button
                key={k}
                type="button"
                role="tab"
                aria-selected={filter === k}
                onClick={() => setFilter(k)}
                className={`rounded-full px-3 py-1.5 text-xs transition-colors ${
                  filter === k ? "bg-zinc-100 text-black" : "border border-zinc-800 text-zinc-400 hover:text-white"
                }`}
              >
                {k === "all" ? `All (${items.length})` : KIND_LABEL[k]}
              </button>
            ))}
          </div>
        ) : null}

        {error ? <p className="mt-8 text-sm text-[#e53e3e]">{error}</p> : null}
        {items === null && !error ? <p className="mt-8 text-sm text-zinc-500">Loading…</p> : null}
        {items && items.length === 0 ? (
          <div className="mt-10 rounded-xl border border-white/5 bg-zinc-900/40 p-8 text-center">
            <p className="text-sm text-zinc-300">Nothing here yet.</p>
            <p className="mt-1 text-sm text-zinc-500">
              Process a lecture and it lands here automatically, ready to reopen or share.
            </p>
          </div>
        ) : null}

        <ul className="mt-6 flex flex-col gap-3">
          {shown.map((item) => (
            <LibraryRow
              key={item.id}
              item={item}
              onChange={replace}
              onDelete={() => setItems((prev) => prev?.filter((i) => i.id !== item.id) ?? null)}
            />
          ))}
        </ul>
      </main>
    </div>
  );
}

function LibraryRow({
  item,
  onChange,
  onDelete,
}: {
  item: LibraryItem;
  onChange: (i: LibraryItem) => void;
  onDelete: () => void;
}): JSX.Element {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(item.title);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setNote(null);
    try {
      await fn();
    } catch (e) {
      setNote(e instanceof ApiError ? e.message : "That didn't work. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  // Both call copyText straight from the click (no await before it), which Safari requires.
  const afterCopy = (ok: boolean) => {
    if (ok) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
      setNote(null);
    } else {
      setNote("Your browser blocked copying. Select the link above and copy it.");
    }
  };

  const copyExisting = (token: string) => void copyText(shareUrl(token)).then(afterCopy);

  const shareAndCopy = () => {
    setBusy(true);
    setNote(null);
    const link = shareLibraryItem(item.id).then((shared) => {
      onChange(shared);
      return shareUrl(shared.share_token!);
    });
    void copyText(link)
      .then(afterCopy)
      .catch((e) => setNote(e instanceof ApiError ? e.message : "Couldn't turn on sharing. Please try again."))
      .finally(() => setBusy(false));
  };

  const action = "text-xs text-zinc-400 transition-colors hover:text-white disabled:opacity-50";

  return (
    <li className="rounded-xl border border-white/5 bg-zinc-900/40 p-4 transition-colors hover:border-white/10">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className={`rounded-full border px-2 py-0.5 font-mono text-[10px] uppercase ${KIND_STYLE[item.kind]}`}>
              {KIND_LABEL[item.kind]}
            </span>
            {item.shared ? (
              <span className="rounded-full border border-white/10 px-2 py-0.5 font-mono text-[10px] uppercase text-zinc-400">
                Shared
              </span>
            ) : null}
            <span className="text-xs text-zinc-600">{formatDate(item.created_at)}</span>
          </div>
          {editing ? (
            <form
              className="mt-2 flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                void run(async () => {
                  onChange(await renameLibraryItem(item.id, title));
                  setEditing(false);
                });
              }}
            >
              <input
                autoFocus
                value={title}
                maxLength={200}
                onChange={(e) => setTitle(e.target.value)}
                aria-label="Title"
                className="min-h-[36px] flex-1 rounded-lg border border-white/10 bg-zinc-900 px-3 text-sm text-white outline-none focus:border-[#5e6ad2]/60"
              />
              <button type="submit" disabled={busy || !title.trim()} className={action}>
                Save
              </button>
              <button
                type="button"
                onClick={() => {
                  setEditing(false);
                  setTitle(item.title);
                }}
                className={action}
              >
                Cancel
              </button>
            </form>
          ) : (
            <Link
              href={itemHref(item.kind, { item: item.id })}
              className="mt-1.5 block truncate text-base text-white hover:underline"
            >
              {item.title}
            </Link>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-4">
          {item.shared && item.share_token ? (
            <>
              <button type="button" className={action} onClick={() => copyExisting(item.share_token!)}>
                {copied ? "Copied ✓" : "Copy link"}
              </button>
              <button
                type="button"
                disabled={busy}
                className={action}
                onClick={() =>
                  void run(async () => {
                    onChange(await unshareLibraryItem(item.id));
                    setNote("Link turned off. Anyone who had it can no longer open it.");
                  })
                }
              >
                Stop sharing
              </button>
            </>
          ) : (
            <button type="button" disabled={busy} className={action} onClick={shareAndCopy}>
              Share
            </button>
          )}
          {!editing ? (
            <button type="button" className={action} onClick={() => setEditing(true)}>
              Rename
            </button>
          ) : null}
          <button
            type="button"
            disabled={busy}
            className="text-xs text-zinc-500 transition-colors hover:text-[#e53e3e] disabled:opacity-50"
            onClick={() => {
              if (!window.confirm(`Delete "${item.title}"? This can't be undone${item.shared ? ", and its share link stops working" : ""}.`)) return;
              void run(async () => {
                await deleteLibraryItem(item.id);
                onDelete();
              });
            }}
          >
            Delete
          </button>
        </div>
      </div>
      {item.shared && item.share_token ? (
        <div className="mt-3 flex flex-col gap-1.5">
          <label className="sr-only" htmlFor={`share-${item.id}`}>
            Share link
          </label>
          <input
            id={`share-${item.id}`}
            readOnly
            value={shareUrl(item.share_token)}
            onFocus={(e) => e.currentTarget.select()}
            onClick={(e) => e.currentTarget.select()}
            className="w-full rounded-lg border border-white/10 bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-300 outline-none focus:border-[#5e6ad2]/60"
          />
          <p className="text-xs text-zinc-500">
            {copied ? "Copied. " : ""}Anyone with this link can view (not edit) it.
          </p>
        </div>
      ) : null}
      {note ? <p className="mt-3 break-all text-xs text-zinc-400">{note}</p> : null}
    </li>
  );
}
