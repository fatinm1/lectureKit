"use client";

/**
 * "Ask the lecture" chat for the study page.
 *
 * Each answer streams in with inline citations ([2], [1, 3]) that become timestamp links into the
 * video. Citations are checked against the excerpts the server actually retrieved; a marker for a
 * source that doesn't exist is dropped. The conversation is kept per lecture in
 * localStorage so a refresh doesn't lose it, and the last few turns go back to the server so
 * follow-up questions ("why?", "give an example") make sense.
 */

import { useEffect, useRef, useState } from "react";

import { AskError, askLecture, splitCitations, type AskSource, type AskTurn } from "../../../utils/ask";
import { formatTimestamp } from "../../../utils/format";

type Message = {
  question: string;
  answer: string;
  sources: AskSource[];
  citations: number[];
  status: "streaming" | "done" | "error" | "stopped";
  grounded?: boolean;
  cached?: boolean;
  error?: string;
};

const SUGGESTIONS = [
  "What are the main ideas of this lecture?",
  "Explain the hardest concept in simpler terms.",
  "What should I review before an exam on this?",
];

const HISTORY_TURNS = 3;

function storageKey(videoId: string): string {
  return `lecturekit_ask_${videoId}`;
}

function loadMessages(videoId: string): Message[] {
  try {
    const raw = window.localStorage.getItem(storageKey(videoId));
    const parsed = raw ? (JSON.parse(raw) as Message[]) : [];
    // A reload mid-answer leaves a "streaming" turn behind; show it as stopped.
    return parsed.map((m) => (m.status === "streaming" ? { ...m, status: "stopped" } : m));
  } catch {
    return [];
  }
}

export function AskPanel({
  videoId,
  youtubeUrl,
  available,
  seekTo,
}: {
  videoId: string;
  youtubeUrl: string;
  /** False until the transcript is indexed (answers are retrieved from the search index). */
  available: boolean;
  seekTo: (seconds: number) => void;
}): JSX.Element {
  // Loaded synchronously on first render: loading in an effect raced the save effect below,
  // which wrote the empty initial state over the stored chat. (The parent keys this component
  // by video_id, so a different lecture gets a fresh instance.) The panel only renders after
  // the Ask tab is clicked, never on the server, so reading localStorage here is safe.
  const [messages, setMessages] = useState<Message[]>(() => loadMessages(videoId));
  const [input, setInput] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const busy = messages.some((m) => m.status === "streaming");

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    try {
      window.localStorage.setItem(storageKey(videoId), JSON.stringify(messages.slice(-20)));
    } catch {
      /* storage full or unavailable: the chat still works for this visit */
    }
  }, [messages, videoId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [messages]);

  const update = (index: number, patch: Partial<Message>) =>
    setMessages((prev) => prev.map((m, i) => (i === index ? { ...m, ...patch } : m)));

  async function ask(raw: string) {
    const question = raw.trim();
    if (!question || busy) return;
    setInput("");
    const history: AskTurn[] = messages
      .filter((m) => m.status === "done" && m.answer)
      .slice(-HISTORY_TURNS)
      .map((m) => ({ question: m.question, answer: m.answer }));
    const index = messages.length;
    setMessages((prev) => [...prev, { question, answer: "", sources: [], citations: [], status: "streaming" }]);

    const controller = new AbortController();
    abortRef.current = controller;
    let answer = "";
    try {
      const done = await askLecture(
        { youtube_url: youtubeUrl, question, history },
        {
          onSources: (sources) => update(index, { sources }),
          onDelta: (text) => {
            answer += text;
            update(index, { answer });
          },
        },
        controller.signal
      );
      update(index, {
        answer: done.answer,
        citations: done.citations,
        grounded: done.grounded,
        cached: done.cached,
        status: "done",
      });
    } catch (err) {
      if (controller.signal.aborted) {
        update(index, { status: "stopped" });
      } else {
        update(index, {
          status: "error",
          error: err instanceof AskError ? err.message : "Could not reach the server. Please try again.",
        });
      }
    } finally {
      abortRef.current = null;
    }
  }

  if (!available) {
    return <p className="text-sm text-zinc-500">Ask becomes available once the transcript is indexed.</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      {messages.length === 0 ? (
        <div className="flex flex-col gap-2">
          <p className="text-sm text-zinc-400">
            Ask anything about this lecture. Answers come only from what was said, with links to the moments they
            come from.
          </p>
          <div className="flex flex-wrap gap-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => void ask(s)}
                className="rounded-full border border-zinc-800 px-3 py-1.5 text-left text-xs text-zinc-400 transition-colors hover:border-zinc-600 hover:text-white"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <ol className="flex max-h-[60vh] flex-col gap-5 overflow-y-auto pr-1" aria-live="polite">
          {messages.map((m, i) => (
            <li key={i} className="flex flex-col gap-2">
              <p className="self-end rounded-2xl rounded-br-sm bg-zinc-800 px-3 py-2 text-sm text-zinc-100">
                {m.question}
              </p>
              <Answer message={m} seekTo={seekTo} />
            </li>
          ))}
          <div ref={endRef} />
        </ol>
      )}

      <form
        className="flex flex-col gap-2 sm:flex-row sm:items-center"
        onSubmit={(e) => {
          e.preventDefault();
          void ask(input);
        }}
      >
        <label htmlFor="ask-input" className="sr-only">
          Ask about this lecture
        </label>
        <input
          id="ask-input"
          value={input}
          maxLength={500}
          onChange={(e) => setInput(e.target.value)}
          placeholder={messages.length ? "Ask a follow-up…" : "e.g. Why does the algorithm need a base case?"}
          className="min-h-[44px] flex-1 rounded-lg border border-white/10 bg-zinc-900 px-3 py-2 text-sm text-white outline-none transition-colors placeholder:text-zinc-500 focus:border-[#5e6ad2]/60 focus:ring-1 focus:ring-[#5e6ad2]"
        />
        {busy ? (
          <button
            type="button"
            onClick={() => abortRef.current?.abort()}
            className="min-h-[44px] shrink-0 rounded-full border border-zinc-700 px-6 py-2.5 text-sm font-medium text-zinc-200 transition-colors hover:border-zinc-500"
          >
            Stop
          </button>
        ) : (
          <button
            type="submit"
            disabled={!input.trim()}
            className="min-h-[44px] shrink-0 rounded-full bg-zinc-100 px-6 py-2.5 text-sm font-medium text-black transition-colors hover:bg-zinc-200 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Ask
          </button>
        )}
      </form>
      {messages.length > 0 && !busy ? (
        <button
          type="button"
          onClick={() => setMessages([])}
          className="self-start text-xs text-zinc-500 transition-colors hover:text-zinc-300"
        >
          Clear conversation
        </button>
      ) : null}
    </div>
  );
}

function Answer({ message: m, seekTo }: { message: Message; seekTo: (s: number) => void }): JSX.Element {
  const byNumber = new Map(m.sources.map((s) => [s.n, s]));
  const cited = m.citations.map((n) => byNumber.get(n)).filter((s): s is AskSource => Boolean(s));

  return (
    <div className="flex flex-col gap-2 rounded-2xl rounded-bl-sm border border-white/5 bg-zinc-900/50 px-3 py-2.5">
      {m.answer ? (
        <p className="whitespace-pre-line text-sm leading-relaxed text-zinc-300">
          {splitCitations(m.answer).map((part, i) =>
            part.kind === "text" ? (
              <span key={i}>{part.text}</span>
            ) : (
              <span key={i}>
                {part.numbers.map((n) => {
                  const s = byNumber.get(n);
                  return s ? (
                    <button
                      key={n}
                      type="button"
                      onClick={() => seekTo(s.start)}
                      title={s.snippet}
                      className="mx-0.5 rounded bg-[#5e6ad2]/15 px-1 font-mono text-[11px] text-[#9ca3f5] transition-colors hover:bg-[#5e6ad2]/30"
                    >
                      {formatTimestamp(s.start)}
                    </button>
                  ) : null; // cites an excerpt that wasn't retrieved: dropped, as on the server
                })}
              </span>
            )
          )}
          {m.status === "streaming" ? (
            <span className="ml-0.5 inline-block h-3.5 w-1.5 translate-y-0.5 bg-[#5e6ad2] motion-safe:animate-pulse" />
          ) : null}
        </p>
      ) : m.status === "streaming" ? (
        <p className="text-sm text-zinc-500 motion-safe:animate-pulse">Finding the relevant parts of the lecture…</p>
      ) : null}

      {m.status === "error" ? <p className="text-sm text-[#e53e3e]">{m.error}</p> : null}
      {m.status === "stopped" ? <p className="text-xs text-zinc-500">Stopped.</p> : null}
      {m.status === "done" && m.grounded === false ? (
        <p className="text-xs text-zinc-500">This answer doesn&apos;t cite the lecture, so it may not be covered there.</p>
      ) : null}

      {m.status === "done" && cited.length > 0 ? (
        <details className="text-xs text-zinc-500">
          <summary className="cursor-pointer select-none hover:text-zinc-300">
            {cited.length} source{cited.length === 1 ? "" : "s"} from the lecture{m.cached ? " · instant (cached)" : ""}
          </summary>
          <ul className="mt-2 flex flex-col gap-2">
            {cited.map((s) => (
              <li key={s.n} className="flex gap-2">
                <button
                  type="button"
                  onClick={() => seekTo(s.start)}
                  className="shrink-0 font-mono text-zinc-400 underline-offset-2 hover:text-white hover:underline"
                >
                  {formatTimestamp(s.start)}–{formatTimestamp(s.end)}
                </button>
                <span className="text-zinc-500">{s.snippet}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}
