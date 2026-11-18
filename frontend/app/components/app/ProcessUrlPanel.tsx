/**
 * App workspace — YouTube URL capture.
 *
 * Purpose: Functional surface at `/app` (distinct from landing `/`).
 * Data flow (background jobs, preferred):
 *   POST /jobs → job_id (instant) → EventSource on /jobs/{id}/events drives the real progress
 *   stepper. Student mode jumps to /study as soon as the transcript is ready; the study page
 *   keeps listening and fills in each section as it arrives. Faculty / Provost navigate on `done`.
 * Fallback (backend without Redis): the original blocking POST /process | /faculty | /provost.
 */

"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import type { FacultySession, LectureSession, ProvostSession } from "../../../types/lecture";
import { createJob, JobRequestError, subscribeToJob, type CreateJobBody, type JobSubscription } from "../../../utils/jobs";
import { track } from "../../../utils/analytics";

const FEATURES = ["Instant Summaries", "Smart Flashcards", "Semantic Search"] as const;

const BTN_PRIMARY =
  "rounded-full bg-zinc-100 px-6 py-2.5 text-sm font-medium text-black transition-colors hover:bg-zinc-200 disabled:cursor-not-allowed disabled:opacity-60";
const BTN_SECONDARY =
  "rounded-full border border-zinc-700 bg-transparent px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-white/5";
const MODE_ACTIVE = "rounded-full bg-zinc-100 px-4 py-2 text-sm font-medium text-black";
const MODE_INACTIVE =
  "rounded-full border border-zinc-800 px-4 py-2 text-sm font-medium text-zinc-400 transition-colors hover:border-zinc-600 hover:text-white";
const INPUT_BASE =
  "min-h-[44px] w-full rounded-lg border border-white/10 bg-zinc-900 px-3 py-2 text-sm text-white outline-none transition-colors placeholder:text-zinc-500 focus:border-[#5e6ad2]/60 focus:ring-1 focus:ring-[#5e6ad2]";

const ERROR_BANNER =
  "mx-auto w-full max-w-2xl rounded-xl border border-red-500/45 bg-red-950/50 px-5 py-4 text-left shadow-lg shadow-red-950/20";

function getApiBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_URL?.trim();
  return raw && raw.length > 0 ? raw.replace(/\/$/, "") : "http://localhost:8000";
}

/** Prefer FastAPI `detail` string; supports validation error arrays. */
function parseErrorDetailFromBody(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") return null;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) return detail.trim();
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0];
    if (first && typeof first === "object" && first !== null && "msg" in first) {
      const msg = (first as { msg?: unknown }).msg;
      if (typeof msg === "string" && msg.trim()) return msg.trim();
    }
  }
  return null;
}

export function ProcessUrlPanel(): JSX.Element {
  const searchParams = useSearchParams();
  const [url, setUrl] = useState("");
  const [mode, setMode] = useState<"student" | "faculty" | "provost">("student");
  const [provostUrls, setProvostUrls] = useState("");
  const [learningObjectives, setLearningObjectives] = useState("");
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
  const subscriptionRef = useRef<JobSubscription | null>(null);
  const [progressNote, setProgressNote] = useState<string | null>(null);

  const router = useRouter();

  const steps = useMemo(() => {
    return mode === "provost"
      ? ([
          { id: 1 as const, label: "Fetching transcripts" },
          { id: 2 as const, label: "Analyzing curriculum coverage" },
          { id: 3 as const, label: "Generating curriculum map" },
        ] as const)
      : mode === "faculty"
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
    return () => {
      clearTimers();
      subscriptionRef.current?.close();
    };
  }, []);

  useEffect(() => {
    const modeParam = searchParams.get("mode");
    if (modeParam === "faculty" || modeParam === "provost" || modeParam === "student") {
      setMode(modeParam as "student" | "faculty" | "provost");
    }
  }, [searchParams]);

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
    subscriptionRef.current?.close();
    subscriptionRef.current = null;
    setProgressNote(null);
    setUiMode("form");
    setIsSubmitting(false);
    setActiveStep(1);
    setCompletedSteps({ 1: false, 2: false, 3: false });
    setStatusMessage(message ?? null);
  }

  function switchWorkspaceMode(next: "student" | "faculty" | "provost"): void {
    setMode(next);
    setStatusMessage(null);
    setUrl("");
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

  function persistProvostSession(payload: unknown): void {
    if (!payload || typeof payload !== "object") {
      throw new Error("Unexpected response payload.");
    }
    const obj = payload as Record<string, unknown>;
    const rawFailed = obj.failed_urls;
    const failed_urls: ProvostSession["failed_urls"] = Array.isArray(rawFailed)
      ? rawFailed.map((item) => {
          const row = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
          return { url: String(row.url ?? ""), error: String(row.error ?? "") };
        })
      : [];

    const session: ProvostSession = {
      lecture_count: Number(obj.lecture_count ?? 0),
      video_ids: (obj.video_ids as string[]) ?? [],
      curriculum_map: (obj.curriculum_map as ProvostSession["curriculum_map"]) ?? ({} as ProvostSession["curriculum_map"]),
      failed_urls,
    };
    if (!session.lecture_count || !session.curriculum_map) {
      throw new Error("Missing required fields in response.");
    }
    window.localStorage.setItem("lecturekit_provost_session", JSON.stringify(session));
  }

  function markStep(done: Array<1 | 2 | 3>, active: 1 | 2 | 3): void {
    setCompletedSteps((prev) => {
      const next = { ...prev };
      for (const d of done) next[d] = true;
      return next;
    });
    setActiveStep(active);
  }

  /**
   * Drive the stepper from real backend events. Returns once the subscription is set up;
   * navigation / errors happen inside the event handler.
   */
  function followJob(jobId: string, jobMode: "student" | "faculty" | "provost"): void {
    clearTimers();
    setActiveStep(1);
    setCompletedSteps({ 1: false, 2: false, 3: false });

    // If nothing moves for a while the job is waiting for a free worker.
    timersRef.current.push(
      window.setTimeout(() => setProgressNote("Waiting for a free worker — other lectures are being processed."), 20000)
    );

    subscriptionRef.current = subscribeToJob(
      jobId,
      (event) => {
        if (event.type !== "queued") {
          clearTimers();
          setProgressNote(null);
        }
        switch (event.type) {
          case "transcript_fetched":
            if (jobMode === "student") {
              // First visible content is ready: open the study page now and let it stream the rest.
              markStep([1], 2);
              subscriptionRef.current?.close();
              router.push(`/study?job=${encodeURIComponent(jobId)}`);
              return;
            }
            markStep([1], 2);
            return;
          case "lecture_fetched":
          case "lecture_failed":
            setProgressNote(
              `${event.data.index + 1} of ${event.data.total} lecture transcripts checked` +
                (event.type === "lecture_failed" ? " (one could not be fetched)" : "")
            );
            return;
          case "mapping":
            setProgressNote(
              (event.data.lecture_index !== undefined ? `Lecture ${event.data.lecture_index + 1} is long: ` : "Long lecture: ") +
                `reading it in ${event.data.sections} sections first`
            );
            return;
          case "section_mapped":
            setProgressNote(
              (event.data.lecture_index !== undefined ? `Lecture ${event.data.lecture_index + 1}: ` : "") +
                `${event.data.done} of ${event.data.total} sections read`
            );
            return;
          case "analyzing":
            setProgressNote(null);
            markStep([1], 2);
            return;
          case "done": {
            setCompletedSteps({ 1: true, 2: true, 3: true });
            const result = event.data.result;
            if (jobMode === "faculty") persistFacultySession(result);
            else if (jobMode === "provost") persistProvostSession(result);
            else persistStudentSession(result);
            window.setTimeout(() => {
              router.push(jobMode === "faculty" ? "/report" : jobMode === "provost" ? "/curriculum" : "/study");
            }, 400);
            return;
          }
          case "failed":
            track("job_failed", { mode: jobMode, status: event.data.status, stage: event.data.stage });
            resetToForm(event.data.message || "Processing failed. Please try a different URL.");
            return;
          default:
            return;
        }
      },
      () => resetToForm("Lost connection to the server while processing. Please try again.")
    );
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatusMessage(null);
    setIsSubmitting(true);
    setUiMode("loading");
    startStepperTimers();

    try {
      try {
        if (mode === "provost") {
          const urls = provostUrls
            .split("\n")
            .map((u) => u.trim())
            .filter(Boolean);
          if (urls.length === 0) {
            resetToForm("Please paste at least one YouTube URL (one per line).");
            return;
          }
          if (urls.length > 10) {
            resetToForm("Maximum 10 URLs allowed.");
            return;
          }
          for (const u of urls) {
            // eslint-disable-next-line no-new
            new URL(u);
          }
          if (!learningObjectives.trim()) {
            resetToForm("Please paste your learning objectives.");
            return;
          }
        } else {
          // eslint-disable-next-line no-new
          new URL(url);
        }
      } catch {
        resetToForm("Please paste a valid YouTube URL (e.g. https://www.youtube.com/watch?v=...).");
        return;
      }

      const jobBody: CreateJobBody =
        mode === "provost"
          ? {
              mode: "provost",
              youtube_urls: provostUrls
                .split("\n")
                .map((u) => u.trim())
                .filter(Boolean),
              learning_objectives: learningObjectives.trim(),
            }
          : { mode, youtube_url: url };

      try {
        const jobId = await createJob(jobBody);
        if (jobId) {
          track("job_started", { mode });
          followJob(jobId, mode);
          return;
        }
      } catch (err) {
        if (err instanceof JobRequestError) {
          track(err.status === 429 || err.status === 503 ? "rate_limited" : "job_failed", {
            mode,
            status: err.status,
          });
          resetToForm(err.message);
          return;
        }
        throw err;
      }

      // Fallback: backend without background jobs → original blocking request with a timed stepper.
      const path = mode === "faculty" ? "/faculty" : mode === "provost" ? "/provost" : "/process";
      const endpoint = `${getApiBaseUrl()}${path}`;
      const body =
        mode === "provost"
          ? {
              youtube_urls: provostUrls
                .split("\n")
                .map((u) => u.trim())
                .filter(Boolean),
              learning_objectives: learningObjectives.trim(),
            }
          : { youtube_url: url };
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      const payload = await response.json().catch(() => null);

      console.log(`[LectureKit] POST ${path} response`, {
        ok: response.ok,
        status: response.status,
        body: payload,
      });

      if (!response.ok) {
        const errorData = payload && typeof payload === "object" ? payload : {};
        const detailMsg = parseErrorDetailFromBody(errorData);
        const fallbackStatus = `Error ${response.status} — please try a different URL`;
        const message =
          detailMsg ||
          (response.status === 422
            ? "Please paste a valid YouTube URL."
            : response.status === 404
              ? "Could not retrieve transcript for this video. Make sure the URL is public and has captions available."
              : response.status === 504
                ? "The transcript fetch timed out. Please try again."
                : fallbackStatus);
        resetToForm(message);
        return;
      }

      setCompletedSteps({ 1: true, 2: true, 3: true });

      if (mode === "faculty") {
        persistFacultySession(payload);
      } else if (mode === "provost") {
        persistProvostSession(payload);
      } else {
        persistStudentSession(payload);
      }

      window.setTimeout(() => {
        router.push(mode === "faculty" ? "/report" : mode === "provost" ? "/curriculum" : "/study");
      }, 500);
    } catch (error) {
      console.error("[LectureKit] Failed to reach backend", error);
      resetToForm("Network error — is the FastAPI server running?");
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
      state === "active" ? "text-white" : state === "complete" ? "text-zinc-500" : "text-zinc-500";

    return (
      <div className="flex items-center gap-4 py-4">
        <div className="flex h-5 w-5 shrink-0 items-center justify-center">
          {state === "active" ? (
            <span
              className="motion-safe:animate-pulse motion-reduce:animate-none"
              aria-hidden="true"
              style={{
                width: 8,
                height: 8,
                borderRadius: 9999,
                backgroundColor: "#f4f4f5",
              }}
            />
          ) : state === "complete" ? (
            <span className="text-[#1d9e75]" aria-hidden="true">
              ✓
            </span>
          ) : (
            <span
              aria-hidden="true"
              style={{
                width: 6,
                height: 6,
                borderRadius: 9999,
                backgroundColor: "#27272a",
              }}
            />
          )}
        </div>
        <p className={`text-sm transition-colors ${labelClass}`}>{label}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center px-6 pb-16 pt-10">
      <section aria-labelledby="app-workspace-title" className="mx-auto w-full max-w-2xl text-center">
        <p className="text-xs font-semibold uppercase tracking-widest text-zinc-500">Workspace</p>
        <h1 id="app-workspace-title" className="mt-3 font-lk-serif text-3xl text-white md:text-4xl">
          {mode === "provost"
            ? "Curriculum Coverage Map"
            : mode === "faculty"
              ? "Faculty Audit Report"
              : "Generate your study kit"}
        </h1>
        <p className="mt-4 text-sm leading-relaxed text-zinc-400">
          {mode === "provost"
            ? "Paste up to 10 YouTube lecture URLs from a single course and your learning objectives. LectureKit will map what was actually taught against what the course promises to deliver."
            : mode === "faculty"
              ? "Paste a public YouTube lecture link. LectureKit will analyze your lecture across pedagogical quality, accessibility, equity, and clarity — and generate a private prioritized fix list with timestamped suggested rewrites."
              : "Paste a public YouTube lecture link. LectureKit fetches the transcript, then opens your study kit right away and fills in the outline, summaries, flashcards and search as each one is ready."}
        </p>

        {statusMessage && uiMode === "form" ? (
          <div className={`${ERROR_BANNER} mt-8`} role="alert" aria-live="polite">
            <p className="text-xs font-semibold uppercase tracking-widest text-red-400/90">Could not complete request</p>
            <p className="mt-2 text-base font-medium leading-relaxed text-red-50">{statusMessage}</p>
          </div>
        ) : null}

        {uiMode === "form" ? (
          <form
            onSubmit={handleSubmit}
            className="mx-auto mt-10 flex w-full flex-col gap-6 transition-opacity duration-200"
          >
            <div className="flex flex-wrap justify-center gap-2">
              <button type="button" onClick={() => switchWorkspaceMode("student")} className={mode === "student" ? MODE_ACTIVE : MODE_INACTIVE}>
                Student
              </button>
              <button type="button" onClick={() => switchWorkspaceMode("faculty")} className={mode === "faculty" ? MODE_ACTIVE : MODE_INACTIVE}>
                Faculty
              </button>
              <button type="button" onClick={() => switchWorkspaceMode("provost")} className={mode === "provost" ? MODE_ACTIVE : MODE_INACTIVE}>
                Provost
              </button>
            </div>

            {mode === "provost" ? (
              <div className="flex w-full flex-col gap-4 text-left">
                <label htmlFor="provost-urls" className="text-xs font-semibold uppercase tracking-widest text-zinc-500">
                  Lecture URLs (up to 10, one per line)
                </label>
                <textarea
                  id="provost-urls"
                  value={provostUrls}
                  onChange={(e) => setProvostUrls(e.target.value)}
                  rows={6}
                  placeholder={"https://www.youtube.com/watch?v=...\nhttps://www.youtube.com/watch?v=..."}
                  className={`${INPUT_BASE} min-h-[140px] resize-y py-3`}
                />
                <label htmlFor="provost-objectives" className="text-xs font-semibold uppercase tracking-widest text-zinc-500">
                  Learning objectives
                </label>
                <textarea
                  id="provost-objectives"
                  value={learningObjectives}
                  onChange={(e) => setLearningObjectives(e.target.value)}
                  rows={5}
                  placeholder={"1) ...\n2) ...\n3) ..."}
                  className={`${INPUT_BASE} min-h-[120px] resize-y py-3`}
                />
                <div className="flex justify-center pt-2">
                  <button type="submit" disabled={isSubmitting} className={`${BTN_PRIMARY} min-h-[44px]`}>
                    {isSubmitting ? "Sending…" : "Generate Curriculum Map"}
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center sm:justify-center">
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
                  className={`${INPUT_BASE} sm:max-w-xl sm:flex-1`}
                />
                <button type="submit" disabled={isSubmitting} className={`${BTN_PRIMARY} min-h-[44px] shrink-0`}>
                  {isSubmitting
                    ? "Sending…"
                    : mode === "faculty"
                      ? "Generate Audit Report"
                      : "Generate Study Kit"}
                </button>
              </div>
            )}

            <div className="flex flex-wrap justify-center gap-x-6 gap-y-2 text-sm text-zinc-500">
              {FEATURES.map((label) => (
                <span key={label} className="transition-opacity hover:opacity-80">
                  {label}
                </span>
              ))}
            </div>

            <p className="text-xs text-zinc-500">
              Prefer the story?{" "}
              <Link
                href="/"
                className="text-zinc-400 underline-offset-2 transition-colors hover:text-white hover:underline"
              >
                Back to landing
              </Link>
            </p>
          </form>
        ) : (
          <div className="mt-10 flex w-full flex-col items-center justify-center py-8">
            <div className="w-full rounded-2xl border border-white/5 bg-zinc-900/50 p-6 transition-colors hover:border-white/10 sm:max-w-md">
              {steps.map((step) => {
                const state = completedSteps[step.id] ? "complete" : activeStep === step.id ? "active" : "inactive";
                return <StepIndicator key={step.id} label={step.label} state={state} />;
              })}
              {progressNote ? <p className="pt-2 text-left text-xs text-zinc-500">{progressNote}</p> : null}
            </div>

            {statusMessage ? (
              <div className="mt-8 w-full max-w-2xl">
                <div className={ERROR_BANNER} role="alert" aria-live="polite">
                  <p className="text-xs font-semibold uppercase tracking-widest text-red-400/90">Could not complete request</p>
                  <p className="mt-2 text-base font-medium leading-relaxed text-red-50">{statusMessage}</p>
                </div>
                <div className="mt-6 flex justify-center">
                  <button type="button" onClick={() => resetToForm()} className={BTN_SECONDARY}>
                    Retry
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        )}
      </section>
    </div>
  );
}
