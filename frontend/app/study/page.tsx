/**
 * Study dashboard route.
 *
 * Purpose (Step 2):
 * - Read the latest processed lecture session from `localStorage` (`lecturekit_session`)
 * - Redirect to `/app` if missing (dashboard must survive refresh)
 * - Render the three-column responsive layout with the Outline panel (left column)
 *
 * Data flow:
 * - `/app` stores a `LectureSession` in localStorage after `/process` completes
 * - `/study` loads it on mount and renders live backend-derived content
 */

"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { AppSubpageHeader } from "../components/app/AppSubpageHeader";
import { MarketingScrollReveal } from "../components/marketing/MarketingScrollReveal";

import type { LectureSession } from "../../types/lecture";
import { formatTimestamp } from "../../utils/format";

type RightTab = "summary" | "flashcards" | "search";

type SearchResult = {
  text: string;
  start: number;
  end: number;
  chunk_index: number;
  relevance_score: number;
};

type TranslatedContentPayload = {
  outline?: LectureSession["outline"];
  summary_90s?: string;
  summary_5min?: string;
  summary_full?: string;
  flashcards?: LectureSession["flashcards"];
};

type LanguageCode = "en" | "es" | "fr" | "bn" | "ar";

const LANGUAGE_OPTIONS: Array<{ code: LanguageCode; label: string; target: string | null }> = [
  { code: "en", label: "English", target: null },
  { code: "es", label: "Spanish", target: "Spanish" },
  { code: "fr", label: "French", target: "French" },
  { code: "bn", label: "Bengali", target: "Bengali" },
  { code: "ar", label: "Arabic", target: "Arabic" },
];

const PILL_ACTIVE = "bg-[#5e6ad2] text-white shadow-sm";
const PILL_INACTIVE =
  "border border-[#2a2a2a] text-zinc-400 hover:border-[#5e6ad2] hover:text-white transition-colors";

function formatProcessedAt(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function seekTo(seconds: number): void {
  const iframe = document.getElementById("yt-player") as HTMLIFrameElement | null;
  iframe?.contentWindow?.postMessage(
    JSON.stringify({ event: "command", func: "seekTo", args: [seconds, true] }),
    "*"
  );
}

function getApiBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_URL?.trim();
  return raw && raw.length > 0 ? raw.replace(/\/$/, "") : "http://localhost:8000";
}

function isActivationKey(key: string): boolean {
  return key === "Enter" || key === " " || key === "Spacebar";
}

export default function StudyPage(): JSX.Element {
  const router = useRouter();
  const [baseSession, setBaseSession] = useState<LectureSession | null>(null);
  const [session, setSession] = useState<LectureSession | null>(null);
  const [activeOutlineIndex, setActiveOutlineIndex] = useState(0);
  const [summaryDepth, setSummaryDepth] = useState<"90s" | "5min" | "full">("90s");
  const [rightTab, setRightTab] = useState<RightTab>("summary");

  const [cardIndex, setCardIndex] = useState(0);
  const [isCardFlipped, setIsCardFlipped] = useState(false);

  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const [language, setLanguage] = useState<LanguageCode>("en");
  const [isTranslating, setIsTranslating] = useState(false);
  const [translateError, setTranslateError] = useState<string | null>(null);

  const translationCacheRef = useRef<Map<LanguageCode, Partial<LectureSession>>>(new Map());
  const searchTranslationCacheRef = useRef<Map<string, SearchResult[]>>(new Map());

  useEffect(() => {
    const raw = window.localStorage.getItem("lecturekit_session");
    if (!raw) {
      router.replace("/app");
      return;
    }

    try {
      const parsed = JSON.parse(raw) as LectureSession;
      if (!parsed || !parsed.video_id) {
        router.replace("/app");
        return;
      }

      setBaseSession(parsed);
      setSession(parsed);
      setActiveOutlineIndex(0);
    } catch {
      router.replace("/app");
    }
  }, [router]);

  const processedLabel = useMemo(() => {
    if (!session) return "";
    return formatProcessedAt(session.processed_at);
  }, [session]);

  const playerSrc = useMemo(() => {
    if (!session) return "";
    const origin = "http://localhost:3000";
    return `https://www.youtube.com/embed/${session.video_id}?enablejsapi=1&origin=${encodeURIComponent(origin)}`;
  }, [session]);

  const activeSummary = useMemo(() => {
    if (!session) return "";
    if (summaryDepth === "90s") return session.summary_90s;
    if (summaryDepth === "5min") return session.summary_5min;
    return session.summary_full;
  }, [session, summaryDepth]);

  const summaryTabs = useMemo(
    () =>
      [
        { id: "90s" as const, label: "90 SEC" },
        { id: "5min" as const, label: "5 MIN" },
        { id: "full" as const, label: "FULL" },
      ] as const,
    []
  );

  const rightTabs = useMemo(
    () =>
      [
        { id: "summary" as const, label: "Summary" },
        { id: "flashcards" as const, label: "Flashcards" },
        { id: "search" as const, label: "Search" },
      ] as const,
    []
  );

  useEffect(() => {
    setIsCardFlipped(false);
  }, [cardIndex, rightTab]);

  async function translateTo(nextLang: LanguageCode): Promise<void> {
    if (!baseSession) return;
    setTranslateError(null);

    if (nextLang === "en") {
      setLanguage("en");
      setSession(baseSession);
      return;
    }

    const cached = translationCacheRef.current.get(nextLang);
    if (cached) {
      setLanguage(nextLang);
      setSession({ ...baseSession, ...cached });
      return;
    }

    const option = LANGUAGE_OPTIONS.find((o) => o.code === nextLang);
    if (!option?.target) return;

    setIsTranslating(true);
    try {
      const endpoint = `${getApiBaseUrl()}/translate`;
      const content = {
        outline: baseSession.outline,
        summary_90s: baseSession.summary_90s,
        summary_5min: baseSession.summary_5min,
        summary_full: baseSession.summary_full,
        flashcards: baseSession.flashcards,
      };
      const requestBody = { content, target_language: option.target };
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
      });
      const payload = (await response.json().catch(() => null)) as { content?: unknown; detail?: string } | null;
      if (!response.ok) {
        setTranslateError("Translation failed. Showing English content.");
        setLanguage("en");
        setSession(baseSession);
        return;
      }

      const translated = payload?.content;
      if (!translated || typeof translated !== "object") {
        setTranslateError("Translation returned an invalid payload.");
        setLanguage("en");
        setSession(baseSession);
        return;
      }

      const translatedObj = translated as TranslatedContentPayload;
      const patch: Partial<LectureSession> = {
        outline: Array.isArray(translatedObj.outline) ? translatedObj.outline : baseSession.outline,
        summary_90s:
          typeof translatedObj.summary_90s === "string" ? translatedObj.summary_90s : baseSession.summary_90s,
        summary_5min:
          typeof translatedObj.summary_5min === "string" ? translatedObj.summary_5min : baseSession.summary_5min,
        summary_full:
          typeof translatedObj.summary_full === "string" ? translatedObj.summary_full : baseSession.summary_full,
        flashcards: Array.isArray(translatedObj.flashcards) ? translatedObj.flashcards : baseSession.flashcards,
      };

      translationCacheRef.current.set(nextLang, patch);
      setLanguage(nextLang);
      setSession({ ...baseSession, ...patch });
    } catch {
      setTranslateError("Network error — translation service unavailable.");
      setLanguage("en");
      setSession(baseSession);
    } finally {
      setIsTranslating(false);
    }
  }

  async function runSearch(): Promise<void> {
    if (!session) return;
    const q = searchQuery.trim();
    if (!q) {
      setSearchError("Please enter a search query.");
      return;
    }
    if (!session.indexed) {
      setSearchError("Search is not available for this lecture.");
      return;
    }

    setIsSearching(true);
    setSearchError(null);
    try {
      const endpoint = `${getApiBaseUrl()}/search`;
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ youtube_url: session.youtube_url, query: q }),
      });
      const payload = (await response.json().catch(() => null)) as
        | { results: SearchResult[] }
        | { detail?: string }
        | null;

      if (!response.ok) {
        const message =
          payload && typeof payload === "object" && "detail" in payload && typeof payload.detail === "string"
            ? payload.detail
            : "Search failed. Please try again.";
        setSearchError(message);
        setSearchResults([]);
        return;
      }

      const results = payload && typeof payload === "object" && "results" in payload ? payload.results : [];
      const baseResults = Array.isArray(results) ? results : [];

      if (language !== "en" && baseSession) {
        const cacheKey = `${language}:${q}`;
        const cached = searchTranslationCacheRef.current.get(cacheKey);
        if (cached) {
          setSearchResults(cached);
          return;
        }

        const option = LANGUAGE_OPTIONS.find((o) => o.code === language);
        if (option?.target) {
          try {
            const tEndpoint = `${getApiBaseUrl()}/translate`;
            const tResp = await fetch(tEndpoint, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                content: { results: baseResults.map((r) => ({ text: r.text })) },
                target_language: option.target,
              }),
            });
            const tPayload = (await tResp.json().catch(() => null)) as { content?: unknown } | null;
            const tContent = tPayload?.content as { results?: Array<{ text?: unknown }> } | undefined;
            const tResults = tContent?.results;
            if (tResp.ok && Array.isArray(tResults) && tResults.length === baseResults.length) {
              const merged = baseResults.map((r: SearchResult, i: number) => ({
                ...r,
                text: typeof tResults[i]?.text === "string" ? tResults[i].text : r.text,
              }));
              searchTranslationCacheRef.current.set(cacheKey, merged);
              setSearchResults(merged);
              return;
            }
          } catch {
            // ignore translation failure; fall back to English results
          }
        }
      }

      setSearchResults(baseResults);
    } catch {
      setSearchError("Network error — is the FastAPI server running?");
      setSearchResults([]);
    } finally {
      setIsSearching(false);
    }
  }

  if (!session || !baseSession) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-zinc-950 px-6 text-zinc-400">
        <p>Loading session…</p>
      </main>
    );
  }

  const headerRight = (
    <>
      {isTranslating ? (
        <span
          aria-label="Translating"
          className="h-4 w-4 shrink-0 rounded-full border-2 border-white/10 border-t-[#5e6ad2] motion-safe:animate-spin motion-reduce:animate-none"
        />
      ) : null}
      <select
        aria-label="Language"
        value={language}
        onChange={(e) => translateTo(e.target.value as LanguageCode)}
        className="h-9 rounded-lg border border-white/10 bg-zinc-900 px-3 text-sm text-white outline-none transition-colors focus:border-[#5e6ad2]/60"
      >
        {LANGUAGE_OPTIONS.map((opt) => (
          <option key={opt.code} value={opt.code}>
            {opt.label}
          </option>
        ))}
      </select>
    </>
  );

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-200">
      <AppSubpageHeader title="Study dashboard" right={headerRight} />
      {translateError ? (
        <div className="border-b border-white/5 bg-zinc-950 px-6 py-2">
          <div className="mx-auto max-w-[1600px]">
            <p className="text-xs text-[#e53e3e]">{translateError}</p>
          </div>
        </div>
      ) : null}

      <div className="border-b border-white/5">
        <div className="mx-auto flex max-w-[1600px] flex-col gap-1 px-6 py-3 text-xs text-zinc-500 sm:flex-row sm:items-center sm:justify-between">
          <span className="font-mono text-[#5e6ad2]">video_id: {session.video_id}</span>
          <span>{session.chunk_count} chunks processed</span>
          <span>Processed {processedLabel}</span>
        </div>
      </div>

      <main className="mx-auto max-w-[1600px] px-6 py-8">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[0.9fr_1.8fr_0.9fr]">
          <section className="lg:pr-2">
            <p className="text-xs font-semibold uppercase tracking-widest text-zinc-500">Outline</p>
            <MarketingScrollReveal className="mt-3 rounded-xl border border-white/5 bg-zinc-900/50 p-2 transition-colors hover:border-white/10">
              <ul className="max-h-[70vh] divide-y divide-white/5 overflow-auto pr-1">
                {session.outline.map((item, idx) => {
                  const isActive = idx === activeOutlineIndex;
                  return (
                    <li key={`${item.timestamp}-${item.title}`}>
                      <div
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (!isActivationKey(e.key)) return;
                          e.preventDefault();
                          setActiveOutlineIndex(idx);
                          seekTo(item.timestamp);
                        }}
                        onClick={() => {
                          setActiveOutlineIndex(idx);
                          seekTo(item.timestamp);
                        }}
                        className={[
                          "group w-full cursor-pointer select-none rounded-lg py-3 pl-3 pr-2 text-left transition-colors",
                          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#5e6ad2] focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950",
                          isActive ? "border-l-2 border-[#5e6ad2] bg-white/[0.03]" : "border-l-2 border-transparent hover:border-[#5e6ad2]/40",
                        ].join(" ")}
                      >
                        <div className="flex items-start gap-3">
                          <span className="pointer-events-none shrink-0 font-mono text-xs tabular-nums text-[#5e6ad2]">
                            {formatTimestamp(item.timestamp)}
                          </span>
                          <div className="min-w-0">
                            <p className="text-sm text-white transition-colors group-hover:text-zinc-200">{item.title}</p>
                            <p className="mt-1 text-xs text-zinc-500">{item.description}</p>
                          </div>
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </MarketingScrollReveal>
          </section>

          <section className="lg:px-4">
            <p className="text-xs font-semibold uppercase tracking-widest text-zinc-500">Lecture</p>
            <div className="mt-3 overflow-hidden rounded-xl border border-white/5">
              <div className="relative w-full">
                <div className="w-full pt-[56.25%]" aria-hidden />
                <iframe
                  id="yt-player"
                  title="YouTube player"
                  src={playerSrc}
                  className="absolute inset-0 h-full w-full"
                  allow="accelerometer autoplay clipboard-write encrypted-media gyroscope picture-in-picture"
                  referrerPolicy="strict-origin-when-cross-origin"
                />
              </div>
            </div>

            <div className="mt-8">
              <div className="flex flex-wrap items-center gap-2">
                {summaryTabs.map((t) => {
                  const active = summaryDepth === t.id;
                  return (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => setSummaryDepth(t.id)}
                      className={`rounded-full px-4 py-1.5 text-xs font-medium transition-colors ${active ? PILL_ACTIVE : `${PILL_INACTIVE}`}`}
                    >
                      {t.label}
                    </button>
                  );
                })}
              </div>
              <div className="mt-6">
                <p className="whitespace-pre-line text-sm leading-relaxed text-zinc-300">{activeSummary}</p>
              </div>
            </div>
          </section>

          <section className="lg:pl-2">
            <div className="relative">
              <div className="flex flex-wrap items-end gap-2">
                {rightTabs.map((t) => {
                  const active = rightTab === t.id;
                  return (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => setRightTab(t.id)}
                      className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                        active ? PILL_ACTIVE : `${PILL_INACTIVE}`
                      }`}
                    >
                      {t.label}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="mt-6">
              {rightTab === "summary" ? (
                <div className="flex flex-col gap-6">
                  <div className="flex flex-wrap gap-2">
                    {summaryTabs.map((t) => {
                      const active = summaryDepth === t.id;
                      return (
                        <button
                          key={t.id}
                          type="button"
                          onClick={() => setSummaryDepth(t.id)}
                          className={`rounded-full px-4 py-1.5 text-xs font-medium transition-colors ${active ? PILL_ACTIVE : `${PILL_INACTIVE}`}`}
                        >
                          {t.label}
                        </button>
                      );
                    })}
                  </div>
                  <MarketingScrollReveal className="max-h-[60vh] overflow-auto rounded-xl border border-white/5 bg-zinc-900/50 p-4 pr-2 transition-colors hover:border-white/10">
                    <p className="whitespace-pre-line text-sm leading-relaxed text-zinc-300">{activeSummary}</p>
                  </MarketingScrollReveal>
                </div>
              ) : null}

              {rightTab === "flashcards" ? (
                <div className="flex flex-col gap-6">
                  <p className="text-center text-xs text-zinc-500">
                    Card {cardIndex + 1} of {session.flashcards.length}
                  </p>

                  <div className="w-full" style={{ perspective: "1000px" }}>
                    <button
                      type="button"
                      onClick={() => setIsCardFlipped((v) => !v)}
                      className="relative min-h-[260px] w-full rounded-2xl border border-white/5 bg-zinc-900/50 p-6 text-left transition-colors hover:border-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#5e6ad2] focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950"
                    >
                      <div
                        className={[
                          "absolute inset-0 p-6 motion-safe:transition-transform motion-safe:duration-[400ms] motion-safe:ease-out motion-reduce:transition-none",
                          isCardFlipped ? "motion-safe:[transform:rotateY(180deg)]" : "motion-safe:[transform:rotateY(0deg)]",
                        ].join(" ")}
                        style={{ transformStyle: "preserve-3d" }}
                      >
                        <div
                          className="absolute inset-0 flex items-center justify-center p-6"
                          style={{ backfaceVisibility: "hidden" }}
                        >
                          <p className="text-center text-lg font-semibold tracking-tight text-white">
                            {session.flashcards[cardIndex]?.question}
                          </p>
                        </div>
                        <div
                          className="absolute inset-0 flex flex-col justify-between p-6"
                          style={{ backfaceVisibility: "hidden", transform: "rotateY(180deg)" }}
                        >
                          <p className="whitespace-pre-line text-sm text-zinc-300">{session.flashcards[cardIndex]?.answer}</p>
                          <p className="mt-4 font-mono text-xs tabular-nums text-[#5e6ad2]">
                            Source: {formatTimestamp(session.flashcards[cardIndex]?.source_timestamp ?? 0)}
                          </p>
                        </div>
                      </div>
                    </button>
                  </div>

                  <div className="flex items-center justify-between text-sm">
                    <button
                      type="button"
                      disabled={cardIndex === 0}
                      onClick={() => setCardIndex((i) => Math.max(0, i - 1))}
                      className="text-zinc-400 transition-colors hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      ← Previous
                    </button>
                    <button
                      type="button"
                      disabled={cardIndex >= session.flashcards.length - 1}
                      onClick={() => setCardIndex((i) => Math.min(session.flashcards.length - 1, i + 1))}
                      className="text-zinc-400 transition-colors hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      Next →
                    </button>
                  </div>
                </div>
              ) : null}

              {rightTab === "search" ? (
                <div className="flex flex-col gap-6">
                  {!session.indexed ? (
                    <p className="text-sm text-zinc-500">Search is not available for this lecture.</p>
                  ) : (
                    <>
                      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                        <input
                          value={searchQuery}
                          onChange={(e) => setSearchQuery(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              e.preventDefault();
                              runSearch();
                            }
                          }}
                          placeholder="Ask anything about this lecture..."
                          className="min-h-[44px] flex-1 rounded-lg border border-white/10 bg-zinc-900 px-3 py-2 text-sm text-white outline-none transition-colors placeholder:text-zinc-500 focus:border-[#5e6ad2]/60 focus:ring-1 focus:ring-[#5e6ad2]"
                        />
                        <button
                          type="button"
                          onClick={() => runSearch()}
                          className="min-h-[44px] shrink-0 rounded-full bg-[#5e6ad2] px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-[#4f5ec0] disabled:cursor-not-allowed disabled:opacity-60"
                          disabled={isSearching}
                        >
                          Search
                        </button>
                      </div>

                      {language !== "en" ? (
                        <p className="text-xs text-zinc-500">
                          Search works best in English. You can type your question in English to find relevant moments.
                        </p>
                      ) : null}

                      {isSearching ? (
                        <p className="text-sm text-zinc-500 motion-safe:animate-pulse motion-reduce:animate-none">Searching…</p>
                      ) : null}

                      {searchError ? <p className="text-sm text-[#e53e3e]">{searchError}</p> : null}

                      {searchResults.length > 0 ? (
                        <MarketingScrollReveal>
                          <ul className="divide-y divide-white/5 rounded-xl border border-white/5 bg-zinc-900/50 transition-colors hover:border-white/10">
                            {searchResults.slice(0, 3).map((r, idx) => {
                              const pct = Math.round(Math.max(0, Math.min(1, r.relevance_score)) * 100);
                              return (
                                <li
                                  key={`${r.chunk_index}-${r.start}`}
                                  className="p-4"
                                  style={{ transitionDelay: `${idx * 50}ms` }}
                                >
                                  <p className="text-xs text-zinc-500">Match: {pct}%</p>
                                  <p className="mt-1 text-sm text-zinc-300">{r.text}</p>
                                  <button
                                    type="button"
                                    onClick={() => seekTo(r.start)}
                                    className="mt-2 font-mono text-xs tabular-nums text-[#5e6ad2] transition-colors hover:text-white"
                                  >
                                    {formatTimestamp(r.start)}
                                  </button>
                                </li>
                              );
                            })}
                          </ul>
                        </MarketingScrollReveal>
                      ) : null}
                    </>
                  )}
                </div>
              ) : null}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
