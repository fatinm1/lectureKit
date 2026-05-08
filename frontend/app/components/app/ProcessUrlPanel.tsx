/**
 * App workspace — YouTube URL capture wired to FastAPI `POST /process`.
 *
 * Purpose: Functional surface at `/app` (distinct from marketing `/`).
 * Data flow: Browser → `${NEXT_PUBLIC_API_URL}/process` → structured acknowledgement JSON (logged).
 */

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import type { FacultySession, LectureSession } from "../../../types/lecture";

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
  const [mode, setMode] = useState<"student" | "faculty">("student");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [uiMode, setUiMode] = useState<"form" | "loading">("form");
  const [activeStep, setActiveStep] = useState<1 | 2 | 3>(1);
  const [completedSteps, setCompletedSteps] = useState<Record<1 | 2 | 3, boolean>>({
    1: false,
    2: false,
    3: false,
  });
  const timersRef = useRef<number[]>([]);

  const router = useRouter();

  const steps = useMemo(() => {
    return mode === "faculty"
      ? ([
          { id: 1 as const, label: "Fetching transcript" },
          { id: 2 as const, label: "Analyzing lecture quality" },
          { id: 3 as const, label: "Generating audit report" },
        ] as const)
      : ([
          { id: 1 as const, label: "Fetching transcript" },
          { id: 2 as const, label: "Analyzing content" },
          { id: 3 as const, label: "Building study kit" },
        ] as const);
  }, [mode]);

  function clearTimers(): void {
    for (const t of timersRef.current) {
      window.clearTimeout(t);
    }
    timersRef.current = [];
  }

  useEffect(() => {
    return () => clearTimers();
  }, []);

  function startStepperTimers(): void {
    clearTimers();
    setActiveStep(1);
    setCompletedSteps({ 1: false, 2: false, 3: false });

    timersRef.current.push(
      window.setTimeout(() => {
        setCompletedSteps((prev) => ({ ...prev, 1: true }));
        setActiveStep(2);
      }, 8000)
    );

    timersRef.current.push(
      window.setTimeout(() => {
        setCompletedSteps((prev) => ({ ...prev, 2: true }));
        setActiveStep(3);
      }, 20000)
    );
  }

  function resetToForm(message?: string): void {
    clearTimers();
    setUiMode("form");
    setIsSubmitting(false);
    setActiveStep(1);
    setCompletedSteps({ 1: false, 2: false, 3: false });
    setStatusMessage(message ?? null);
  }

  function persistStudentSession(payload: unknown): void {
    if (!payload || typeof payload !== "object") {
      throw new Error("Unexpected response payload.");
    }

    const obj = payload as Record<string, unknown>;
    const session: LectureSession = {
      video_id: String(obj.video_id ?? ""),
      youtube_url: String(obj.youtube_url ?? url),
      chunk_count: Number(obj.chunk_count ?? 0),
      outline: (obj.outline as LectureSession["outline"]) ?? [],
      summary_90s: String(obj.summary_90s ?? ""),
      summary_5min: String(obj.summary_5min ?? ""),
      summary_full: String(obj.summary_full ?? ""),
      flashcards: (obj.flashcards as LectureSession["flashcards"]) ?? [],
      indexed: Boolean(obj.indexed),
      processed_at: new Date().toISOString(),
    };

    if (!session.video_id || !session.youtube_url) {
      throw new Error("Missing required fields in response.");
    }

    window.localStorage.setItem("lecturekit_session", JSON.stringify(session));
  }

  function persistFacultySession(payload: unknown): void {
    if (!payload || typeof payload !== "object") {
      throw new Error("Unexpected response payload.");
    }
    const obj = payload as Record<string, unknown>;
    const session: FacultySession = {
      video_id: String(obj.video_id ?? ""),
      youtube_url: String(obj.youtube_url ?? url),
      report: (obj.report as FacultySession["report"]) ?? ({} as FacultySession["report"]),
    };
    if (!session.video_id || !session.youtube_url || !session.report) {
      throw new Error("Missing required fields in response.");
    }
    window.localStorage.setItem("lecturekit_faculty_session", JSON.stringify(session));
  }

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
    setUiMode("loading");
    startStepperTimers();

    try {
      // Step: Provide a friendly client-side check so users get immediate feedback.
      try {
        // eslint-disable-next-line no-new
        new URL(url);
      } catch {
        resetToForm("Please paste a valid YouTube URL (e.g. https://www.youtube.com/watch?v=...).");
        return;
      }

      const endpoint = `${getApiBaseUrl()}${mode === "faculty" ? "/faculty" : "/process"}`;
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ youtube_url: url }),
      });

      const payload = await response.json().catch(() => null);

      console.log(`[LectureKit] POST ${mode === "faculty" ? "/faculty" : "/process"} response`, {
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

      setCompletedSteps({ 1: true, 2: true, 3: true });

      // Step: Store the full session, then navigate.
      if (mode === "faculty") {
        persistFacultySession(payload);
      } else {
        persistStudentSession(payload);
      }

      window.setTimeout(() => {
        router.push(mode === "faculty" ? "/report" : "/study");
      }, 500);
    } catch (error) {
      console.error("[LectureKit] Failed to reach backend", error);
      setStatusMessage("Network error — is the FastAPI server running?");
    } finally {
      setIsSubmitting(false);
    }
  }

  function StepIndicator(props: {
    label: string;
    state: "inactive" | "active" | "complete";
  }): JSX.Element {
    const { label, state } = props;

    const labelClass =
      state === "active" ? "text-ink" : state === "complete" ? "text-marketing-muted" : "text-marketing-muted";

    return (
      <div className="flex items-center gap-md py-md">
        <div className="flex h-5 w-5 items-center justify-center">
          {state === "active" ? (
            <span
              className="motion-safe:animate-pulse motion-reduce:animate-none"
              aria-hidden="true"
              style={{
                width: 8,
                height: 8,
                borderRadius: 9999,
                backgroundColor: "#5e6ad2",
              }}
            />
          ) : state === "complete" ? (
            <span className="text-primary" aria-hidden="true">
              ✓
            </span>
          ) : (
            <span
              aria-hidden="true"
              style={{
                width: 6,
                height: 6,
                borderRadius: 9999,
                backgroundColor: "#1a1a1a",
              }}
            />
          )}
        </div>
        <p className={`text-body transition-colors duration-interaction ease-out ${labelClass}`}>{label}</p>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#010102] px-6">
      <section aria-labelledby="app-workspace-title" className="mx-auto w-full max-w-2xl text-center">
        <div>
        <p className="text-caption font-medium uppercase tracking-[0.22em] text-marketing-muted">
          Workspace
        </p>
        <h1 id="app-workspace-title" className="mt-sm text-hero text-ink">
          {mode === "faculty" ? "Faculty Audit Report" : "Generate your study kit"}
        </h1>
        <p className="mt-md text-body text-marketing-muted">
          {mode === "faculty"
            ? "Paste a public YouTube lecture link. LectureKit will analyze your lecture across pedagogical quality, accessibility, equity, and clarity — and generate a private prioritized fix list with timestamped suggested rewrites."
            : "Paste a public YouTube lecture link. LectureKit will orchestrate transcript extraction, analysis, and search indexing — results surface here as soon as the pipeline ships."}
        </p>
      </div>

      {uiMode === "form" ? (
        <form
          onSubmit={handleSubmit}
          className="mx-auto mt-xl flex w-full flex-col gap-md transition-opacity duration-interaction ease-out"
        >
          <div className="mb-6 flex justify-center gap-2">
            <button
              type="button"
              onClick={() => setMode("student")}
              className={`rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 ${
                mode === "student"
                  ? "bg-[#5e6ad2] text-white"
                  : "border border-[#2a2a2a] text-[#a1a1aa] hover:border-[#5e6ad2] hover:text-white"
              }`}
            >
              Student
            </button>
            <button
              type="button"
              onClick={() => setMode("faculty")}
              className={`rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 ${
                mode === "faculty"
                  ? "bg-[#5e6ad2] text-white"
                  : "border border-[#2a2a2a] text-[#a1a1aa] hover:border-[#5e6ad2] hover:text-white"
              }`}
            >
              Faculty
            </button>
          </div>
          <div className="flex flex-col items-stretch gap-sm sm:flex-row sm:items-center sm:justify-center">
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
              className="min-h-[44px] w-full flex-1 rounded-linear border border-marketing-divider bg-surface-1 px-sm py-xs text-body text-ink outline-none transition duration-interaction ease-out placeholder:text-ink-tertiary focus:border-primary-focus focus:shadow-focus-glow sm:max-w-xl"
            />
            <button
              type="submit"
              disabled={isSubmitting}
              className="min-h-[44px] rounded-linear bg-primary px-[14px] py-[8px] text-button font-medium text-onprimary transition duration-interaction ease-out hover:bg-primary-hover active:bg-primary-focus disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSubmitting
                ? "Sending…"
                : mode === "faculty"
                  ? "Generate Audit Report"
                  : "Generate Study Kit"}
            </button>
          </div>

          <div className="flex flex-wrap justify-center gap-x-lg gap-y-xs text-secondary text-marketing-muted">
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
      ) : (
        <div className="mt-xl flex w-full flex-col items-center justify-center py-xxl">
          <div className="w-full">
            <div className="mx-auto w-full max-w-md">
              {steps.map((step) => {
                const state =
                  completedSteps[step.id] ? "complete" : activeStep === step.id ? "active" : "inactive";
                return <StepIndicator key={step.id} label={step.label} state={state} />;
              })}
            </div>

            {statusMessage ? (
              <div className="mt-lg text-center">
                <p className="text-secondary text-[#d16a6a]" role="status">
                  {statusMessage}
                </p>
                <button
                  type="button"
                  onClick={() => resetToForm()}
                  className="mt-md text-button font-medium text-marketing-muted transition duration-interaction ease-out hover:text-ink"
                >
                  Retry
                </button>
              </div>
            ) : null}
          </div>
        </div>
      )}
      </section>
    </div>
  );
}
