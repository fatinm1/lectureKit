/**
 * App workspace — YouTube URL capture wired to FastAPI `POST /process`.
 *
 * Purpose: Functional surface at `/app` (distinct from marketing `/`).
 * Data flow: Browser → `${NEXT_PUBLIC_API_URL}/process` → structured acknowledgement JSON (logged).
 */

"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

const FEATURES = ["Instant Summaries", "Smart Flashcards", "Semantic Search"] as const;

function getApiBaseUrl(): string {
  /**
   * Resolve backend origin for client-side requests.
   *
   * Returns: Non-empty origin without trailing slash.
   *
   * Steps:
   * 1. Prefer `NEXT_PUBLIC_API_URL` when defined at build time.
   * 2. Fall back to local FastAPI default for development ergonomics.
   */
  const raw = process.env.NEXT_PUBLIC_API_URL?.trim();
  return raw && raw.length > 0 ? raw.replace(/\/$/, "") : "http://localhost:8000";
}

export function ProcessUrlPanel(): JSX.Element {
  const [url, setUrl] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    /**
     * Submit the lecture URL for orchestration (stub in Part 1).
     *
     * Steps:
     * 1. Prevent full-page reload on submit.
     * 2. Serialize `{ youtube_url }` per backend schema.
     * 3. Log responses for engineers/judges and mirror failures into `statusMessage`.
     */
    event.preventDefault();
    setStatusMessage(null);
    setIsSubmitting(true);

    try {
      // Step: Provide a friendly client-side check so users get immediate feedback.
      try {
        // eslint-disable-next-line no-new
        new URL(url);
      } catch {
        setStatusMessage("Please paste a valid YouTube URL (e.g. https://www.youtube.com/watch?v=...).");
        return;
      }

      const endpoint = `${getApiBaseUrl()}/process`;
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ youtube_url: url }),
      });

      const payload = await response.json().catch(() => null);

      console.log("[LectureKit] POST /process response", {
        ok: response.ok,
        status: response.status,
        body: payload,
      });

      if (!response.ok) {
        const detailValue =
          payload && typeof payload === "object" && "detail" in payload ? (payload as { detail: unknown }).detail : null;

        const friendly =
          response.status === 422
            ? "Please paste a valid YouTube URL."
            : response.status === 404
              ? "No transcript available for that video (private/unavailable/transcripts disabled)."
              : response.status === 504
                ? "The transcript fetch timed out. Please try again."
                : "Request failed. Please try again.";

        // Step: Keep a short technical tail for debugging without dumping raw JSON.
        const technicalTail =
          detailValue && typeof detailValue === "string" ? ` (${detailValue})` : "";

        setStatusMessage(`${friendly}${technicalTail}`);
        return;
      }

      setStatusMessage("Submitted — check the console for the full JSON response.");
    } catch (error) {
      console.error("[LectureKit] Failed to reach backend", error);
      setStatusMessage("Network error — is the FastAPI server running?");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section
      aria-labelledby="app-workspace-title"
      className="mx-auto flex w-full max-w-content flex-col gap-xl px-md py-section-xl"
    >
      <div className="max-w-3xl">
        <p className="text-caption font-medium uppercase tracking-[0.22em] text-marketing-muted">
          Workspace
        </p>
        <h1 id="app-workspace-title" className="mt-sm text-hero text-ink">
          Generate your study kit
        </h1>
        <p className="mt-md text-body text-marketing-muted">
          Paste a public YouTube lecture link. LectureKit will orchestrate transcript extraction, analysis,
          and search indexing — results surface here as soon as the pipeline ships.
        </p>
      </div>

      <form
        onSubmit={handleSubmit}
        className="flex w-full max-w-xl flex-col gap-md transition-opacity duration-interaction ease-out"
      >
        <div className="flex flex-col items-stretch gap-sm sm:flex-row sm:items-center">
          <label htmlFor="youtube-url-app" className="sr-only">
            YouTube lecture URL
          </label>
          <input
            id="youtube-url-app"
            name="youtube-url-app"
            type="text"
            required
            placeholder="https://www.youtube.com/watch?v=..."
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            inputMode="url"
            autoComplete="off"
            className="min-h-[44px] flex-1 rounded-linear border border-marketing-divider bg-surface-1 px-sm py-xs text-body text-ink outline-none transition duration-interaction ease-out placeholder:text-ink-tertiary focus:border-primary-focus focus:shadow-focus-glow"
          />
          <button
            type="submit"
            disabled={isSubmitting}
            className="min-h-[44px] rounded-linear bg-primary px-[14px] py-[8px] text-button font-medium text-onprimary transition duration-interaction ease-out hover:bg-primary-hover active:bg-primary-focus disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSubmitting ? "Sending…" : "Generate study kit"}
          </button>
        </div>

        <div className="flex flex-wrap gap-x-lg gap-y-xs text-secondary text-marketing-muted">
          {FEATURES.map((label) => (
            <span key={label} className="transition-opacity duration-interaction ease-out hover:opacity-80">
              {label}
            </span>
          ))}
        </div>

        {statusMessage ? (
          <p className="text-secondary text-ink-muted" role="status">
            {statusMessage}
          </p>
        ) : null}

        <p className="text-caption text-marketing-muted">
          Prefer the story?{" "}
          <Link href="/" className="text-primary transition-colors duration-interaction ease-out hover:text-primary-hover">
            Back to marketing
          </Link>
          {" · "}
          <Link href="/study" className="text-primary transition-colors duration-interaction ease-out hover:text-primary-hover">
            Study shell preview
          </Link>
        </p>
      </form>
    </section>
  );
}
