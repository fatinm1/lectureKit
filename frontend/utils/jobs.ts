/**
 * Background-job client: `POST /jobs` + Server-Sent Events from `GET /jobs/{id}/events`.
 *
 * Data flow:
 * - createJob() enqueues work and returns a job_id right away (HTTP 202).
 * - subscribeToJob() opens an EventSource. The server replays every event from the start
 *   (Redis Stream), so a late subscriber, e.g. /study after a page navigation or refresh,
 *   still receives transcript_fetched, outline_ready, ... in order. If the connection drops,
 *   EventSource reconnects on its own and sends Last-Event-ID, so nothing is delivered twice.
 * - createJob() returns null when the backend has no Redis (503) or predates jobs (404/405);
 *   callers then fall back to the original synchronous endpoints.
 */

import type { CurriculumMap, FacultyReport, Flashcard, OutlineItem } from "../types/lecture";

export type JobMode = "student" | "faculty" | "provost";

export type StudentResult = {
  video_id: string;
  youtube_url: string;
  chunk_count: number;
  outline: OutlineItem[];
  summary_90s: string;
  summary_5min: string;
  summary_full: string;
  flashcards: Flashcard[];
  indexed: boolean;
};

export type FacultyResult = { video_id: string; youtube_url: string; report: FacultyReport };

export type ProvostResult = {
  lecture_count: number;
  failed_urls: Array<{ url: string; error: string }>;
  video_ids: string[];
  curriculum_map: CurriculumMap;
};

/** Every event carries `t`: seconds since the job was created (used for timing metrics). */
export type JobEventMap = {
  queued: { kind: JobMode };
  started: { mode: JobMode; total?: number };
  transcript_fetched: { video_id: string; youtube_url: string; chunk_count: number; duration_s?: number };
  chunks_indexed: { indexed: boolean };
  outline_ready: { outline: OutlineItem[] };
  summaries_ready: { summary_90s: string; summary_5min: string; summary_full: string };
  flashcards_ready: { flashcards: Flashcard[] };
  lecture_fetched: { index: number; total: number; video_id: string };
  lecture_failed: { index: number; total: number; url: string; error: string };
  analyzing: { lecture_count?: number };
  done: { result: StudentResult | FacultyResult | ProvostResult; timings: Record<string, number> };
  failed: { stage: string; status: number; message: string };
};

export type JobEventType = keyof JobEventMap;
export type JobEvent = { [K in JobEventType]: { type: K; data: JobEventMap[K] & { t: number } } }[JobEventType];

const EVENT_TYPES: JobEventType[] = [
  "queued",
  "started",
  "transcript_fetched",
  "chunks_indexed",
  "outline_ready",
  "summaries_ready",
  "flashcards_ready",
  "lecture_fetched",
  "lecture_failed",
  "analyzing",
  "done",
  "failed",
];

export function getApiBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_URL?.trim();
  return raw && raw.length > 0 ? raw.replace(/\/$/, "") : "http://localhost:8000";
}

export class JobRequestError extends Error {
  constructor(
    message: string,
    public status: number
  ) {
    super(message);
  }
}

export type CreateJobBody =
  | { mode: "student" | "faculty"; youtube_url: string }
  | { mode: "provost"; youtube_urls: string[]; learning_objectives: string };

/** Returns the job_id, or null if background jobs aren't available (caller should fall back). */
export async function createJob(body: CreateJobBody): Promise<string | null> {
  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    return null;
  }
  if (response.status === 503 || response.status === 404 || response.status === 405) {
    return null;
  }
  const payload = (await response.json().catch(() => null)) as { job_id?: string; detail?: unknown } | null;
  if (!response.ok || !payload?.job_id) {
    const detail = typeof payload?.detail === "string" ? payload.detail : `Error ${response.status}`;
    throw new JobRequestError(detail, response.status);
  }
  return payload.job_id;
}

export type JobSubscription = { close: () => void };

/**
 * Subscribe to a job's events. `onEvent` gets every event in order; the stream closes itself
 * after `done` or `failed`. `onConnectionError` fires if the stream can't be (re)established.
 */
export function subscribeToJob(
  jobId: string,
  onEvent: (event: JobEvent) => void,
  onConnectionError?: () => void
): JobSubscription {
  const source = new EventSource(`${getApiBaseUrl()}/jobs/${encodeURIComponent(jobId)}/events`);
  let closed = false;
  let failures = 0;

  const close = () => {
    closed = true;
    source.close();
  };

  for (const type of EVENT_TYPES) {
    source.addEventListener(type, (raw) => {
      failures = 0;
      let data: unknown = {};
      try {
        data = JSON.parse((raw as MessageEvent<string>).data);
      } catch {
        return;
      }
      onEvent({ type, data } as JobEvent);
      if (type === "done" || type === "failed") close();
    });
  }

  source.onerror = () => {
    if (closed) return;
    // EventSource retries automatically (with Last-Event-ID). Give up after a few failed
    // attempts, or immediately if the server refused the stream (e.g. job expired → 404).
    failures += 1;
    if (source.readyState === EventSource.CLOSED || failures >= 5) {
      close();
      onConnectionError?.();
    }
  };

  return { close };
}

/** GET /jobs/{id}: status + final result, for when SSE isn't usable. */
export async function fetchJob(
  jobId: string
): Promise<{ status: string; result: StudentResult | FacultyResult | ProvostResult | null } | null> {
  try {
    const r = await fetch(`${getApiBaseUrl()}/jobs/${encodeURIComponent(jobId)}`);
    if (!r.ok) return null;
    return (await r.json()) as { status: string; result: StudentResult | FacultyResult | ProvostResult | null };
  } catch {
    return null;
  }
}
