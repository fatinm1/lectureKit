/**
 * Accounts, library and share links (client side).
 *
 * The session is a bearer token in localStorage (`lecturekit_token`), sent as
 * `Authorization: Bearer …`. Cross-site cookies between Vercel and Railway are unreliable now that
 * browsers block third-party cookies, so a header is the dependable option. `useAccount()` gives
 * any component the signed-in user and re-renders on sign-in/out, including from other tabs.
 *
 * Runs finished before signing in aren't lost: their job IDs are remembered for a day
 * (`lecturekit_recent_jobs`), and signing in saves them to the new library (`flushRecentJobs`).
 */

"use client";

import { useEffect, useState } from "react";

import { getApiBaseUrl } from "./jobs";

export type User = { id: string; email: string; created_at: string };
export type LibraryKind = "student" | "faculty" | "provost";
export type LibraryItem = {
  id: string;
  kind: LibraryKind;
  video_id: string | null;
  title: string;
  shared: boolean;
  share_token: string | null;
  created_at: string;
};
export type SharedItem = { kind: LibraryKind; video_id: string | null; title: string; payload: unknown; created_at: string };

const TOKEN_KEY = "lecturekit_token";
const USER_KEY = "lecturekit_user";
const RECENT_KEY = "lecturekit_recent_jobs";
const CHANGE_EVENT = "lecturekit-auth";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number
  ) {
    super(message);
  }
}

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* storage unavailable */
  }
}

export function getToken(): string | null {
  return typeof window === "undefined" ? null : read(TOKEN_KEY);
}

function storedUser(): User | null {
  const raw = typeof window === "undefined" ? null : read(USER_KEY);
  try {
    return raw ? (JSON.parse(raw) as User) : null;
  } catch {
    return null;
  }
}

function setSession(token: string | null, user: User | null): void {
  sessionCheck = null;
  write(TOKEN_KEY, token);
  write(USER_KEY, user ? JSON.stringify(user) : null);
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

async function api<T>(path: string, init: RequestInit & { auth?: boolean } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const token = getToken();
  if (init.auth !== false && token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}${path}`, { ...init, headers });
  } catch {
    throw new ApiError("Can't reach LectureKit right now. Check your connection and try again.", 0);
  }
  if (response.status === 401 && token && init.auth !== false) {
    setSession(null, null); // session expired or revoked elsewhere
  }
  if (!response.ok) {
    const data = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const detail = typeof data?.detail === "string" ? data.detail : `Something went wrong (${response.status}).`;
    throw new ApiError(detail, response.status);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

// ---------- auth ----------

async function startSession(path: string, email: string, password: string): Promise<User> {
  const { token, user } = await api<{ token: string; user: User }>(path, {
    method: "POST",
    auth: false,
    body: JSON.stringify({ email, password }),
  });
  setSession(token, user);
  await flushRecentJobs(); // before the caller navigates to /library, so they're already there
  return user;
}

export const signUp = (email: string, password: string) => startSession("/auth/signup", email, password);
export const signIn = (email: string, password: string) => startSession("/auth/login", email, password);

export async function signOut(): Promise<void> {
  try {
    await api("/auth/logout", { method: "POST" });
  } finally {
    setSession(null, null);
  }
}

export async function changePassword(current_password: string, new_password: string): Promise<void> {
  await api("/auth/password", { method: "POST", body: JSON.stringify({ current_password, new_password }) });
}

export async function deleteAccount(password: string): Promise<void> {
  await api("/auth/account", { method: "DELETE", body: JSON.stringify({ password }) });
  setSession(null, null);
}

let sessionCheck: Promise<User> | null = null;

/** One /auth/me per page load, however many components ask. */
function checkSession(): Promise<User> {
  sessionCheck ??= api<{ user: User }>("/auth/me").then(({ user }) => {
    write(USER_KEY, JSON.stringify(user));
    return user;
  });
  sessionCheck.catch(() => {
    sessionCheck = null;
  });
  return sessionCheck;
}

/** The signed-in user (null when signed out), re-checked with the server once per page load. */
export function useAccount(): { user: User | null; ready: boolean } {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const sync = () => setUser(getToken() ? storedUser() : null);
    sync();
    setReady(true);
    if (getToken()) {
      checkSession()
        .then((fresh) => setUser(fresh))
        .catch(() => sync()); // a 401 already cleared the session
    }
    const onStorage = (e: StorageEvent) => {
      if (e.key === TOKEN_KEY || e.key === USER_KEY) sync();
    };
    window.addEventListener(CHANGE_EVENT, sync);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(CHANGE_EVENT, sync);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  return { user, ready };
}

// ---------- library ----------

export const listLibrary = () => api<{ items: LibraryItem[] }>("/library").then((r) => r.items);
export const getLibraryItem = (id: string) =>
  api<LibraryItem & { payload: unknown }>(`/library/${encodeURIComponent(id)}`);
export const renameLibraryItem = (id: string, title: string) =>
  api<LibraryItem>(`/library/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify({ title }) });
export const deleteLibraryItem = (id: string) =>
  api<void>(`/library/${encodeURIComponent(id)}`, { method: "DELETE" });
export const shareLibraryItem = (id: string) =>
  api<LibraryItem>(`/library/${encodeURIComponent(id)}/share`, { method: "POST" });
export const unshareLibraryItem = (id: string) =>
  api<LibraryItem>(`/library/${encodeURIComponent(id)}/share`, { method: "DELETE" });
export const getShared = (token: string) =>
  api<SharedItem>(`/shared/${encodeURIComponent(token)}`, { auth: false });

export function shareUrl(token: string): string {
  return `${window.location.origin}/s/${token}`;
}

/** Where an item opens: the same pages a fresh run lands on, told where to load from. */
export function itemHref(kind: LibraryKind, source: { item: string } | { share: string }): string {
  const page = kind === "faculty" ? "/report" : kind === "provost" ? "/curriculum" : "/study";
  const [key, value] = "item" in source ? ["item", source.item] : ["share", source.share];
  return `${page}?${key}=${encodeURIComponent(value)}`;
}

/**
 * Call when a run finishes. Signed in → saved now (returns true). Signed out → remembered for a
 * day, so signing in later still puts it in the library.
 */
export async function recordFinishedJob(jobId: string): Promise<boolean> {
  if (getToken()) {
    try {
      await api("/library", { method: "POST", body: JSON.stringify({ job_id: jobId }) });
      return true;
    } catch {
      return false;
    }
  }
  const now = Date.now();
  const recent = recentJobs().filter((j) => j.id !== jobId);
  recent.unshift({ id: jobId, at: now });
  write(RECENT_KEY, JSON.stringify(recent.slice(0, 10)));
  return false;
}

function recentJobs(): { id: string; at: number }[] {
  try {
    const raw = read(RECENT_KEY);
    const list = raw ? (JSON.parse(raw) as { id: string; at: number }[]) : [];
    return list.filter((j) => Date.now() - j.at < 23 * 3600 * 1000); // job results live 24h
  } catch {
    return [];
  }
}

async function flushRecentJobs(): Promise<void> {
  const jobs = recentJobs();
  write(RECENT_KEY, null);
  // Oldest first, so the library keeps the order they were made in.
  for (const j of jobs.reverse()) {
    try {
      await api("/library", { method: "POST", body: JSON.stringify({ job_id: j.id }) });
    } catch {
      /* expired: nothing to save */
    }
  }
}

/**
 * For result pages: a library item (`?item=`) or share link (`?share=`) in the current URL.
 * null when the URL has neither (the page falls back to its usual localStorage session).
 */
export async function loadFromUrl(): Promise<{ payload: unknown; title: string; shared: boolean } | null> {
  const params = new URLSearchParams(window.location.search);
  const item = params.get("item");
  const share = params.get("share");
  if (share) {
    const s = await getShared(share);
    return { payload: s.payload, title: s.title, shared: true };
  }
  if (item) {
    if (!getToken()) throw new ApiError("Sign in to open items from your library.", 401);
    const i = await getLibraryItem(item);
    return { payload: i.payload, title: i.title, shared: false };
  }
  return null;
}
