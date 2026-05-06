/**
 * Purpose: Small formatting helpers shared across the study UI.
 *
 * Data flow:
 * - Used by outline timestamps, flashcard citations, and search results to display MM:SS.
 */

export function formatTimestamp(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

