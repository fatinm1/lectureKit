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

export interface ObjectiveAnalysis {
  objective: string;
  coverage_status: "covered" | "partial" | "missing";
  coverage_score: number;
  evidence: string;
  lectures_covering: number[];
  gaps: string;
}

export interface CriticalGap {
  gap: string;
  impact: string;
  recommendation: string;
}

export interface ProvostRecommendation {
  priority: number;
  recommendation: string;
  rationale: string;
}

export interface CurriculumMap {
  overall_coverage_score: number;
  executive_summary: string;
  objectives_analysis: ObjectiveAnalysis[];
  curriculum_strengths: string[];
  critical_gaps: CriticalGap[];
  coverage_distribution: {
    fully_covered: number;
    partially_covered: number;
    not_covered: number;
  };
  recommendations: ProvostRecommendation[];
}

export interface ProvostFailedUrl {
  url: string;
  error: string;
}

export interface ProvostSession {
  lecture_count: number;
  video_ids: string[];
  curriculum_map: CurriculumMap;
  failed_urls?: ProvostFailedUrl[];
}

