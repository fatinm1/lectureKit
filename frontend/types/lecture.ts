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

export interface FacultyIssue {
  description: string;
  timestamp: number;
  suggested_rewrite: string;
}

export interface FacultyCategory {
  score: number;
  summary: string;
  strengths: string[];
  issues: FacultyIssue[];
}

export interface PrioritizedFix {
  priority: number;
  category: string;
  title: string;
  description: string;
  timestamp: number;
  suggested_rewrite: string;
}

export interface FacultyReport {
  overall_score: number;
  top_priority_fix: {
    title: string;
    description: string;
    timestamp: number;
    suggested_rewrite: string;
  };
  pedagogical: FacultyCategory;
  accessibility: FacultyCategory;
  equity: FacultyCategory;
  clarity: FacultyCategory;
  prioritized_fixes: PrioritizedFix[];
}

export interface FacultySession {
  video_id: string;
  youtube_url: string;
  report: FacultyReport;
}

