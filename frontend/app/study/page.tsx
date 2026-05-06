/**
 * Study dashboard route (shell for Parts 3+).
 *
 * Purpose: Placeholder route matching the agreed folder layout; will host the three-column
 * Linear layout with outline, player, and tabbed summaries/flashcards/search.
 *
 * Agents: Will render outputs from Transcript, Content, and Search agents once APIs return data.
 */

import Link from "next/link";

export default function StudyPage() {
  return (
    <main className="min-h-screen bg-canvas text-ink flex flex-col items-center justify-center gap-lg px-md">
      <p className="text-secondary text-ink-muted text-center max-w-md">
        Study dashboard ships in a later part. Use the home page to verify API wiring for now.
      </p>
      <Link
        href="/"
        className="text-button text-primary transition-opacity duration-interaction ease-out hover:opacity-80 hover:text-primary-hover"
      >
        ← Back home
      </Link>
    </main>
  );
}
