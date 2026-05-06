/**
 * Purpose: Shared frontend types for the LectureKit study session.
 *
 * Data flow:
 * - `/app` submits a YouTube URL to the backend `/process`.
 * - The backend returns transcript + content + indexing status.
 * - The client stores a normalized `LectureSession` in localStorage under `lecturekit_session`.
 * - `/study` reads from localStorage to render the dashboard (works after refresh).
 */

export interface OutlineItem {
  timestamp: number;
  title: string;
  description: string;
}

export interface Flashcard {
  question: string;
  answer: string;
  source_timestamp: number;
}

export interface LectureSession {
  video_id: string;
  youtube_url: string;
  chunk_count: number;
  outline: OutlineItem[];
  summary_90s: string;
  summary_5min: string;
  summary_full: string;
  flashcards: Flashcard[];
  indexed: boolean;
  processed_at: string;
}

