"use client";

/**
 * Sign in / create an account (`/login`, `/login?mode=signup`, `?next=/library`).
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useState } from "react";

import { AppWorkspaceNavbar } from "../components/app/AppWorkspaceNavbar";
import { ApiError, signIn, signUp, useAccount } from "../../utils/account";

function safeNext(raw: string | null): string {
  // Only same-site paths: never bounce someone to another site after signing in.
  return raw && raw.startsWith("/") && !raw.startsWith("//") ? raw : "/library";
}

function LoginForm(): JSX.Element {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const { user, ready } = useAccount();
  const [mode, setMode] = useState<"signin" | "signup">(params.get("mode") === "signup" ? "signup" : "signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Already signed in when the page opens → go straight on. Not while submitting: sign-in
  // finishes saving earlier runs to the library first, then navigates itself.
  useEffect(() => {
    if (ready && user && !busy) router.replace(next);
  }, [ready, user, busy, next, router]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await (mode === "signup" ? signUp(email, password) : signIn(email, password));
      router.replace(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
      setBusy(false);
    }
  }

  const input =
    "min-h-[44px] w-full rounded-lg border border-white/10 bg-zinc-900 px-3 py-2 text-sm text-white outline-none transition-colors placeholder:text-zinc-500 focus:border-[#5e6ad2]/60 focus:ring-1 focus:ring-[#5e6ad2]";

  return (
    <div className="mx-auto w-full max-w-sm">
      <h1 className="text-center font-lk-serif text-3xl text-white">
        {mode === "signup" ? "Create your account" : "Welcome back"}
      </h1>
      <p className="mt-2 text-center text-sm text-zinc-400">
        {mode === "signup"
          ? "Keep every study kit, audit and curriculum map in one library, and share any of them with a link."
          : "Sign in to see your library."}
      </p>

      <form onSubmit={submit} className="mt-8 flex flex-col gap-4">
        <label className="flex flex-col gap-1.5 text-sm text-zinc-300">
          Email
          <input
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={input}
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm text-zinc-300">
          Password
          <input
            type="password"
            autoComplete={mode === "signup" ? "new-password" : "current-password"}
            required
            minLength={mode === "signup" ? 8 : undefined}
            maxLength={128}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={input}
          />
          {mode === "signup" ? <span className="text-xs text-zinc-500">At least 8 characters.</span> : null}
        </label>
        {error ? (
          <p role="alert" className="text-sm text-[#e53e3e]">
            {error}
          </p>
        ) : null}
        <button
          type="submit"
          disabled={busy}
          className="min-h-[44px] rounded-full bg-zinc-100 px-6 py-2.5 text-sm font-medium text-black transition-colors hover:bg-zinc-200 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {busy ? "One moment…" : mode === "signup" ? "Create account" : "Sign in"}
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-zinc-500">
        {mode === "signup" ? "Already have an account? " : "New to LectureKit? "}
        <button
          type="button"
          onClick={() => {
            setMode(mode === "signup" ? "signin" : "signup");
            setError(null);
          }}
          className="text-zinc-300 underline-offset-2 hover:text-white hover:underline"
        >
          {mode === "signup" ? "Sign in" : "Create an account"}
        </button>
      </p>
      {mode === "signin" ? (
        <p className="mt-3 text-center text-xs text-zinc-600">
          Forgot your password? Password reset by email isn&apos;t available yet.
        </p>
      ) : null}
      <p className="mt-8 text-center text-xs text-zinc-600">
        <Link href="/app" className="hover:text-zinc-400">
          Continue without an account
        </Link>
      </p>
    </div>
  );
}

export default function LoginPage(): JSX.Element {
  return (
    <div className="relative min-h-screen bg-zinc-950 text-zinc-200">
      <AppWorkspaceNavbar />
      <main className="relative z-10 px-6 pt-36">
        <Suspense fallback={null}>
          <LoginForm />
        </Suspense>
      </main>
    </div>
  );
}
