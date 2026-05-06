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

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

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
    // Step: Reset flashcard flip state when switching cards/tabs.
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
      const payload = (await response.json().catch(() => null)) as
        | { content?: unknown; detail?: string }
        | null;
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
          typeof translatedObj.summary_90s === "string"
            ? translatedObj.summary_90s
            : baseSession.summary_90s,
        summary_5min:
          typeof translatedObj.summary_5min === "string"
            ? translatedObj.summary_5min
            : baseSession.summary_5min,
        summary_full:
          typeof translatedObj.summary_full === "string"
            ? translatedObj.summary_full
            : baseSession.summary_full,
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

      // Step: Translate search result text if a non-English language is selected.
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
      <main className="min-h-screen bg-canvas text-ink flex items-center justify-center px-md">
        <p className="text-secondary text-marketing-muted">Loading session…</p>
      </main>
    );
  }

  return (
    <div className="min-h-screen bg-canvas text-ink">
      {/* Top nav */}
      <header className="border-b border-marketing-divider bg-canvas/90 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-content items-center justify-between px-md">
          <Link
            href="/"
            className="inline-flex items-center gap-sm text-[15px] font-semibold tracking-tight text-ink transition-opacity duration-interaction ease-out hover:opacity-90"
          >
            <span aria-hidden="true" className="text-marketing-muted">
              ←
            </span>
            <span>LectureKit</span>
          </Link>

          <div className="flex items-center gap-sm">
            {isTranslating ? (
              <span
                aria-label="Translating"
                className="h-4 w-4 rounded-full border border-marketing-divider border-t-primary motion-safe:animate-spin motion-reduce:animate-none"
              />
            ) : null}

            <select
              aria-label="Language"
              value={language}
              onChange={(e) => translateTo(e.target.value as LanguageCode)}
              className="h-9 rounded-linear border border-marketing-divider bg-canvas px-sm text-secondary text-ink transition duration-interaction ease-out focus:border-primary-focus focus:shadow-focus-glow"
            >
              {LANGUAGE_OPTIONS.map((opt) => (
                <option key={opt.code} value={opt.code}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
        </div>
        {translateError ? (
          <div className="mx-auto max-w-content px-md pb-sm">
            <p className="text-caption text-[#d16a6a]">{translateError}</p>
          </div>
        ) : null}
      </header>

      {/* Processing stats bar */}
      <div className="border-b border-marketing-divider">
        <div className="mx-auto flex max-w-content flex-col gap-xxs px-md py-sm text-caption text-marketing-muted sm:flex-row sm:items-center sm:justify-between">
          <span className="font-mono text-primary">video_id: {session.video_id}</span>
          <span>{session.chunk_count} chunks processed</span>
          <span>Processed {processedLabel}</span>
        </div>
      </div>

      {/* Main layout */}
      <main className="mx-auto max-w-content px-md py-lg">
        <div className="grid grid-cols-1 gap-lg md:grid-cols-1 md:gap-0 lg:grid-cols-[0.9fr_1.8fr_0.9fr]">
          {/* Left column — Outline */}
          <section className="lg:pr-lg">
            <div className="flex items-center justify-between">
              <p className="text-caption font-medium uppercase tracking-[0.22em] text-marketing-muted">
                Outline
              </p>
            </div>
            <div className="mt-sm h-px w-full bg-marketing-divider" aria-hidden="true" />

            <ul className="divide-y divide-marketing-divider">
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
                        "group w-full text-left py-md pl-md pr-sm transition duration-interaction ease-out",
                        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-canvas",
                        isActive ? "border-l-2 border-primary/40" : "border-l-2 border-transparent",
                        "hover:border-primary/40",
                        "cursor-pointer select-none",
                      ].join(" ")}
                    >
                      <div className="flex items-start gap-md">
                        <span className="shrink-0 font-mono text-[12px] tabular-nums text-primary pointer-events-none">
                          {formatTimestamp(item.timestamp)}
                        </span>
                        <div className="min-w-0">
                          <p className="text-secondary text-ink transition-colors duration-interaction ease-out group-hover:text-ink-muted">
                            {item.title}
                          </p>
                          <p className="mt-xxs text-caption text-marketing-muted">{item.description}</p>
                        </div>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>

          {/* Center column — placeholder for Step 3 */}
          <section className="lg:px-lg lg:border-l lg:border-marketing-divider">
            <p className="text-caption font-medium uppercase tracking-[0.22em] text-marketing-muted">
              Lecture
            </p>
            <div className="mt-sm h-px w-full bg-marketing-divider" aria-hidden="true" />

            {/* YouTube player */}
            <div className="mt-lg w-full">
              <div className="relative w-full overflow-hidden">
                <div className="w-full pt-[56.25%]" aria-hidden="true" />
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

            {/* Summary depth selector */}
            <div className="mt-xl">
              <div className="flex items-center gap-lg text-caption font-medium uppercase tracking-[0.18em]">
                {summaryTabs.map((t) => {
                  const active = summaryDepth === t.id;
                  return (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => setSummaryDepth(t.id)}
                      className={[
                        "relative pb-xs transition-colors duration-interaction ease-out",
                        active ? "text-ink" : "text-marketing-muted hover:text-ink",
                      ].join(" ")}
                    >
                      <span>{t.label}</span>
                      <span
                        aria-hidden="true"
                        className={[
                          "absolute inset-x-0 -bottom-[1px] h-[2px] transition-all duration-interaction ease-out",
                          active ? "bg-primary" : "bg-transparent",
                        ].join(" ")}
                      />
                    </button>
                  );
                })}
              </div>

              <div className="mt-lg">
                <p className="text-body text-ink whitespace-pre-line">{activeSummary}</p>
              </div>
            </div>
          </section>

          {/* Right column — placeholder for Step 4 */}
          <section className="lg:pl-lg lg:border-l lg:border-marketing-divider">
            {/* Tabs header */}
            <div className="relative">
              <div className="flex items-end justify-between gap-lg">
                <div className="flex gap-lg text-secondary">
                  {rightTabs.map((t) => {
                    const active = rightTab === t.id;
                    return (
                      <button
                        key={t.id}
                        type="button"
                        onClick={() => setRightTab(t.id)}
                        className={[
                          "relative pb-sm transition-colors duration-interaction ease-out",
                          active ? "text-ink" : "text-marketing-muted hover:text-ink",
                        ].join(" ")}
                      >
                        {t.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Sliding underline */}
              <div className="mt-xs h-px w-full bg-marketing-divider" aria-hidden="true" />
              <div
                aria-hidden="true"
                className="relative h-[2px] w-full"
                style={{ marginTop: -1 }}
              >
                <div
                  className="absolute bottom-0 h-[2px] bg-primary transition-all duration-interaction ease-out"
                  style={{
                    width: "33.333%",
                    left: rightTab === "summary" ? "0%" : rightTab === "flashcards" ? "33.333%" : "66.666%",
                  }}
                />
              </div>
            </div>

            {/* Tab content */}
            <div className="mt-lg">
              {rightTab === "summary" ? (
                <div className="flex flex-col gap-lg">
                  <div className="flex items-center gap-lg text-caption font-medium uppercase tracking-[0.18em]">
                    {summaryTabs.map((t) => {
                      const active = summaryDepth === t.id;
                      return (
                        <button
                          key={t.id}
                          type="button"
                          onClick={() => setSummaryDepth(t.id)}
                          className={[
                            "relative pb-xs transition-colors duration-interaction ease-out",
                            active ? "text-ink" : "text-marketing-muted hover:text-ink",
                          ].join(" ")}
                        >
                          <span>{t.label}</span>
                          <span
                            aria-hidden="true"
                            className={[
                              "absolute inset-x-0 -bottom-[1px] h-[2px] transition-all duration-interaction ease-out",
                              active ? "bg-primary" : "bg-transparent",
                            ].join(" ")}
                          />
                        </button>
                      );
                    })}
                  </div>

                  <div className="max-h-[60vh] overflow-auto pr-xs">
                    <p className="text-body text-ink whitespace-pre-line">{activeSummary}</p>
                  </div>
                </div>
              ) : null}

              {rightTab === "flashcards" ? (
                <div className="flex flex-col gap-lg">
                  <p className="text-caption text-marketing-muted text-center">
                    Card {cardIndex + 1} of {session.flashcards.length}
                  </p>

                  <div
                    className="w-full"
                    style={{ perspective: "1000px" }}
                  >
                    <button
                      type="button"
                      onClick={() => setIsCardFlipped((v) => !v)}
                      className="relative w-full min-h-[260px] rounded-linear border border-marketing-divider bg-canvas text-left transition duration-interaction ease-out hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-canvas"
                    >
                      <div
                        className={[
                          "absolute inset-0 p-lg motion-safe:transition-transform motion-safe:duration-[400ms] motion-safe:ease-out motion-reduce:transition-none",
                          isCardFlipped ? "motion-safe:[transform:rotateY(180deg)]" : "motion-safe:[transform:rotateY(0deg)]",
                        ].join(" ")}
                        style={{ transformStyle: "preserve-3d" }}
                      >
                        {/* Front */}
                        <div
                          className="absolute inset-0 flex items-center justify-center p-lg"
                          style={{ backfaceVisibility: "hidden" }}
                        >
                          <p className="text-[18px] font-semibold tracking-tight text-ink text-center">
                            {session.flashcards[cardIndex]?.question}
                          </p>
                        </div>

                        {/* Back */}
                        <div
                          className="absolute inset-0 flex flex-col justify-between p-lg"
                          style={{ backfaceVisibility: "hidden", transform: "rotateY(180deg)" }}
                        >
                          <p className="text-body text-ink whitespace-pre-line">
                            {session.flashcards[cardIndex]?.answer}
                          </p>
                          <p className="mt-lg font-mono text-[12px] tabular-nums text-primary">
                            Source: {formatTimestamp(session.flashcards[cardIndex]?.source_timestamp ?? 0)}
                          </p>
                        </div>
                      </div>
                    </button>
                  </div>

                  <div className="flex items-center justify-between">
                    <button
                      type="button"
                      disabled={cardIndex === 0}
                      onClick={() => setCardIndex((i) => Math.max(0, i - 1))}
                      className="text-button text-marketing-muted transition duration-interaction ease-out hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      ← Previous
                    </button>
                    <button
                      type="button"
                      disabled={cardIndex >= session.flashcards.length - 1}
                      onClick={() => setCardIndex((i) => Math.min(session.flashcards.length - 1, i + 1))}
                      className="text-button text-marketing-muted transition duration-interaction ease-out hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      Next →
                    </button>
                  </div>
                </div>
              ) : null}

              {rightTab === "search" ? (
                <div className="flex flex-col gap-lg">
                  {!session.indexed ? (
                    <p className="text-secondary text-marketing-muted">Search is not available for this lecture.</p>
                  ) : (
                    <>
                      <div className="flex items-center gap-sm">
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
                          className="min-h-[44px] flex-1 rounded-linear border border-marketing-divider bg-surface-1 px-sm py-xs text-body text-ink outline-none transition duration-interaction ease-out placeholder:text-ink-tertiary focus:border-primary-focus focus:shadow-focus-glow"
                        />
                        <button
                          type="button"
                          onClick={() => runSearch()}
                          className="min-h-[44px] rounded-linear bg-primary px-[14px] py-[8px] text-button font-medium text-onprimary transition duration-interaction ease-out hover:bg-primary-hover active:bg-primary-focus disabled:cursor-not-allowed disabled:opacity-60"
                          disabled={isSearching}
                        >
                          Search
                        </button>
                      </div>

                      {isSearching ? (
                        <p className="text-secondary text-marketing-muted motion-safe:animate-pulse motion-reduce:animate-none">
                          Searching…
                        </p>
                      ) : null}

                      {searchError ? (
                        <p className="text-secondary text-[#d16a6a]">{searchError}</p>
                      ) : null}

                      {searchResults.length > 0 ? (
                        <ul className="divide-y divide-marketing-divider">
                          {searchResults.slice(0, 3).map((r, idx) => {
                            const pct = Math.round(Math.max(0, Math.min(1, r.relevance_score)) * 100);
                            return (
                              <li
                                key={`${r.chunk_index}-${r.start}`}
                                className="py-md"
                                style={{
                                  transitionDelay: `${idx * 50}ms`,
                                }}
                              >
                                <p className="text-caption text-marketing-muted">Match: {pct}%</p>
                                <p className="mt-xs text-secondary text-ink">{r.text}</p>
                                <button
                                  type="button"
                                  onClick={() => seekTo(r.start)}
                                  className="mt-sm font-mono text-[12px] tabular-nums text-primary transition duration-interaction ease-out hover:text-primary-hover"
                                >
                                  {formatTimestamp(r.start)}
                                </button>
                              </li>
                            );
                          })}
                        </ul>
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
