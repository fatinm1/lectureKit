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

const PILL_ACTIVE = "rounded-full bg-zinc-100 px-4 py-2 text-sm font-medium text-black";
const PILL_INACTIVE =
  "rounded-full border border-zinc-800 px-4 py-2 text-sm font-medium text-zinc-400 transition-colors hover:border-zinc-600 hover:text-white";
const BTN_PRIMARY =
  "rounded-full bg-zinc-100 px-6 py-2.5 text-sm font-medium text-black transition-colors hover:bg-zinc-200 disabled:cursor-not-allowed disabled:opacity-60";
const TIMESTAMP_LINK =
  "cursor-pointer text-zinc-400 underline-offset-2 transition-colors hover:text-white hover:underline";

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

function getApiBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_URL?.trim();
  return raw && raw.length > 0 ? raw.replace(/\/$/, "") : "http://localhost:8000";
}

/** POST /search requires a full http(s) URL; session may store only an ID or a short URL. */
function youtubeUrlForSearchApi(session: LectureSession): string {
  const raw = (session.youtube_url ?? "").trim();
  if (/^https?:\/\//i.test(raw)) {
    return raw;
  }
  const id = (session.video_id ?? "").trim();
  return `https://www.youtube.com/watch?v=${encodeURIComponent(id)}`;
}

/** Read `results` from FastAPI SearchResponse (same shape as curl). */
function parseSearchResultsPayload(payload: unknown): SearchResult[] {
  if (!payload || typeof payload !== "object") return [];
  const obj = payload as Record<string, unknown>;
  const raw = obj.results;
  if (!Array.isArray(raw)) return [];
  const out: SearchResult[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const row = item as Record<string, unknown>;
    out.push({
      text: typeof row.text === "string" ? row.text : String(row.text ?? ""),
      start: typeof row.start === "number" ? row.start : Number(row.start ?? 0),
      end: typeof row.end === "number" ? row.end : Number(row.end ?? 0),
      chunk_index: typeof row.chunk_index === "number" ? row.chunk_index : Number(row.chunk_index ?? 0),
      relevance_score:
        typeof row.relevance_score === "number" && Number.isFinite(row.relevance_score)
          ? row.relevance_score
          : Number(row.relevance_score ?? 0),
    });
  }
  return out;
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
  const [lastQuery, setLastQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isTranslatingSearchResults, setIsTranslatingSearchResults] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const [language, setLanguage] = useState<LanguageCode>("en");
  const [isTranslating, setIsTranslating] = useState(false);
  const [translateError, setTranslateError] = useState<string | null>(null);

  const translationCacheRef = useRef<Map<LanguageCode, Partial<LectureSession>>>(new Map());
  const searchTranslationCacheRef = useRef<Map<string, SearchResult[]>>(new Map());
  const playerRef = useRef<HTMLIFrameElement>(null);
  const [embedOrigin, setEmbedOrigin] = useState("");

  useEffect(() => {
    setEmbedOrigin(typeof window !== "undefined" ? window.location.origin : "");
  }, []);

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

  useEffect(() => {
    if (!baseSession?.video_id) return;
    setLastQuery("");
    setSearchQuery("");
    setSearchResults([]);
    setSearchError(null);
    searchTranslationCacheRef.current.clear();
  }, [baseSession?.video_id]);

  const processedLabel = useMemo(() => {
    if (!session) return "";
    return formatProcessedAt(session.processed_at);
  }, [session]);

  const playerSrc = useMemo(() => {
    if (!session) return "";
    return `https://www.youtube.com/embed/${session.video_id}?enablejsapi=1&origin=${embedOrigin}&rel=0`;
  }, [session, embedOrigin]);

  const seekTo = (seconds: number) => {
    const t = Number(seconds);
    if (!Number.isFinite(t)) return;
    if (playerRef.current) {
      playerRef.current.contentWindow?.postMessage(
        JSON.stringify({
          event: "command",
          func: "seekTo",
          args: [t, true],
        }),
        "*"
      );
    }
  };

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

  async function translateTo(nextLang: LanguageCode): Promise<LanguageCode> {
    if (!baseSession) return language;

    setTranslateError(null);

    if (nextLang === "en") {
      setLanguage("en");
      setSession(baseSession);
      return "en";
    }

    const cached = translationCacheRef.current.get(nextLang);
    if (cached) {
      setLanguage(nextLang);
      setSession({ ...baseSession, ...cached });
      return nextLang;
    }

    const option = LANGUAGE_OPTIONS.find((o) => o.code === nextLang);
    if (!option?.target) return language;

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
        return "en";
      }

      const translated = payload?.content;
      if (!translated || typeof translated !== "object") {
        setTranslateError("Translation returned an invalid payload.");
        setLanguage("en");
        setSession(baseSession);
        return "en";
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
      return nextLang;
    } catch {
      setTranslateError("Network error — translation service unavailable.");
      setLanguage("en");
      setSession(baseSession);
      return "en";
    } finally {
      setIsTranslating(false);
    }
  }

  async function handleLanguageChange(nextLang: LanguageCode): Promise<void> {
    const applied = await translateTo(nextLang);
    const q = lastQuery.trim();
    if (q) {
      await handleSearch(q, applied);
    }
  }

  async function handleSearch(query: string, langOverride?: LanguageCode): Promise<void> {
    const effectiveLanguage = langOverride ?? language;
    const s = baseSession;
    if (!s) return;

    const q = query.trim();
    if (!q) {
      setSearchError("Please enter a search query.");
      return;
    }
    if (!s.indexed) {
      setSearchError("Search is not available for this lecture.");
      return;
    }

    const cacheKey = `${effectiveLanguage}:${q}`;
    const englishCacheKey = `en:${q}`;

    setIsSearching(true);
    setIsTranslatingSearchResults(false);
    setSearchError(null);
    setSearchResults([]);
    try {
      const cachedForLang = searchTranslationCacheRef.current.get(cacheKey);
      if (cachedForLang) {
        console.log("[Study] Search results (cache):", cachedForLang);
        setSearchResults(cachedForLang);
        setLastQuery(q);
        return;
      }

      let baseResults: SearchResult[] | undefined = searchTranslationCacheRef.current.get(englishCacheKey);
      if (!baseResults) {
        const endpoint = `${getApiBaseUrl()}/search`;
        const response = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ youtube_url: youtubeUrlForSearchApi(s), query: q }),
        });
        const payload = (await response.json().catch(() => null)) as { results?: unknown; detail?: string } | null;

        if (!response.ok) {
          const message =
            payload && typeof payload === "object" && "detail" in payload && typeof payload.detail === "string"
              ? payload.detail
              : "Search failed. Please try again.";
          setSearchError(message);
          setSearchResults([]);
          return;
        }

        const parsed = parseSearchResultsPayload(payload);
        baseResults = parsed.length > 0 ? [...parsed] : [];
        searchTranslationCacheRef.current.set(englishCacheKey, baseResults);
      }

      const hits: SearchResult[] = Array.isArray(baseResults) ? baseResults : [];
      setLastQuery(q);

      if (effectiveLanguage !== "en" && hits.length > 0) {
        const option = LANGUAGE_OPTIONS.find((o) => o.code === effectiveLanguage);
        if (option?.target) {
          setIsTranslatingSearchResults(true);
          try {
            const tEndpoint = `${getApiBaseUrl()}/translate`;
            const tResp = await fetch(tEndpoint, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                content: { search_results: hits.map((r) => r.text) },
                target_language: option.target,
              }),
            });
            const tPayload = (await tResp.json().catch(() => null)) as { content?: unknown } | null;
            const tContent = tPayload?.content as { search_results?: unknown } | undefined;
            const translatedTexts = tContent?.search_results;

            if (
              tResp.ok &&
              Array.isArray(translatedTexts) &&
              translatedTexts.length === hits.length &&
              translatedTexts.every((t) => typeof t === "string")
            ) {
              const merged = hits.map((r: SearchResult, i: number) => ({
                ...r,
                text: translatedTexts[i] as string,
              }));
              searchTranslationCacheRef.current.set(cacheKey, merged);
              console.log("[Study] Search results (translated):", merged);
              setSearchResults(merged);
              return;
            }
          } catch {
            // fall back to English result snippets
          } finally {
            setIsTranslatingSearchResults(false);
          }
        }
      }

      searchTranslationCacheRef.current.set(cacheKey, hits);
      console.log("[Study] Search results:", hits);
      setSearchResults(hits);
    } catch {
      setSearchError("Network error — is the FastAPI server running?");
      setSearchResults([]);
    } finally {
      setIsSearching(false);
      setIsTranslatingSearchResults(false);
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
          className="h-4 w-4 shrink-0 rounded-full border-2 border-white/10 border-t-white motion-safe:animate-spin motion-reduce:animate-none"
        />
      ) : null}
      <select
        aria-label="Language"
        value={language}
        onChange={(e) => void handleLanguageChange(e.target.value as LanguageCode)}
        className="h-9 rounded-full border border-zinc-800 bg-zinc-950 px-4 py-2 text-sm text-white outline-none transition-colors hover:border-zinc-600 focus:border-zinc-600"
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
                          seekTo(Number(item.timestamp));
                        }}
                        onClick={() => {
                          setActiveOutlineIndex(idx);
                          seekTo(Number(item.timestamp));
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
                  ref={playerRef}
                  id="yt-player"
                  title="YouTube player"
                  src={playerSrc}
                  className="absolute inset-0 h-full w-full"
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
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
                      className={`transition-colors ${active ? PILL_ACTIVE : PILL_INACTIVE}`}
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
                      className={`transition-colors ${active ? PILL_ACTIVE : PILL_INACTIVE}`}
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
                          className={`transition-colors ${active ? PILL_ACTIVE : PILL_INACTIVE}`}
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
                          <button
                            type="button"
                            onClick={() =>
                              seekTo(Number(session.flashcards[cardIndex]?.source_timestamp ?? 0))
                            }
                            className={`mt-4 text-left font-mono text-xs tabular-nums ${TIMESTAMP_LINK}`}
                          >
                            Source: {formatTimestamp(session.flashcards[cardIndex]?.source_timestamp ?? 0)}
                          </button>
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
                  {!baseSession.indexed ? (
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
                              void handleSearch(searchQuery);
                            }
                          }}
                          placeholder="Ask anything about this lecture..."
                          className="min-h-[44px] flex-1 rounded-lg border border-white/10 bg-zinc-900 px-3 py-2 text-sm text-white outline-none transition-colors placeholder:text-zinc-500 focus:border-[#5e6ad2]/60 focus:ring-1 focus:ring-[#5e6ad2]"
                        />
                        <button
                          type="button"
                          onClick={() => void handleSearch(searchQuery)}
                          className={`${BTN_PRIMARY} min-h-[44px] shrink-0`}
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

                      {isTranslatingSearchResults ? (
                        <div className="flex items-center gap-2 text-sm text-zinc-400">
                          <span
                            aria-hidden
                            className="inline-block h-3.5 w-3.5 shrink-0 rounded-full border-2 border-white/15 border-t-[#5e6ad2] motion-safe:animate-spin motion-reduce:animate-none"
                          />
                          <span>Translating results…</span>
                        </div>
                      ) : null}

                      {searchError ? <p className="text-sm text-[#e53e3e]">{searchError}</p> : null}

                      {searchResults.length > 0 ? (
                        <div className="rounded-xl border border-white/5 bg-zinc-900/50 transition-colors hover:border-white/10">
                          <ul className="divide-y divide-white/5">
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
                                    onClick={() => seekTo(Number(r.start))}
                                    className={`mt-2 font-mono text-xs tabular-nums ${TIMESTAMP_LINK}`}
                                  >
                                    {formatTimestamp(r.start)}
                                  </button>
                                </li>
                              );
                            })}
                          </ul>
                        </div>
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
