"use client";

/** Account (`/account`): change password, sign out, delete the account and its library. */

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { AppWorkspaceNavbar } from "../components/app/AppWorkspaceNavbar";
import { ApiError, changePassword, deleteAccount, signOut, useAccount } from "../../utils/account";

const input =
  "min-h-[44px] w-full rounded-lg border border-white/10 bg-zinc-900 px-3 py-2 text-sm text-white outline-none transition-colors focus:border-[#5e6ad2]/60 focus:ring-1 focus:ring-[#5e6ad2]";
const label = "flex flex-col gap-1.5 text-sm text-zinc-300";

export default function AccountPage(): JSX.Element {
  const router = useRouter();
  const { user, ready } = useAccount();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [pwNote, setPwNote] = useState<{ ok: boolean; text: string } | null>(null);
  const [deletePw, setDeletePw] = useState("");
  const [deleteNote, setDeleteNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (ready && !user) router.replace("/login?next=/account");
  }, [ready, user, router]);

  async function onChangePassword(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setPwNote(null);
    try {
      await changePassword(current, next);
      setCurrent("");
      setNext("");
      setPwNote({ ok: true, text: "Password changed. You've been signed out everywhere else." });
    } catch (err) {
      setPwNote({ ok: false, text: err instanceof ApiError ? err.message : "Couldn't change your password." });
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(e: FormEvent) {
    e.preventDefault();
    if (!window.confirm("Delete your account and everything in your library? Share links you've sent will stop working. This can't be undone.")) return;
    setBusy(true);
    setDeleteNote(null);
    try {
      await deleteAccount(deletePw);
      router.replace("/app");
    } catch (err) {
      setDeleteNote(err instanceof ApiError ? err.message : "Couldn't delete your account.");
      setBusy(false);
    }
  }

  if (!user) return <div className="min-h-screen bg-zinc-950" />;

  return (
    <div className="relative min-h-screen bg-zinc-950 text-zinc-200">
      <AppWorkspaceNavbar />
      <main className="relative z-10 mx-auto flex max-w-md flex-col gap-10 px-6 pb-24 pt-32">
        <section>
          <h1 className="font-lk-serif text-3xl text-white">Account</h1>
          <p className="mt-1 text-sm text-zinc-400">{user.email}</p>
          <button
            type="button"
            onClick={() => void signOut().then(() => router.replace("/app"))}
            className="mt-4 rounded-full border border-zinc-700 px-5 py-2 text-sm text-zinc-200 transition-colors hover:border-zinc-500"
          >
            Sign out
          </button>
        </section>

        <form onSubmit={onChangePassword} className="flex flex-col gap-4">
          <h2 className="text-base font-medium text-white">Change password</h2>
          <label className={label}>
            Current password
            <input type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} className={input} />
          </label>
          <label className={label}>
            New password
            <input type="password" autoComplete="new-password" required minLength={8} maxLength={128} value={next} onChange={(e) => setNext(e.target.value)} className={input} />
          </label>
          {pwNote ? <p className={`text-sm ${pwNote.ok ? "text-emerald-300" : "text-[#e53e3e]"}`}>{pwNote.text}</p> : null}
          <button
            type="submit"
            disabled={busy}
            className="self-start rounded-full bg-zinc-100 px-5 py-2 text-sm font-medium text-black transition-colors hover:bg-zinc-200 disabled:opacity-60"
          >
            Change password
          </button>
        </form>

        <form onSubmit={onDelete} className="flex flex-col gap-4 rounded-xl border border-[#e53e3e]/20 p-5">
          <h2 className="text-base font-medium text-white">Delete account</h2>
          <p className="text-sm text-zinc-400">
            Removes your account, your whole library and every share link you&apos;ve made.
          </p>
          <label className={label}>
            Password
            <input type="password" autoComplete="current-password" required value={deletePw} onChange={(e) => setDeletePw(e.target.value)} className={input} />
          </label>
          {deleteNote ? <p className="text-sm text-[#e53e3e]">{deleteNote}</p> : null}
          <button
            type="submit"
            disabled={busy}
            className="self-start rounded-full border border-[#e53e3e]/40 px-5 py-2 text-sm text-[#f87171] transition-colors hover:bg-[#e53e3e]/10 disabled:opacity-60"
          >
            Delete my account
          </button>
        </form>
      </main>
    </div>
  );
}
